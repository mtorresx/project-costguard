"""Consulta do custo mensal não alocado da assinatura Azure."""

import asyncio
import math
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import reflex as rx

from ..components.mensagens import sucesso

from .. import api
from ..formatadores import formatar_valor
from ..state import AuthState

ROTA_CONEXAO = "/azure/conexao"
ROTA_CUSTO = "/azure/custo"
ROTA_SINCRONIZAR = "/azure/custo/sincronizar"
INDISPONIVEL = "Recurso indisponível no servidor agora."
ERRO_LEITURA = "Não foi possível carregar o custo do Azure agora."
ESTADOS = {
    "nao_configurado": "Azure não configurado.",
    "configuracao_invalida": "A configuração do Azure no servidor está inválida.",
    "sem_leitura": "Ainda não há leitura de custo.",
    "ok": "Conectado ao Azure",
    "sem_dados": "Conectado ao Azure",
    "sem_permissao": "Sem permissão no Azure. Verifique o acesso do aplicativo à assinatura.",
    "indisponivel": "Azure indisponível agora.",
    "resposta_incompleta": "O Azure devolveu uma resposta inesperada; o valor não foi guardado.",
}


def _data_local(ms, fuso: str) -> str:
    if type(ms) is not int:
        return ""
    try:
        return datetime.fromtimestamp(ms / 1000, ZoneInfo(fuso)).strftime("%d/%m/%Y às %H:%M")
    except (OverflowError, OSError, ValueError, ZoneInfoNotFoundError):
        return ""


def _valor(corpo: dict) -> str:
    custo, moeda = corpo.get("custo_mes_total"), corpo.get("moeda")
    if type(custo) not in (int, float) or not math.isfinite(custo) or not isinstance(moeda, str) or not re.fullmatch(r"[A-Z]{3}", moeda):
        return ""
    return formatar_valor(custo, moeda)


def _cooldown(corpo: object, agora_ms: int) -> int:
    if not isinstance(corpo, dict):
        return 0
    segundos = corpo.get("segundos_restantes")
    if type(segundos) is int:
        return min(60, max(0, segundos))
    prazo = corpo.get("proxima_leitura_em")
    if type(prazo) is int and 0 < prazo - agora_ms <= 60_000:
        return math.ceil((prazo - agora_ms) / 1000)
    # Um prazo de horas pertence ao contrato anterior. Só a espera curta bloqueia a leitura.
    return min(60, api.segundos_restantes(corpo) or 0)


class AzureState(rx.State):
    carregando: bool = True
    sincronizando: bool = False
    titulo: str = ""
    detalhe: str = ""
    ultima_leitura: str = ""
    apelido: str = "Azure"
    conta_mascarada: str = "•••• ••••"
    erro_leitura: str = ""
    origem: str = ""
    conectado: bool = False
    segundos: int = 0
    desconectando: bool = False
    aviso: str = ""
    _liberar_em: float = 0.0
    _versao_conexao: int = 0
    _fuso: str = ""

    def _aplicar(self, status: int, corpo, *, leitura: bool = True):
        self.titulo = INDISPONIVEL if status in (200, 404) else ERRO_LEITURA
        self.detalhe = self.ultima_leitura = ""
        if leitura:
            self.erro_leitura = self.titulo
            self.apelido = "Azure"
            self.conta_mascarada = "•••• ••••"
            self.origem = ""
            self.conectado = False
        if status != 200 or not isinstance(corpo, dict):
            return
        estado = corpo.get("status")
        if not isinstance(estado, str) or corpo.get("provedor") != "azure" or corpo.get("nao_alocado") is not True:
            return
        if estado == "desatualizado" and re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", str(corpo.get("mes_referencia"))):
            self.titulo = f"O último valor é de {corpo['mes_referencia']}. Sincronize para ler o mês atual."
        elif estado in ESTADOS:
            self.titulo = ESTADOS[estado]
        else:
            return
        if leitura:
            self.erro_leitura = ""
            apelido = corpo.get("apelido")
            self.apelido = apelido.strip() if isinstance(apelido, str) and apelido.strip() else "Azure"
            final = corpo.get("tenant_final")
            if isinstance(final, str) and len(final.strip()) == 4:
                self.conta_mascarada += " " + final.strip()
            origem = corpo.get("origem")
            self.origem = origem if origem in ("tela", "servidor") else ""
        self.conectado = estado in ("ok", "sem_dados") or (
            estado not in ("nao_configurado", "configuracao_invalida")
            and (self.origem == "tela" or corpo.get("configurado") is True)
        )
        valor = _valor(corpo)
        data = _data_local(corpo.get("atualizado_em"), self._fuso)
        if estado == "ok":
            if not valor:
                self.titulo = ESTADOS["resposta_incompleta"]
            else:
                self.detalhe = f"Não alocado: {valor}"
                self.ultima_leitura = data
        elif estado == "sem_dados":
            self.detalhe = "Sem consumo registrado neste mês."
            self.ultima_leitura = data
        elif estado == "indisponivel":
            if valor:
                self.detalhe = f"Último valor conhecido: {valor}" + (f" (lido em {data})" if data else "")
            else:
                self.ultima_leitura = data

    def _iniciar_espera(self, corpo) -> bool:
        segundos = _cooldown(corpo, int(time.time() * 1000))
        if not segundos:
            if isinstance(corpo, dict) and ("segundos_restantes" in corpo or "proxima_leitura_em" in corpo):
                self.segundos = 0
                self._liberar_em = 0
            return False
        self.segundos = segundos
        self._liberar_em = time.monotonic() + segundos
        return True

    def _conexao_alterada(self):
        self._versao_conexao += 1
        self.segundos = 0
        self._liberar_em = 0
        self.origem = ""
        self.aviso = ""

    @rx.event(background=True)
    async def contar_segundos(self, prazo: float):
        while True:
            async with self:
                if self._liberar_em != prazo:
                    return
                self.segundos = max(0, math.ceil(prazo - time.monotonic()))
                if not self.segundos:
                    self._liberar_em = 0
                    return
            await asyncio.sleep(1)

    @rx.event
    async def carregar(self, fuso: str = ""):
        auth = await self.get_state(AuthState)
        if not auth.token:
            yield AuthState.handle_unauthenticated
            return
        if fuso:
            self._fuso = fuso
        self.carregando = True
        self.origem = ""
        self.aviso = ""
        yield
        status, corpo = await api.requisitar("GET", ROTA_CUSTO, auth.token, forcar=True)
        self._aplicar(status, corpo)
        self.carregando = False
        if status == 401:
            yield AuthState.handle_unauthenticated
        elif self._iniciar_espera(corpo):
            yield AzureState.contar_segundos(self._liberar_em)

    @rx.event
    async def desconectar(self):
        auth = await self.get_state(AuthState)
        if not auth.token:
            yield AuthState.handle_unauthenticated
            return
        if not auth.is_admin or self.origem != "tela" or self.desconectando or self.sincronizando:
            return
        self.desconectando = True
        self.aviso = ""
        yield
        status, corpo = await api.requisitar("DELETE", ROTA_CONEXAO, auth.token)
        self.desconectando = False
        if status == 401:
            yield AuthState.handle_unauthenticated
        elif 200 <= status < 300:
            self._conexao_alterada()
            self.conectado = False
            self.carregando = True
            yield sucesso("Conexão do Azure removida.")
            yield AzureState.carregar
        else:
            self.aviso = api.mensagem_erro(corpo, "Não foi possível desconectar o Azure.")

    @rx.event(background=True)
    async def sincronizar(self):
        async with self:
            auth = await self.get_state(AuthState)
            token = auth.token
            if token and (not auth.is_admin or self.sincronizando or self.carregando
                          or self.desconectando or self.segundos):
                return
            self.sincronizando = bool(token)
            self.aviso = ""
            versao = self._versao_conexao
        if not token:
            yield AuthState.handle_unauthenticated
            return
        status, corpo = await api.requisitar("POST", ROTA_SINCRONIZAR, token, timeout=60)
        async with self:
            self.sincronizando = False
            auth = await self.get_state(AuthState)
            if auth.token != token or versao != self._versao_conexao:
                return
            esperar = self._iniciar_espera(corpo)
            prazo = self._liberar_em
            if status == 200:
                self._aplicar(status, corpo, leitura=False)
            elif status == 429:
                self.aviso = "O limite de consultas foi atingido. Tente novamente após a espera."
            elif status != 401:
                self.aviso = "Acesso negado" if status == 403 else "Não foi possível sincronizar o custo do Azure agora."
            confirmar = status == 200 and self.titulo == ESTADOS["ok"]
        if status == 401:
            yield AuthState.handle_unauthenticated
        if confirmar:
            yield sucesso("Leitura do Azure concluída.")
        if esperar:
            yield AzureState.contar_segundos(prazo)

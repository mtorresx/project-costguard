"""Estado da página de Alertas — alertas e recursos não classificados (Xano).

Leitura para qualquer usuário autenticado; "Resolver" e "Avaliar alertas agora"
só aparecem para admin (a autorização real é do backend). Cada bloco tem seu
próprio estado de erro, para que a falha de um não esconda o outro.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Optional, TypedDict

import reflex as rx

from ..components.mensagens import sucesso

from ..api import mensagem_erro, requisitar
from ..components.contador_state import ContadorAlertasState
from ..components.periodo_state import PeriodoState, parametro_mes
from ..sincronizacao_auto import recurso_novo
from ..state import AuthState

ERRO_ALERTAS = "Não foi possível carregar os alertas."
ERRO_RECURSOS = "Não foi possível carregar os recursos não classificados."

TIPOS = {
    "orcamento": "Orçamento",
    "nao_classificado": "Recurso não classificado",
    "importacao": "Falha de importação",
}
NIVEIS = {
    "atencao": "Atenção",
    "critico": "Aviso",
    "estourado": "Orçamento excedido",
    "erro": "Erro",
}
NIVEIS_CRITICOS = ("critico", "estourado", "erro")


class Alerta(TypedDict):
    id: int
    tipo: str
    tipo_rotulo: str
    nivel: str
    nivel_rotulo: str
    mensagem: str
    detalhe: str
    projeto_id: int
    provedor_nome: str
    resolvido: bool
    resolucao_texto: str
    criado_ms: int
    quando: str


class RecursoNaoClassificado(TypedDict):
    id: int
    provedor_nome: str
    arn: str
    nome: str
    servico: str
    regiao: str
    tag: str
    novo: bool


def _ms(valor: Any) -> Optional[int]:
    """Timestamp do Xano (ms desde a época) ou texto ISO -> ms; inválido -> None."""
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return int(valor)
    if isinstance(valor, str) and valor:
        try:
            dt = datetime.fromisoformat(valor.replace("Z", "+00:00"))
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    return None


def tempo_relativo(ms: Optional[int], agora_ms: int) -> str:
    if ms is None:
        return "—"
    segundos = max(0, (agora_ms - ms) // 1000)
    if segundos < 60:
        return "agora"
    minutos = segundos // 60
    if minutos < 60:
        return f"há {minutos} min"
    horas = minutos // 60
    if horas < 24:
        return f"há {horas} h"
    dias = horas // 24
    return "há 1 dia" if dias == 1 else f"há {dias} dias"


def normalizar_alerta(bruto: Any, agora_ms: int) -> Optional[Alerta]:
    if not isinstance(bruto, dict) or not isinstance(bruto.get("id"), int):
        return None
    tipo = bruto.get("tipo") if bruto.get("tipo") in TIPOS else ""
    nivel = bruto.get("nivel") if bruto.get("nivel") in NIVEIS else ""
    if not tipo or not nivel:
        return None
    criado = _ms(bruto.get("criado_em"))
    resolvido = bruto.get("resolvido") is True
    resolucao = ""
    if resolvido:
        quando_res = tempo_relativo(_ms(bruto.get("resolvido_em")), agora_ms)
        modo = "automaticamente" if bruto.get("resolucao") == "automatica" else "manualmente"
        resolucao = f"Resolvido {modo} ({quando_res})"
    return {
        "id": bruto["id"],
        "tipo": tipo,
        "tipo_rotulo": TIPOS[tipo],
        "nivel": nivel,
        "nivel_rotulo": NIVEIS[nivel],
        "mensagem": str(bruto.get("mensagem") or ""),
        "detalhe": str(bruto.get("detalhe") or ""),
        "projeto_id": bruto.get("projeto_id") if isinstance(bruto.get("projeto_id"), int) else 0,
        "provedor_nome": str(bruto.get("provedor_nome") or ""),
        "resolvido": resolvido,
        "resolucao_texto": resolucao,
        "criado_ms": criado or 0,
        "quando": tempo_relativo(criado, agora_ms),
    }


def nome_recurso(arn: str) -> str:
    """Parte final legível do ARN (ex.: ...:instance/i-123 -> i-123)."""
    if not arn:
        return ""
    ultimo = arn.split(":")[-1]
    return ultimo.split("/")[-1] or arn


def normalizar_recurso(bruto: Any, agora_ms: int = 0) -> Optional[RecursoNaoClassificado]:
    if not isinstance(bruto, dict) or not isinstance(bruto.get("id"), int):
        return None
    arn = str(bruto.get("arn") or "")
    return {
        "id": bruto["id"],
        "provedor_nome": str(bruto.get("provedor_nome") or "—"),
        "arn": arn,
        "nome": nome_recurso(arn),
        "servico": str(bruto.get("servico") or "—"),
        "regiao": str(bruto.get("regiao") or "—"),
        "tag": str(bruto.get("codigo_projeto_tag") or ""),
        "novo": recurso_novo(bruto.get("descoberto_em"), agora_ms),
    }


def filtrar(alertas: list[Alerta], filtro: str, busca: str) -> list[Alerta]:
    if filtro == "abertos":
        alertas = [a for a in alertas if not a["resolvido"]]
    elif filtro == "resolvidos":
        alertas = [a for a in alertas if a["resolvido"]]
    termo = (busca or "").strip().lower()
    if termo:
        alertas = [
            a for a in alertas
            if termo in a["mensagem"].lower() or termo in a["detalhe"].lower() or termo in a["tipo_rotulo"].lower()
        ]
    return alertas


class AlertasState(rx.State):
    alertas: list[Alerta] = []
    recursos: list[RecursoNaoClassificado] = []
    loading: bool = False
    erro_alertas: str = ""
    erro_recursos: str = ""
    erro_acao: str = ""
    filtro: str = "abertos"
    busca: str = ""
    resolvendo_id: int = 0
    avaliando: bool = False
    agora_ms: int = 0

    @rx.var
    def alertas_filtrados(self) -> list[Alerta]:
        return filtrar(self.alertas, self.filtro, self.busca)

    @rx.var
    def total_abertos(self) -> int:
        return len([a for a in self.alertas if not a["resolvido"]])

    @rx.var
    def total_criticos(self) -> int:
        return len([a for a in self.alertas if not a["resolvido"] and a["nivel"] in NIVEIS_CRITICOS])

    @rx.var
    def total_24h(self) -> int:
        limite = self.agora_ms - 24 * 3600 * 1000
        return len([a for a in self.alertas if a["criado_ms"] >= limite])

    @rx.var
    def total_recursos(self) -> int:
        return len(self.recursos)

    async def _token(self) -> str:
        return (await self.get_state(AuthState)).token

    @rx.event
    def set_filtro(self, valor: str | list[str]):
        self.filtro = valor if isinstance(valor, str) else (valor[0] if valor else "abertos")

    @rx.event
    def set_busca(self, valor: str):
        self.busca = valor

    @rx.event
    async def carregar(self):
        token = await self._token()
        if not token:
            yield AuthState.handle_unauthenticated
            return
        self.loading = True
        self.erro_alertas = ""
        self.erro_recursos = ""
        yield
        self.agora_ms = int(time.time() * 1000)

        mes = (await self.get_state(PeriodoState)).preparar()
        status_p, painel = await requisitar("GET", "/painel", token, params=parametro_mes(mes))
        if status_p == 401:
            self.loading = False
            yield AuthState.handle_unauthenticated
            return
        if status_p == 200 and isinstance(painel, dict):
            res_alertas = (200, painel.get("alertas"))
            res_recursos = (200, painel.get("recursos_nao_classificados"))
        else:
            res_alertas, res_recursos = await asyncio.gather(
                requisitar("GET", "/alertas", token),
                requisitar("GET", "/recursos-nao-classificados", token),
            )

        status, corpo = res_alertas
        if status == 401:
            self.loading = False
            yield AuthState.handle_unauthenticated
            return
        if status == 200 and isinstance(corpo, list):
            self.alertas = [a for a in (normalizar_alerta(b, self.agora_ms) for b in corpo) if a is not None]
            contador = await self.get_state(ContadorAlertasState)
            abertos = [a for a in self.alertas if not a["resolvido"]]
            contador.atualizar(len(abertos), len([a for a in abertos if a["nivel"] in NIVEIS_CRITICOS]))
        else:
            self.alertas = []
            self.erro_alertas = mensagem_erro(corpo, ERRO_ALERTAS) if status else ERRO_ALERTAS

        status, corpo = res_recursos
        if status == 401:
            self.loading = False
            yield AuthState.handle_unauthenticated
            return
        if status == 200 and isinstance(corpo, list):
            self.recursos = [r for r in (normalizar_recurso(b, self.agora_ms) for b in corpo) if r is not None]
        else:
            self.recursos = []
            self.erro_recursos = mensagem_erro(corpo, ERRO_RECURSOS) if status else ERRO_RECURSOS
        self.loading = False

    @rx.event
    async def resolver(self, alerta_id: int):
        token = await self._token()
        self.resolvendo_id = alerta_id
        self.erro_acao = ""
        yield
        status, corpo = await requisitar("POST", f"/alertas/{alerta_id}/resolver", token, {})
        self.resolvendo_id = 0
        if status == 401:
            yield AuthState.handle_unauthenticated
            return
        if status != 200:
            self.erro_acao = mensagem_erro(corpo, "Não foi possível resolver o alerta.")
            return
        yield sucesso("Alerta resolvido.")
        yield AlertasState.carregar

    @rx.event(background=True)
    async def avaliar(self):
        """Em segundo plano (P2-3): a avaliação pode levar até 120 s sem segurar a aba."""
        async with self:
            if self.avaliando:
                return
            token = await self._token()
            self.avaliando = True
            self.erro_acao = ""
        status, corpo = await requisitar("POST", "/alertas/avaliar", token, {"simular": False}, timeout=120)
        falhou = status != 200 or not isinstance(corpo, dict)
        async with self:
            self.avaliando = False
            if falhou and status != 401:
                self.erro_acao = mensagem_erro(corpo, "Não foi possível avaliar os alertas.")
        if status == 401:
            yield AuthState.handle_unauthenticated
            return
        if falhou:
            return
        criados = len(corpo.get("criar") or [])
        resolvidos = len(corpo.get("resolver") or [])
        yield sucesso(f"Avaliação concluída: {criados} alertas novos, {resolvidos} encerrados automaticamente.")
        yield AlertasState.carregar

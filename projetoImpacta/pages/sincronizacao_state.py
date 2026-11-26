"""Sincronização manual de um provedor ("Sincronizar agora", admin).

Sequência:
1. POST /provedores/{id}/sincronizar-recursos  — inventário;
2. POST /provedores/{id}/classificar-custos-equipe — custos por equipe
   (executada mesmo se a etapa 1 falhar: as fontes são independentes);
3. POST /alertas/avaliar — avaliação de alertas.

Cada etapa mostra sucesso, aviso ou erro sanitizado; nenhuma falha é omitida.
A autorização real é do backend. Há uma pausa curta entre chamadas por causa do
limite de requisições do plano Xano.

O evento roda em segundo plano (P2-3): as etapas podem levar minutos e não
seguram a fila de eventos da aba (navegar e os outros botões seguem respondendo).
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime
from typing import Any, TypedDict

import reflex as rx

from ..api import mensagem_erro, requisitar
from ..components.periodo_state import FUSO
from ..state import AuthState

PAUSA_ENTRE_ETAPAS = 2.0
# Precondition de `sincronizar-recursos` quando a trava do provedor está tomada.
PREFIXO_OCUPADO = "Já existe uma sincronização de recursos em andamento"
AVISO_OCUPADO = "Sincronização já em andamento; o ciclo automático está atualizando este provedor."
# Precondition de `classificar-custos-equipe` quando outra classificação segura a trava (P2-9).
PREFIXO_OCUPADO_CUSTOS = "Já existe uma classificação de custos em andamento"
AVISO_OCUPADO_CUSTOS = "Classificação de custos já em andamento para este provedor; os valores serão atualizados por ela."


class Etapa(TypedDict):
    nome: str
    estado: str  # "pendente" | "executando" | "sucesso" | "aviso" | "ocupado" | "erro"
    mensagem: str


def inicio_janela_custos(hoje: date) -> str:
    """Primeiro dia do mês anterior (`YYYY-MM-DD`).

    Sem isso o backend usa "últimos 30 dias", o que deixa o mês anterior pela
    metade e, no início do mês, quase nada do mês corrente. O fim fica a cargo
    do backend (até ontem, UTC).
    """
    ano, mes = (hoje.year - 1, 12) if hoje.month == 1 else (hoje.year, hoje.month - 1)
    return date(ano, mes, 1).isoformat()


def _etapas_iniciais() -> list[Etapa]:
    return [
        {"nome": "Inventário de recursos", "estado": "pendente", "mensagem": ""},
        {"nome": "Custos por equipe", "estado": "pendente", "mensagem": ""},
        {"nome": "Avaliação de alertas", "estado": "pendente", "mensagem": ""},
    ]


def _mensagem_execucao(corpo: dict, padrao: str) -> str:
    """Mensagem sanitizada de uma execução com status "erro" (campo `mensagem`)."""
    texto = corpo.get("mensagem")
    return texto.strip() if isinstance(texto, str) and texto.strip() else padrao


def sincronizacao_em_andamento(status: int, corpo: Any) -> bool:
    """O backend recusou porque outra sincronização (ex.: o ciclo automático) segura a trava."""
    return status == 400 and mensagem_erro(corpo, "").startswith(PREFIXO_OCUPADO)


def resultado_inventario(status: int, corpo: Any) -> tuple[str, str]:
    """(estado, mensagem) da etapa de inventário a partir da resposta HTTP."""
    if sincronizacao_em_andamento(status, corpo):
        return "ocupado", AVISO_OCUPADO
    if status != 200 or not isinstance(corpo, dict):
        return "erro", mensagem_erro(corpo, "Não foi possível sincronizar o inventário.")
    if corpo.get("status") != "sucesso":
        return "erro", _mensagem_execucao(corpo, "Falha na sincronização de recursos.")
    partes = [
        f"{corpo.get('recursos_ativos', 0)} recursos ativos",
        f"{corpo.get('recursos_desativados', 0)} desativados",
        f"{corpo.get('sem_responsavel', 0)} sem responsável",
        f"{corpo.get('projetos_desconhecidos', 0)} com projeto desconhecido",
    ]
    if corpo.get("equipes_criadas"):
        partes.append(f"{corpo['equipes_criadas']} equipes criadas")
    return "sucesso", ", ".join(partes) + "."


def resultado_custos(status: int, corpo: Any) -> tuple[str, str]:
    """(estado, mensagem) da etapa de custos por equipe."""
    if status == 400 and mensagem_erro(corpo, "").startswith(PREFIXO_OCUPADO_CUSTOS):
        return "ocupado", AVISO_OCUPADO_CUSTOS
    if status != 200 or not isinstance(corpo, dict):
        return "erro", mensagem_erro(corpo, "Não foi possível classificar os custos por equipe.")
    if corpo.get("status") != "sucesso":
        return "erro", _mensagem_execucao(corpo, "Falha na classificação de custos por equipe.")
    texto = (
        f"{corpo.get('registros_gravados', 0)} registros gravados, "
        f"{corpo.get('nao_alocados', 0)} sem projeto, "
        f"{corpo.get('tags_sem_projeto', 0)} com projeto desconhecido."
    )
    aviso = corpo.get("aviso")
    if isinstance(aviso, str) and aviso.strip():
        return "aviso", f"{texto} Aviso: {aviso.strip()}"
    return "sucesso", texto


def resultado_alertas(status: int, corpo: Any) -> tuple[str, str]:
    """(estado, mensagem) da etapa de avaliação de alertas."""
    if status != 200 or not isinstance(corpo, dict):
        return "erro", mensagem_erro(corpo, "Não foi possível avaliar os alertas.")
    criados = len(corpo.get("criar") or [])
    resolvidos = len(corpo.get("resolver") or [])
    return "sucesso", f"{criados} alertas novos, {resolvidos} encerrados automaticamente."


class SincronizacaoState(rx.State):
    aberto: bool = False
    executando: bool = False
    provedor_id: int = 0
    provedor_nome: str = ""
    etapas: list[Etapa] = _etapas_iniciais()

    @rx.var
    def concluida_com_falha(self) -> bool:
        return any(e["estado"] == "erro" for e in self.etapas)

    @rx.event
    def fechar(self):
        if not self.executando:
            self.aberto = False

    def _marcar(self, indice: int, estado: str, mensagem: str = "") -> None:
        etapas = list(self.etapas)
        etapas[indice] = {**etapas[indice], "estado": estado, "mensagem": mensagem}
        self.etapas = etapas

    @rx.event(background=True)
    async def sincronizar(self, provedor_id: int, provedor_nome: str):
        async with self:
            if self.executando:
                return
            token = (await self.get_state(AuthState)).token
            if token:
                self.provedor_id = provedor_id
                self.provedor_nome = provedor_nome
                self.etapas = _etapas_iniciais()
                self.aberto = True
                self.executando = True
        if not token:
            yield AuthState.handle_unauthenticated
            return

        chamadas = [
            (f"/provedores/{provedor_id}/sincronizar-recursos", None, resultado_inventario, 300),
            (
                f"/provedores/{provedor_id}/classificar-custos-equipe",
                {"data_inicio": inicio_janela_custos(datetime.now(FUSO).date())},
                resultado_custos,
                300,
            ),
            ("/alertas/avaliar", {"simular": False}, resultado_alertas, 120),
        ]
        for indice, (caminho, corpo, interpretar, timeout) in enumerate(chamadas):
            if indice:
                await asyncio.sleep(PAUSA_ENTRE_ETAPAS)
            async with self:
                self._marcar(indice, "executando")
            status, resposta = await requisitar("POST", caminho, token, corpo or {}, timeout=timeout)
            if status == 401:
                async with self:
                    self.executando = False
                    self.aberto = False
                yield AuthState.handle_unauthenticated
                return
            estado, mensagem = interpretar(status, resposta)
            async with self:
                self._marcar(indice, estado, mensagem)

        async with self:
            self.executando = False

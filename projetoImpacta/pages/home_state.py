"""Estado da home (dashboard) — somente dados reais do Xano.

Três leituras em sequência (limite de requisições do plano Xano):
`GET /projetos-resumo-consumo-mtd`, `GET /alertas` e `GET /recursos-nao-classificados`.
Cada bloco tem seu próprio erro; a falha de um não esconde os demais.
"""

from __future__ import annotations

import asyncio
import time
from datetime import date, timedelta
from typing import Any, TypedDict

import reflex as rx

from ..api import requisitar
from ..components.contador_state import ContadorAlertasState
from ..components.periodo_state import PeriodoState, parametro_mes
from ..state import AuthState
from .alertas_state import NIVEIS_CRITICOS, Alerta, normalizar_alerta
from ..formatadores import formatar_valor, percentual_br
from .projetos_state import CUSTO_INDISPONIVEL, itens_do_resumo

ERRO_CONSUMO = "Não foi possível carregar o consumo dos projetos."
ERRO_ALERTAS = "Não foi possível carregar os alertas."
ERRO_RECURSOS = "Não foi possível carregar os recursos não classificados."

_FAIXAS = {
    "normal": ("green", "Normal"),
    "atencao": ("yellow", "Atenção"),
    "critico": ("orange", "Aviso"),
    "estourado": ("red", "Excedido"),
}


class ConsumoProjeto(TypedDict):
    id: int
    nome: str
    codigo: str
    custo_texto: str
    orcamento_texto: str
    percentual_texto: str
    barra_valor: int
    faixa_cor: str
    faixa_rotulo: str


def resumo_custo(itens: list[dict]) -> dict:
    """Soma do custo classificado em USD e quantos projetos ficaram fora da soma."""
    total = 0.0
    com_custo = 0
    fora = 0
    indisponiveis = 0
    for p in itens:
        if p["custo_status"] == "ok":
            total += float(p["custo_mtd"])
            com_custo += 1
        elif p["custo_status"] in ("moeda_incompativel", "moedas_mistas"):
            fora += 1
        elif p["custo_status"] == CUSTO_INDISPONIVEL:
            indisponiveis += 1
    return {"total": round(total, 2), "com_custo": com_custo, "fora": fora, "indisponiveis": indisponiveis}


def texto_periodo(data_inicio: str, data_fim: str) -> str:
    """'01/10/2026 a 27/10/2026' (data_fim do backend é exclusiva)."""
    try:
        ini = date.fromisoformat(data_inicio)
        fim = date.fromisoformat(data_fim) - timedelta(days=1)
    except (TypeError, ValueError):
        return ""
    return f"{ini:%d/%m/%Y} a {fim:%d/%m/%Y}"


def maiores_consumos(itens: list[dict], limite: int = 5) -> list[ConsumoProjeto]:
    """Projetos ativos com percentual calculado pelo backend, do maior para o menor."""
    elegiveis = [
        p for p in itens
        if p["status"] == "ativo" and p["percentual_usado"] is not None and p["faixa"] in _FAIXAS
    ]
    elegiveis.sort(key=lambda p: float(p["percentual_usado"]), reverse=True)
    saida: list[ConsumoProjeto] = []
    for p in elegiveis[:limite]:
        pct = float(p["percentual_usado"])
        cor, rotulo = _FAIXAS[p["faixa"]]
        saida.append({
            "id": p["id"],
            "nome": p["nome"],
            "codigo": p["codigo"],
            "custo_texto": formatar_valor(float(p["custo_mtd"]), "USD"),
            "orcamento_texto": formatar_valor(float(p["budget"]), "USD"),
            "percentual_texto": percentual_br(pct),
            "barra_valor": int(round(min(max(pct, 0.0), 100.0))),
            "faixa_cor": cor,
            "faixa_rotulo": rotulo,
        })
    return saida


class HomeState(rx.State):
    loading: bool = False
    # Falso até a primeira carga do mês terminar: os KPIs mostram um marcador de
    # carregamento em vez do 0 inicial (P2-4). Recargas do acompanhamento mantêm os valores.
    carregado: bool = False
    erro_consumo: str = ""
    erro_alertas: str = ""
    erro_recursos: str = ""

    custo_texto: str = ""
    custo_nota: str = ""
    periodo_texto: str = ""
    projetos_ativos: int = 0
    consumos: list[ConsumoProjeto] = []

    alertas_abertos: int = 0
    alertas_criticos: int = 0
    alertas_recentes: list[Alerta] = []

    recursos_nao_classificados: int = 0
    _forcar: bool = False  # próxima carga ignora o cache (botão Atualizar)

    @rx.event
    def atualizar(self):
        self._forcar = True
        return HomeState.carregar

    @rx.event
    async def mudar_mes(self, valor: str):
        periodo = await self.get_state(PeriodoState)
        periodo.mes = valor
        self.carregado = False  # os valores na tela são do mês anterior
        yield HomeState.carregar

    @rx.event
    async def carregar(self):
        token = (await self.get_state(AuthState)).token
        if not token:
            yield AuthState.handle_unauthenticated
            return
        self.loading = True
        self.erro_consumo = self.erro_alertas = self.erro_recursos = ""
        yield

        # As três leituras são independentes: em paralelo.
        mes = (await self.get_state(PeriodoState)).preparar()
        forcar, self._forcar = self._forcar, False
        # Uma leitura agregada (painel), compartilhada com Projetos e Alertas pelo
        # cache. Se falhar, as três leituras individuais mantêm os blocos independentes.
        status_p, painel = await requisitar("GET", "/painel", token, params=parametro_mes(mes), forcar=forcar)
        if status_p == 401:
            self.loading = False
            yield AuthState.handle_unauthenticated
            return
        if status_p == 200 and isinstance(painel, dict):
            res_resumo = (200, painel.get("resumo"))
            res_alertas = (200, painel.get("alertas"))
            res_recursos = (200, painel.get("recursos_nao_classificados"))
        else:
            res_resumo, res_alertas, res_recursos = await asyncio.gather(
                requisitar("GET", "/projetos-resumo-consumo-mtd", token, params=parametro_mes(mes), forcar=forcar),
                requisitar("GET", "/alertas", token, forcar=forcar),
                requisitar("GET", "/recursos-nao-classificados", token, forcar=forcar),
            )

        # Consumo dos projetos no mês selecionado.
        status, corpo = res_resumo
        if status == 401:
            self.loading = False
            yield AuthState.handle_unauthenticated
            return
        itens = itens_do_resumo(corpo) if status == 200 else None
        if itens is None:
            self.erro_consumo = ERRO_CONSUMO
            self.custo_texto = ""
            self.custo_nota = ""
            self.consumos = []
        else:
            r = resumo_custo(itens)
            self.periodo_texto = texto_periodo(corpo.get("data_inicio"), corpo.get("data_fim"))
            self.projetos_ativos = len([p for p in itens if p["status"] == "ativo"])
            if r["com_custo"]:
                self.custo_texto = formatar_valor(r["total"], "USD")
                self.custo_nota = ""
            else:
                self.custo_texto = ""
                self.custo_nota = (
                    "Ainda não há custos classificados neste mês. Selecione um mês anterior ou sincronize os provedores."
                    if corpo.get("mes_corrente", True)
                    else "Sem custos classificados neste mês."
                )
            if r["fora"]:
                extra = f"{r['fora']} projeto(s) com custo em outra moeda não entram na soma."
                self.custo_nota = f"{self.custo_nota} {extra}".strip()
            if r["indisponiveis"]:
                extra = f"{r['indisponiveis']} projeto(s) com consumo indisponível não entram na soma."
                self.custo_nota = f"{self.custo_nota} {extra}".strip()
            self.consumos = maiores_consumos(itens)

        # Alertas.
        status, corpo = res_alertas
        if status == 401:
            self.loading = False
            yield AuthState.handle_unauthenticated
            return
        if status == 200 and isinstance(corpo, list):
            agora = int(time.time() * 1000)
            alertas = [a for a in (normalizar_alerta(b, agora) for b in corpo) if a is not None]
            abertos = [a for a in alertas if not a["resolvido"]]
            self.alertas_abertos = len(abertos)
            self.alertas_criticos = len([a for a in abertos if a["nivel"] in NIVEIS_CRITICOS])
            self.alertas_recentes = abertos[:5]
            contador = await self.get_state(ContadorAlertasState)
            contador.atualizar(self.alertas_abertos, self.alertas_criticos)
        else:
            self.erro_alertas = ERRO_ALERTAS
            self.alertas_recentes = []

        # Recursos não classificados.
        status, corpo = res_recursos
        if status == 401:
            self.loading = False
            yield AuthState.handle_unauthenticated
            return
        if status == 200 and isinstance(corpo, list):
            self.recursos_nao_classificados = len(corpo)
        else:
            self.erro_recursos = ERRO_RECURSOS
        self.loading = False
        self.carregado = True

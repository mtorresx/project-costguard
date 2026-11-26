"""Mês selecionado, compartilhado entre Início, Projetos e detalhe do projeto.

`mes` vazio significa o mês atual (até a data atual). Um mês anterior é o mês
fechado inteiro. O mês é o de America/Sao_Paulo.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import TypedDict
from zoneinfo import ZoneInfo

import reflex as rx

FUSO = ZoneInfo("America/Sao_Paulo")
MES_ATUAL = "atual"  # valor do seletor para o mês atual (o Select não aceita "")
MESES_ANTERIORES = 5
_NOMES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho",
          "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]


class OpcaoMes(TypedDict):
    valor: str
    rotulo: str


def _mes_anterior(d: date) -> date:
    return (d.replace(day=1) - timedelta(days=1)).replace(day=1)


def opcoes_meses(hoje: date) -> list[OpcaoMes]:
    """Mês atual e os 5 anteriores, do mais recente para o mais antigo."""
    opcoes: list[OpcaoMes] = [{"valor": MES_ATUAL, "rotulo": f"{_NOMES[hoje.month - 1]}/{hoje.year} (mês atual)"}]
    d = hoje.replace(day=1)
    for _ in range(MESES_ANTERIORES):
        d = _mes_anterior(d)
        opcoes.append({"valor": f"{d.year:04d}-{d.month:02d}", "rotulo": f"{_NOMES[d.month - 1]}/{d.year}"})
    return opcoes


def janela_mes(mes: str, agora: datetime) -> tuple[date, date, bool]:
    """(data_inicio, data_fim exclusivo, é mês corrente) para o mês selecionado.

    `mes` vazio, `MES_ATUAL` ou igual ao mês corrente → dia 1 até amanhã.
    Mês anterior (`AAAA-MM`) → dia 1 até o dia 1 do mês seguinte.
    Valor inválido ou futuro → mês corrente.
    """
    hoje = agora.astimezone(FUSO).date()
    corrente = (hoje.replace(day=1), hoje + timedelta(days=1), True)
    if not mes or mes == MES_ATUAL:
        return corrente
    try:
        ano, num = (int(x) for x in mes.split("-"))
        inicio = date(ano, num, 1)
    except (ValueError, TypeError):
        return corrente
    if inicio >= hoje.replace(day=1):
        return corrente
    fim = date(ano + 1, 1, 1) if num == 12 else date(ano, num + 1, 1)
    return inicio, fim, False


def parametro_mes(mes: str) -> dict | None:
    """Parâmetro `mes` para o resumo do backend (None = mês atual)."""
    return None if not mes or mes == MES_ATUAL else {"mes": mes}


class PeriodoState(rx.State):
    mes: str = MES_ATUAL
    opcoes: list[OpcaoMes] = opcoes_meses(datetime.now(FUSO).date())

    def preparar(self) -> str:
        """Atualiza as opções (o mês pode ter virado) e devolve o mês válido."""
        self.opcoes = opcoes_meses(datetime.now(FUSO).date())
        if self.mes not in {o["valor"] for o in self.opcoes}:
            self.mes = MES_ATUAL
        return self.mes


def seletor_mes(on_change) -> rx.Component:
    """Seletor de mês (compartilhado). `on_change` recebe o valor escolhido."""
    return rx.hstack(
        rx.icon("calendar", size=16, color="#94a3b8"),
        rx.select.root(
            rx.select.trigger(min_width="210px"),
            rx.select.content(
                rx.foreach(PeriodoState.opcoes, lambda o: rx.select.item(o["rotulo"], value=o["valor"])),
            ),
            value=PeriodoState.mes,
            on_change=on_change,
            size="2",
        ),
        spacing="2",
        align="center",
    )

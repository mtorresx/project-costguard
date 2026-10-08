"""Página de Projetos ("/projetos") — apresentação/mock.

Reaproveita o visual de cards de projeto do frontend externo com dados
ilustrativos. Sem backend nesta etapa: não há chamadas de API nem persistência.
"""

import reflex as rx

from .. import theme as t
from ..components.layout import app_shell

# Dados ilustrativos (demonstração) — não vêm de backend.
_PROJETOS_MOCK = [
    {"nome": "Pagamentos", "codigo": "PAGAMENTOS", "custo": "US$ 8.420,00", "budget": "US$ 10.000,00", "pct": 84},
    {"nome": "Dados & BI", "codigo": "DADOS", "custo": "US$ 3.110,00", "budget": "US$ 6.000,00", "pct": 52},
    {"nome": "Mobile", "codigo": "MOBILE", "custo": "US$ 6.900,00", "budget": "US$ 6.000,00", "pct": 115},
]


def _cor_barra(pct: int) -> str:
    if pct > 100:
        return "red"
    if pct >= 80:
        return "amber"
    return "green"


def _card(projeto: dict) -> rx.Component:
    pct = projeto["pct"]
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.vstack(
                    rx.text(projeto["nome"], font_size="17px", font_weight="600", color=t.TEXT_HIGH),
                    rx.text(f"PRJ_{projeto['codigo']}", font_size="12px", color=t.TEXT_MED),
                    spacing="1",
                    align="start",
                ),
                rx.spacer(),
                rx.box(
                    rx.icon("server", size=15),
                    background=t.INPUT_BG,
                    padding="10px",
                    border_radius="9999px",
                    border=f"1px solid {t.BORDER_SUBTLE}",
                    color=t.TEXT_MED,
                ),
                width="100%",
                align="center",
            ),
            rx.box(
                rx.text("CUSTO ATUAL (MÊS)", font_size="11px", font_weight="600", color=t.TEXT_MED, letter_spacing="0.05em"),
                rx.text(projeto["custo"], font_size="28px", font_weight="700", color=t.TEXT_HIGH),
                margin_top="16px",
            ),
            rx.vstack(
                rx.hstack(
                    rx.text(f"Budget: {projeto['budget']}", font_size="12px", color=t.TEXT_MED),
                    rx.spacer(),
                    rx.text(f"{pct}%", font_size="12px", color=t.TEXT_HIGH, font_weight="600"),
                    width="100%",
                ),
                rx.progress(
                    value=min(pct, 100),
                    color_scheme=_cor_barra(pct),
                    height="6px",
                    border_radius="9999px",
                    width="100%",
                ),
                width="100%",
                margin_top="16px",
            ),
            align="start",
            width="100%",
        ),
        background=t.SURFACE,
        border=f"1px solid {t.BORDER_SUBTLE}",
        border_radius="14px",
        padding="22px",
        width="100%",
    )


def _conteudo() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.vstack(
                    rx.heading("Projetos", size="7", color=t.TEXT_HIGH),
                    rx.text("Visão de orçamento por projeto.", color=t.TEXT_MED, size="2"),
                    spacing="1",
                    align="start",
                ),
                rx.spacer(),
                rx.badge("Demonstração — sem backend", color_scheme="gray", variant="surface"),
                width="100%",
                align="center",
            ),
            rx.grid(
                *[_card(p) for p in _PROJETOS_MOCK],
                columns=rx.breakpoints(initial="1", md="3"),
                spacing="4",
                width="100%",
            ),
            spacing="6",
            width="100%",
            max_width="1100px",
        ),
        padding=["24px", "32px", "48px"],
        width="100%",
    )


def projetos_page() -> rx.Component:
    return app_shell(_conteudo(), active="projetos")

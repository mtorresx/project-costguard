"""Página de Alertas ("/alertas") — apresentação/mock.

Lista alertas com dados ilustrativos. Sem backend nesta etapa.
"""

import reflex as rx

from .. import theme as t
from ..components.layout import app_shell
from ..components.pill import pill

_ALERTAS_MOCK = [
    {"nivel": "aviso", "mensagem": "Projeto MOBILE ultrapassou 100% do orçamento.", "quando": "há 2 horas"},
    {"nivel": "atencao", "mensagem": "Projeto PAGAMENTOS atingiu 84% do orçamento.", "quando": "há 5 horas"},
    {"nivel": "importacao", "mensagem": "Falha ao importar custos de AWS Dados.", "quando": "ontem"},
]


def _nivel_pill(nivel: str) -> rx.Component:
    mapa = {
        "atencao": ("Atenção", t.WARNING, "rgba(245,158,11,0.1)", "rgba(245,158,11,0.3)"),
        "aviso": ("Orçamento excedido", t.ERROR, "rgba(239,68,68,0.1)", "rgba(239,68,68,0.3)"),
        "importacao": ("Falha de importação", t.ERROR, "rgba(239,68,68,0.1)", "rgba(239,68,68,0.3)"),
    }
    texto, cor, fundo, borda = mapa.get(nivel, ("Alerta", t.TEXT_MED, "rgba(148,163,184,0.1)", "rgba(148,163,184,0.3)"))
    return pill(texto, cor, fundo, borda)


def _card(alerta: dict) -> rx.Component:
    return rx.hstack(
        rx.icon("bell", size=18, color=t.PRIMARY_ACCENT),
        rx.vstack(
            _nivel_pill(alerta["nivel"]),
            rx.text(alerta["mensagem"], color=t.TEXT_HIGH, size="2"),
            rx.text(alerta["quando"], color=t.TEXT_MED, size="1"),
            spacing="1",
            align="start",
        ),
        spacing="3",
        align="start",
        width="100%",
        padding="16px",
        background=t.SURFACE,
        border=f"1px solid {t.BORDER_SUBTLE}",
        border_radius="12px",
    )


def _conteudo() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.vstack(
                    rx.heading("Alertas", size="7", color=t.TEXT_HIGH),
                    rx.text("Situações que exigem atenção.", color=t.TEXT_MED, size="2"),
                    spacing="1",
                    align="start",
                ),
                rx.spacer(),
                rx.badge("Demonstração — sem backend", color_scheme="gray", variant="surface"),
                width="100%",
                align="center",
            ),
            rx.vstack(*[_card(a) for a in _ALERTAS_MOCK], spacing="3", width="100%"),
            spacing="6",
            width="100%",
            max_width="900px",
        ),
        padding=["24px", "32px", "48px"],
        width="100%",
    )


def alertas_page() -> rx.Component:
    return app_shell(_conteudo(), active="alertas")

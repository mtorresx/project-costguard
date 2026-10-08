"""Página de Provedores ("/provedores") — apresentação/mock.

Lista provedores de nuvem com dados ilustrativos. Sem backend nesta etapa.
"""

import reflex as rx

from .. import theme as t
from ..components.layout import app_shell
from ..components.pill import pill
from ..components.tabela import th

_PROVEDORES_MOCK = [
    {"apelido": "AWS Produção", "tipo": "AWS", "conta": "1234-5678-9012", "status": "ok"},
    {"apelido": "AWS Dados", "tipo": "AWS", "conta": "2233-4455-6677", "status": "com_erro"},
]


def _status_pill(status: str) -> rx.Component:
    if status == "ok":
        return pill("Conectado", t.SUCCESS, "rgba(34,197,94,0.1)", "rgba(34,197,94,0.3)")
    if status == "com_erro":
        return pill("Com erro", t.WARNING, "rgba(245,158,11,0.1)", "rgba(245,158,11,0.3)")
    return pill("Inativo", t.TEXT_MED, "rgba(148,163,184,0.1)", "rgba(148,163,184,0.3)")


def _linha(p: dict) -> rx.Component:
    return rx.table.row(
        rx.table.cell(p["apelido"], color=t.TEXT_HIGH),
        rx.table.cell(p["tipo"], color=t.TEXT_MED),
        rx.table.cell(p["conta"], color=t.TEXT_MED, font_family="monospace"),
        rx.table.cell(_status_pill(p["status"])),
    )


def _conteudo() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.vstack(
                    rx.heading("Provedores", size="7", color=t.TEXT_HIGH),
                    rx.text("Contas de nuvem conectadas (somente leitura).", color=t.TEXT_MED, size="2"),
                    spacing="1",
                    align="start",
                ),
                rx.spacer(),
                rx.badge("Demonstração — sem backend", color_scheme="gray", variant="surface"),
                width="100%",
                align="center",
            ),
            rx.box(
                rx.table.root(
                    rx.table.header(
                        rx.table.row(th("Apelido"), th("Tipo"), th("Conta"), th("Status")),
                    ),
                    rx.table.body(*[_linha(p) for p in _PROVEDORES_MOCK]),
                    variant="surface",
                    width="100%",
                ),
                background=t.SURFACE,
                border=f"1px solid {t.BORDER_SUBTLE}",
                border_radius="14px",
                padding="8px",
                width="100%",
            ),
            spacing="6",
            width="100%",
            max_width="1000px",
        ),
        padding=["24px", "32px", "48px"],
        width="100%",
    )


def provedores_page() -> rx.Component:
    return app_shell(_conteudo(), active="provedores")

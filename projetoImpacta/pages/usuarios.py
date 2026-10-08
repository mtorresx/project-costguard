"""Página de Usuários ("/usuarios") — apresentação/mock.

Lista usuários com dados ilustrativos. Sem backend de gestão de usuários nesta
etapa (gestão de usuários é feature futura). Sem chamadas de API.
"""

import reflex as rx

from .. import theme as t
from ..components.layout import app_shell
from ..components.pill import pill
from ..components.tabela import th

_USUARIOS_MOCK = [
    {"nome": "Administrador", "username": "admin", "role": "admin", "status": "ativo"},
    {"nome": "Analista FinOps", "username": "analista", "role": "leitura", "status": "ativo"},
]


def _role_pill(role: str) -> rx.Component:
    if role == "admin":
        return pill("Admin", t.PRIMARY_ACCENT, "rgba(20,184,166,0.12)", "rgba(20,184,166,0.3)")
    return pill("Leitura", t.TEXT_MED, "rgba(148,163,184,0.1)", "rgba(148,163,184,0.3)")


def _status_pill(status: str) -> rx.Component:
    if status == "ativo":
        return pill("Ativo", t.SUCCESS, "rgba(34,197,94,0.1)", "rgba(34,197,94,0.3)")
    return pill("Inativo", t.TEXT_MED, "rgba(148,163,184,0.1)", "rgba(148,163,184,0.3)")


def _linha(u: dict) -> rx.Component:
    return rx.table.row(
        rx.table.cell(u["nome"], color=t.TEXT_HIGH),
        rx.table.cell(u["username"], color=t.TEXT_MED, font_family="monospace"),
        rx.table.cell(_role_pill(u["role"])),
        rx.table.cell(_status_pill(u["status"])),
    )


def _conteudo() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.vstack(
                    rx.heading("Usuários", size="7", color=t.TEXT_HIGH),
                    rx.text("Gestão de acesso (feature futura).", color=t.TEXT_MED, size="2"),
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
                        rx.table.row(th("Nome"), th("Usuário"), th("Papel"), th("Status")),
                    ),
                    rx.table.body(*[_linha(u) for u in _USUARIOS_MOCK]),
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


def usuarios_page() -> rx.Component:
    return app_shell(_conteudo(), active="usuarios")

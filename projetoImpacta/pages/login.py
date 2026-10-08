"""Página pública de login (/login) do CostGuard.

Visual incorporado do frontend externo (components/auth_ui), aplicado sobre o
fluxo de login funcional existente: `AuthState.do_login` com o contrato
`{username, password}`. Nenhuma lógica de auth externa é usada.
"""

import reflex as rx

from ..components.auth_ui import (
    FONT_BODY,
    ON_PRIMARY,
    auth_card,
    auth_page,
    divider,
    error_banner,
    field_label,
    heading_block,
    text_input,
)
from ..state import AuthState
from .. import theme as t


def _submit_button() -> rx.Component:
    """Botão de submit no visual incorporado (dispara apenas o on_submit do form)."""
    return rx.button(
        rx.cond(
            AuthState.is_loading,
            rx.hstack(
                rx.spinner(size="2", color="white"),
                rx.text("Entrando…", font_size="14px", font_weight="600", color=ON_PRIMARY),
                align="center",
                spacing="2",
            ),
            rx.text("Entrar", font_size="14px", font_weight="600", color=ON_PRIMARY),
        ),
        type="submit",
        disabled=AuthState.is_loading,
        background_color=t.PRIMARY,
        border="none",
        border_radius="4px",
        padding="12px 24px",
        width="100%",
        height="44px",
        cursor=rx.cond(AuthState.is_loading, "not-allowed", "pointer"),
        box_shadow="0 0 20px rgba(45, 212, 191, 0.25)",
        _hover={"box_shadow": "0 0 30px rgba(45, 212, 191, 0.5)", "opacity": "0.92"},
        _disabled={"opacity": "0.5"},
        transition="box-shadow 0.15s ease, opacity 0.15s ease",
        display="flex",
        align_items="center",
        justify_content="center",
    )


def _campo_usuario() -> rx.Component:
    return rx.vstack(
        field_label("Usuário"),
        text_input(
            placeholder="seu.usuario",
            name="username",
            type="text",
            auto_focus=True,
        ),
        spacing="2",
        width="100%",
    )


def _campo_senha() -> rx.Component:
    return rx.vstack(
        field_label("Senha"),
        text_input(
            placeholder="••••••••",
            name="password",
            type="password",
        ),
        spacing="2",
        width="100%",
    )


def _login_card() -> rx.Component:
    return auth_card(
        heading_block("Bem-vindo de volta", "Acesse sua inteligência financeira."),
        divider(),
        rx.form(
            rx.vstack(
                _campo_usuario(),
                _campo_senha(),
                error_banner(AuthState.login_error),
                _submit_button(),
                spacing="4",
                width="100%",
            ),
            on_submit=AuthState.do_login,
            reset_on_submit=False,
            width="100%",
        ),
        rx.center(
            rx.text(
                "Gerenciamento de custos cloud em tempo real",
                font_family=FONT_BODY,
                font_size="11px",
                color=t.LANDING_MUTED,
                letter_spacing="0.02em",
                text_align="center",
            ),
            width="100%",
            margin_top="8px",
        ),
    )


def login_page() -> rx.Component:
    return auth_page(_login_card())

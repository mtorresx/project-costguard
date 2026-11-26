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
from ..config import URL_LANDING
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


class SenhaVisivelState(rx.State):
    """Só apresentação: alterna a senha entre oculta e visível no campo do login."""

    visivel: bool = False

    @rx.event
    def alternar(self):
        self.visivel = not self.visivel


def _campo_senha() -> rx.Component:
    return rx.vstack(
        field_label("Senha"),
        rx.box(
            text_input(
                placeholder="••••••••",
                name="password",
                type=rx.cond(SenhaVisivelState.visivel, "text", "password"),
                padding_right="40px",
            ),
            rx.el.button(
                rx.cond(
                    SenhaVisivelState.visivel,
                    rx.icon("eye-off", size=16),
                    rx.icon("eye", size=16),
                ),
                type="button",  # não envia o formulário
                on_click=SenhaVisivelState.alternar,
                aria_label=rx.cond(SenhaVisivelState.visivel, "Ocultar senha", "Mostrar senha"),
                title=rx.cond(SenhaVisivelState.visivel, "Ocultar senha", "Mostrar senha"),
                position="absolute",
                right="10px",
                top="50%",
                transform="translateY(-50%)",
                background="transparent",
                border="none",
                cursor="pointer",
                color=t.TEXT_MED,
                display="flex",
                align_items="center",
                _hover={"color": t.TEXT_HIGH},
            ),
            position="relative",
            width="100%",
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


def _link_voltar() -> rx.Component:
    """Link discreto para a landing page, no canto superior esquerdo, fora do card."""
    return rx.link(
        rx.icon("arrow-left", size=16, aria_hidden="true"),
        rx.text("Voltar", as_="span", display=["inline", "inline", "none"]),
        rx.text("Voltar ao início", as_="span", display=["none", "none", "inline"]),
        href=URL_LANDING,
        # Com URL absoluta (produção) a landing é outra origem: navegação de documento.
        # Sem a variável ("/"), segue a navegação interna do cliente de sempre.
        **({"reload_document": True} if URL_LANDING != "/" else {}),
        aria_label="Voltar para a página inicial",
        underline="none",
        position="absolute",
        top="24px",
        left=["16px", "16px", "32px"],
        z_index="3",
        display="inline-flex",
        align_items="center",
        gap="6px",
        font_family=FONT_BODY,
        font_size="13px",
        color=t.LANDING_MUTED_LIGHT,
        transition="color 0.15s ease",
        _hover={"color": t.LANDING_ACCENT},
    )


def login_page() -> rx.Component:
    return auth_page(_login_card(), _link_voltar())

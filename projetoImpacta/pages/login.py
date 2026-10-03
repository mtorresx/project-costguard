"""Página pública de login (/login) do CostGuard."""

import reflex as rx

from ..state import AuthState


def login_page() -> rx.Component:
    """Formulário mínimo de login: username e password."""
    return rx.center(
        rx.card(
            rx.vstack(
                rx.heading("CostGuard", size="7"),
                rx.text("Entre com suas credenciais", size="3"),
                rx.form(
                    rx.vstack(
                        rx.input(
                            placeholder="Usuário",
                            name="username",
                            required=True,
                            width="100%",
                        ),
                        rx.input(
                            placeholder="Senha",
                            name="password",
                            type="password",
                            required=True,
                            width="100%",
                        ),
                        rx.cond(
                            AuthState.login_error != "",
                            rx.callout(
                                AuthState.login_error,
                                color_scheme="red",
                                size="1",
                                width="100%",
                            ),
                        ),
                        rx.button(
                            rx.cond(AuthState.is_loading, "Entrando...", "Entrar"),
                            type="submit",
                            width="100%",
                            disabled=AuthState.is_loading,
                        ),
                        spacing="3",
                        width="100%",
                    ),
                    on_submit=AuthState.do_login,
                    reset_on_submit=False,
                    width="100%",
                ),
                spacing="4",
                width="100%",
            ),
            width="22rem",
        ),
        min_height="100vh",
    )

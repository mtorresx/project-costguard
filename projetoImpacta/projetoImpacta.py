"""Aplicação CostGuard (Reflex) — autenticação base.

Rotas desta change:
- /login : página pública de login.
- /      : área autenticada mínima protegida (não é o dashboard definitivo).

A proteção de /` é de navegação/UX (on_load + redirect). A autorização real
permanece no backend Xano.
"""

import reflex as rx

from .pages.login import login_page
from .state import AuthState


def index() -> rx.Component:
    """Área autenticada mínima. Protegida por on_load=AuthState.require_auth."""
    return rx.center(
        rx.card(
            rx.vstack(
                rx.heading("CostGuard", size="7"),
                rx.text("Área autenticada", size="3"),
                rx.text(
                    rx.text.strong("Usuário: "),
                    AuthState.username,
                    size="2",
                ),
                rx.text(
                    rx.text.strong("Papel: "),
                    AuthState.role,
                    size="2",
                ),
                rx.button(
                    "Sair",
                    on_click=AuthState.logout,
                    color_scheme="gray",
                    variant="soft",
                ),
                spacing="3",
                align="start",
            ),
            width="22rem",
        ),
        min_height="100vh",
    )


app = rx.App()
# Área autenticada: verifica a sessão no carregamento (D6).
app.add_page(index, route="/", on_load=AuthState.require_auth)
# Página pública de login.
app.add_page(login_page, route="/login")

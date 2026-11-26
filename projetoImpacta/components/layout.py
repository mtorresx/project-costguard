"""Shell visual compartilhado (sidebar + topbar) — Dark Kinetic.

Incorporado do frontend externo (design) e adaptado ao projeto principal:
- usa o `AuthState` do projeto (`projetoImpacta/state.py`), não o auth externo;
- sem chamada própria ao backend: o contador de alertas vem de `ContadorAlertasState`,
  atualizado pelas páginas que já leem `GET /alertas` (limite do plano Xano);
- `UIState` guarda apenas a abertura dos modais (sem preferências não persistidas).

Usado por todas as páginas autenticadas via `app_shell(content, active=...)`.
"""

from typing import Literal, Optional

import reflex as rx

from .. import theme as t
from ..state import AuthState
from .contador_state import ContadorAlertasState

NavKey = Literal["home", "projetos", "provedores", "usuarios", "alertas"]

# (chave, rótulo, ícone lucide, rota)
_NAV_ITEMS: list[tuple[NavKey, str, str, str]] = [
    ("home", "Início", "layout-dashboard", "/inicio"),
    ("projetos", "Projetos", "folder-kanban", "/projetos"),
    ("provedores", "Provedores", "cloud", "/provedores"),
    ("usuarios", "Usuários", "users", "/usuarios"),
    ("alertas", "Alertas", "bell", "/alertas"),
]

_PLACEHOLDER_BUSCA: dict[NavKey, str] = {
    "home": "Buscar...",
    "projetos": "Buscar recursos, projetos, alertas...",
    "provedores": "Buscar provedores...",
    "usuarios": "Buscar usuários...",
    "alertas": "Buscar alertas...",
}


class UIState(rx.State):
    """Abertura dos modais do shell (somente em memória)."""

    settings_open: bool = False
    help_open: bool = False

    @rx.event
    def abrir_settings(self):
        self.settings_open = True

    @rx.event
    def fechar_settings(self):
        self.settings_open = False

    @rx.event
    def abrir_help(self):
        self.help_open = True

    @rx.event
    def fechar_help(self):
        self.help_open = False


def _badge_alertas() -> rx.Component:
    return rx.cond(
        ContadorAlertasState.abertos > 0,
        rx.box(
            rx.text(ContadorAlertasState.abertos, font_size="11px", font_weight="700"),
            margin_left="auto",
            padding="0 7px",
            border_radius="999px",
            background=rx.cond(ContadorAlertasState.criticos > 0, t.ERROR, t.WARNING),
            color="#0f172a",
        ),
        rx.fragment(),
    )


def _nav_link(chave: NavKey, label: str, icone: str, rota: str, active: NavKey) -> rx.Component:
    is_active = chave == active
    link = rx.link(
        rx.hstack(
            rx.icon(icone, size=18, stroke_width=1.5),
            rx.text(label, font_size="13px", font_weight="500"),
            *([_badge_alertas()] if chave == "alertas" else []),
            spacing="3",
            align="center",
            width="100%",
        ),
        href=rota,
        underline="none",
        width="100%",
        justify="start",
        padding_x="14px",
        padding_y="10px",
        border_radius="8px",
        background=rx.cond(is_active, t.NAV_ACTIVE_BG, "transparent"),
        color=rx.cond(is_active, t.PRIMARY_ACCENT, t.TEXT_MED),
        border=rx.cond(is_active, "1px solid rgba(20, 184, 166, 0.45)", "1px solid transparent"),
        _hover={"background": t.NAV_HOVER_BG, "color": t.TEXT_MAIN},
        cursor="pointer",
        display="block",
    )
    if chave != "usuarios":
        return link
    # A gestão de usuários é apresentada apenas a administradores (UI; autorização real no Xano).
    return rx.cond(AuthState.is_admin, link, rx.fragment())


def _brand() -> rx.Component:
    return rx.link(
        rx.hstack(
            rx.image(src="/logo-costguard.svg", width="36px", height="36px", border_radius="6px"),
            rx.vstack(
                rx.text("CostGuard", font_size="18px", font_weight="700", color=t.PRIMARY_ACCENT, line_height="1"),
                rx.text("FinOps Intelligence", font_size="11px", color=t.TEXT_MED),
                spacing="1",
                align="start",
            ),
            spacing="3",
            align="center",
        ),
        href="/inicio",
        underline="none",
        margin_bottom="28px",
        padding_x="8px",
    )


def _user_card() -> rx.Component:
    return rx.hstack(
        rx.avatar(fallback=AuthState.initial, size="2", radius="full", color_scheme="teal"),
        rx.vstack(
            rx.text(AuthState.username, font_size="12px", font_weight="600", color=t.TEXT_HIGH),
            rx.text(
                rx.cond(AuthState.is_admin, "Administrador", "Leitura"),
                font_size="10px",
                color=t.TEXT_MED,
            ),
            spacing="0",
            align="start",
        ),
        spacing="3",
        align="center",
        width="100%",
        padding="10px",
        background="rgba(23, 31, 51, 0.6)",
        border=f"1px solid {t.BORDER_SUBTLE}",
        border_radius="10px",
    )


def _sidebar(active: NavKey) -> rx.Component:
    return rx.box(
        rx.vstack(
            _brand(),
            rx.vstack(
                *[
                    _nav_link(chave, label, icone, rota, active=active)
                    for chave, label, icone, rota in _NAV_ITEMS
                ],
                spacing="2",
                width="100%",
            ),
            rx.spacer(),
            rx.vstack(
                _user_card(),
                rx.button(
                    rx.hstack(rx.icon("log-out", size=16), rx.text("Encerrar Sessão", font_size="12px")),
                    on_click=AuthState.logout,
                    variant="ghost",
                    color=t.ERROR,
                    width="100%",
                    justify_content="start",
                    _hover={"background": "rgba(239, 68, 68, 0.1)"},
                ),
                spacing="2",
                width="100%",
            ),
            height="100%",
            width="100%",
            padding="24px 16px",
        ),
        width="256px",
        height="100vh",
        position="fixed",
        left="0",
        top="0",
        background=t.BG,
        border_right=f"1px solid {t.BORDER_SUBTLE}",
        z_index="40",
        display=["none", "none", "block"],
    )


def _search_box(active: NavKey, value: rx.Var[str], on_change) -> rx.Component:
    return rx.hstack(
        rx.icon("search", size=16, color=t.TEXT_MED),
        rx.input(
            placeholder=_PLACEHOLDER_BUSCA[active],
            value=value,
            on_change=on_change,
            border="none",
            background="transparent",
            color=t.TEXT_MAIN,
            font_size="13px",
            _focus={"outline": "none"},
            width="100%",
        ),
        background=t.BG,
        border=f"1px solid {t.BORDER_SUBTLE}",
        border_radius="9999px",
        padding="5px 12px",
        width="380px",
        align="center",
    )


def _indicador_alertas() -> rx.Component:
    """Alertas abertos da última leitura real de GET /alertas (nada antes da primeira carga)."""
    cor = rx.cond(
        ContadorAlertasState.criticos > 0,
        t.ERROR,
        rx.cond(ContadorAlertasState.abertos > 0, t.WARNING, t.SUCCESS),
    )
    return rx.cond(
        ContadorAlertasState.carregado,
        rx.link(
            rx.badge(
                rx.hstack(
                    rx.box(width="6px", height="6px", border_radius="9999px", background=cor),
                    rx.text(
                        rx.cond(
                            ContadorAlertasState.abertos > 1,
                            ContadorAlertasState.abertos.to_string() + " alertas abertos",
                            rx.cond(ContadorAlertasState.abertos == 1, "1 alerta aberto", "Sem alertas abertos"),
                        ),
                        font_size="11px",
                    ),
                    align="center",
                    spacing="1",
                ),
                color_scheme=rx.cond(
                    ContadorAlertasState.criticos > 0,
                    "red",
                    rx.cond(ContadorAlertasState.abertos > 0, "amber", "green"),
                ),
                variant="surface",
            ),
            href="/alertas",
            underline="none",
        ),
        rx.fragment(),
    )


def _avatar_menu() -> rx.Component:
    return rx.menu.root(
        rx.menu.trigger(
            rx.avatar(
                fallback=AuthState.initial,
                size="2",
                color_scheme="teal",
                cursor="pointer",
                style={"border": "1px solid rgba(255, 255, 255, 0.15)"},
            ),
        ),
        rx.menu.content(
            rx.vstack(
                rx.text(AuthState.username, size="1", weight="bold"),
                rx.text(
                    rx.cond(AuthState.is_admin, "Administrador", "Leitura"),
                    size="1",
                    color=t.TEXT_MED,
                ),
                spacing="0",
                align="start",
                padding="0.25rem 0.5rem 0.5rem",
            ),
            rx.menu.separator(),
            rx.cond(
                AuthState.is_admin,
                rx.menu.item(
                    rx.hstack(rx.icon("users", size=14), rx.text("Gerenciar equipe"), spacing="2"),
                    on_click=rx.redirect("/usuarios"),
                ),
                rx.fragment(),
            ),
            rx.menu.item(
                rx.hstack(rx.icon("user", size=14), rx.text("Minha conta"), spacing="2"),
                on_click=UIState.abrir_settings,
            ),
            rx.menu.separator(),
            rx.menu.item(
                rx.hstack(rx.icon("log-out", size=14), rx.text("Sair do sistema"), spacing="2"),
                on_click=AuthState.logout,
                color="red",
            ),
        ),
    )


def _topbar(active: NavKey, search_value: Optional[rx.Var[str]], on_search) -> rx.Component:
    busca = _search_box(active, search_value, on_search) if search_value is not None else rx.box()
    return rx.box(
        rx.hstack(
            busca,
            rx.spacer(),
            _indicador_alertas(),
            rx.icon_button(
                rx.icon("user-cog", size=24),
                on_click=UIState.abrir_settings,
                variant="ghost",
                width="40px",
                height="40px",
                color=t.TEXT_MED,
                title="Minha conta",
            ),
            rx.icon_button(
                rx.icon("circle-help", size=24),
                on_click=UIState.abrir_help,
                variant="ghost",
                width="40px",
                height="40px",
                color=t.TEXT_MED,
                title="Ajuda",
            ),
            _avatar_menu(),
            width="100%",
            height="64px",
            padding_x="32px",
            align="center",
            spacing="4",
        ),
        position="fixed",
        top="0",
        right="0",
        width="calc(100% - 256px)",
        height="64px",
        background=t.BG,
        border_bottom=f"1px solid {t.BORDER_SUBTLE}",
        z_index="30",
        display=["none", "none", "block"],
    )


def _settings_modal() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(
                rx.hstack(
                    rx.icon("user-cog", size=18, color=t.PRIMARY_ACCENT),
                    rx.text("Minha conta"),
                    rx.spacer(),
                    rx.dialog.close(
                        rx.icon_button(rx.icon("x", size=16), variant="ghost", color=t.TEXT_MED, on_click=UIState.fechar_settings),
                    ),
                    spacing="2",
                    align="center",
                    width="100%",
                ),
            ),
            rx.vstack(
                rx.hstack(
                    rx.avatar(fallback=AuthState.initial, size="3", radius="full", color_scheme="teal"),
                    rx.vstack(
                        rx.text(AuthState.username, weight="bold", size="3"),
                        rx.badge(
                            rx.cond(AuthState.is_admin, "Administrador", "Leitura"),
                            color_scheme=rx.cond(AuthState.is_admin, "purple", "gray"),
                            variant="soft",
                        ),
                        spacing="1",
                        align="start",
                    ),
                    spacing="3",
                    align="center",
                ),
                rx.text(
                    rx.cond(
                        AuthState.is_admin,
                        "Administradores gerenciam usuários, projetos, orçamentos e provedores.",
                        "O papel Leitura permite consultar todas as informações, sem alterá-las.",
                    ),
                    size="2",
                    color=t.TEXT_MED,
                ),
                rx.box(height="1px", width="100%", background=t.BORDER_SUBTLE, margin_y="0.25rem"),
                rx.vstack(
                    rx.text("Faixas de alerta de orçamento", size="2", weight="medium"),
                    rx.text("70% — Atenção · 90% — Aviso · 100% ou mais — Orçamento excedido", size="2", color=t.TEXT_MED),
                    rx.text(
                        "As faixas são definidas pelo domínio do CostGuard e valem para todos os projetos.",
                        size="1",
                        color=t.TEXT_LOW,
                    ),
                    spacing="1",
                    width="100%",
                    align="start",
                ),
                rx.hstack(
                    rx.dialog.close(rx.button("Fechar", variant="soft", on_click=UIState.fechar_settings)),
                    width="100%",
                    justify="end",
                    padding_top="0.5rem",
                ),
                spacing="4",
                width="100%",
            ),
            background=t.SURFACE_RAISED,
            border=f"1px solid {t.BORDER_SUBTLE}",
            color=t.TEXT_MAIN,
            max_width="440px",
        ),
        open=UIState.settings_open,
    )


def _help_modal() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(
                rx.hstack(
                    rx.icon("circle-help", size=18, color=t.PRIMARY_ACCENT),
                    rx.text("Central de Ajuda CostGuard"),
                    rx.spacer(),
                    rx.dialog.close(
                        rx.icon_button(rx.icon("x", size=16), variant="ghost", color=t.TEXT_MED, on_click=UIState.fechar_help),
                    ),
                    spacing="2",
                    align="center",
                    width="100%",
                ),
            ),
            rx.vstack(
                rx.text("O CostGuard associa os custos da AWS a projetos e equipes pelas tags dos recursos e compara o consumo com o orçamento mensal.", size="2"),
                rx.box(
                    rx.vstack(
                        rx.text("Atalhos de navegação:", size="2", weight="bold"),
                        rx.text("• Início: visão geral do mês, maiores consumos e alertas.", size="2"),
                        rx.text("• Projetos: orçamento mensal, consumo e detalhamento por equipe.", size="2"),
                        rx.text("• Provedores: contas AWS, teste de conexão e sincronização.", size="2"),
                        rx.text("• Alertas: orçamento (70/90/100%), recursos sem projeto e falhas.", size="2"),
                        rx.text("• Usuários: gestão de acesso, restrita a administradores.", size="2"),
                        rx.text("Para corrigir a responsabilidade de um recurso, ajuste as tags na AWS e sincronize o provedor.", size="1", color=t.TEXT_MED),
                        spacing="1",
                        align="start",
                    ),
                    background=t.SURFACE,
                    padding="0.75rem",
                    border_radius="8px",
                    border=f"1px solid {t.BORDER_SUBTLE}",
                    width="100%",
                ),
                rx.hstack(
                    rx.dialog.close(
                        rx.button(
                            "Entendi",
                            on_click=UIState.fechar_help,
                            background=t.PRIMARY,
                            color=t.ON_PRIMARY,
                            font_weight="700",
                            _hover={"background": t.PRIMARY_HOVER},
                        )
                    ),
                    width="100%",
                    justify="end",
                ),
                spacing="4",
                width="100%",
            ),
            background=t.SURFACE_RAISED,
            border=f"1px solid {t.BORDER_SUBTLE}",
            color=t.TEXT_MAIN,
            max_width="440px",
        ),
        open=UIState.help_open,
    )


def app_shell(
    content: rx.Component,
    active: NavKey,
    search_value: Optional[rx.Var[str]] = None,
    on_search=None,
) -> rx.Component:
    """Envolve o conteúdo de uma página autenticada com sidebar + topbar."""
    return rx.fragment(
        _sidebar(active),
        _topbar(active, search_value, on_search),
        _settings_modal(),
        _help_modal(),
        rx.box(
            rx.cond(
                AuthState.validacao_pendente,
                rx.callout(
                    "Não foi possível validar a sessão agora (limite de requisições do servidor). "
                    "Recarregue a página em alguns segundos.",
                    icon="triangle-alert",
                    color_scheme="amber",
                    size="1",
                    margin="16px 32px 0",
                ),
                rx.fragment(),
            ),
            content,
            margin_left="256px",
            padding_top="64px",
            min_height="100vh",
            box_sizing="border-box",
            background=t.BG,
        ),
    )

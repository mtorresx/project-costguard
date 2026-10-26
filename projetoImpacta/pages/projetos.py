"""Página de Projetos ("/projetos") — dados reais do Xano.

Lista projetos do backend (api_group `app`). Controles de criar/editar/desativar
só aparecem para admin (ocultação é UX; a autorização real é no backend).
Não exibe custo consumido nem percentual de orçamento (não existem no backend).
"""

import reflex as rx

from .. import theme as t
from ..components.layout import app_shell
from ..state import AuthState
from .projetos_state import Projeto, ProjetosState


def _moeda(valor: rx.Var[float]) -> rx.Var[str]:
    return "US$ " + valor.to_string()


def _status_badge(status: rx.Var[str]) -> rx.Component:
    return rx.badge(
        status,
        color_scheme=rx.cond(status == "ativo", "green", "gray"),
        variant="soft",
    )


def _card(projeto: Projeto) -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.vstack(
                    rx.text(projeto["nome"], font_size="17px", font_weight="600", color=t.TEXT_HIGH),
                    rx.text("PRJ_" + projeto["codigo"], font_size="12px", color=t.TEXT_MED),
                    spacing="1",
                    align="start",
                ),
                rx.spacer(),
                _status_badge(projeto["status"]),
                width="100%",
                align="center",
            ),
            rx.box(
                rx.text("ORÇAMENTO MENSAL", font_size="11px", font_weight="600", color=t.TEXT_MED, letter_spacing="0.05em"),
                rx.text(_moeda(projeto["budget"]), font_size="28px", font_weight="700", color=t.TEXT_HIGH),
                margin_top="16px",
            ),
            rx.cond(
                AuthState.is_admin,
                rx.hstack(
                    rx.button(
                        rx.icon("pencil", size=14),
                        "Editar",
                        on_click=ProjetosState.abrir_editar(projeto).stop_propagation,
                        variant="soft",
                        color_scheme="gray",
                        size="1",
                    ),
                    rx.cond(
                        projeto["status"] == "ativo",
                        rx.button(
                            rx.icon("ban", size=14),
                            "Desativar",
                            on_click=ProjetosState.desativar(projeto["id"]).stop_propagation,
                            variant="soft",
                            color_scheme="red",
                            size="1",
                        ),
                        rx.fragment(),
                    ),
                    spacing="2",
                    margin_top="14px",
                ),
                rx.fragment(),
            ),
            rx.hstack(
                rx.text("Ver detalhamento", font_size="12px", color=t.TEXT_MED),
                rx.icon("arrow-right", size=13, color=t.TEXT_MED),
                spacing="1",
                align="center",
                justify="end",
                width="100%",
                margin_top="12px",
            ),
            align="start",
            width="100%",
        ),
        background=t.SURFACE,
        border=f"1px solid {t.BORDER_SUBTLE}",
        border_radius="14px",
        padding="22px",
        cursor="pointer",
        on_click=rx.redirect(f"/projetos/{projeto['id']}"),
        _hover={"box_shadow": "0 10px 28px rgba(0, 0, 0, 0.45)", "border_color": "rgba(20, 184, 166, 0.35)"},
        transition="all 0.2s ease",
        width="100%",
    )


def _campo(label: str, value, on_change, placeholder: str = "", tipo: str = "text", disabled=False) -> rx.Component:
    return rx.vstack(
        rx.text(label, size="2", weight="medium", color=t.TEXT_MED),
        rx.input(
            value=value,
            on_change=on_change,
            placeholder=placeholder,
            type=tipo,
            disabled=disabled,
            width="100%",
        ),
        spacing="1",
        width="100%",
        align="start",
    )


def _form_modal() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(
                rx.cond(ProjetosState.form_modo == "criar", "Novo projeto", "Editar projeto"),
                color=t.TEXT_HIGH,
            ),
            rx.vstack(
                _campo("Nome", ProjetosState.form_nome, ProjetosState.set_form_nome, "Ex.: Pagamentos"),
                _campo(
                    "Código (imutável após criação)",
                    ProjetosState.form_codigo,
                    ProjetosState.set_form_codigo,
                    "PAGAMENTOS",
                    disabled=ProjetosState.form_modo == "editar",
                ),
                _campo("Orçamento mensal (US$)", ProjetosState.form_budget, ProjetosState.set_form_budget, "10000", tipo="number"),
                rx.cond(
                    ProjetosState.form_error != "",
                    rx.callout(ProjetosState.form_error, color_scheme="red", size="1", width="100%"),
                    rx.fragment(),
                ),
                rx.hstack(
                    rx.dialog.close(rx.button("Cancelar", variant="soft", on_click=ProjetosState.fechar_form)),
                    rx.spacer(),
                    rx.button(
                        "Salvar",
                        on_click=ProjetosState.salvar,
                        loading=ProjetosState.form_loading,
                        background=t.PRIMARY,
                        color=t.ON_PRIMARY,
                        font_weight="700",
                        _hover={"background": t.PRIMARY_HOVER},
                    ),
                    width="100%",
                ),
                spacing="4",
                width="100%",
                margin_top="0.5rem",
            ),
            background=t.SURFACE_RAISED,
            border=f"1px solid {t.BORDER_SUBTLE}",
            color=t.TEXT_MAIN,
            max_width="440px",
        ),
        open=ProjetosState.form_aberto,
    )


def _conteudo() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.vstack(
                    rx.heading("Projetos", size="7", color=t.TEXT_HIGH),
                    rx.text("Orçamento mensal por projeto.", color=t.TEXT_MED, size="2"),
                    spacing="1",
                    align="start",
                ),
                rx.spacer(),
                rx.cond(
                    AuthState.is_admin,
                    rx.button(
                        rx.icon("plus", size=16),
                        "Novo projeto",
                        on_click=ProjetosState.abrir_criar,
                        background=t.PRIMARY,
                        color=t.ON_PRIMARY,
                        font_weight="700",
                        _hover={"background": t.PRIMARY_HOVER},
                    ),
                    rx.fragment(),
                ),
                width="100%",
                align="center",
            ),
            rx.cond(
                ProjetosState.error_message != "",
                rx.callout(ProjetosState.error_message, color_scheme="red", size="1", width="100%"),
                rx.fragment(),
            ),
            rx.cond(
                ProjetosState.loading,
                rx.center(rx.spinner(size="3"), padding_y="8"),
                rx.cond(
                    ProjetosState.projetos.length() > 0,
                    rx.grid(
                        rx.foreach(ProjetosState.projetos, _card),
                        columns=rx.breakpoints(initial="1", md="3"),
                        spacing="4",
                        width="100%",
                    ),
                    rx.center(
                        rx.text("Nenhum projeto cadastrado ainda.", color=t.TEXT_MED, size="3"),
                        padding_y="8",
                    ),
                ),
            ),
            _form_modal(),
            spacing="6",
            width="100%",
            max_width="1100px",
        ),
        padding=["24px", "32px", "48px"],
        width="100%",
    )


def projetos_page() -> rx.Component:
    return app_shell(_conteudo(), active="projetos")

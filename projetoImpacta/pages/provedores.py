"""Página de Provedores ("/provedores") — dados reais do Xano.

Lista provedores do backend (api_group `app`). Controles de cadastrar/editar/
testar/desativar só aparecem para admin (ocultação é UX; a autorização real é no
backend). O segredo da credencial nunca é reexibido: o campo começa vazio e, na
edição, deixá-lo vazio preserva o segredo salvo.
"""

import reflex as rx

from .. import theme as t
from ..components.layout import app_shell
from ..components.pill import pill
from ..components.tabela import th
from ..state import AuthState
from .provedores_state import Provedor, ProvedoresState


def _status_pill(status: rx.Var[str]) -> rx.Component:
    return rx.match(
        status,
        ("ok", pill("Conectado", t.SUCCESS, "rgba(34,197,94,0.1)", "rgba(34,197,94,0.3)")),
        ("erro", pill("Com erro", t.WARNING, "rgba(245,158,11,0.1)", "rgba(245,158,11,0.3)")),
        ("pendente", pill("Pendente", t.TEXT_MED, "rgba(148,163,184,0.1)", "rgba(148,163,184,0.3)")),
        ("inativo", pill("Inativo", t.TEXT_MED, "rgba(148,163,184,0.1)", "rgba(148,163,184,0.3)")),
        pill("—", t.TEXT_MED, "rgba(148,163,184,0.1)", "rgba(148,163,184,0.3)"),
    )


def _acoes_admin(p: Provedor) -> rx.Component:
    return rx.hstack(
        rx.button(
            rx.icon("plug-zap", size=14),
            "Testar",
            on_click=ProvedoresState.testar_conexao(p["id"]),
            loading=ProvedoresState.testando_id == p["id"],
            variant="soft",
            color_scheme="teal",
            size="1",
        ),
        rx.button(
            rx.icon("pencil", size=14),
            "Editar",
            on_click=ProvedoresState.abrir_editar(p),
            variant="soft",
            color_scheme="gray",
            size="1",
        ),
        rx.cond(
            p["status"] != "inativo",
            rx.button(
                rx.icon("ban", size=14),
                "Desativar",
                on_click=ProvedoresState.desativar(p["id"]),
                variant="soft",
                color_scheme="red",
                size="1",
            ),
            rx.fragment(),
        ),
        spacing="2",
    )


def _linha(p: Provedor) -> rx.Component:
    return rx.table.row(
        rx.table.cell(p["apelido"], color=t.TEXT_HIGH),
        rx.table.cell(rx.text("AWS", text_transform="uppercase"), color=t.TEXT_MED),
        rx.table.cell(p["identificador_conta"], color=t.TEXT_MED, font_family="monospace"),
        rx.table.cell(_status_pill(p["status"])),
        rx.table.cell(
            rx.cond(AuthState.is_admin, _acoes_admin(p), rx.fragment()),
        ),
    )


def _campo(label: str, value, on_change, placeholder: str = "", tipo: str = "text") -> rx.Component:
    return rx.vstack(
        rx.text(label, size="2", weight="medium", color=t.TEXT_MED),
        rx.input(
            value=value,
            on_change=on_change,
            placeholder=placeholder,
            type=tipo,
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
                rx.cond(ProvedoresState.form_modo == "criar", "Novo provedor AWS", "Editar provedor AWS"),
                color=t.TEXT_HIGH,
            ),
            rx.vstack(
                _campo("Apelido", ProvedoresState.form_apelido, ProvedoresState.set_form_apelido, "Ex.: AWS Produção"),
                _campo(
                    "Identificador da conta (AWS Account ID)",
                    ProvedoresState.form_identificador_conta,
                    ProvedoresState.set_form_identificador_conta,
                    "123456789012",
                ),
                _campo(
                    "AWS Access Key ID",
                    ProvedoresState.form_access_key_id,
                    ProvedoresState.set_form_access_key_id,
                    rx.cond(
                        ProvedoresState.form_modo == "editar",
                        "Deixe em branco para manter o atual",
                        "AKIA...",
                    ),
                ),
                _campo(
                    "AWS Secret Access Key",
                    ProvedoresState.form_secret_access_key,
                    ProvedoresState.set_form_secret_access_key,
                    rx.cond(
                        ProvedoresState.form_modo == "editar",
                        "Deixe em branco para manter o atual",
                        "Nunca é exibido após salvo",
                    ),
                    tipo="password",
                ),
                rx.text(
                    "Use uma credencial IAM dedicada, somente leitura. O segredo é "
                    "armazenado cifrado e nunca é reexibido após salvo.",
                    size="1",
                    color=t.TEXT_MED,
                ),
                rx.cond(
                    ProvedoresState.form_error != "",
                    rx.callout(ProvedoresState.form_error, color_scheme="red", size="1", width="100%"),
                    rx.fragment(),
                ),
                rx.hstack(
                    rx.dialog.close(rx.button("Cancelar", variant="soft", on_click=ProvedoresState.fechar_form)),
                    rx.spacer(),
                    rx.button(
                        "Salvar",
                        on_click=ProvedoresState.salvar,
                        loading=ProvedoresState.form_loading,
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
            max_width="460px",
        ),
        open=ProvedoresState.form_aberto,
    )


def _conteudo() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.vstack(
                    rx.heading("Provedores", size="7", color=t.TEXT_HIGH),
                    rx.text("Contas de nuvem conectadas (AWS).", color=t.TEXT_MED, size="2"),
                    spacing="1",
                    align="start",
                ),
                rx.spacer(),
                rx.cond(
                    AuthState.is_admin,
                    rx.button(
                        rx.icon("plus", size=16),
                        "Novo provedor",
                        on_click=ProvedoresState.abrir_criar,
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
                ProvedoresState.error_message != "",
                rx.callout(ProvedoresState.error_message, color_scheme="red", size="1", width="100%"),
                rx.fragment(),
            ),
            rx.cond(
                ProvedoresState.loading,
                rx.center(rx.spinner(size="3"), padding_y="8"),
                rx.cond(
                    ProvedoresState.provedores.length() > 0,
                    rx.box(
                        rx.table.root(
                            rx.table.header(
                                rx.table.row(
                                    th("Apelido"),
                                    th("Tipo"),
                                    th("Conta"),
                                    th("Status"),
                                    th("Ações"),
                                ),
                            ),
                            rx.table.body(rx.foreach(ProvedoresState.provedores, _linha)),
                            variant="surface",
                            width="100%",
                        ),
                        background=t.SURFACE,
                        border=f"1px solid {t.BORDER_SUBTLE}",
                        border_radius="14px",
                        padding="8px",
                        width="100%",
                    ),
                    rx.center(
                        rx.text("Nenhum provedor cadastrado ainda.", color=t.TEXT_MED, size="3"),
                        padding_y="8",
                    ),
                ),
            ),
            _form_modal(),
            spacing="6",
            width="100%",
            max_width="1000px",
        ),
        padding=["24px", "32px", "48px"],
        width="100%",
    )


def provedores_page() -> rx.Component:
    return app_shell(_conteudo(), active="provedores")

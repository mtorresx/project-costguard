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
from .descoberta_state import DescobertaState, ProjetoDescoberto
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
        rx.cond(
            p["tipo"] == "aws",
            rx.button(
                rx.icon("search", size=14),
                "Descobrir projetos",
                on_click=DescobertaState.abrir(p),
                variant="soft",
                color_scheme="teal",
                size="1",
            ),
            rx.fragment(),
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
        rx.table.cell(
            rx.hstack(
                rx.text(p["apelido"], color=t.TEXT_HIGH),
                rx.cond(
                    p["usar_mock"],
                    pill("Mock", t.TEXT_MED, "rgba(148,163,184,0.1)", "rgba(148,163,184,0.3)"),
                    rx.fragment(),
                ),
                spacing="2",
                align="center",
            ),
        ),
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
                rx.checkbox(
                    "Usar ambiente AWS Mock",
                    checked=ProvedoresState.form_usar_mock,
                    on_change=ProvedoresState.set_form_usar_mock,
                    color_scheme="teal",
                    size="2",
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


def _linha_descoberto(d: ProjetoDescoberto) -> rx.Component:
    return rx.hstack(
        rx.cond(
            d["existente"],
            # Existente: sem checkbox, apenas um espaço reservado para alinhar.
            rx.box(width="20px", height="20px"),
            rx.checkbox(
                checked=DescobertaState.selecionados.contains(d["codigo"]),
                on_change=DescobertaState.toggle_codigo(d["codigo"]),
                color_scheme="teal",
            ),
        ),
        rx.text(d["codigo"], color=t.TEXT_HIGH, font_family="monospace", size="2"),
        rx.spacer(),
        rx.cond(
            d["existente"],
            pill("Já existe", t.TEXT_MED, "rgba(148,163,184,0.1)", "rgba(148,163,184,0.3)"),
            pill("Novo", t.PRIMARY_ACCENT, "rgba(20,184,166,0.12)", "rgba(20,184,166,0.35)"),
        ),
        align="center",
        width="100%",
        padding_y="8px",
        padding_x="10px",
        border_bottom=f"1px solid {t.BORDER_SUBTLE}",
        spacing="3",
    )


def _descoberta_corpo() -> rx.Component:
    return rx.cond(
        DescobertaState.loading_descoberta,
        rx.center(rx.spinner(size="3"), padding_y="8"),
        rx.cond(
            DescobertaState.descobertos.length() > 0,
            rx.vstack(
                rx.hstack(
                    rx.text(
                        "Tag Key: ",
                        rx.text.span(DescobertaState.tag_key, font_family="monospace", color=t.TEXT_HIGH),
                        size="1",
                        color=t.TEXT_MED,
                    ),
                    rx.spacer(),
                    rx.cond(
                        DescobertaState.tem_novos,
                        rx.button(
                            "Selecionar todos os novos",
                            on_click=DescobertaState.selecionar_todos_novos,
                            variant="ghost",
                            color_scheme="teal",
                            size="1",
                            disabled=DescobertaState.todos_novos_selecionados,
                        ),
                        rx.fragment(),
                    ),
                    width="100%",
                    align="center",
                ),
                rx.box(
                    rx.foreach(DescobertaState.descobertos, _linha_descoberto),
                    width="100%",
                    max_height="320px",
                    overflow_y="auto",
                    border=f"1px solid {t.BORDER_SUBTLE}",
                    border_radius="10px",
                ),
                spacing="2",
                width="100%",
            ),
            rx.center(
                rx.text("Nenhum projeto descoberto para este provedor.", color=t.TEXT_MED, size="2"),
                padding_y="8",
            ),
        ),
    )


def _descoberta_modal() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(
                rx.hstack(
                    rx.text("Descobrir projetos", color=t.TEXT_HIGH),
                    rx.text.span(DescobertaState.provedor_apelido, color=t.TEXT_MED, size="2"),
                    spacing="2",
                    align="baseline",
                ),
            ),
            rx.vstack(
                rx.text(
                    "Projetos encontrados nas tags do provedor. Selecione os novos para importar.",
                    size="1",
                    color=t.TEXT_MED,
                ),
                rx.cond(
                    DescobertaState.mensagem_sucesso != "",
                    rx.callout(DescobertaState.mensagem_sucesso, color_scheme="green", size="1", width="100%"),
                    rx.fragment(),
                ),
                rx.cond(
                    DescobertaState.erro != "",
                    rx.callout(DescobertaState.erro, color_scheme="red", size="1", width="100%"),
                    rx.fragment(),
                ),
                _descoberta_corpo(),
                rx.hstack(
                    rx.dialog.close(
                        rx.button("Fechar", variant="soft", on_click=DescobertaState.fechar),
                    ),
                    rx.spacer(),
                    rx.button(
                        rx.icon("download", size=14),
                        rx.cond(
                            DescobertaState.total_selecionados > 0,
                            rx.text("Importar selecionados (", DescobertaState.total_selecionados, ")"),
                            rx.text("Importar selecionados"),
                        ),
                        on_click=DescobertaState.importar,
                        loading=DescobertaState.loading_importacao,
                        disabled=~DescobertaState.pode_importar,
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
            max_width="560px",
        ),
        open=DescobertaState.aberto,
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
            _descoberta_modal(),
            spacing="6",
            width="100%",
            max_width="1000px",
        ),
        padding=["24px", "32px", "48px"],
        width="100%",
    )


def provedores_page() -> rx.Component:
    return app_shell(_conteudo(), active="provedores")

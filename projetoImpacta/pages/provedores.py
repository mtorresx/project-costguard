"""Página de Provedores ("/provedores") — dados reais do Xano.

Lista provedores do backend (api_group `app`). Controles de cadastrar/editar/
testar/desativar só aparecem para admin (ocultação é UX; a autorização real é no
backend). O segredo da credencial nunca é reexibido: o campo começa vazio e, na
edição, deixá-lo vazio preserva o segredo salvo.
"""

import reflex as rx

from .. import theme as t
from ..components.mensagens import aviso_fechavel
from ..components.layout import app_shell
from ..components.pill import pill
from ..components.tabela import th
from ..state import AuthState
from .azure_state import AzureState
from .descoberta_state import DescobertaState, ProjetoDescoberto
from .provedores_state import CAMPOS_AZURE, Provedor, ProvedoresState
from .sincronizacao_state import Etapa, SincronizacaoState


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
        rx.cond(
            p["status"] == "ok",
            rx.button(
                rx.icon("refresh-cw", size=14),
                "Sincronizar agora",
                on_click=SincronizacaoState.sincronizar(p["id"], p["apelido"]),
                loading=SincronizacaoState.executando & (SincronizacaoState.provedor_id == p["id"]),
                disabled=SincronizacaoState.executando,
                variant="solid",
                color_scheme="teal",
                size="1",
            ),
            rx.fragment(),
        ),
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
        # Em telas de ~1440 px os cinco botões não cabem numa linha: quebram em vez de sair cortados.
        flex_wrap="wrap",
        min_width="280px",
    )


def _sincronizacao(p: Provedor) -> rx.Component:
    """Estado do inventário: "Sincronizado há X min" ou o erro, com a última sincronização boa."""
    return rx.cond(
        p["sinc_erro"] != "",
        rx.vstack(
            rx.hstack(
                rx.icon("triangle-alert", size=14, color=t.ERROR),
                rx.text(p["sinc_erro"], font_size="12px", color=t.ERROR, font_weight="600"),
                spacing="1",
                align="start",
            ),
            rx.text(p["sinc_ultima_boa"], font_size="11px", color=t.TEXT_MED),
            spacing="1",
            align="start",
            max_width="360px",
        ),
        rx.text(p["sinc_texto"], font_size="12px", color=t.TEXT_MED),
    )


def _linha(p: Provedor) -> rx.Component:
    return rx.table.row(
        rx.table.cell(
            rx.text(p["apelido"], color=t.TEXT_HIGH),
        ),
        rx.table.cell(rx.text("AWS", text_transform="uppercase"), color=t.TEXT_MED),
        rx.table.cell(p["conta_mascarada"], color=t.TEXT_MED, font_family="monospace"),
        rx.table.cell(_status_pill(p["status"])),
        rx.table.cell(_sincronizacao(p)),
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


def _form_aws() -> rx.Component:
    return rx.vstack(
        _campo("Apelido", ProvedoresState.form_apelido, ProvedoresState.set_form_apelido, "Ex.: AWS Produção"),
        _campo(
            "Identificador da conta (AWS Account ID)",
            ProvedoresState.form_identificador_conta,
            ProvedoresState.set_form_identificador_conta,
            "123456789012",
        ),
        _campo(
            "Tag Key de projeto",
            ProvedoresState.form_tag_projeto,
            ProvedoresState.set_form_tag_projeto,
            "PRJ",
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
        rx.cond(
            ProvedoresState.form_modo == "editar",
            rx.text(
                "Use uma credencial IAM dedicada, somente leitura. O segredo é "
                "armazenado cifrado e nunca é reexibido após salvo.",
                size="1", color=t.TEXT_MED,
            ),
        ),
        rx.cond(
            ProvedoresState.form_error != "",
            aviso_fechavel(ProvedoresState.form_error),
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
    )


def _form_azure() -> rx.Component:
    return rx.vstack(
        rx.el.form(
            rx.vstack(
                rx.el.label(
                    "Apelido",
                    rx.input(name="apelido", placeholder="Ex.: Azure Corporativo",
                             disabled=ProvedoresState.form_loading, width="100%"),
                    width="100%", font_size="14px",
                ),
                *(
                    rx.el.label(
                        titulo,
                        rx.el.input(
                            name=campo, type="password", auto_complete="off",
                            placeholder=("Nunca é exibido após salvo" if campo == "client_secret"
                                         else "00000000-0000-0000-0000-000000000000"),
                            disabled=ProvedoresState.form_loading, width="100%",
                            display="block", padding="8px", margin_top="4px",
                            background=t.INPUT_BG, border=f"1px solid {t.BORDER_SUBTLE}",
                            border_radius="6px", style={"&::-ms-reveal": {"display": "none"},
                                                       "&::placeholder": {"color": "var(--gray-a10)"}},
                        ),
                        width="100%", font_size="14px",
                    )
                    for campo, titulo in CAMPOS_AZURE
                ),
                rx.flex(
                    rx.button("Cancelar", type="button", variant="soft", on_click=ProvedoresState.fechar_form),
                    rx.button("Conectar", type="submit", loading=ProvedoresState.form_loading),
                    justify="between", width="100%",
                ),
                align="start", spacing="3", width="100%",
            ),
            method="post", on_submit=ProvedoresState.conectar_azure, reset_on_submit=True,
            key=ProvedoresState.versao_form_azure, auto_complete="off", width="100%",
        ),
        rx.cond(ProvedoresState.form_error != "", aviso_fechavel(ProvedoresState.form_error)),
        align="start", spacing="3", width="100%",
    )


def _form_modal() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(
                rx.cond(ProvedoresState.form_modo == "criar", "Novo provedor", "Editar provedor AWS"),
                color=t.TEXT_HIGH,
            ),
            rx.vstack(
                rx.cond(
                    ProvedoresState.form_modo == "criar",
                    rx.vstack(
                        rx.el.label("Provedor", html_for="tipo-provedor"),
                        rx.select.root(
                            rx.select.trigger(id="tipo-provedor", width="100%"),
                            rx.select.content(
                                rx.select.group(rx.select.item("AWS", value="AWS"), rx.select.item("Azure", value="Azure")),
                                position="popper", side="bottom", side_offset=4,
                                custom_attrs={"avoidCollisions": False}, max_height="6rem",
                            ),
                            value=ProvedoresState.form_provedor, on_change=ProvedoresState.selecionar_provedor,
                        ),
                        align="start", width="100%", spacing="1",
                        style={"&:has([aria-expanded=true])": {"padding_bottom": "calc(6rem + 4px)"}},
                    ),
                ),
                rx.cond(ProvedoresState.form_provedor == "Azure", _form_azure(), _form_aws()),
                width="100%", align="stretch", spacing="3",
            ),
            background=t.SURFACE_RAISED,
            border=f"1px solid {t.BORDER_SUBTLE}",
            color=t.TEXT_MAIN,
            max_width="460px",
        ),
        open=ProvedoresState.form_aberto, on_open_change=ProvedoresState.alterar_abertura,
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


def _icone_etapa(e: Etapa) -> rx.Component:
    return rx.match(
        e["estado"],
        ("executando", rx.spinner(size="2")),
        ("sucesso", rx.icon("circle-check", size=18, color=t.SUCCESS)),
        ("aviso", rx.icon("triangle-alert", size=18, color=t.WARNING)),
        ("ocupado", rx.icon("info", size=18, color=t.PRIMARY_ACCENT)),
        ("erro", rx.icon("circle-x", size=18, color=t.ERROR)),
        rx.icon("circle-dashed", size=18, color=t.TEXT_LOW),
    )


def _linha_etapa(e: Etapa) -> rx.Component:
    return rx.hstack(
        rx.box(_icone_etapa(e), padding_top="2px", flex_shrink="0"),
        rx.vstack(
            rx.text(e["nome"], size="2", weight="bold", color=t.TEXT_HIGH),
            rx.cond(
                e["mensagem"] != "",
                rx.text(
                    e["mensagem"],
                    size="1",
                    color=rx.match(e["estado"], ("erro", t.ERROR), ("aviso", t.WARNING), t.TEXT_MED),
                ),
                rx.fragment(),
            ),
            spacing="1",
            align="start",
        ),
        spacing="3",
        align="start",
        width="100%",
        padding="12px",
        border_radius="10px",
        background=t.SURFACE,
        border=f"1px solid {t.BORDER_SUBTLE}",
    )


def _sincronizacao_modal() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(
                rx.hstack(
                    rx.icon("refresh-cw", size=18, color=t.PRIMARY_ACCENT),
                    rx.text("Sincronizar ", SincronizacaoState.provedor_nome),
                    spacing="2",
                    align="center",
                ),
                color=t.TEXT_HIGH,
            ),
            rx.dialog.description(
                "Importa o inventário e os custos por equipe do provedor e avalia os alertas.",
                size="2",
                color=t.TEXT_MED,
            ),
            rx.vstack(
                rx.foreach(SincronizacaoState.etapas, _linha_etapa),
                rx.cond(
                    ~SincronizacaoState.executando & SincronizacaoState.concluida_com_falha,
                    aviso_fechavel("Uma ou mais etapas falharam. A falha fica registrada e aparece em Alertas."),
                    rx.fragment(),
                ),
                rx.hstack(
                    rx.spacer(),
                    rx.button(
                        rx.cond(SincronizacaoState.executando, "Sincronizando...", "Fechar"),
                        on_click=[SincronizacaoState.fechar, ProvedoresState.carregar(False)],
                        disabled=SincronizacaoState.executando,
                        variant="soft",
                    ),
                    width="100%",
                ),
                spacing="3",
                width="100%",
                margin_top="0.75rem",
            ),
            background=t.SURFACE_RAISED,
            border=f"1px solid {t.BORDER_SUBTLE}",
            color=t.TEXT_MAIN,
            max_width="480px",
        ),
        open=SincronizacaoState.aberto,
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
                    DescobertaState.erro != "",
                    aviso_fechavel(DescobertaState.erro),
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


def _desconectar_azure() -> rx.Component:
    return rx.alert_dialog.root(
        rx.alert_dialog.trigger(
            rx.button("Desconectar", variant="soft", color_scheme="red", size="1",
                      disabled=AzureState.sincronizando | AzureState.desconectando),
        ),
        rx.alert_dialog.content(
            rx.alert_dialog.title("Desconectar do Azure?"),
            rx.alert_dialog.description("As credenciais cadastradas nesta tela serão removidas."),
            rx.flex(
                rx.alert_dialog.cancel(rx.button("Cancelar", variant="soft")),
                rx.alert_dialog.action(
                    rx.button("Confirmar desconexão", on_click=AzureState.desconectar, color_scheme="red"),
                ),
                justify="end", gap="3", margin_top="16px",
            ),
        ),
    )


def _linha_azure() -> rx.Component:
    return rx.table.row(
        rx.table.cell(rx.text(AzureState.apelido, color=t.TEXT_HIGH)),
        rx.table.cell(rx.text("Azure"), color=t.TEXT_MED),
        rx.table.cell(AzureState.conta_mascarada, color=t.TEXT_MED, font_family="monospace"),
        rx.table.cell(_status_pill("ok")),
        rx.table.cell(
            rx.vstack(
                rx.cond(AzureState.titulo != "Conectado ao Azure", rx.text(AzureState.titulo)),
                rx.cond(AzureState.detalhe != "", rx.text(AzureState.detalhe)),
                rx.cond(AzureState.ultima_leitura != "", rx.text("Última leitura: ", AzureState.ultima_leitura)),
                align="start", spacing="1", color=t.TEXT_MED, font_size="12px",
            ),
        ),
        rx.table.cell(rx.cond(AuthState.is_admin, rx.vstack(
            rx.flex(
                rx.button(
                    rx.icon("refresh-cw", size=14), "Sincronizar agora", on_click=AzureState.sincronizar,
                    loading=AzureState.sincronizando,
                    disabled=AzureState.carregando | AzureState.sincronizando | (AzureState.segundos > 0),
                    variant="solid", color_scheme="teal", size="1",
                ),
                rx.cond(AzureState.origem == "tela", _desconectar_azure()),
                gap="2", wrap="wrap",
            ),
            rx.cond(AzureState.segundos > 0, rx.text("Sincronizar novamente em ", AzureState.segundos, " s.", size="1")),
            rx.cond(AzureState.aviso != "", aviso_fechavel(AzureState.aviso)),
            align="start", spacing="1",
        ))),
    )


def _conteudo() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.vstack(
                    rx.heading("Provedores", size="7", color=t.TEXT_HIGH),
                    rx.text("Contas de nuvem conectadas.", color=t.TEXT_MED, size="2"),
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
                aviso_fechavel(ProvedoresState.error_message),
                rx.fragment(),
            ),
            rx.cond(
                ProvedoresState.falha_teste != "",
                aviso_fechavel(ProvedoresState.falha_teste),
                rx.fragment(),
            ),
            rx.cond(
                (ProvedoresState.loading | AzureState.carregando) & (ProvedoresState.provedores.length() == 0) & ~AzureState.conectado,
                rx.center(rx.spinner(size="3"), padding_y="8"),
                rx.cond(
                    (ProvedoresState.provedores.length() > 0) | AzureState.conectado,
                    rx.box(
                        rx.table.root(
                            rx.table.header(
                                rx.table.row(
                                    th("Apelido"),
                                    th("Tipo"),
                                    th("Conta"),
                                    th("Status"),
                                    th("Inventário"),
                                    th("Ações"),
                                ),
                            ),
                            rx.table.body(
                                rx.foreach(ProvedoresState.provedores, _linha),
                                rx.cond(AzureState.conectado, _linha_azure()),
                            ),
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
            rx.cond(~AzureState.conectado & ~AzureState.carregando & (AzureState.erro_leitura != ""),
                    aviso_fechavel(AzureState.erro_leitura)),
            _form_modal(),
            _descoberta_modal(),
            _sincronizacao_modal(),
            spacing="6",
            width="100%",
            max_width="1280px",
        ),
        padding=["24px", "32px", "48px"],
        width="100%",
    )


def provedores_page() -> rx.Component:
    return app_shell(_conteudo(), active="provedores")

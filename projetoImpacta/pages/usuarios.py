"""Página de Usuários ("/usuarios") — gestão de usuários com dados reais do Xano.

Design adaptado do frontend original de referência
(KPIs, tabela com avatar, pill de papel, indicador de status). Restrita a admin:
o backend responde 403 para os demais e a página mostra o aviso de acesso restrito.
"""

import reflex as rx

from .. import theme as t
from ..components.mensagens import aviso_fechavel
from ..components.layout import app_shell
from ..components.pill import pill
from ..state import AuthState
from .usuarios_state import ACESSO_RESTRITO, Usuario, UsuariosState


def _campo(label: str, value, on_change, placeholder: str = "", tipo: str = "text", disabled=False, ajuda: str = "") -> rx.Component:
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
        rx.text(ajuda, size="1", color=t.TEXT_LOW) if not (isinstance(ajuda, str) and ajuda == "") else rx.fragment(),
        spacing="1",
        width="100%",
        align="start",
    )


def _botao_primario(texto: str, on_click, loading=False) -> rx.Component:
    return rx.button(
        texto,
        on_click=on_click,
        loading=loading,
        background=t.PRIMARY,
        color=t.ON_PRIMARY,
        font_weight="700",
        _hover={"background": t.PRIMARY_HOVER},
    )


def _form_modal() -> rx.Component:
    criando = UsuariosState.form_modo == "criar"
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(rx.cond(criando, "Novo usuário", "Editar usuário"), color=t.TEXT_HIGH),
            rx.dialog.description(
                "O login usa o nome de usuário; o e-mail é o canal de contato.",
                size="2",
                color=t.TEXT_MED,
            ),
            rx.vstack(
                _campo("Nome completo", UsuariosState.form_nome, UsuariosState.set_form_nome, "Marina Souza"),
                _campo(
                    "Nome de usuário (login)",
                    UsuariosState.form_username,
                    UsuariosState.set_form_username,
                    "marina.souza",
                    disabled=~criando,
                    ajuda=rx.cond(criando, "Sem espaços. Não pode ser alterado depois.", "Não pode ser alterado."),
                ),
                _campo("E-mail", UsuariosState.form_email, UsuariosState.set_form_email, "usuario@exemplo.com", tipo="email"),
                rx.vstack(
                    rx.text("Papel", size="2", weight="medium", color=t.TEXT_MED),
                    rx.select.root(
                        rx.select.trigger(width="100%"),
                        rx.select.content(
                            rx.select.item("Leitura — somente consulta", value="leitura"),
                            rx.select.item("Administrador", value="admin"),
                        ),
                        value=UsuariosState.form_role,
                        on_change=UsuariosState.set_form_role,
                    ),
                    spacing="1",
                    width="100%",
                    align="start",
                ),
                rx.cond(
                    criando,
                    _campo(
                        "Senha inicial",
                        UsuariosState.form_senha,
                        UsuariosState.set_form_senha,
                        "mínimo de 8 caracteres",
                        tipo="password",
                        ajuda="Informe a senha ao usuário por um canal seguro.",
                    ),
                    rx.fragment(),
                ),
                rx.cond(
                    UsuariosState.form_error != "",
                    aviso_fechavel(UsuariosState.form_error),
                    rx.fragment(),
                ),
                rx.hstack(
                    rx.dialog.close(rx.button("Cancelar", variant="soft", on_click=UsuariosState.fechar_form)),
                    rx.spacer(),
                    _botao_primario(
                        rx.cond(criando, "Criar usuário", "Salvar"),
                        UsuariosState.salvar,
                        UsuariosState.form_loading,
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
        open=UsuariosState.form_aberto,
    )


def _senha_modal() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("Definir nova senha", color=t.TEXT_HIGH),
            rx.dialog.description(
                rx.text("Usuário: ", rx.text(UsuariosState.senha_nome, as_="span", weight="bold")),
                size="2",
                color=t.TEXT_MED,
            ),
            rx.vstack(
                _campo(
                    "Nova senha",
                    UsuariosState.senha_valor,
                    UsuariosState.set_senha_valor,
                    "mínimo de 8 caracteres",
                    tipo="password",
                    ajuda="A senha anterior deixa de funcionar imediatamente.",
                ),
                rx.cond(
                    UsuariosState.senha_error != "",
                    aviso_fechavel(UsuariosState.senha_error),
                    rx.fragment(),
                ),
                rx.hstack(
                    rx.dialog.close(rx.button("Cancelar", variant="soft", on_click=UsuariosState.fechar_senha)),
                    rx.spacer(),
                    _botao_primario("Definir senha", UsuariosState.salvar_senha, UsuariosState.senha_loading),
                    width="100%",
                ),
                spacing="4",
                width="100%",
                margin_top="0.5rem",
            ),
            background=t.SURFACE_RAISED,
            border=f"1px solid {t.BORDER_SUBTLE}",
            color=t.TEXT_MAIN,
            max_width="420px",
        ),
        open=UsuariosState.senha_aberto,
    )


def _kpi(icone: str, rotulo: str, valor) -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.text(rotulo.upper(), font_size="11px", font_weight="600", color=t.TEXT_MED, letter_spacing="0.05em"),
            rx.spacer(),
            rx.icon(icone, size=18, color=t.TEXT_MED),
            width="100%",
        ),
        rx.text(valor, font_size="28px", font_weight="700", color=t.TEXT_HIGH),
        align="start",
        spacing="2",
        width="100%",
        background=t.SURFACE,
        border=f"1px solid {t.BORDER_SUBTLE}",
        border_radius="12px",
        padding="20px",
    )


def _role_pill(role) -> rx.Component:
    return rx.cond(
        role == "admin",
        pill("Administrador", "#f87171", "rgba(239, 68, 68, 0.15)", "rgba(239, 68, 68, 0.4)"),
        pill("Leitura", t.TEXT_MED, "rgba(148, 163, 184, 0.12)", "rgba(148, 163, 184, 0.3)"),
    )


def _status(status) -> rx.Component:
    ativo = status == "ativo"
    return rx.hstack(
        rx.box(width="8px", height="8px", border_radius="50%", background=rx.cond(ativo, t.SUCCESS, t.TEXT_LOW)),
        rx.text(
            rx.cond(ativo, "Ativo", "Inativo"),
            font_size="13px",
            font_weight="600",
            color=rx.cond(ativo, t.SUCCESS, t.TEXT_LOW),
        ),
        spacing="2",
        align="center",
    )


def _acao(icone: str, dica: str, on_click, cor_hover: str = t.TEXT_HIGH) -> rx.Component:
    return rx.tooltip(
        rx.icon_button(
            rx.icon(icone, size=18),
            on_click=on_click,
            aria_label=dica,
            variant="ghost",
            color=t.TEXT_MED,
            cursor="pointer",
            _hover={"color": cor_hover, "background": t.NAV_HOVER_BG},
        ),
        content=dica,
    )


_CELULA = {"padding_x": "20px", "padding_y": "14px", "vertical_align": "middle"}


def _linha(u: Usuario) -> rx.Component:
    eh_eu = u["username"] == AuthState.username
    return rx.table.row(
        rx.table.cell(
            rx.hstack(
                rx.center(
                    rx.text(u["iniciais"], font_size="13px", font_weight="700", color=t.PRIMARY_ACCENT),
                    width="40px",
                    height="40px",
                    border_radius="50%",
                    background="rgba(20, 184, 166, 0.12)",
                    border="1px solid rgba(20, 184, 166, 0.3)",
                    flex_shrink="0",
                ),
                rx.vstack(
                    rx.hstack(
                        rx.text(u["nome"], font_size="15px", font_weight="700", color=t.TEXT_HIGH),
                        rx.cond(eh_eu, rx.badge("você", color_scheme="teal", variant="soft", size="1"), rx.fragment()),
                        spacing="2",
                        align="center",
                    ),
                    rx.text(u["username"], font_size="12px", font_family="monospace", color=t.TEXT_MED),
                    spacing="0",
                    align="start",
                ),
                spacing="3",
                align="center",
            ),
            **_CELULA,
        ),
        rx.table.cell(rx.text(u["email"], font_size="13px", color=t.TEXT_MED), **_CELULA),
        rx.table.cell(_role_pill(u["role"]), **_CELULA),
        rx.table.cell(_status(u["status"]), **_CELULA),
        rx.table.cell(
            rx.hstack(
                _acao("pencil", "Editar", UsuariosState.abrir_editar(u)),
                _acao("key-round", "Definir nova senha", UsuariosState.abrir_senha(u)),
                rx.cond(
                    eh_eu,
                    rx.box(width="32px"),
                    rx.cond(
                        u["status"] == "ativo",
                        _acao("user-minus", "Desativar usuário", UsuariosState.alternar_status(u), t.ERROR),
                        _acao("user-check", "Reativar usuário", UsuariosState.alternar_status(u), t.SUCCESS),
                    ),
                ),
                spacing="1",
                justify="end",
                width="100%",
            ),
            **_CELULA,
        ),
        _hover={"background": "rgba(255, 255, 255, 0.02)"},
    )


def _th(texto: str, alinhamento: str = "left") -> rx.Component:
    return rx.table.column_header_cell(
        texto,
        text_align=alinhamento,
        padding_x="20px",
        padding_y="14px",
        font_size="11px",
        font_weight="600",
        letter_spacing="0.05em",
        color=t.TEXT_MED,
        background="rgba(11, 19, 38, 0.6)",
    )


def _tabela() -> rx.Component:
    return rx.cond(
        UsuariosState.usuarios_filtrados.length() > 0,
        rx.box(
            rx.table.root(
                rx.table.header(
                    rx.table.row(_th("USUÁRIO"), _th("E-MAIL"), _th("PAPEL"), _th("STATUS"), _th("AÇÕES", "right")),
                ),
                rx.table.body(rx.foreach(UsuariosState.usuarios_filtrados, _linha)),
                variant="ghost",
                width="100%",
            ),
            width="100%",
            overflow_x="auto",
            background=t.SURFACE,
            border=f"1px solid {t.BORDER_SUBTLE}",
            border_radius="12px",
        ),
        rx.center(
            rx.text(
                rx.cond(
                    UsuariosState.usuarios.length() > 0,
                    "Nenhum usuário encontrado para essa busca.",
                    "Nenhum usuário cadastrado.",
                ),
                color=t.TEXT_MED,
                size="3",
            ),
            padding_y="8",
        ),
    )


def _acesso_restrito() -> rx.Component:
    return rx.callout(ACESSO_RESTRITO, icon="lock", color_scheme="amber", size="2", width="100%")


def _conteudo() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.vstack(
                    rx.heading("Usuários & Acessos", size="7", color=t.TEXT_HIGH),
                    rx.text(
                        "Controle de acesso por papel: administradores gerenciam, leitura apenas consulta.",
                        color=t.TEXT_MED,
                        font_size="14px",
                    ),
                    spacing="1",
                    align="start",
                ),
                rx.spacer(),
                rx.cond(
                    AuthState.is_admin & ~UsuariosState.acesso_negado,
                    rx.button(
                        rx.icon("user-plus", size=16),
                        "Novo usuário",
                        on_click=UsuariosState.abrir_criar,
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
                UsuariosState.acesso_negado,
                _acesso_restrito(),
                rx.vstack(
                    rx.box(
                        _kpi("users", "Usuários", UsuariosState.total_usuarios),
                        _kpi("shield", "Administradores", UsuariosState.total_admins),
                        _kpi("circle-check", "Ativos", UsuariosState.total_ativos),
                        display="grid",
                        grid_template_columns=["1fr", "repeat(3, 1fr)"],
                        gap="16px",
                        width="100%",
                    ),
                    rx.cond(
                        UsuariosState.error_message != "",
                        aviso_fechavel(UsuariosState.error_message),
                        rx.fragment(),
                    ),
                    rx.cond(
                        UsuariosState.loading & (UsuariosState.usuarios.length() == 0),
                        rx.center(rx.spinner(size="3"), padding_y="8", width="100%"),
                        _tabela(),
                    ),
                    spacing="5",
                    width="100%",
                ),
            ),
            spacing="6",
            width="100%",
            max_width="1100px",
        ),
        _form_modal(),
        _senha_modal(),
        padding=["24px", "32px", "48px"],
        width="100%",
    )


def usuarios_page() -> rx.Component:
    return app_shell(
        _conteudo(),
        active="usuarios",
        search_value=UsuariosState.busca,
        on_search=UsuariosState.set_busca,
    )

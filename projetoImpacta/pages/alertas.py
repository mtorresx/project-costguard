"""Página de Alertas ("/alertas") — alertas reais e recursos não classificados.

Design adaptado do frontend original de referência
(KPIs, lista com ícone por nível e tempo relativo). As regras de alerta
configuráveis da referência ficam fora do escopo: os alertas são gerados pelo
backend conforme o domínio (orçamento, não classificado, falha de importação).
"""

import reflex as rx

from .. import theme as t
from ..components.mensagens import aviso_fechavel
from ..components.layout import app_shell
from ..components.pill import pill, selo_novo
from ..state import AuthState
from .alertas_state import Alerta, AlertasState, RecursoNaoClassificado

_VERMELHO = (t.ERROR, "rgba(239, 68, 68, 0.15)", "rgba(239, 68, 68, 0.4)")
_LARANJA = ("#fb923c", "rgba(249, 115, 22, 0.15)", "rgba(249, 115, 22, 0.4)")
_AMARELO = (t.WARNING, "rgba(245, 158, 11, 0.15)", "rgba(245, 158, 11, 0.4)")
_VERDE = (t.SUCCESS, "rgba(34, 197, 94, 0.12)", "rgba(34, 197, 94, 0.35)")


def _kpi(titulo: str, valor, subtexto: str, icone: str, cor_valor: str = t.TEXT_HIGH, cor_icone: str = t.TEXT_LOW) -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.text(titulo.upper(), font_size="11px", font_weight="600", color=t.TEXT_MED, letter_spacing="0.05em"),
            rx.spacer(),
            rx.icon(icone, size=18, stroke_width=1.5, color=cor_icone),
            width="100%",
        ),
        rx.text(valor, font_size="32px", font_weight="700", color=cor_valor),
        rx.text(subtexto, font_size="12px", color=t.TEXT_MED),
        align="start",
        spacing="2",
        width="100%",
        background=t.SURFACE,
        border=f"1px solid {t.BORDER_SUBTLE}",
        border_radius="12px",
        padding="20px",
    )


def _kpis() -> rx.Component:
    return rx.box(
        _kpi("Alertas abertos", AlertasState.total_abertos, "aguardando tratamento", "bell", cor_icone=t.PRIMARY_ACCENT),
        _kpi("Críticos abertos", AlertasState.total_criticos, "aviso, excedido ou erro", "circle-alert", cor_valor=t.ERROR, cor_icone=t.ERROR),
        _kpi("Disparados (24h)", AlertasState.total_24h, "criados nas últimas 24 horas", "triangle-alert"),
        _kpi("Não classificados", AlertasState.total_recursos, "recursos sem projeto válido", "tag", cor_icone=t.WARNING),
        display="grid",
        grid_template_columns=["1fr", "repeat(2, 1fr)", "repeat(4, 1fr)"],
        gap="16px",
        width="100%",
    )


def _cores(alerta: Alerta, indice: int):
    """Cor (texto, fundo, borda) por nível; resolvido fica verde."""
    return rx.cond(
        alerta["resolvido"],
        _VERDE[indice],
        rx.match(
            alerta["nivel"],
            ("estourado", _VERMELHO[indice]),
            ("erro", _VERMELHO[indice]),
            ("critico", _LARANJA[indice]),
            _AMARELO[indice],
        ),
    )


def _icone(alerta: Alerta) -> rx.Component:
    return rx.center(
        rx.cond(
            alerta["resolvido"],
            rx.icon("circle-check", size=16, color=t.SUCCESS),
            rx.match(
                alerta["tipo"],
                ("orcamento", rx.icon("wallet", size=16, color=_cores(alerta, 0))),
                ("nao_classificado", rx.icon("tag", size=16, color=_cores(alerta, 0))),
                rx.icon("cloud-off", size=16, color=_cores(alerta, 0)),
            ),
        ),
        width="34px",
        height="34px",
        border_radius="50%",
        background=_cores(alerta, 1),
        flex_shrink="0",
    )


def _linha_alerta(alerta: Alerta) -> rx.Component:
    return rx.hstack(
        _icone(alerta),
        rx.vstack(
            rx.hstack(
                rx.text(
                    alerta["nivel_rotulo"],
                    font_size="11px",
                    font_weight="700",
                    padding="2px 10px",
                    border_radius="999px",
                    color=_cores(alerta, 0),
                    background=_cores(alerta, 1),
                    border_width="1px",
                    border_style="solid",
                    border_color=_cores(alerta, 2),
                ),
                rx.text(alerta["tipo_rotulo"], font_size="12px", color=t.TEXT_MED),
                spacing="2",
                align="center",
                wrap="wrap",
            ),
            rx.cond(
                alerta["projeto_id"] > 0,
                rx.link(
                    rx.text(alerta["mensagem"], font_weight="700", font_size="14px", color=t.TEXT_HIGH),
                    href="/projetos/" + alerta["projeto_id"].to_string(),
                    underline="hover",
                ),
                rx.text(alerta["mensagem"], font_weight="700", font_size="14px", color=t.TEXT_HIGH),
            ),
            rx.cond(alerta["detalhe"] != "", rx.text(alerta["detalhe"], font_size="12px", color=t.TEXT_MED), rx.fragment()),
            rx.cond(
                alerta["resolvido"],
                rx.text(alerta["resolucao_texto"], font_size="12px", color=t.SUCCESS),
                rx.fragment(),
            ),
            spacing="1",
            align="start",
            flex="1",
            min_width="0",
        ),
        rx.vstack(
            rx.text(alerta["quando"], font_size="12px", color=t.TEXT_LOW, white_space="nowrap"),
            rx.cond(
                AuthState.is_admin & ~alerta["resolvido"],
                rx.button(
                    "Resolver",
                    on_click=AlertasState.resolver(alerta["id"]),
                    loading=AlertasState.resolvendo_id == alerta["id"],
                    size="1",
                    variant="soft",
                    color_scheme="teal",
                ),
                rx.fragment(),
            ),
            align="end",
            spacing="2",
        ),
        width="100%",
        padding_y="14px",
        border_bottom=f"1px solid {t.BORDER_SUBTLE}",
        align="start",
        spacing="3",
    )


def _secao_alertas() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.text("Alertas", font_size="16px", font_weight="600", color=t.TEXT_HIGH),
                rx.spacer(),
                rx.segmented_control.root(
                    rx.segmented_control.item("Abertos", value="abertos"),
                    rx.segmented_control.item("Resolvidos", value="resolvidos"),
                    rx.segmented_control.item("Todos", value="todos"),
                    value=AlertasState.filtro,
                    on_change=AlertasState.set_filtro,
                    size="1",
                ),
                width="100%",
                align="center",
                wrap="wrap",
                spacing="3",
            ),
            rx.cond(
                AlertasState.erro_alertas != "",
                aviso_fechavel(AlertasState.erro_alertas),
                rx.cond(
                    AlertasState.loading & (AlertasState.alertas.length() == 0),
                    rx.center(rx.spinner(size="3"), padding_y="8", width="100%"),
                    rx.cond(
                        AlertasState.alertas_filtrados.length() > 0,
                        rx.vstack(rx.foreach(AlertasState.alertas_filtrados, _linha_alerta), spacing="0", width="100%"),
                        rx.center(
                            rx.vstack(
                                rx.icon("bell-off", size=28, color=t.TEXT_LOW),
                                rx.text(
                                    rx.match(
                                        AlertasState.filtro,
                                        ("abertos", "Nenhum alerta aberto."),
                                        ("resolvidos", "Nenhum alerta resolvido."),
                                        "Nenhum alerta registrado.",
                                    ),
                                    color=t.TEXT_MED,
                                    size="3",
                                ),
                                align="center",
                                spacing="2",
                            ),
                            padding_y="8",
                            width="100%",
                        ),
                    ),
                ),
            ),
            spacing="3",
            width="100%",
        ),
        width="100%",
        background=t.SURFACE,
        border=f"1px solid {t.BORDER_SUBTLE}",
        border_radius="12px",
        padding="20px",
    )


def _linha_recurso(r: RecursoNaoClassificado) -> rx.Component:
    return rx.table.row(
        rx.table.cell(
            rx.vstack(
                rx.hstack(
                    rx.text(r["nome"], font_size="13px", font_weight="600", color=t.TEXT_HIGH),
                    rx.cond(r["novo"], selo_novo(), rx.fragment()),
                    spacing="2",
                    align="center",
                    wrap="wrap",
                ),
                rx.text(r["arn"], font_size="11px", font_family="monospace", color=t.TEXT_LOW, word_break="break-all"),
                spacing="0",
                align="start",
            ),
        ),
        rx.table.cell(rx.text(r["servico"], text_transform="uppercase", font_size="12px"), color=t.TEXT_MED),
        rx.table.cell(r["regiao"], color=t.TEXT_MED, font_size="12px"),
        rx.table.cell(r["provedor_nome"], color=t.TEXT_MED, font_size="12px"),
        rx.table.cell(
            rx.cond(
                r["tag"] != "",
                pill(r["tag"], t.WARNING, "rgba(245,158,11,0.1)", "rgba(245,158,11,0.3)"),
                rx.text("sem tag", font_size="12px", color=t.TEXT_LOW, font_style="italic"),
            ),
        ),
    )


def _secao_recursos() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.vstack(
                rx.text("Recursos não classificados", font_size="16px", font_weight="600", color=t.TEXT_HIGH),
                rx.text(
                    "Recursos sem projeto válido ficam fora dos orçamentos. A correção é feita nas tags do "
                    "provedor; a próxima sincronização reclassifica automaticamente.",
                    font_size="12px",
                    color=t.TEXT_MED,
                ),
                spacing="1",
                align="start",
            ),
            rx.cond(
                AlertasState.erro_recursos != "",
                aviso_fechavel(AlertasState.erro_recursos),
                rx.cond(
                    AlertasState.recursos.length() > 0,
                    rx.box(
                        rx.table.root(
                            rx.table.header(
                                rx.table.row(
                                    rx.table.column_header_cell("RECURSO"),
                                    rx.table.column_header_cell("SERVIÇO"),
                                    rx.table.column_header_cell("REGIÃO"),
                                    rx.table.column_header_cell("PROVEDOR"),
                                    rx.table.column_header_cell("TAG DE PROJETO"),
                                ),
                            ),
                            rx.table.body(rx.foreach(AlertasState.recursos, _linha_recurso)),
                            variant="ghost",
                            size="1",
                            width="100%",
                        ),
                        width="100%",
                        overflow_x="auto",
                    ),
                    rx.hstack(
                        rx.icon("circle-check", size=16, color=t.SUCCESS),
                        rx.text("Nenhum recurso sem projeto no inventário atual.", font_size="13px", color=t.TEXT_MED),
                        spacing="2",
                        align="center",
                        padding_y="12px",
                    ),
                ),
            ),
            spacing="3",
            width="100%",
        ),
        width="100%",
        background=t.SURFACE,
        border=f"1px solid {t.BORDER_SUBTLE}",
        border_radius="12px",
        padding="20px",
    )


def _conteudo() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.vstack(
                    rx.heading("Alertas", size="7", color=t.TEXT_HIGH),
                    rx.text(
                        "Orçamento (70%, 90% e 100%), recursos sem classificação e falhas de importação.",
                        color=t.TEXT_MED,
                        font_size="14px",
                    ),
                    spacing="1",
                    align="start",
                ),
                rx.spacer(),
                rx.cond(
                    AuthState.is_admin,
                    rx.button(
                        rx.icon("radar", size=16),
                        "Avaliar alertas agora",
                        on_click=AlertasState.avaliar,
                        loading=AlertasState.avaliando,
                        background=t.PRIMARY,
                        color=t.ON_PRIMARY,
                        font_weight="700",
                        _hover={"background": t.PRIMARY_HOVER},
                    ),
                    rx.fragment(),
                ),
                width="100%",
                align="center",
                wrap="wrap",
                spacing="3",
            ),
            rx.cond(
                AlertasState.erro_acao != "",
                aviso_fechavel(AlertasState.erro_acao),
                rx.fragment(),
            ),
            _kpis(),
            _secao_alertas(),
            _secao_recursos(),
            spacing="5",
            width="100%",
            max_width="1100px",
        ),
        padding=["24px", "32px", "48px"],
        width="100%",
    )


def alertas_page() -> rx.Component:
    return app_shell(
        _conteudo(),
        active="alertas",
        search_value=AlertasState.busca,
        on_search=AlertasState.set_busca,
    )

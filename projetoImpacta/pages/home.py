"""Painel autenticado ("/inicio"): dashboard do CostGuard com dados reais do Xano.

Mantém a linguagem visual incorporada (cartões, cores e tipografia do shell) e
exibe apenas dados do backend: custo classificado no mês, projetos ativos,
alertas abertos, recursos não classificados, maiores consumos e alertas recentes.
"""

import reflex as rx

from .. import theme as t
from ..components.mensagens import aviso_fechavel
from ..components.layout import app_shell
from ..components.periodo_state import seletor_mes
from .alertas_state import Alerta
from .home_state import ConsumoProjeto, HomeState

_FONT_HEADLINE = "'Geist', 'Inter', system-ui, sans-serif"


def _cartao(*filhos, **estilo) -> rx.Component:
    return rx.box(
        *filhos,
        background=t.SURFACE,
        border=f"1px solid {t.BORDER_SUBTLE}",
        border_radius="14px",
        padding="20px",
        width="100%",
        **estilo,
    )


def _kpi(rotulo: str, icone: str, valor, nota, erro, href: str, cor_valor=t.TEXT_HIGH) -> rx.Component:
    return rx.link(
        _cartao(
            rx.vstack(
                rx.hstack(
                    rx.text(rotulo.upper(), font_size="11px", font_weight="600", color=t.TEXT_MED, letter_spacing="0.05em"),
                    rx.spacer(),
                    rx.icon(icone, size=18, stroke_width=1.5, color=t.PRIMARY_ACCENT),
                    width="100%",
                ),
                rx.cond(
                    ~HomeState.carregado,
                    # Primeira carga: marcador em vez do 0 inicial do estado.
                    rx.skeleton(
                        rx.text("0000", font_family=_FONT_HEADLINE, font_size="28px", font_weight="700", line_height="1.15"),
                        loading=True,
                    ),
                    rx.cond(
                        erro != "",
                        rx.text("Indisponível", font_size="20px", font_weight="700", color=t.TEXT_LOW),
                        rx.text(valor, font_family=_FONT_HEADLINE, font_size="28px", font_weight="700", color=cor_valor, line_height="1.15"),
                    ),
                ),
                rx.text(
                    rx.cond(~HomeState.carregado, "Carregando…", rx.cond(erro != "", erro, nota)),
                    font_size="12px",
                    color=t.TEXT_MED,
                ),
                align="start",
                spacing="2",
            ),
            height="100%",
            transition="border-color 0.2s ease, transform 0.2s ease",
            _hover={"border_color": t.LANDING_BORDER, "transform": "translateY(-2px)"},
        ),
        href=href,
        underline="none",
        width="100%",
    )


def _kpis() -> rx.Component:
    return rx.box(
        _kpi(
            "Custo classificado (mês)",
            "wallet",
            rx.cond(HomeState.custo_texto != "", HomeState.custo_texto, "—"),
            rx.cond(
                HomeState.custo_nota != "",
                HomeState.custo_nota,
                rx.cond(HomeState.periodo_texto != "", HomeState.periodo_texto, ""),
            ),
            HomeState.erro_consumo,
            "/projetos",
        ),
        _kpi("Projetos ativos", "folder-kanban", HomeState.projetos_ativos, "com orçamento mensal em USD", HomeState.erro_consumo, "/projetos"),
        _kpi(
            "Alertas abertos",
            "bell",
            HomeState.alertas_abertos,
            HomeState.alertas_criticos.to_string() + " críticos",
            HomeState.erro_alertas,
            "/alertas",
            cor_valor=rx.cond(HomeState.alertas_criticos > 0, t.ERROR, t.TEXT_HIGH),
        ),
        _kpi(
            "Não classificados",
            "tag",
            HomeState.recursos_nao_classificados,
            "recursos sem projeto válido",
            HomeState.erro_recursos,
            "/alertas",
            cor_valor=rx.cond(HomeState.recursos_nao_classificados > 0, t.WARNING, t.TEXT_HIGH),
        ),
        display="grid",
        grid_template_columns=["1fr", "repeat(2, 1fr)", "repeat(4, 1fr)"],
        gap="16px",
        width="100%",
    )


def _linha_consumo(p: ConsumoProjeto) -> rx.Component:
    return rx.link(
        rx.vstack(
            rx.hstack(
                rx.vstack(
                    rx.text(p["nome"], font_size="14px", font_weight="600", color=t.TEXT_HIGH),
                    rx.text(p["codigo"], font_size="11px", font_family="monospace", color=t.TEXT_LOW),
                    spacing="0",
                    align="start",
                ),
                rx.spacer(),
                rx.vstack(
                    rx.hstack(
                        rx.badge(p["faixa_rotulo"], color_scheme=p["faixa_cor"], variant="soft", size="1"),
                        rx.text(p["percentual_texto"], font_size="14px", font_weight="700", color=t.TEXT_HIGH),
                        spacing="2",
                        align="center",
                    ),
                    rx.text(p["custo_texto"], " de ", p["orcamento_texto"], font_size="11px", color=t.TEXT_MED),
                    spacing="0",
                    align="end",
                ),
                width="100%",
                align="center",
            ),
            rx.progress(value=p["barra_valor"], max=100, color_scheme=p["faixa_cor"], size="1", width="100%"),
            spacing="2",
            width="100%",
            padding_y="10px",
            border_bottom=f"1px solid {t.BORDER_SUBTLE}",
        ),
        href="/projetos/" + p["id"].to_string(),
        underline="none",
        width="100%",
    )


def _bloco_consumo() -> rx.Component:
    return _cartao(
        rx.vstack(
            rx.hstack(
                rx.text("Maiores consumos do orçamento", font_size="16px", font_weight="600", color=t.TEXT_HIGH),
                rx.spacer(),
                rx.link("Ver projetos", href="/projetos", font_size="12px", color=t.PRIMARY_ACCENT),
                width="100%",
                align="center",
            ),
            rx.cond(
                HomeState.erro_consumo != "",
                aviso_fechavel(HomeState.erro_consumo),
                rx.cond(
                    HomeState.consumos.length() > 0,
                    rx.vstack(rx.foreach(HomeState.consumos, _linha_consumo), spacing="0", width="100%"),
                    rx.text(
                        rx.cond(
                            HomeState.loading,
                            "Carregando...",
                            "Nenhum projeto ativo com orçamento e custo classificado no mês selecionado.",
                        ),
                        font_size="13px",
                        color=t.TEXT_MED,
                        padding_y="12px",
                    ),
                ),
            ),
            spacing="3",
            width="100%",
        ),
    )


def _linha_alerta(a: Alerta) -> rx.Component:
    cor = rx.match(a["nivel"], ("estourado", t.ERROR), ("erro", t.ERROR), ("critico", "#fb923c"), t.WARNING)
    return rx.hstack(
        rx.box(width="8px", height="8px", border_radius="50%", background=cor, margin_top="6px", flex_shrink="0"),
        rx.vstack(
            rx.text(a["mensagem"], font_size="13px", font_weight="600", color=t.TEXT_HIGH),
            rx.text(a["nivel_rotulo"], " · ", a["tipo_rotulo"], " · ", a["quando"], font_size="11px", color=t.TEXT_MED),
            spacing="0",
            align="start",
        ),
        spacing="3",
        align="start",
        width="100%",
        padding_y="10px",
        border_bottom=f"1px solid {t.BORDER_SUBTLE}",
    )


def _bloco_alertas() -> rx.Component:
    return _cartao(
        rx.vstack(
            rx.hstack(
                rx.text("Alertas abertos recentes", font_size="16px", font_weight="600", color=t.TEXT_HIGH),
                rx.spacer(),
                rx.link("Ver alertas", href="/alertas", font_size="12px", color=t.PRIMARY_ACCENT),
                width="100%",
                align="center",
            ),
            rx.cond(
                HomeState.erro_alertas != "",
                aviso_fechavel(HomeState.erro_alertas),
                rx.cond(
                    HomeState.alertas_recentes.length() > 0,
                    rx.vstack(rx.foreach(HomeState.alertas_recentes, _linha_alerta), spacing="0", width="100%"),
                    rx.hstack(
                        rx.icon("circle-check", size=16, color=t.SUCCESS),
                        rx.text(
                            rx.cond(HomeState.loading, "Carregando...", "Nenhum alerta aberto."),
                            font_size="13px",
                            color=t.TEXT_MED,
                        ),
                        spacing="2",
                        align="center",
                        padding_y="12px",
                    ),
                ),
            ),
            spacing="3",
            width="100%",
        ),
    )


def _atalho(icone: str, titulo: str, descricao: str, rota: str) -> rx.Component:
    return rx.link(
        rx.hstack(
            rx.center(
                rx.icon(icone, size=20, stroke_width=1.75, color=t.LANDING_ACCENT),
                width="40px",
                height="40px",
                border_radius="10px",
                border=f"1px solid {t.LANDING_BORDER}",
                background="rgba(45, 212, 191, 0.06)",
                flex_shrink="0",
            ),
            rx.vstack(
                rx.text(titulo, font_size="14px", font_weight="700", color=t.TEXT_HIGH),
                rx.text(descricao, font_size="12px", color=t.TEXT_MED),
                spacing="0",
                align="start",
            ),
            spacing="3",
            align="center",
            padding="16px",
            border_radius="12px",
            background=t.LANDING_SURFACE,
            border=f"1px solid {t.BORDER_SUBTLE}",
            width="100%",
            transition="border-color 0.2s ease",
            _hover={"border_color": t.LANDING_BORDER},
        ),
        href=rota,
        underline="none",
        width="100%",
    )


def _conteudo() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.vstack(
                    rx.heading(
                        "Visão geral",
                        font_family=_FONT_HEADLINE,
                        size="7",
                        color=t.TEXT_HIGH,
                    ),
                    rx.text(
                        "Custos classificados por projeto, consumo do orçamento mensal e alertas.",
                        font_size="14px",
                        color=t.TEXT_MED,
                    ),
                    spacing="1",
                    align="start",
                ),
                rx.spacer(),
                seletor_mes(HomeState.mudar_mes),
                rx.icon_button(
                    rx.icon("refresh-cw", size=16),
                    on_click=HomeState.atualizar,
                    loading=HomeState.loading,
                    variant="soft",
                    color_scheme="teal",
                    title="Atualizar",
                ),
                width="100%",
                align="center",
                wrap="wrap",
                spacing="3",
            ),
            _kpis(),
            rx.box(
                _bloco_consumo(),
                _bloco_alertas(),
                display="grid",
                grid_template_columns=["1fr", "1fr", "3fr 2fr"],
                gap="16px",
                width="100%",
                align_items="start",
            ),
            rx.box(
                _atalho("folder-kanban", "Projetos", "Orçamento mensal e consumo por projeto.", "/projetos"),
                _atalho("cloud", "Provedores", "Contas AWS conectadas e sincronização.", "/provedores"),
                _atalho("bell", "Alertas", "Orçamento, recursos sem projeto e falhas.", "/alertas"),
                display="grid",
                grid_template_columns=["1fr", "1fr", "repeat(3, 1fr)"],
                gap="16px",
                width="100%",
            ),
            align="start",
            spacing="5",
            width="100%",
            max_width="1200px",
        ),
        padding=["24px", "32px", "48px"],
        width="100%",
    )


def home_page() -> rx.Component:
    return app_shell(_conteudo(), active="home")

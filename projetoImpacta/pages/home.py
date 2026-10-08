"""Home autenticada ("/"): área principal do CostGuard.

Reaproveita a linguagem visual da landing externa (hero, métricas, cards de
recurso) como home autenticada dentro do app shell. Não é site público de
marketing. Conteúdo de apresentação/mock — sem backend nesta etapa.
"""

import reflex as rx

from .. import theme as t
from ..components.layout import app_shell
from ..components.pulso import ponto_pulsante

_FONT_HEADLINE = "'Geist', 'Inter', system-ui, sans-serif"


def _badge() -> rx.Component:
    return rx.hstack(
        ponto_pulsante(width="8px", height="8px", border_radius="50%", background=t.LANDING_ACCENT),
        rx.text(
            "Visibilidade de custos cloud em tempo real",
            font_size="13px",
            color=t.LANDING_ACCENT,
            font_weight="500",
        ),
        spacing="2",
        align="center",
        padding="7px 16px",
        border_radius="999px",
        border=f"1px solid {t.LANDING_BORDER}",
        background="rgba(45, 212, 191, 0.07)",
    )


def _mini_metrica(rotulo: str, valor: str, cor: str = t.TEXT_HIGH) -> rx.Component:
    return rx.vstack(
        rx.text(rotulo, font_size="12px", color=t.TEXT_MED),
        rx.text(valor, font_family=_FONT_HEADLINE, font_size="30px", font_weight="700", color=cor, line_height="1.1"),
        align="start",
        spacing="2",
        padding="20px",
        border_radius="12px",
        background=t.SURFACE,
        border=f"1px solid {t.BORDER_SUBTLE}",
    )


def _card_recurso(icone: str, titulo: str, descricao: str, rota: str) -> rx.Component:
    return rx.link(
        rx.vstack(
            rx.center(
                rx.icon(icone, size=22, stroke_width=1.75, color=t.LANDING_ACCENT),
                width="48px",
                height="48px",
                border_radius="12px",
                border=f"1px solid {t.LANDING_BORDER}",
                background="rgba(45, 212, 191, 0.06)",
            ),
            rx.text(titulo, font_family=_FONT_HEADLINE, font_size="20px", font_weight="700", color=t.TEXT_HIGH),
            rx.text(descricao, font_size="15px", line_height="1.65", color=t.TEXT_MED),
            align="start",
            spacing="4",
            padding="28px",
            border_radius="16px",
            background=t.LANDING_SURFACE,
            border=f"1px solid {t.BORDER_SUBTLE}",
            height="100%",
            transition="border-color 0.2s ease, transform 0.2s ease",
            _hover={"border_color": t.LANDING_BORDER, "transform": "translateY(-2px)"},
        ),
        href=rota,
        underline="none",
        width="100%",
    )


def _conteudo() -> rx.Component:
    return rx.box(
        rx.vstack(
            _badge(),
            rx.heading(
                "Controle total sobre o custo da sua ",
                rx.text("nuvem", as_="span", color=t.LANDING_ACCENT),
                font_family=_FONT_HEADLINE,
                font_size=["30px", "38px", "46px"],
                font_weight="700",
                line_height="1.1",
                letter_spacing="-0.02em",
                color=t.TEXT_HIGH,
                max_width="820px",
            ),
            rx.text(
                "Atribuição de custo, alertas inteligentes e projeções de orçamento em uma única "
                "plataforma. Os números abaixo são ilustrativos (demonstração).",
                font_size=["15px", "16px", "17px"],
                line_height="1.65",
                color=t.TEXT_MED,
                max_width="640px",
            ),
            rx.box(
                _mini_metrica("Custo total (mês)", "US$ 24.720"),
                _mini_metrica("Projetos monitorados", "18"),
                _mini_metrica("Alertas ativos", "2", cor=t.WARNING),
                display="grid",
                grid_template_columns=["1fr", "1fr", "repeat(3, 1fr)"],
                gap="16px",
                width="100%",
                margin_top="8px",
            ),
            rx.box(
                _card_recurso("folder-kanban", "Projetos", "Orçamento mensal e status de cada projeto.", "/projetos"),
                _card_recurso("cloud", "Provedores", "Contas de nuvem conectadas (somente leitura).", "/provedores"),
                _card_recurso("bell", "Alertas", "Teto de gastos e histórico de disparos.", "/alertas"),
                display="grid",
                grid_template_columns=["1fr", "1fr", "repeat(3, 1fr)"],
                gap="24px",
                width="100%",
                margin_top="16px",
            ),
            align="start",
            spacing="6",
            width="100%",
            max_width="1100px",
        ),
        padding=["24px", "32px", "48px"],
        width="100%",
    )


def home_page() -> rx.Component:
    return app_shell(_conteudo(), active="home")

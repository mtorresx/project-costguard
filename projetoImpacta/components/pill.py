import reflex as rx

from .. import theme as t


def pill(texto: str, cor: str, fundo: str, borda: str) -> rx.Component:
    """Pill preenchido (texto colorido, fundo translúcido e borda da mesma cor)."""
    return rx.text(
        texto,
        display="inline-flex",
        align_items="center",
        padding="3px 12px",
        border_radius="999px",
        font_size="12px",
        font_weight="600",
        color=cor,
        background=fundo,
        border=f"1px solid {borda}",
    )


def selo_novo() -> rx.Component:
    """Selo de recurso descoberto há menos de 48 h (o sistema não mede custo por recurso)."""
    return rx.text(
        "Novo · custo ainda não disponível",
        display="inline-flex",
        align_items="center",
        padding="1px 8px",
        border_radius="999px",
        font_size="11px",
        font_weight="600",
        white_space="nowrap",
        color=t.PRIMARY_ACCENT,
        background=t.NAV_ACTIVE_BG,
        border=f"1px solid {t.PRIMARY}",
    )

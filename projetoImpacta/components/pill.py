import reflex as rx


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

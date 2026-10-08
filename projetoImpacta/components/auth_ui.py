"""Peças visuais compartilhadas pelas telas de autenticação (login).

Incorporado do frontend externo (design). Fundo futurista, card, logo, campos,
botão, banners e links no estilo "Dark Kinetic".
"""

import reflex as rx

from .. import theme as t

FONT_HEADLINE = "'Geist', 'Inter', system-ui, sans-serif"
FONT_BODY = "'Inter', system-ui, sans-serif"

ON_PRIMARY = "#003731"
CARD_BG = "rgba(15, 22, 32, 0.9)"
CARD_BORDER = "1px solid rgba(45, 212, 191, 0.25)"


def logo_mark() -> rx.Component:
    return rx.hstack(
        rx.image(src="/logo-costguard.svg", alt="CostGuard", width="40px", height="40px"),
        rx.text(
            "CostGuard",
            font_family=FONT_HEADLINE,
            font_size="22px",
            font_weight="700",
            color=t.TEXT_HIGH,
            letter_spacing="-0.02em",
            line_height="1",
        ),
        align="center",
        justify="center",
        width="100%",
        spacing="3",
    )


def heading_block(titulo: str, subtitulo: str) -> rx.Component:
    """Logo + título + subtítulo, centralizados no topo do card."""
    return rx.vstack(
        logo_mark(),
        rx.box(height="20px"),
        rx.text(
            titulo,
            font_family=FONT_HEADLINE,
            font_size="26px",
            font_weight="600",
            color=t.TEXT_HIGH,
            letter_spacing="-0.01em",
            line_height="32px",
            text_align="center",
            width="100%",
        ),
        rx.text(
            subtitulo,
            font_family=FONT_BODY,
            font_size="14px",
            font_weight="400",
            color=t.TEXT_MED,
            line_height="20px",
            text_align="center",
            width="100%",
        ),
        align="center",
        spacing="1",
        width="100%",
    )


def divider() -> rx.Component:
    return rx.box(
        height="0",
        width="100%",
        border_top="1px solid rgba(138, 166, 163, 0.22)",
        margin_y="8px",
    )


def field_label(texto: str) -> rx.Component:
    return rx.text(
        texto,
        font_family=FONT_BODY,
        font_size="11px",
        font_weight="500",
        letter_spacing="0.06em",
        color=t.LANDING_MUTED,
        text_transform="uppercase",
    )


_INPUT_STYLE = dict(
    box_sizing="border-box",
    background_color="transparent",
    border=f"1px solid {t.BORDER_INPUT}",
    border_radius="4px",
    color=t.TEXT_MAIN,
    font_family=FONT_BODY,
    font_size="14px",
    line_height="20px",
    text_align="left",
    padding="12px 16px",
    width="100%",
    height="44px",
    outline="none",
    _placeholder={"color": t.TEXT_LOW},
    _hover={"border_color": t.TEXT_LOW},
    _focus={
        "border_color": t.PRIMARY,
        "box_shadow": f"0 0 0 1px {t.PRIMARY}",
        "outline": "none",
    },
    _autofill={
        "box_shadow": "0 0 0 1000px rgb(14, 21, 31) inset",
        "-webkit-text-fill-color": t.TEXT_MAIN,
        "caret_color": t.PRIMARY_ACCENT,
    },
    transition="border-color 0.15s ease, box-shadow 0.15s ease",
)


def text_input(**props) -> rx.Component:
    """Campo de texto no estilo da autenticação; `props` sobrescrevem o padrão."""
    return rx.el.input(**{**_INPUT_STYLE, **props})


def link(texto: str, href: str, **props) -> rx.Component:
    estilo = dict(
        font_family=FONT_BODY,
        font_size="12px",
        color=t.PRIMARY_ACCENT,
        text_decoration="none",
        _hover={"color": t.PRIMARY, "text_decoration": "underline"},
        transition="color 0.15s ease",
    )
    return rx.link(texto, href=href, **{**estilo, **props})


def banner(mensagem, cor: str, fundo: str, borda: str, icone: str) -> rx.Component:
    return rx.hstack(
        rx.icon(icone, size=14, color=cor, flex_shrink="0"),
        rx.text(
            mensagem,
            font_family=FONT_BODY,
            font_size="13px",
            color=cor,
            line_height="18px",
            text_align="left",
        ),
        background_color=fundo,
        border=f"1px solid {borda}",
        border_radius="4px",
        padding="10px 14px",
        width="100%",
        align="center",
        spacing="2",
    )


def error_banner(mensagem: rx.Var[str]) -> rx.Component:
    return rx.cond(
        mensagem != "",
        banner(mensagem, t.ERROR, "rgba(239, 68, 68, 0.08)", "rgba(239, 68, 68, 0.25)", "triangle-alert"),
        rx.fragment(),
    )


def primary_button(
    texto: str,
    on_click,
    loading: rx.Var[bool] | bool = False,
    texto_loading: str = "Enviando…",
) -> rx.Component:
    return rx.button(
        rx.cond(
            loading,
            rx.hstack(
                rx.spinner(size="2", color="white"),
                rx.text(texto_loading, font_size="14px", font_weight="600", color=ON_PRIMARY),
                align="center",
                spacing="2",
            ),
            rx.text(texto, font_size="14px", font_weight="600", color=ON_PRIMARY),
        ),
        on_click=on_click,
        disabled=loading,
        background_color=t.PRIMARY,
        border="none",
        border_radius="4px",
        padding="12px 24px",
        width="100%",
        height="44px",
        cursor=rx.cond(loading, "not-allowed", "pointer"),
        box_shadow="0 0 20px rgba(45, 212, 191, 0.25)",
        _hover={"box_shadow": "0 0 30px rgba(45, 212, 191, 0.5)", "opacity": "0.92"},
        _disabled={"opacity": "0.5"},
        transition="box-shadow 0.15s ease, opacity 0.15s ease",
        display="flex",
        align_items="center",
        justify_content="center",
    )


def auth_card(*children: rx.Component) -> rx.Component:
    return rx.box(
        rx.vstack(*children, spacing="4", width="100%", align="stretch"),
        position="relative",
        z_index="2",
        display="flex",
        flex_direction="column",
        align_items="center",
        text_align="center",
        background=CARD_BG,
        border=CARD_BORDER,
        border_radius=["0", "8px"],
        padding=["24px", "40px"],
        width=["100%", "420px"],
        min_height=["100dvh", "auto"],
        box_shadow="0px 8px 32px rgba(0, 0, 0, 0.5), 0 0 40px rgba(45, 212, 191, 0.12)",
        max_width="100vw",
        id="cg-auth-card",
    )


_CAMADA_DE_FUNDO = {"position": "absolute", "pointer_events": "none", "z_index": "0"}


def _fundo_futurista() -> list[rx.Component]:
    """Grade sutil e dois círculos decorativos, atrás do card (não recebem cliques)."""
    grade = rx.box(
        style={
            **_CAMADA_DE_FUNDO,
            "inset": "0",
            "background_image": (
                "linear-gradient(rgba(45, 212, 191, 0.06) 1px, transparent 1px), "
                "linear-gradient(90deg, rgba(45, 212, 191, 0.06) 1px, transparent 1px)"
            ),
            "background_size": "36px 36px",
        },
    )
    circulo_grande = rx.box(
        style={
            **_CAMADA_DE_FUNDO,
            "width": "280px",
            "height": "280px",
            "border_radius": "50%",
            "background": "transparent",
            "border": "1px solid rgba(45, 212, 191, 0.15)",
            "top": "-60px",
            "left": "-60px",
        },
    )
    circulo_pequeno = rx.box(
        style={
            **_CAMADA_DE_FUNDO,
            "width": "180px",
            "height": "180px",
            "border_radius": "50%",
            "background": "transparent",
            "border": "1px solid rgba(45, 212, 191, 0.12)",
            "bottom": "-40px",
            "right": "40px",
        },
    )
    return [grade, circulo_grande, circulo_pequeno]


def auth_page(card: rx.Component, *extras: rx.Component) -> rx.Component:
    """Página inteira: fundo futurista e o card centralizado.

    `extras` são elementos posicionados sobre o fundo, fora do card.
    """
    return rx.box(
        *_fundo_futurista(),
        *extras,
        card,
        style={
            "background": f"radial-gradient(ellipse 700px 400px at 50% 0%, rgba(45, 212, 191, 0.14), transparent), {t.LANDING_BG}",
            "position": "relative",
            "overflow": "hidden",
            "min_height": "100vh",
            "display": "flex",
            "align_items": "center",
            "justify_content": "center",
        },
        padding_x="16px",
        width="100%",
        font_family=FONT_BODY,
    )

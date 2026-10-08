import reflex as rx

from .. import theme as t


def th(texto: str, alinhamento: str = "left") -> rx.Component:
    """Célula de cabeçalho de tabela: maiúsculas, cinza claro, letra espaçada."""
    return rx.table.column_header_cell(
        texto,
        text_align=alinhamento,
        font_size="11px",
        font_weight="600",
        letter_spacing="0.05em",
        color=t.TEXT_MED,
    )

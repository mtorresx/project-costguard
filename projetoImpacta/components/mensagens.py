"""Feedback de ações nas páginas autenticadas."""

import reflex as rx


def sucesso(mensagem: str):
    return rx.toast.success(mensagem, duration=4000, position="top-center")


def aviso_fechavel(mensagem) -> rx.Component:
    # Um diálogo não modal mantém o erro visível até o fechamento pelo formulário
    # nativo, sem apagar a condição de erro que controla o restante da página.
    return rx.el.dialog(
        rx.flex(
            rx.text(mensagem, role="alert", size="2"),
            rx.el.form(rx.button("Fechar", type="submit", variant="soft", size="1"), method="dialog", on_submit=None),
            align="center", justify="between", gap="3",
        ),
        open=True, key=mensagem, aria_label="Aviso", position="relative",
        margin="0", padding="0.65rem", width="100%", color=rx.color("red", 11),
        background=rx.color("red", 2), border=f"1px solid {rx.color('red', 6)}",
        border_radius="8px",
    )

"""Página de detalhamento de projeto ("/projetos/[projeto_id]").

Porta o design de C:\\frontend-costguard (pages/projetos.py, projeto_detalhe_page)
e liga os blocos aos endpoints reais do Xano. Blocos sem dado real não são
desenhados: não há projeção, tendência, custo por provedor nem custo por recurso.

Ver openspec/changes/frontend-detalhamento-projeto (proposal, design, spec).
"""

import reflex as rx

from .. import theme as t
from ..components.layout import app_shell
from .projeto_detalhe_state import (
    TEXTO_SEM_CUSTO,
    EquipeCusto,
    GrupoRecursos,
    ProjetoDetalheState,
    RecursoDetalhe,
)


def _badge_status() -> rx.Component:
    return rx.badge(
        ProjetoDetalheState.status_texto,
        color_scheme=rx.cond(ProjetoDetalheState.inativo, "gray", "green"),
        variant="soft",
    )


def _breadcrumb() -> rx.Component:
    return rx.hstack(
        rx.link(
            rx.hstack(
                rx.icon("arrow-left", size=14),
                rx.text("PROJETOS", size="1", weight="bold", letter_spacing="0.05em"),
                spacing="1",
                align="center",
            ),
            href="/projetos",
            color=t.TEXT_MED,
            text_decoration="none",
            _hover={"color": t.TEXT_HIGH},
        ),
        rx.icon("chevron-right", size=14, color=t.TEXT_LOW),
        rx.text(ProjetoDetalheState.nome, size="1", weight="bold", color=t.PRIMARY_ACCENT, letter_spacing="0.05em"),
        spacing="2",
        align="center",
    )


def _cabecalho() -> rx.Component:
    return rx.hstack(
        rx.vstack(
            rx.hstack(
                rx.heading(ProjetoDetalheState.nome, size="7", color=t.TEXT_HIGH),
                _badge_status(),
                spacing="3",
                align="center",
            ),
            rx.text(
                "Visão analítica consolidada de gastos com nuvem e recursos de infraestrutura deste projeto.",
                color=t.TEXT_MED,
                font_size="14px",
            ),
            rx.text(ProjetoDetalheState.periodo, size="1", color=t.TEXT_MED),
            spacing="1",
            align="start",
        ),
        rx.spacer(),
        rx.button(
            rx.icon("download", size=16),
            "Exportar Dados",
            on_click=ProjetoDetalheState.exportar_csv,
            variant="outline",
            size="2",
        ),
        width="100%",
        align="start",
        margin_top="1rem",
    )


def _kpi_card(icone: str, label: str, valor, rodape: rx.Component) -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.text(label.upper(), font_size="11px", font_weight="600", color=t.TEXT_MED, letter_spacing="0.05em"),
            rx.spacer(),
            rx.icon(icone, size=16, color=t.TEXT_LOW),
            width="100%",
            align="center",
        ),
        rx.text(valor, font_size="24px", font_weight="700", color=t.TEXT_HIGH, margin_top="0.5rem"),
        rodape,
        background=t.SURFACE,
        border=f"1px solid {t.BORDER_SUBTLE}",
        border_radius="12px",
        padding="1.25rem",
        width="100%",
    )


def _card_custo() -> rx.Component:
    return _kpi_card(
        "wallet",
        "Custo classificado (MTD)",
        ProjetoDetalheState.custo_texto,
        rx.text(ProjetoDetalheState.rodape_custo, size="1", color=t.TEXT_MED, margin_top="0.5rem"),
    )


def _card_orcamento() -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.text("ORÇAMENTO RESTANTE", font_size="11px", font_weight="600", color=t.TEXT_MED, letter_spacing="0.05em"),
            rx.spacer(),
            rx.icon("pie-chart", size=16, color=t.TEXT_LOW),
            width="100%",
            align="center",
        ),
        rx.text(ProjetoDetalheState.restante_texto, font_size="24px", font_weight="700", color=t.TEXT_HIGH, margin_top="0.5rem"),
        rx.cond(
            ProjetoDetalheState.comparavel,
            rx.box(
                rx.box(
                    width=ProjetoDetalheState.largura_barra,
                    height="100%",
                    background=t.PRIMARY_ACCENT,
                    border_radius="9999px",
                ),
                width="100%",
                height="5px",
                background=t.INPUT_BG,
                border_radius="9999px",
                overflow="hidden",
                margin_top="0.5rem",
            ),
            rx.fragment(),
        ),
        rx.cond(
            ProjetoDetalheState.comparavel,
            rx.text(ProjetoDetalheState.percentual_texto, size="1", color=t.TEXT_MED, margin_top="0.25rem"),
            rx.text(ProjetoDetalheState.comparacao_texto, size="1", color=t.TEXT_MED, margin_top="0.25rem"),
        ),
        background=t.SURFACE,
        border=f"1px solid {t.BORDER_SUBTLE}",
        border_radius="12px",
        padding="1.25rem",
        width="100%",
    )


def _vazio(texto) -> rx.Component:
    return rx.center(rx.text(texto, color=t.TEXT_MED, size="3"), padding_y="6", width="100%")


def _barra_equipe(item: EquipeCusto) -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.hstack(
                rx.box(width="8px", height="8px", border_radius="full", background=rx.color("teal", 9)),
                rx.text(item["nome"], size="2", weight="medium"),
                rx.text(item["recursos_texto"], size="1", color=t.TEXT_MED),
                spacing="2",
                align="center",
            ),
            rx.spacer(),
            rx.text(item["total_texto"], size="2", weight="bold", font_family="monospace"),
            width="100%",
            align="center",
        ),
        rx.box(
            rx.box(
                width=item["largura"],
                height="100%",
                background=rx.color("teal", 9),
                border_radius="full",
            ),
            width="100%",
            height="6px",
            background=rx.color("gray", 4),
            border_radius="full",
            overflow="hidden",
        ),
        spacing="2",
        width="100%",
    )


def _bloco_equipes() -> rx.Component:
    return rx.box(
        rx.text("Custo por equipe", weight="bold", margin_bottom="3", color=t.TEXT_HIGH),
        rx.cond(
            ProjetoDetalheState.carregando_custos,
            rx.center(rx.spinner(size="3"), padding_y="6"),
            rx.cond(
                ProjetoDetalheState.erro_custos != "",
                rx.callout(ProjetoDetalheState.erro_custos, color_scheme="red", size="1", width="100%"),
                rx.cond(
                    ProjetoDetalheState.sem_custos,
                    _vazio(TEXTO_SEM_CUSTO),
                    rx.cond(
                        ProjetoDetalheState.equipes_custo.length() > 0,
                        rx.grid(
                            rx.foreach(ProjetoDetalheState.equipes_custo, _barra_equipe),
                            columns="2",
                            spacing="5",
                            width="100%",
                        ),
                        _vazio("Nenhum custo por equipe no mês até a data atual."),
                    ),
                ),
            ),
        ),
        background=t.SURFACE,
        border=f"1px solid {t.BORDER_SUBTLE}",
        border_radius="12px",
        padding="1.25rem",
        width="100%",
    )


def _recurso_row(recurso: RecursoDetalhe) -> rx.Component:
    return rx.table.row(
        rx.table.cell(
            rx.tooltip(
                rx.hstack(
                    rx.icon(recurso["servico_icone"], size=14, color=recurso["servico_cor"]),
                    rx.text(recurso["nome"], font_family="monospace", size="2"),
                    spacing="2",
                    align="center",
                ),
                content=recurso["arn"],
            ),
        ),
        rx.table.cell(rx.text(recurso["servico"], size="2", color=rx.color("gray", 10))),
        rx.table.cell(rx.text(recurso["regiao"], size="2", color=rx.color("gray", 10))),
    )


def _grupo_recursos(grupo: GrupoRecursos) -> rx.Component:
    recolhido = ProjetoDetalheState.equipes_recolhidas.contains(grupo["chave"])
    return rx.box(
        rx.hstack(
            rx.hstack(
                rx.text(grupo["equipe"], weight="bold", color=rx.color("teal", 9)),
                rx.text(grupo["total_texto"], size="1", color=rx.color("gray", 10)),
                spacing="2",
            ),
            rx.spacer(),
            rx.icon(
                "chevron-down",
                size=18,
                color=rx.color("gray", 9),
                transform=rx.cond(recolhido, "rotate(0deg)", "rotate(180deg)"),
                transition="transform 0.2s ease",
            ),
            on_click=ProjetoDetalheState.alternar_equipe_expandida(grupo["chave"]),
            cursor="pointer",
            width="100%",
            padding="0.75rem 1rem",
            background=rx.color("gray", 3),
            align="center",
        ),
        rx.cond(
            ~recolhido,
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell("Recurso"),
                        rx.table.column_header_cell("Serviço"),
                        rx.table.column_header_cell("Região"),
                    ),
                ),
                rx.table.body(
                    rx.foreach(grupo["recursos"].to(list[RecursoDetalhe]), _recurso_row),
                ),
                width="100%",
                variant="ghost",
                size="1",
            ),
            rx.fragment(),
        ),
        border=f"1px solid {rx.color('gray', 5)}",
        border_radius="8px",
        overflow="hidden",
        width="100%",
    )


def _bloco_recursos() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.text("Recursos detalhados por equipe", weight="bold", color=t.TEXT_HIGH),
            rx.spacer(),
            rx.button(
                rx.icon("download", size=14),
                "Exportar CSV",
                on_click=ProjetoDetalheState.exportar_csv,
                variant="soft",
                size="1",
            ),
            width="100%",
            align="center",
        ),
        rx.cond(
            ProjetoDetalheState.carregando_recursos,
            rx.center(rx.spinner(size="3"), padding_y="6", width="100%"),
            rx.cond(
                ProjetoDetalheState.erro_recursos != "",
                rx.callout(ProjetoDetalheState.erro_recursos, color_scheme="red", size="1", width="100%"),
                rx.cond(
                    ProjetoDetalheState.grupos.length() > 0,
                    rx.vstack(
                        rx.foreach(ProjetoDetalheState.grupos, _grupo_recursos),
                        spacing="3",
                        width="100%",
                    ),
                    _vazio("Nenhum recurso registrado ainda."),
                ),
            ),
        ),
        spacing="3",
        width="100%",
    )


def _bloco_sem_responsavel() -> rx.Component:
    # Critério de exibição: inventário com recursos ativos sem equipe (não o custo).
    return rx.cond(
        ProjetoDetalheState.bloco_sem_responsavel,
        rx.box(
            rx.hstack(
                rx.icon("triangle-alert", size=20, color=t.ERROR, flex_shrink="0"),
                rx.vstack(
                    rx.text("⚠️ Recursos sem responsável", font_weight="600", font_size="13px", color=t.TEXT_HIGH),
                    rx.text(ProjetoDetalheState.texto_sem_responsavel, font_size="12px", font_weight="600", color=t.TEXT_HIGH),
                    rx.text(
                        "Estes recursos já pertencem ao projeto, mas não têm tag de equipe (EQP) atribuída. "
                        "Sem equipe, não há como saber quem gerou o custo (chargeback).",
                        font_size="12px",
                        color=t.TEXT_MED,
                    ),
                    rx.cond(
                        ProjetoDetalheState.sem_responsavel_custo_texto != "",
                        rx.text(
                            ProjetoDetalheState.sem_responsavel_custo_texto,
                            font_size="13px",
                            font_weight="700",
                            color="#fb923c",
                        ),
                        rx.fragment(),
                    ),
                    spacing="1",
                    align="start",
                ),
                rx.spacer(),
                rx.button(
                    rx.icon("mail", size=14),
                    "Notificar DevOps",
                    disabled=True,
                    variant="surface",
                    color_scheme="yellow",
                    size="2",
                ),
                width="100%",
                align="center",
            ),
            background="rgba(239, 68, 68, 0.08)",
            border="1px solid rgba(239, 68, 68, 0.25)",
            border_left=f"4px solid {t.ERROR}",
            border_radius="10px",
            padding="16px",
            width="100%",
        ),
        rx.fragment(),
    )


def _conteudo() -> rx.Component:
    return rx.vstack(
        _breadcrumb(),
        _cabecalho(),
        rx.grid(
            _card_custo(),
            _card_orcamento(),
            columns="2",
            spacing="4",
            width="100%",
        ),
        _bloco_equipes(),
        rx.box(
            _bloco_recursos(),
            width="100%",
        ),
        _bloco_sem_responsavel(),
        spacing="5",
        width="100%",
    )


def _nao_encontrado() -> rx.Component:
    return rx.vstack(
        rx.icon("folder-x", size=32, color=t.TEXT_LOW),
        rx.text("Projeto não encontrado.", color=t.TEXT_MED, size="4"),
        rx.link(
            rx.hstack(rx.icon("arrow-left", size=14), rx.text("Voltar para Projetos"), spacing="1"),
            href="/projetos",
            color=t.PRIMARY_ACCENT,
        ),
        align="center",
        spacing="3",
        padding_y="8",
        width="100%",
    )


def projeto_detalhe_page() -> rx.Component:
    content = rx.box(
        rx.cond(
            ProjetoDetalheState.carregando,
            rx.center(rx.spinner(size="3"), padding_y="8"),
            rx.cond(
                ProjetoDetalheState.nao_encontrado,
                _nao_encontrado(),
                rx.cond(
                    ProjetoDetalheState.erro != "",
                    rx.callout(ProjetoDetalheState.erro, color_scheme="red", size="1", width="100%"),
                    _conteudo(),
                ),
            ),
        ),
        padding=["24px", "32px", "48px"],
        width="100%",
    )
    return app_shell(content, active="projetos")

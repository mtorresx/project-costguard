"""Página pública do CostGuard. A sessão existente segue para o painel."""

import os

import reflex as rx
from reflex_components_core.el.element import Element

from .. import theme as t
from ..state import AuthState

# Destino dos botões de acesso. Lida na compilação do frontend. Em produção a
# landing e o app ficam em origens diferentes (a sessão vive no sessionStorage
# de cada origem), então o valor é a URL absoluta do login do app.
_URL_LOGIN = os.getenv("COSTGUARD_LOGIN_URL", "").strip() or "/login"

_PROVEDORES = (
    ("aws", "AWS", ("Amazon Simple Storage Service", "AWS Lambda", "Amazon EC2",
                    "Amazon RDS", "Amazon DynamoDB", "Amazon Elastic Block Store")),
    ("azure", "Azure", ("Storage/Blob", "Functions", "Virtual Machines", "SQL Database",
                        "Cosmos DB", "Managed Disks")),
    ("google", "Google Cloud", ("Compute", "Databases", "Cloud Storage",
                                "Cloud Run", "Cloud SQL", "Hyperdisk")),
    ("oracle", "Oracle Cloud", ("Object Storage", "Functions", "Compute",
                                "Autonomous Database", "NoSQL Database", "Block Volume")),
)

_NOTA_DE_MARCAS = (
    "AWS e os ícones de serviços da AWS são marcas da Amazon.com, Inc. ou de suas afiliadas. "
    "Azure, Google Cloud e Oracle Cloud são marcas de seus respectivos titulares. "
    "Os ícones de serviços da AWS e de outros provedores pertencem aos respectivos titulares "
    "e são usados conforme os termos de cada fornecedor. "
    "O CostGuard é um projeto acadêmico independente, sem vínculo, patrocínio ou endosso."
)


class LandingState(rx.State):
    @rx.event
    async def entrar_se_autenticado(self):
        # A validação da sessão permanece no on_load de /inicio.
        auth = await self.get_state(AuthState)
        if auth.is_authenticated:
            return rx.redirect("/inicio")


def _marca() -> rx.Component:
    return rx.el.a(
        rx.image(src="/logo-costguard.svg", alt="", width="30px", height="30px"),
        "CostGuard",
        href="#topo",
        class_name="cg-marca",
        aria_label="CostGuard, voltar ao topo",
    )


def _acesso(texto: str, discreto: bool = False) -> rx.Component:
    return rx.link(
        texto,
        rx.icon("arrow-right", size=16, aria_hidden="true"),
        href=_URL_LOGIN,
        reload_document=True,
        class_name="cg-acesso discreto" if discreto else "cg-acesso",
    )


def _cabecalho() -> rx.Component:
    return rx.el.header(
        rx.el.div(
            _marca(),
            rx.el.nav(
                rx.el.a("Quem somos", href="#quem-somos"),
                rx.el.a("O que fazemos", href="#o-que-fazemos"),
                rx.el.a("Provedores", href="#provedores"),
                aria_label="Navegação principal",
            ),
            _acesso("Entrar", discreto=True),
            class_name="cg-largura cg-navegacao",
        ),
        class_name="cg-cabecalho",
    )


class _CenaScroll(Element):
    """Elemento da landing que acompanha montagem e desmontagem no navegador."""

    tag = "cg-cena-scroll"


def _camada(indice: int) -> rx.Component:
    return rx.el.div(
        rx.el.div(
            rx.html(
                '<svg viewBox="0 0 148 148" focusable="false">'
                '<use href="/camadas-costguard.svg#gravura"/></svg>'
            ),
            class_name="cg-placa",
        ),
        class_name="cg-nivel",
        style={"--nivel": 1.5 - indice},
    )


def _abas(local: str) -> rx.Component:
    return rx.el.div(
        *(rx.el.button(
            rx.el.img(src="/nuvem-neutra.svg", alt="", width=18, height=18),
            rx.el.span(nome), rx.el.small("Disponível" if chave == "aws" else "No roadmap"),
            type="button", role="tab", id=f"aba-{local}-{chave}",
            aria_selected="true" if chave == "aws" else "false",
            aria_controls=f"painel-{local}-{chave}", tab_index=0 if chave == "aws" else -1,
            custom_attrs={"data-provedor": chave},
        ) for chave, nome, _ in _PROVEDORES),
        role="tablist", aria_label="Provedores da cena" if local == "cena" else "Provedores",
        aria_orientation="vertical", class_name=f"cg-abas cg-abas-{local}",
    )


def _paineis(local: str) -> rx.Component:
    return rx.el.div(
        *(rx.el.section(
            rx.el.h3("Serviços AWS que o CostGuard acompanha hoje" if chave == "aws" else
                     "Serviços previstos no roadmap. O CostGuard ainda não lê este provedor."),
            rx.el.ul(*(rx.el.li(servico) for servico in servicos)),
            role="tabpanel", tab_index=0, id=f"painel-{local}-{chave}",
            aria_labelledby=f"aba-{local}-{chave}", hidden=chave != "aws",
            custom_attrs={"data-servicos": chave},
        ) for chave, _, servicos in _PROVEDORES),
        class_name=f"cg-servicos cg-servicos-{local}",
    )


def _ilustracao() -> rx.Component:
    return rx.el.figure(
        rx.el.div(
            rx.icon("layers", size=17),
            "Visão por projeto",
            class_name="cg-figura-topo",
        ),
        _CenaScroll.create(
            rx.el.div(
                rx.el.div(
                    rx.el.div(
                        *(_camada(i) for i in range(len(_PROVEDORES))),
                        class_name="cg-pilha",
                    ),
                    class_name="cg-volume",
                    aria_hidden="true",
                ),
                rx.image(src="/logo-costguard.svg", alt="", class_name="cg-escudo"),
                _abas("cena"),
                class_name="cg-quadro",
            ),
            _paineis("cena"),
            class_name="cg-cena",
        ),
        rx.el.figcaption(
            rx.icon("scan-line", size=16),
            rx.el.div(*(
                rx.el.span(rotulo) for rotulo in (
                    "Custos por projeto e equipe", "Engenharia e finanças",
                    "Classificação por tags", "Orçamento mensal", "Alertas de custo",
                    "Disponibilidade dos provedores", "Visão consolidada",
                )
            ), class_name="cg-legendas"),
            aria_hidden="true",
        ),
        class_name="cg-figura",
    )


def _hero() -> rx.Component:
    return rx.el.section(
        rx.el.p("FinOps", class_name="cg-sobretitulo"),
        rx.el.h1("Custos de nuvem,", rx.el.span("por projeto e equipe.")),
        rx.el.p(
            "Identifique quem responde pelos gastos e compare o consumo de cada "
            "projeto com o orçamento do mês. Hoje, a leitura dos custos é feita na AWS.",
            class_name="cg-intro",
        ),
        rx.el.div(
            _acesso("Começar agora"),
            rx.el.a(
                "Ver como funciona", rx.icon("arrow-down", size=16, aria_hidden="true"),
                href="#o-que-fazemos", class_name="cg-link-secao",
            ),
            class_name="cg-acoes",
        ),
        id="topo", class_name="cg-hero", custom_attrs={"data-passo": "hero"},
    )


def _quem_somos() -> rx.Component:
    return rx.el.section(
        rx.el.p("Quem somos", class_name="cg-sobretitulo"),
        rx.el.h2("Uma visão comum para engenharia e finanças."),
        rx.el.p(
            "As tags ligam cada gasto de nuvem ao trabalho que o gerou. "
            "Quem cuida da infraestrutura e quem acompanha o orçamento "
            "podem consultar os mesmos custos por projeto e equipe."
        ),
        rx.el.p(
            rx.icon("shield-check", size=18, aria_hidden="true"),
            "Conexão com a AWS somente para leitura", class_name="cg-nota",
        ),
        id="quem-somos", class_name="cg-sobre", custom_attrs={"data-passo": "sobre"},
    )


def _recurso(passo: str, icone: str, titulo: str, descricao: str) -> rx.Component:
    return rx.el.article(
        rx.icon(icone, size=23, stroke_width=1.6, aria_hidden="true"),
        rx.el.div(rx.el.h3(titulo), rx.el.p(descricao)),
        custom_attrs={"data-passo": passo},
    )


def _recursos() -> rx.Component:
    return rx.el.section(
        rx.el.p("O que fazemos", class_name="cg-sobretitulo"),
        rx.el.h2("Da origem do gasto ao orçamento."),
        rx.el.div(
            _recurso(
                "tags", "tags", "Atribuição por tags",
                "A tag PRJ identifica o projeto e a EQP identifica a equipe. Recursos sem projeto "
                "válido aparecem como não classificados.",
            ),
            _recurso(
                "orcamento", "wallet", "Orçamento mensal",
                "Compare o consumo de cada projeto com o orçamento do mês. "
                "Consulte o histórico e o detalhamento por equipe.",
            ),
            _recurso(
                "alertas", "bell", "Alertas de custo",
                "Acompanhe os limites de 70%, 90% e 100% do orçamento, "
                "os recursos sem classificação e as falhas de importação.",
            ),
            id="recursos", class_name="cg-recursos-grade",
        ),
        id="o-que-fazemos", class_name="cg-recursos",
    )


def _provedores() -> rx.Component:
    return rx.el.section(
        rx.el.h2("Provedores"),
        rx.el.p("A leitura de custos está disponível hoje somente para a AWS."),
        _abas("lista"),
        _paineis("lista"),
        id="provedores", class_name="cg-provedores", custom_attrs={"data-passo": "provedores"},
    )


def landing_page() -> rx.Component:
    return rx.el.div(
        rx.script(src="/landing-scroll.js", defer=True),
        rx.el.a("Pular para o conteúdo", href="#conteudo", class_name="cg-pular"),
        _cabecalho(),
        rx.el.main(
            _hero(),
            _ilustracao(),
            _quem_somos(),
            _recursos(),
            _provedores(),
            rx.el.section(
                rx.el.h2("Acompanhe os custos da sua organização."),
                _acesso("Acessar o CostGuard"),
                class_name="cg-convite", custom_attrs={"data-passo": "final"},
            ),
            id="conteudo", class_name="cg-largura cg-historia", tab_index=-1,
        ),
        rx.el.footer(
            _marca(),
            rx.el.small(_NOTA_DE_MARCAS, class_name="cg-nota-marcas"),
            rx.el.small("© 2026 CostGuard"),
            class_name="cg-largura cg-rodape",
        ),
        class_name="cg-landing",
        lang="pt-BR",
        style={
            "--lp-bg": t.LANDING_BG,
            "--lp-surface": t.BG,
            "--lp-text": t.LANDING_TEXT,
            "--lp-secondary": t.LANDING_MUTED_LIGHT,
            "--lp-muted": t.LANDING_MUTED,
            "--lp-accent": t.LANDING_ACCENT,
            "--lp-accent-text": t.LANDING_ACCENT_TEXT,
            "--lp-line": t.LANDING_BORDER,
            "--lp-soft-line": t.LANDING_BORDER_SOFT,
        },
        on_mount=LandingState.entrar_se_autenticado,
    )

"""Aplicação CostGuard (Reflex).

Rotas:
- /          : landing page pública.
- /login     : página pública de login; após o login, animação de entrada.
- /inicio    : dashboard autenticado (dados reais do Xano).
- /projetos  : projetos (dados reais do Xano).
- /projetos/[projeto_id]: detalhamento de projeto (dados reais do Xano).
- /provedores: provedores (dados reais do Xano).
- /alertas   : alertas e recursos não classificados (dados reais do Xano).
- /usuarios  : gestão de usuários (dados reais do Xano, admin).

Todas as rotas além de / e /login exigem sessão autenticada: `on_load=require_auth`
valida o token no backend via /me (ver state.py). A autorização real permanece
no Xano; o frontend não é mecanismo de segurança.

Design, componentes e assets incorporados do frontend externo; a autenticação é a do projeto principal
(AuthState).
"""

import reflex as rx

from .pages.alertas import alertas_page
from .pages.alertas_state import AlertasState
from .components.splash import SplashState, splash_overlay
from .pages.home import home_page
from .pages.landing import landing_page
from .pages.home_state import HomeState
from .pages.login import login_page
from .pages.projeto_detalhe import projeto_detalhe_page
from .pages.projeto_detalhe_state import ProjetoDetalheState
from .pages.projetos import projetos_page
from .pages.projetos_state import ProjetosState
from .pages.provedores import provedores_page
from .pages.provedores_state import ProvedoresState
from .pages.usuarios_state import UsuariosState
from .pages.usuarios import usuarios_page
from .sincronizacao_auto import AcompanhamentoState, laco_sincronizacao
from .state import AuthState

app = rx.App(
    stylesheets=["/costguard.css"],
    # Favicon em todas as páginas; /favicon.ico (assets/) segue como fallback.
    head_components=[
        rx.el.link(rel="icon", type="image/svg+xml", href="/favicon.svg"),
        rx.el.link(rel="icon", type="image/png", sizes="32x32", href="/favicon-32x32.png"),
        rx.el.link(rel="apple-touch-icon", sizes="180x180", href="/apple-touch-icon.png"),
    ],
)

# Animação de entrada (pós-login): montada acima das rotas para sobreviver à troca de
# rota para o painel (ver components/splash.py).
app.extra_app_wraps[(3, "Splash")] = lambda _stateful: rx.fragment(splash_overlay())

# Sincronização automática do inventário: só dispara o endpoint do Xano; desligada
# por padrão (COSTGUARD_SYNC_ATIVO=1 liga; ver sincronizacao_auto.py).
app.register_lifespan_task(laco_sincronizacao)

# Landing page pública.
app.add_page(
    landing_page,
    route="/",
    title="CostGuard — Custos de nuvem por projeto e equipe",
    description="Atribuição de custos da AWS por projeto e equipe, orçamento mensal e alertas.",
)

# Página pública de login.
app.add_page(login_page, route="/login", title="Login — CostGuard")

# Área autenticada: cada página valida a sessão no carregamento.
app.add_page(
    home_page,
    route="/inicio",
    title="Início — CostGuard",
    # O último evento avisa a animação de entrada que o painel já carregou.
    on_load=[
        AuthState.require_auth,
        HomeState.carregar,
        SplashState.marcar_painel_pronto,
        AcompanhamentoState.acompanhar,
    ],
)
app.add_page(
    projetos_page,
    route="/projetos",
    title="Projetos — CostGuard",
    on_load=[AuthState.require_auth, ProjetosState.carregar],
)
app.add_page(
    projeto_detalhe_page,
    route="/projetos/[projeto_id]",
    title="Detalhamento do Projeto — CostGuard",
    on_load=[AuthState.require_auth, ProjetoDetalheState.carregar, AcompanhamentoState.acompanhar],
)
app.add_page(
    provedores_page,
    route="/provedores",
    title="Provedores — CostGuard",
    on_load=[AuthState.require_auth, ProvedoresState.carregar, AcompanhamentoState.acompanhar],
)
app.add_page(
    alertas_page,
    route="/alertas",
    title="Alertas — CostGuard",
    on_load=[AuthState.require_auth, AlertasState.carregar, AcompanhamentoState.acompanhar],
)
app.add_page(
    usuarios_page,
    route="/usuarios",
    title="Usuários — CostGuard",
    on_load=[AuthState.require_auth, UsuariosState.carregar],
)

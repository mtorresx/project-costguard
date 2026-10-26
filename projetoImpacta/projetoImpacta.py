"""Aplicação CostGuard (Reflex).

Rotas:
- /login     : página pública de login (único público).
- /          : home autenticada (área principal).
- /projetos  : projetos (dados reais do Xano).
- /projetos/[projeto_id]: detalhamento de projeto (dados reais do Xano).
- /provedores: provedores (dados reais do Xano).
- /alertas   : alertas (apresentação/mock).
- /usuarios  : usuários (apresentação/mock).

Todas as rotas além de /login exigem sessão autenticada: `on_load=require_auth`
valida o token no backend via /me (ver state.py). A autorização real permanece
no Xano; o frontend não é mecanismo de segurança.

Design, componentes e assets incorporados do frontend externo (ver change
integracao-frontend); a autenticação é a do projeto principal (AuthState).
"""

import reflex as rx

from .pages.alertas import alertas_page
from .pages.home import home_page
from .pages.login import login_page
from .pages.projeto_detalhe import projeto_detalhe_page
from .pages.projeto_detalhe_state import ProjetoDetalheState
from .pages.projetos import projetos_page
from .pages.projetos_state import ProjetosState
from .pages.provedores import provedores_page
from .pages.provedores_state import ProvedoresState
from .pages.usuarios import usuarios_page
from .state import AuthState

app = rx.App(
    stylesheets=["/costguard.css"],
)

# Página pública de login.
app.add_page(login_page, route="/login", title="Login — CostGuard")

# Área autenticada: cada página valida a sessão no carregamento.
app.add_page(home_page, route="/", title="CostGuard", on_load=AuthState.require_auth)
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
    on_load=[AuthState.require_auth, ProjetoDetalheState.carregar],
)
app.add_page(
    provedores_page,
    route="/provedores",
    title="Provedores — CostGuard",
    on_load=[AuthState.require_auth, ProvedoresState.carregar],
)
app.add_page(alertas_page, route="/alertas", title="Alertas — CostGuard", on_load=AuthState.require_auth)
app.add_page(usuarios_page, route="/usuarios", title="Usuários — CostGuard", on_load=AuthState.require_auth)

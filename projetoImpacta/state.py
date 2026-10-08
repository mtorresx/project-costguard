"""Estado de autenticação do CostGuard (frontend Reflex).

Responsabilidades do frontend (ver design D2–D8):
- manter a sessão autenticada (token, username, role) em rx.SessionStorage,
  de modo que o reload mantenha a sessão e o fechamento do navegador a descarte;
- enviar credenciais ao backend Xano e armazenar o token em caso de sucesso;
- enviar o token nas requisições autenticadas (Authorization: Bearer);
- obter username e role via /me;
- tratar HTTP 401 de forma centralizada, limpando a sessão;
- oferecer logout local.

O frontend NÃO é mecanismo de segurança. A validação de credenciais e a
autorização real permanecem no backend Xano. O password nunca é persistido
nem registrado em log pelo frontend.
"""

from __future__ import annotations

import httpx
import reflex as rx

from .config import get_xano_base_url

# Mensagem genérica de falha de autenticação — não revela se a conta existe.
_ERRO_LOGIN_GENERICO = "Usuário ou senha inválidos."


class AuthState(rx.State):
    """Sessão autenticada mantida no cliente.

    `token`, `username` e `role` usam rx.SessionStorage: sobrevivem ao reload da
    página e são limpos quando a aba/navegador é fechado (comportamento de sessão
    aprovado em D3).
    """

    # Dados de sessão persistidos no sessionStorage do navegador.
    token: str = rx.SessionStorage("", name="costguard_token")
    username: str = rx.SessionStorage("", name="costguard_username")
    role: str = rx.SessionStorage("", name="costguard_role")

    # Estado transitório da tela de login (não persistido).
    login_error: str = ""
    is_loading: bool = False

    @rx.var
    def is_authenticated(self) -> bool:
        """Indica se há uma sessão autenticada no cliente."""
        return self.token != ""

    @rx.var
    def is_admin(self) -> bool:
        """Derivado da role atual (apenas apresentação; autorização real é no Xano)."""
        return self.role == "admin"

    @rx.var
    def initial(self) -> str:
        """Inicial do username para o avatar da interface."""
        return self.username[:1].upper() if self.username else "?"

    def _clear_session(self) -> None:
        """Descarta a sessão local (token e identidade)."""
        self.token = ""
        self.username = ""
        self.role = ""

    @rx.event
    async def do_login(self, form_data: dict):
        """Envia {username, password} ao Xano e estabelece a sessão.

        O password é usado apenas nesta chamada e nunca é persistido nem logado.
        """
        username = (form_data.get("username") or "").strip()
        password = form_data.get("password") or ""

        self.login_error = ""
        self.is_loading = True
        yield

        if not username or not password:
            self.is_loading = False
            self.login_error = _ERRO_LOGIN_GENERICO
            return

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{get_xano_base_url()}/login",
                    json={"username": username, "password": password},
                )
        except Exception:
            # Falha de rede/configuração: não vaza detalhes nem o password.
            self.is_loading = False
            self.login_error = "Não foi possível conectar ao servidor."
            return

        # O backend padroniza a emissão: sucesso traz um token.
        token = ""
        if resp.status_code == 200:
            try:
                data = resp.json()
            except Exception:
                data = {}
            token = data.get("token") or ""

        if not token:
            # Credenciais inválidas (ou qualquer erro de login): mensagem genérica.
            self.is_loading = False
            self.login_error = _ERRO_LOGIN_GENERICO
            return

        self.token = token
        self.is_loading = False
        # Resolve username/role no backend e encaminha para a área autenticada.
        # do_login é um async generator (usa yield), então encadeia o próximo
        # evento com yield em vez de return.
        yield AuthState.load_me

    @rx.event
    async def load_me(self):
        """Confirma o token e obtém username/role via /me (fonte de verdade: backend)."""
        if not self.token:
            return AuthState.handle_unauthenticated

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"{get_xano_base_url()}/me",
                    headers={"Authorization": f"Bearer {self.token}"},
                )
        except Exception:
            # Sem conseguir validar, trata como não autenticado (sem vazar detalhe).
            return AuthState.handle_unauthenticated

        if resp.status_code == 401:
            # Tratamento centralizado de 401: limpa a sessão.
            return AuthState.handle_unauthenticated

        if resp.status_code != 200:
            return AuthState.handle_unauthenticated

        try:
            data = resp.json()
        except Exception:
            data = {}

        self.username = data.get("username") or ""
        self.role = data.get("role") or ""
        return rx.redirect("/")

    @rx.event
    def handle_unauthenticated(self):
        """Ponto único de reação a sessão inválida/401: limpa e vai ao login."""
        self._clear_session()
        return rx.redirect("/login")

    @rx.event
    async def require_auth(self):
        """on_load da área protegida: valida o token no backend via /me.

        Não confia apenas na presença do token/username/role no SessionStorage:
        - sem token -> não autenticado, redireciona a /login;
        - com token -> GET /me com Authorization: Bearer; 200 atualiza
          username/role e mantém a sessão (permanece em /); 401/erro limpa a
          sessão e redireciona a /login.
        """
        if not self.token:
            return AuthState.handle_unauthenticated

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"{get_xano_base_url()}/me",
                    headers={"Authorization": f"Bearer {self.token}"},
                )
        except Exception:
            # Sem conseguir validar, trata como não autenticado.
            return AuthState.handle_unauthenticated

        if resp.status_code != 200:
            # 401 (token adulterado/expirado) ou qualquer outra falha: limpa.
            return AuthState.handle_unauthenticated

        try:
            data = resp.json()
        except Exception:
            data = {}

        # Sessão válida: atualiza identidade a partir do backend e permanece em /.
        self.username = data.get("username") or ""
        self.role = data.get("role") or ""

    @rx.event
    def logout(self):
        """Logout local: descarta a sessão e volta ao login."""
        self._clear_session()
        return rx.redirect("/login")

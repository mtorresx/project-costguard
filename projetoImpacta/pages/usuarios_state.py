"""Estado da página de Usuários — gestão de usuários pelo admin (api_group `app`).

A autorização real é do Xano (admin ativo). Este estado só reflete as respostas:
401 encerra a sessão; 403 mostra o aviso de acesso restrito, sem dados.
A senha digitada no formulário é enviada uma única vez e descartada em seguida.
"""

from __future__ import annotations

from typing import Any, TypedDict

import reflex as rx

from ..components.mensagens import sucesso

from ..api import mensagem_erro, requisitar
from ..state import AuthState

ERRO_CARREGAR = "Não foi possível carregar os usuários."
ACESSO_RESTRITO = "A gestão de usuários é restrita a administradores."


class Usuario(TypedDict):
    id: int
    nome: str
    username: str
    email: str
    role: str
    status: str
    iniciais: str


def iniciais(nome: str, username: str) -> str:
    """Até duas iniciais do nome (ou do username) para o avatar."""
    partes = [p for p in (nome or "").split() if p]
    if len(partes) >= 2:
        return (partes[0][0] + partes[-1][0]).upper()
    base = partes[0] if partes else (username or "?")
    return base[:2].upper()


def normalizar_usuario(bruto: Any) -> Usuario | None:
    """Converte um item do backend; itens fora do contrato são descartados."""
    if not isinstance(bruto, dict) or not isinstance(bruto.get("id"), int):
        return None
    nome = str(bruto.get("nome") or "")
    username = str(bruto.get("username") or "")
    role = bruto.get("role") if bruto.get("role") in ("admin", "leitura") else "leitura"
    status = bruto.get("status") if bruto.get("status") in ("ativo", "inativo") else "inativo"
    return {
        "id": bruto["id"],
        "nome": nome,
        "username": username,
        "email": str(bruto.get("email") or ""),
        "role": role,
        "status": status,
        "iniciais": iniciais(nome, username),
    }


def filtrar(usuarios: list[Usuario], termo: str) -> list[Usuario]:
    termo = (termo or "").strip().lower()
    if not termo:
        return usuarios
    return [
        u for u in usuarios
        if termo in u["nome"].lower() or termo in u["username"].lower() or termo in u["email"].lower()
    ]


class UsuariosState(rx.State):
    usuarios: list[Usuario] = []
    loading: bool = False
    error_message: str = ""
    acesso_negado: bool = False
    busca: str = ""

    # Formulário de criar/editar.
    form_aberto: bool = False
    form_modo: str = "criar"  # "criar" | "editar"
    form_id: int = 0
    form_nome: str = ""
    form_username: str = ""
    form_email: str = ""
    form_role: str = "leitura"
    form_senha: str = ""
    form_error: str = ""
    form_loading: bool = False

    # Diálogo de definição de senha.
    senha_aberto: bool = False
    senha_id: int = 0
    senha_nome: str = ""
    senha_valor: str = ""
    senha_error: str = ""
    senha_loading: bool = False

    @rx.var
    def usuarios_filtrados(self) -> list[Usuario]:
        return filtrar(self.usuarios, self.busca)

    @rx.var
    def total_usuarios(self) -> int:
        return len(self.usuarios)

    @rx.var
    def total_admins(self) -> int:
        return len([u for u in self.usuarios if u["role"] == "admin"])

    @rx.var
    def total_ativos(self) -> int:
        return len([u for u in self.usuarios if u["status"] == "ativo"])

    async def _token(self) -> str:
        return (await self.get_state(AuthState)).token

    @rx.event
    def set_busca(self, valor: str):
        self.busca = valor

    @rx.event
    async def carregar(self):
        token = await self._token()
        if not token:
            yield AuthState.handle_unauthenticated
            return
        self.loading = True
        self.error_message = ""
        self.acesso_negado = False
        yield
        status, corpo = await requisitar("GET", "/usuarios", token)
        self.loading = False
        if status == 401:
            yield AuthState.handle_unauthenticated
            return
        if status == 403:
            self.usuarios = []
            self.acesso_negado = True
            return
        if status != 200 or not isinstance(corpo, list):
            self.usuarios = []
            self.error_message = mensagem_erro(corpo, ERRO_CARREGAR) if status else ERRO_CARREGAR
            return
        self.usuarios = [u for u in (normalizar_usuario(b) for b in corpo) if u is not None]

    # ---- Formulário criar/editar ----

    @rx.event
    def abrir_criar(self):
        self.form_modo = "criar"
        self.form_id = 0
        self.form_nome = ""
        self.form_username = ""
        self.form_email = ""
        self.form_role = "leitura"
        self.form_senha = ""
        self.form_error = ""
        self.form_aberto = True

    @rx.event
    def abrir_editar(self, usuario: Usuario):
        self.form_modo = "editar"
        self.form_id = usuario["id"]
        self.form_nome = usuario["nome"]
        self.form_username = usuario["username"]
        self.form_email = usuario["email"]
        self.form_role = usuario["role"]
        self.form_senha = ""
        self.form_error = ""
        self.form_aberto = True

    @rx.event
    def fechar_form(self):
        self.form_aberto = False
        self.form_senha = ""

    @rx.event
    def set_form_nome(self, v: str):
        self.form_nome = v
        self.form_error = ""

    @rx.event
    def set_form_username(self, v: str):
        self.form_username = v
        self.form_error = ""

    @rx.event
    def set_form_email(self, v: str):
        self.form_email = v
        self.form_error = ""

    @rx.event
    def set_form_role(self, v: str):
        self.form_role = v

    @rx.event
    def set_form_senha(self, v: str):
        self.form_senha = v
        self.form_error = ""

    @rx.event
    async def salvar(self):
        token = await self._token()
        self.form_loading = True
        self.form_error = ""
        yield
        if self.form_modo == "criar":
            corpo = {
                "nome": self.form_nome.strip(),
                "username": self.form_username.strip(),
                "email": self.form_email.strip(),
                "role": self.form_role,
                "senha": self.form_senha,
            }
            status, resp = await requisitar("POST", "/usuarios", token, corpo)
            # A senha é usada uma única vez: descartada em qualquer resultado.
            self.form_senha = ""
        else:
            corpo = {"nome": self.form_nome.strip(), "email": self.form_email.strip(), "role": self.form_role}
            status, resp = await requisitar("PATCH", f"/usuarios/{self.form_id}", token, corpo)
        self.form_loading = False
        if status == 401:
            yield AuthState.handle_unauthenticated
            return
        if status != 200:
            self.form_error = mensagem_erro(resp, "Não foi possível salvar o usuário.")
            return
        self.form_aberto = False
        self.form_senha = ""
        yield sucesso("Usuário criado." if self.form_modo == "criar" else "Usuário atualizado.")
        yield UsuariosState.carregar

    # ---- Definição de senha ----

    @rx.event
    def abrir_senha(self, usuario: Usuario):
        self.senha_id = usuario["id"]
        self.senha_nome = usuario["nome"] or usuario["username"]
        self.senha_valor = ""
        self.senha_error = ""
        self.senha_aberto = True

    @rx.event
    def fechar_senha(self):
        self.senha_aberto = False
        self.senha_valor = ""

    @rx.event
    def set_senha_valor(self, v: str):
        self.senha_valor = v
        self.senha_error = ""

    @rx.event
    async def salvar_senha(self):
        token = await self._token()
        self.senha_loading = True
        self.senha_error = ""
        yield
        status, resp = await requisitar("POST", f"/usuarios/{self.senha_id}/senha", token, {"senha": self.senha_valor})
        self.senha_valor = ""  # descartada em qualquer resultado
        self.senha_loading = False
        if status == 401:
            yield AuthState.handle_unauthenticated
            return
        if status != 200:
            self.senha_error = mensagem_erro(resp, "Não foi possível definir a senha.")
            return
        self.senha_aberto = False
        self.senha_valor = ""
        yield sucesso("Nova senha definida.")

    # ---- Desativar / reativar ----

    @rx.event
    async def alternar_status(self, usuario: Usuario):
        token = await self._token()
        acao = "desativar" if usuario["status"] == "ativo" else "reativar"
        self.error_message = ""
        status, resp = await requisitar("POST", f"/usuarios/{usuario['id']}/{acao}", token, {})
        if status == 401:
            yield AuthState.handle_unauthenticated
            return
        if status != 200:
            self.error_message = mensagem_erro(resp, f"Não foi possível {acao} o usuário.")
            return
        yield sucesso("Usuário desativado." if acao == "desativar" else "Usuário reativado.")
        yield UsuariosState.carregar

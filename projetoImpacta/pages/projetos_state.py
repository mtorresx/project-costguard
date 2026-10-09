"""Estado da página de Projetos — consome o backend Xano (api_group `app`).

Segue o padrão do `AuthState`: envia `Authorization: Bearer <token>` e, em HTTP
401, delega ao tratamento central de sessão (`AuthState.handle_unauthenticated`).
Não calcula custo consumido nem percentual de orçamento (não existem no backend).
"""

from __future__ import annotations

from typing import TypedDict

import httpx
import reflex as rx

from ..config import get_xano_app_base_url
from ..state import AuthState


class Projeto(TypedDict):
    id: int
    nome: str
    codigo: str
    budget: float
    status: str


def _normalizar(bruto: dict) -> Projeto:
    try:
        budget = float(bruto.get("budget") or 0)
    except (TypeError, ValueError):
        budget = 0.0
    return {
        "id": bruto.get("id", 0),
        "nome": bruto.get("nome") or "",
        "codigo": bruto.get("codigo") or "",
        "budget": budget,
        "status": bruto.get("status") or "ativo",
    }


class ProjetosState(rx.State):
    """Lista de projetos reais e o formulário de criação/edição (admin)."""

    projetos: list[Projeto] = []
    loading: bool = False
    error_message: str = ""

    # Formulário (criar/editar).
    form_aberto: bool = False
    form_modo: str = "criar"  # "criar" | "editar"
    form_id: int = 0
    form_nome: str = ""
    form_codigo: str = ""
    form_budget: str = ""
    form_error: str = ""
    form_loading: bool = False

    async def _auth(self) -> AuthState:
        return await self.get_state(AuthState)

    @rx.event
    async def carregar(self):
        """on_load: carrega a lista real do backend."""
        auth = await self._auth()
        if not auth.token:
            # carregar é async generator (usa yield): encadear eventos com yield.
            yield AuthState.handle_unauthenticated
            return

        self.loading = True
        self.error_message = ""
        yield

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"{get_xano_app_base_url()}/projetos",
                    headers={"Authorization": f"Bearer {auth.token}"},
                )
        except Exception:
            self.loading = False
            self.error_message = "Não foi possível carregar os projetos."
            return

        if resp.status_code == 401:
            self.loading = False
            yield AuthState.handle_unauthenticated
            return
        if resp.status_code != 200:
            self.loading = False
            self.error_message = "Não foi possível carregar os projetos."
            return

        try:
            dados = resp.json()
        except Exception:
            dados = []
        self.projetos = [_normalizar(p) for p in dados if isinstance(p, dict)]
        self.loading = False

    @rx.event
    def abrir_criar(self):
        self.form_modo = "criar"
        self.form_id = 0
        self.form_nome = ""
        self.form_codigo = ""
        self.form_budget = ""
        self.form_error = ""
        self.form_aberto = True

    @rx.event
    def abrir_editar(self, projeto: Projeto):
        self.form_modo = "editar"
        self.form_id = projeto["id"]
        self.form_nome = projeto["nome"]
        self.form_codigo = projeto["codigo"]
        self.form_budget = str(projeto["budget"])
        self.form_error = ""
        self.form_aberto = True

    @rx.event
    def fechar_form(self):
        self.form_aberto = False

    @rx.event
    def set_form_nome(self, v: str):
        self.form_nome = v
        self.form_error = ""

    @rx.event
    def set_form_codigo(self, v: str):
        self.form_codigo = v.upper().strip().replace(" ", "_")
        self.form_error = ""

    @rx.event
    def set_form_budget(self, v: str):
        self.form_budget = v
        self.form_error = ""

    @rx.event
    async def salvar(self):
        """Cria ou edita o projeto (admin). Validações finais são do backend."""
        auth = await self._auth()
        if not auth.token:
            return AuthState.handle_unauthenticated

        # Validação leve no cliente (apenas UX; o backend é autoritativo).
        if self.form_modo == "criar" and not self.form_codigo.strip():
            self.form_error = "Informe o código do projeto."
            return
        if not self.form_nome.strip():
            self.form_error = "Informe o nome do projeto."
            return
        try:
            budget = float(self.form_budget.replace(",", "."))
        except ValueError:
            self.form_error = "Informe um orçamento válido (número)."
            return
        if budget < 0:
            self.form_error = "O orçamento deve ser maior ou igual a zero."
            return

        self.form_loading = True
        self.form_error = ""
        base = get_xano_app_base_url()
        headers = {"Authorization": f"Bearer {auth.token}"}

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                if self.form_modo == "criar":
                    resp = await client.post(
                        f"{base}/projetos",
                        json={"nome": self.form_nome.strip(), "codigo": self.form_codigo.strip(), "budget": budget},
                        headers=headers,
                    )
                else:
                    resp = await client.patch(
                        f"{base}/projetos/{self.form_id}",
                        json={"nome": self.form_nome.strip(), "budget": budget},
                        headers=headers,
                    )
        except Exception:
            self.form_loading = False
            self.form_error = "Não foi possível salvar o projeto."
            return

        self.form_loading = False
        if resp.status_code == 401:
            return AuthState.handle_unauthenticated
        if resp.status_code not in (200, 201):
            self.form_error = _mensagem_erro(resp)
            return

        self.form_aberto = False
        return ProjetosState.carregar

    @rx.event
    async def desativar(self, projeto_id: int):
        """Desativa o projeto (admin)."""
        auth = await self._auth()
        if not auth.token:
            return AuthState.handle_unauthenticated
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{get_xano_app_base_url()}/projetos/{projeto_id}/desativar",
                    headers={"Authorization": f"Bearer {auth.token}"},
                )
        except Exception:
            self.error_message = "Não foi possível desativar o projeto."
            return
        if resp.status_code == 401:
            return AuthState.handle_unauthenticated
        if resp.status_code != 200:
            self.error_message = _mensagem_erro(resp)
            return
        return ProjetosState.carregar


def _mensagem_erro(resp: httpx.Response) -> str:
    """Extrai uma mensagem de erro simples do corpo retornado pelo backend."""
    try:
        data = resp.json()
    except Exception:
        return "Operação não permitida ou inválida."
    if isinstance(data, dict):
        return data.get("message") or data.get("erro") or data.get("error") or "Operação não permitida ou inválida."
    return "Operação não permitida ou inválida."

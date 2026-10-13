"""Estado da página de Provedores — consome o backend Xano (api_group `app`).

Segue o padrão do `ProjetosState`/`AuthState`: envia `Authorization: Bearer
<token>` e, em HTTP 401, delega ao tratamento central de sessão
(`AuthState.handle_unauthenticated`).

Segurança do segredo da credencial AWS (ver change provedor-aws-base):
- o `secret_access_key` só é mantido no State o tempo necessário para a
  submissão e é limpo após o envio;
- o segredo salvo nunca é retornado pelo backend nem reexibido na interface;
- na edição, enviar o campo do segredo vazio significa "não alterar".
"""

from __future__ import annotations

from typing import TypedDict

import httpx
import reflex as rx

from ..config import get_xano_app_base_url
from ..state import AuthState


class Provedor(TypedDict):
    id: int
    apelido: str
    tipo: str
    identificador_conta: str
    tipo_credencial: str
    status: str


def _normalizar(bruto: dict) -> Provedor:
    return {
        "id": bruto.get("id", 0),
        "apelido": bruto.get("apelido") or "",
        "tipo": bruto.get("tipo") or "aws",
        "identificador_conta": bruto.get("identificador_conta") or "",
        "tipo_credencial": bruto.get("tipo_credencial") or "aws_access_key",
        "status": bruto.get("status") or "pendente",
    }


class ProvedoresState(rx.State):
    """Lista de provedores reais e o formulário de cadastro/edição (admin)."""

    provedores: list[Provedor] = []
    loading: bool = False
    error_message: str = ""

    # id do provedor cujo teste de conexão está em andamento (0 = nenhum).
    testando_id: int = 0

    # Formulário (criar/editar).
    form_aberto: bool = False
    form_modo: str = "criar"  # "criar" | "editar"
    form_id: int = 0
    form_apelido: str = ""
    form_identificador_conta: str = ""
    form_access_key_id: str = ""
    # Segredo: só preenchido pelo usuário para submissão; nunca vem do backend.
    form_secret_access_key: str = ""
    form_error: str = ""
    form_loading: bool = False

    async def _auth(self) -> AuthState:
        return await self.get_state(AuthState)

    @rx.event
    async def carregar(self):
        """on_load: carrega a lista real do backend."""
        auth = await self._auth()
        if not auth.token:
            yield AuthState.handle_unauthenticated
            return

        self.loading = True
        self.error_message = ""
        yield

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"{get_xano_app_base_url()}/provedores",
                    headers={"Authorization": f"Bearer {auth.token}"},
                )
        except Exception:
            self.loading = False
            self.error_message = "Não foi possível carregar os provedores."
            return

        if resp.status_code == 401:
            self.loading = False
            yield AuthState.handle_unauthenticated
            return
        if resp.status_code != 200:
            self.loading = False
            self.error_message = "Não foi possível carregar os provedores."
            return

        try:
            dados = resp.json()
        except Exception:
            dados = []
        self.provedores = [_normalizar(p) for p in dados if isinstance(p, dict)]
        self.loading = False

    @rx.event
    def abrir_criar(self):
        self.form_modo = "criar"
        self.form_id = 0
        self.form_apelido = ""
        self.form_identificador_conta = ""
        self.form_access_key_id = ""
        self.form_secret_access_key = ""
        self.form_error = ""
        self.form_aberto = True

    @rx.event
    def abrir_editar(self, provedor: Provedor):
        self.form_modo = "editar"
        self.form_id = provedor["id"]
        self.form_apelido = provedor["apelido"]
        self.form_identificador_conta = provedor["identificador_conta"]
        # A listagem não retorna o Access Key ID; o campo começa vazio na edição.
        self.form_access_key_id = ""
        # O segredo salvo nunca é devolvido pelo backend: o campo começa vazio.
        self.form_secret_access_key = ""
        self.form_error = ""
        self.form_aberto = True

    @rx.event
    def fechar_form(self):
        self.form_aberto = False
        # Garante que nenhum segredo permaneça no State após fechar.
        self.form_secret_access_key = ""

    @rx.event
    def set_form_apelido(self, v: str):
        self.form_apelido = v
        self.form_error = ""

    @rx.event
    def set_form_identificador_conta(self, v: str):
        self.form_identificador_conta = v
        self.form_error = ""

    @rx.event
    def set_form_access_key_id(self, v: str):
        self.form_access_key_id = v
        self.form_error = ""

    @rx.event
    def set_form_secret_access_key(self, v: str):
        self.form_secret_access_key = v
        self.form_error = ""

    @rx.event
    async def salvar(self):
        """Cria ou edita o provedor (admin). Validações finais são do backend."""
        auth = await self._auth()
        if not auth.token:
            return AuthState.handle_unauthenticated

        # Validação leve no cliente (apenas UX; o backend é autoritativo).
        if not self.form_apelido.strip():
            self.form_error = "Informe o apelido do provedor."
            return
        if not self.form_identificador_conta.strip():
            self.form_error = "Informe o identificador da conta AWS."
            return
        if self.form_modo == "criar":
            if not self.form_access_key_id.strip():
                self.form_error = "Informe o Access Key ID."
                return
            if not self.form_secret_access_key:
                self.form_error = "Informe o Secret Access Key."
                return

        self.form_loading = True
        self.form_error = ""
        base = get_xano_app_base_url()
        headers = {"Authorization": f"Bearer {auth.token}"}

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                if self.form_modo == "criar":
                    payload = {
                        "apelido": self.form_apelido.strip(),
                        "tipo": "aws",
                        "identificador_conta": self.form_identificador_conta.strip(),
                        "aws_access_key_id": self.form_access_key_id.strip(),
                        "aws_secret_access_key": self.form_secret_access_key,
                    }
                    resp = await client.post(f"{base}/provedores", json=payload, headers=headers)
                else:
                    payload = {
                        "apelido": self.form_apelido.strip(),
                        "identificador_conta": self.form_identificador_conta.strip(),
                    }
                    # Só envia o Access Key ID se o admin informou um novo valor
                    # (vazio = preservar o existente no backend).
                    if self.form_access_key_id.strip():
                        payload["aws_access_key_id"] = self.form_access_key_id.strip()
                    # Só envia o segredo se o admin informou um novo valor.
                    if self.form_secret_access_key:
                        payload["aws_secret_access_key"] = self.form_secret_access_key
                    resp = await client.patch(f"{base}/provedores/{self.form_id}", json=payload, headers=headers)
        except Exception:
            self.form_loading = False
            self.form_secret_access_key = ""
            self.form_error = "Não foi possível salvar o provedor."
            return

        self.form_loading = False
        # Limpa o segredo do State logo após a submissão, qualquer que seja o resultado.
        self.form_secret_access_key = ""

        if resp.status_code == 401:
            return AuthState.handle_unauthenticated
        if resp.status_code not in (200, 201):
            self.form_error = _mensagem_erro(resp)
            return

        self.form_aberto = False
        return ProvedoresState.carregar

    @rx.event
    async def desativar(self, provedor_id: int):
        """Desativa o provedor (admin)."""
        auth = await self._auth()
        if not auth.token:
            return AuthState.handle_unauthenticated
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{get_xano_app_base_url()}/provedores/{provedor_id}/desativar",
                    headers={"Authorization": f"Bearer {auth.token}"},
                )
        except Exception:
            self.error_message = "Não foi possível desativar o provedor."
            return
        if resp.status_code == 401:
            return AuthState.handle_unauthenticated
        if resp.status_code != 200:
            self.error_message = _mensagem_erro(resp)
            return
        return ProvedoresState.carregar

    @rx.event
    async def testar_conexao(self, provedor_id: int):
        """Testa a conexão AWS do provedor (admin) e recarrega para refletir o status."""
        auth = await self._auth()
        if not auth.token:
            yield AuthState.handle_unauthenticated
            return

        self.testando_id = provedor_id
        self.error_message = ""
        yield

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{get_xano_app_base_url()}/provedores/{provedor_id}/testar-conexao",
                    headers={"Authorization": f"Bearer {auth.token}"},
                )
        except Exception:
            self.testando_id = 0
            self.error_message = "Não foi possível testar a conexão do provedor."
            return

        self.testando_id = 0
        if resp.status_code == 401:
            yield AuthState.handle_unauthenticated
            return
        if resp.status_code != 200:
            self.error_message = _mensagem_erro(resp)
            return

        yield ProvedoresState.carregar


def _mensagem_erro(resp: httpx.Response) -> str:
    """Extrai uma mensagem de erro simples do corpo retornado pelo backend."""
    try:
        data = resp.json()
    except Exception:
        return "Operação não permitida ou inválida."
    if isinstance(data, dict):
        return data.get("message") or data.get("erro") or data.get("error") or "Operação não permitida ou inválida."
    return "Operação não permitida ou inválida."

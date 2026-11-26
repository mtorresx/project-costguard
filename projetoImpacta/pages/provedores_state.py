"""Estado da página de Provedores — consome o backend Xano (api_group `app`).

Segue o padrão do `ProjetosState`/`AuthState`: envia `Authorization: Bearer
<token>` e, em HTTP 401, delega ao tratamento central de sessão
(`AuthState.handle_unauthenticated`).

Segurança do segredo da credencial AWS:
- o `secret_access_key` só é mantido no State o tempo necessário para a
  submissão e é limpo após o envio;
- o segredo salvo nunca é retornado pelo backend nem reexibido na interface;
- na edição, enviar o campo do segredo vazio significa "não alterar".
"""

from __future__ import annotations

import re
from typing import TypedDict

import httpx
import reflex as rx

from ..components.mensagens import sucesso

from ..formatadores import mascarar_conta_aws
from ..api import cliente_xano, requisitar
from ..config import get_xano_app_base_url
from ..state import AuthState
from .azure_state import ROTA_CONEXAO, AzureState


CAMPOS_AZURE = (
    ("tenant_id", "Tenant ID"),
    ("client_id", "Client ID"),
    ("client_secret", "Client Secret"),
    ("subscription_id", "Subscription ID"),
)


def _erro_conexao_azure(mensagem, credenciais: dict) -> str:
    if not isinstance(mensagem, str) or not mensagem.strip():
        return "Não foi possível conectar a assinatura Azure."
    valores = sorted({v.strip() for v in credenciais.values() if v.strip()}, key=len, reverse=True)
    return re.sub("|".join(map(re.escape, valores)), "[oculto]", mensagem, flags=re.IGNORECASE)


class Provedor(TypedDict):
    id: int
    apelido: str
    tipo: str
    identificador_conta: str
    conta_mascarada: str
    tipo_credencial: str
    status: str
    tag_alocacao_projeto: str
    # Estado do inventário (GET /sincronizacao/estado); vazio quando não se aplica.
    sinc_texto: str
    sinc_erro: str
    sinc_ultima_boa: str


TAG_PROJETO_PADRAO = "PRJ"


def _normalizar(bruto: dict) -> Provedor:
    return {
        "id": bruto.get("id", 0),
        "apelido": bruto.get("apelido") or "",
        "tipo": bruto.get("tipo") or "aws",
        "identificador_conta": bruto.get("identificador_conta") or "",
        "conta_mascarada": mascarar_conta_aws(str(bruto.get("identificador_conta") or "")),
        "tipo_credencial": bruto.get("tipo_credencial") or "aws_access_key",
        "status": bruto.get("status") or "pendente",
        "tag_alocacao_projeto": (bruto.get("tag_alocacao_projeto") or "").strip() or TAG_PROJETO_PADRAO,
        "sinc_texto": "",
        "sinc_erro": "",
        "sinc_ultima_boa": "",
    }


def com_estado(provedores: list[Provedor], corpo: object) -> list[Provedor]:
    """Provedores com os textos de `/sincronizacao/estado` (provedor fora da resposta fica sem texto)."""
    from ..sincronizacao_auto import estado_por_provedor

    estados = estado_por_provedor(corpo)
    saida: list[Provedor] = []
    for p in provedores:
        e = estados.get(p["id"], {})
        saida.append({
            **p,
            "sinc_texto": e.get("texto", ""),
            "sinc_erro": e.get("erro", ""),
            "sinc_ultima_boa": e.get("ultima_boa", ""),
        })
    return saida


def mensagem_teste_conexao(corpo: object) -> str:
    """Motivo da falha do teste de conexão; vazio quando conectou.

    O backend responde HTTP 200 também quando a credencial é recusada: o
    resultado vem em `conectado`, com `mensagem` e um `diagnostico` sanitizado.
    """
    if not isinstance(corpo, dict) or corpo.get("conectado") is True:
        return ""
    texto = corpo.get("mensagem")
    texto = texto.strip() if isinstance(texto, str) and texto.strip() else "Falha no teste de conexão."
    diag = corpo.get("diagnostico")
    if isinstance(diag, dict):
        detalhes = [str(diag[c]) for c in ("error_code", "error_msg") if diag.get(c)]
        if diag.get("http_status"):
            detalhes.append(f"HTTP {diag['http_status']}")
        if detalhes:
            texto = f"{texto} ({' — '.join(detalhes)})"
    return texto


class ProvedoresState(rx.State):
    """Lista de provedores reais e o formulário de cadastro/edição (admin)."""

    provedores: list[Provedor] = []
    loading: bool = False
    error_message: str = ""

    # id do provedor cujo teste de conexão está em andamento (0 = nenhum).
    testando_id: int = 0
    # Motivo da falha do último teste de conexão (sobrevive à recarga da lista).
    falha_teste: str = ""

    # Formulário (criar/editar).
    form_aberto: bool = False
    form_modo: str = "criar"  # "criar" | "editar"
    form_provedor: str = "AWS"
    versao_form_azure: int = 0
    form_id: int = 0
    form_apelido: str = ""
    form_identificador_conta: str = ""
    form_access_key_id: str = ""
    # Segredo: só preenchido pelo usuário para submissão; nunca vem do backend.
    form_secret_access_key: str = ""
    form_tag_projeto: str = TAG_PROJETO_PADRAO
    form_error: str = ""
    form_loading: bool = False

    async def _auth(self) -> AuthState:
        return await self.get_state(AuthState)

    @rx.event
    async def carregar(self, ao_abrir: bool = True):
        """on_load: carrega a lista real do backend."""
        auth = await self._auth()
        if not auth.token:
            yield AuthState.handle_unauthenticated
            return
        if ao_abrir:
            yield rx.call_script("Intl.DateTimeFormat().resolvedOptions().timeZone", callback=AzureState.carregar)

        self.loading = True
        self.error_message = ""
        yield

        try:
            async with cliente_xano(30) as client:
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
        provedores = [
            _normalizar(p) for p in dados
            if isinstance(p, dict) and (p.get("tipo") or "aws") == "aws"
        ]
        # Estado do inventário por provedor. Se a leitura falhar, a lista aparece sem ele.
        status_e, estado = await requisitar("GET", "/sincronizacao/estado", auth.token, forcar=True)
        self.provedores = com_estado(provedores, estado) if status_e == 200 else provedores
        self.loading = False

    @rx.event
    def aplicar_estado(self, corpo: dict):
        """Atualiza só os textos de sincronização (consulta periódica), sem recarregar a lista."""
        self.provedores = com_estado(self.provedores, corpo)

    @rx.event
    def abrir_criar(self):
        self.form_provedor = "AWS"
        self.form_modo = "criar"
        self.form_id = 0
        self.form_apelido = ""
        self.form_identificador_conta = ""
        self.form_access_key_id = ""
        self.form_secret_access_key = ""
        self.form_tag_projeto = TAG_PROJETO_PADRAO
        self.form_error = ""
        self.form_aberto = True

    @rx.event
    def abrir_editar(self, provedor: Provedor):
        self.form_provedor = "AWS"
        self.form_modo = "editar"
        self.form_id = provedor["id"]
        self.form_apelido = provedor["apelido"]
        self.form_identificador_conta = provedor["identificador_conta"]
        # A listagem não retorna o Access Key ID; o campo começa vazio na edição.
        self.form_access_key_id = ""
        # O segredo salvo nunca é devolvido pelo backend: o campo começa vazio.
        self.form_secret_access_key = ""
        self.form_tag_projeto = provedor.get("tag_alocacao_projeto") or TAG_PROJETO_PADRAO
        self.form_error = ""
        self.form_aberto = True

    @rx.event
    def selecionar_provedor(self, valor: str):
        if self.form_modo == "criar" and valor in ("AWS", "Azure"):
            self.form_provedor = valor
            self.form_error = ""
            self.form_access_key_id = ""
            self.form_secret_access_key = ""

    @rx.event
    def fechar_form(self):
        self.form_aberto = False
        self.form_error = ""
        self.versao_form_azure += 1
        # Garante que nenhum segredo permaneça no State após fechar.
        self.form_secret_access_key = ""

    @rx.event
    def alterar_abertura(self, aberto: bool):
        if not aberto:
            self.fechar_form()

    @rx.event
    async def conectar_azure(self, form_data: dict):
        # Inputs não controlados: as credenciais existem apenas no argumento deste envio.
        credenciais = {campo: form_data.get(campo) for campo, _ in CAMPOS_AZURE}
        apelido = form_data.get("apelido")
        form_data.clear()
        try:
            auth = await self._auth()
            if not auth.token:
                yield AuthState.handle_unauthenticated
                return
            if (not auth.is_admin or self.form_loading or not self.form_aberto
                    or self.form_modo != "criar" or self.form_provedor != "Azure"):
                return
            self.form_error = ""
            self.versao_form_azure += 1
            if not all(isinstance(v, str) and v.strip() for v in credenciais.values()):
                self.form_error = "Preencha os quatro campos da conexão Azure."
                return
            self.form_loading = True
            yield
            try:
                status, corpo = await requisitar("POST", ROTA_CONEXAO, auth.token, {
                    **credenciais, "apelido": apelido.strip() if isinstance(apelido, str) and apelido.strip() else "Azure",
                })
            finally:
                self.form_loading = False
            if status == 401:
                self.fechar_form()
                yield AuthState.handle_unauthenticated
                return
            dados = corpo if isinstance(corpo, dict) else {}
            if not (200 <= status < 300 and dados.get("conectado") is True):
                self.form_error = _erro_conexao_azure(dados.get("message"), credenciais)
                self.versao_form_azure += 1
                return
        finally:
            credenciais.clear()
        self.fechar_form()
        azure = await self.get_state(AzureState)
        azure._conexao_alterada()
        azure.carregando = True
        azure.conectado = False
        yield sucesso("Conectado ao Azure")
        yield AzureState.carregar

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
    def set_form_tag_projeto(self, v: str):
        self.form_tag_projeto = v
        self.form_error = ""

    @rx.event
    async def salvar(self):
        """Cria ou edita o provedor (admin). Validações finais são do backend."""
        auth = await self._auth()
        if not auth.token:
            return AuthState.handle_unauthenticated

        if self.form_provedor != "AWS":
            return

        # Validação leve no cliente (apenas UX; o backend é autoritativo).
        if not self.form_apelido.strip():
            self.form_error = "Informe o apelido do provedor."
            return
        if not self.form_identificador_conta.strip():
            self.form_error = "Informe o identificador da conta AWS."
            return
        if not self.form_tag_projeto.strip():
            self.form_error = "Informe a Tag Key de projeto (padrão: PRJ)."
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
            async with cliente_xano(30) as client:
                if self.form_modo == "criar":
                    payload = {
                        "apelido": self.form_apelido.strip(),
                        "tipo": "aws",
                        "identificador_conta": self.form_identificador_conta.strip(),
                        "aws_access_key_id": self.form_access_key_id.strip(),
                        "aws_secret_access_key": self.form_secret_access_key,
                        "tag_alocacao_projeto": self.form_tag_projeto.strip(),
                    }
                    resp = await client.post(f"{base}/provedores", json=payload, headers=headers)
                else:
                    payload = {
                        "apelido": self.form_apelido.strip(),
                        "identificador_conta": self.form_identificador_conta.strip(),
                        "tag_alocacao_projeto": self.form_tag_projeto.strip(),
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
        return [sucesso("Provedor salvo."), ProvedoresState.carregar(False)]

    @rx.event
    async def desativar(self, provedor_id: int):
        """Desativa o provedor (admin)."""
        auth = await self._auth()
        if not auth.token:
            return AuthState.handle_unauthenticated
        try:
            async with cliente_xano(30) as client:
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
        return [sucesso("Provedor desativado."), ProvedoresState.carregar(False)]

    @rx.event(background=True)
    async def testar_conexao(self, provedor_id: int):
        """Testa a conexão AWS do provedor (admin) e recarrega para refletir o status.

        Em segundo plano (P2-3): o teste pode levar até 60 s sem segurar a aba.
        """
        async with self:
            if self.testando_id:
                return
            token = (await self._auth()).token
            if token:
                self.testando_id = provedor_id
                self.error_message = ""
                self.falha_teste = ""
        if not token:
            yield AuthState.handle_unauthenticated
            return

        try:
            async with cliente_xano(60) as client:
                resp = await client.post(
                    f"{get_xano_app_base_url()}/provedores/{provedor_id}/testar-conexao",
                    headers={"Authorization": f"Bearer {token}"},
                )
        except Exception:
            async with self:
                self.testando_id = 0
                self.error_message = "Não foi possível testar a conexão do provedor."
            return

        async with self:
            self.testando_id = 0
            if resp.status_code == 200:
                # HTTP 200 com `conectado: false` é falha: mostra o motivo.
                try:
                    corpo = resp.json()
                    conectado = isinstance(corpo, dict) and corpo.get("conectado") is True
                    self.falha_teste = "" if conectado else mensagem_teste_conexao(corpo) or "Falha no teste de conexão."
                except ValueError:
                    conectado = False
                    self.falha_teste = "Falha no teste de conexão."
            elif resp.status_code != 401:
                self.error_message = _mensagem_erro(resp)
        if resp.status_code == 401:
            yield AuthState.handle_unauthenticated
        elif resp.status_code == 200:
            if conectado:
                yield sucesso("Conexão com a AWS confirmada.")
            yield ProvedoresState.carregar(False)


def _mensagem_erro(resp: httpx.Response) -> str:
    """Extrai uma mensagem de erro simples do corpo retornado pelo backend."""
    try:
        data = resp.json()
    except Exception:
        return "Operação não permitida ou inválida."
    if isinstance(data, dict):
        return data.get("message") or data.get("erro") or data.get("error") or "Operação não permitida ou inválida."
    return "Operação não permitida ou inválida."

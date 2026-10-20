"""Estado do fluxo de descoberta/importação de projetos AWS (frontend Reflex).

Consome os endpoints já existentes do backend (api_group `app`):
- POST /provedores/{id}/descobrir-projetos  (read-only)
- POST /provedores/{id}/importar-projetos   (cria só inexistentes)

Segue o padrão do projeto: envia `Authorization: Bearer <token>` do `AuthState`,
usa `get_xano_app_base_url()` e delega HTTP 401 ao tratamento central
(`AuthState.handle_unauthenticated`). Mensagens de erro são sanitizadas: nunca
expõe `diagnostico` técnico, resposta crua ou token. A autorização real é do
backend; a ocultação de controles para não-admin é apenas UX.
"""

from __future__ import annotations

from typing import TypedDict

import httpx
import reflex as rx

from ..config import get_xano_app_base_url
from ..state import AuthState


class ProjetoDescoberto(TypedDict):
    codigo: str
    existente: bool
    projeto_id: int | None


def _normalizar_descoberto(bruto: dict) -> ProjetoDescoberto:
    pid = bruto.get("projeto_id")
    return {
        "codigo": bruto.get("codigo") or "",
        "existente": bool(bruto.get("existente") or False),
        "projeto_id": pid if isinstance(pid, int) else None,
    }


_ERRO_DESCOBRIR = "Não foi possível descobrir os projetos deste provedor."
_ERRO_IMPORTAR = "Não foi possível importar os projetos selecionados."


class DescobertaState(rx.State):
    """Fluxo descobrir -> selecionar novos -> importar -> redescobrir, por provedor."""

    aberto: bool = False
    provedor_id: int = 0
    provedor_apelido: str = ""
    tag_key: str = ""

    descobertos: list[ProjetoDescoberto] = []
    # Códigos (novos) atualmente selecionados para importação.
    selecionados: list[str] = []

    loading_descoberta: bool = False
    loading_importacao: bool = False
    erro: str = ""
    mensagem_sucesso: str = ""

    # ---- Derivados (apresentação; sem lógica visual complexa) ----

    @rx.var
    def codigos_novos(self) -> list[str]:
        return [d["codigo"] for d in self.descobertos if not d["existente"]]

    @rx.var
    def tem_novos(self) -> bool:
        return len(self.codigos_novos) > 0

    @rx.var
    def total_selecionados(self) -> int:
        return len(self.selecionados)

    @rx.var
    def pode_importar(self) -> bool:
        return self.total_selecionados > 0 and not self.loading_importacao

    @rx.var
    def todos_novos_selecionados(self) -> bool:
        novos = self.codigos_novos
        return len(novos) > 0 and all(c in self.selecionados for c in novos)

    async def _auth(self) -> AuthState:
        return await self.get_state(AuthState)

    # ---- Abrir / fechar ----

    @rx.event
    def abrir(self, provedor: dict):
        """Abre o modal para um provedor e limpa o estado anterior."""
        self.provedor_id = provedor.get("id", 0)
        self.provedor_apelido = provedor.get("apelido") or ""
        self.tag_key = ""
        self.descobertos = []
        self.selecionados = []
        self.erro = ""
        self.mensagem_sucesso = ""
        self.loading_descoberta = False
        self.loading_importacao = False
        self.aberto = True
        return DescobertaState.descobrir

    @rx.event
    def fechar(self):
        self.aberto = False
        self.descobertos = []
        self.selecionados = []
        self.erro = ""
        self.mensagem_sucesso = ""

    # ---- Seleção ----

    @rx.event
    def toggle_codigo(self, codigo: str):
        """Marca/desmarca um código novo. Existentes nunca entram na seleção."""
        if codigo not in self.codigos_novos:
            return
        if codigo in self.selecionados:
            self.selecionados = [c for c in self.selecionados if c != codigo]
        else:
            self.selecionados = [*self.selecionados, codigo]

    @rx.event
    def selecionar_todos_novos(self):
        self.selecionados = list(self.codigos_novos)

    @rx.event
    def limpar_selecao(self):
        self.selecionados = []

    # ---- Descoberta ----

    @rx.event
    async def descobrir(self):
        auth = await self._auth()
        if not auth.token:
            yield AuthState.handle_unauthenticated
            return
        if self.loading_descoberta or self.provedor_id == 0:
            return

        self.loading_descoberta = True
        self.erro = ""
        yield

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{get_xano_app_base_url()}/provedores/{self.provedor_id}/descobrir-projetos",
                    headers={"Authorization": f"Bearer {auth.token}"},
                )
        except Exception:
            self.loading_descoberta = False
            self.erro = _ERRO_DESCOBRIR
            return

        self.loading_descoberta = False

        if resp.status_code == 401:
            yield AuthState.handle_unauthenticated
            return
        if resp.status_code != 200:
            self.erro = _mensagem_sanitizada(resp, _ERRO_DESCOBRIR)
            return

        try:
            dados = resp.json()
        except Exception:
            dados = {}

        # Erro lógico sinalizado pelo backend (status="erro").
        if isinstance(dados, dict) and dados.get("status") == "erro":
            self.erro = (dados.get("mensagem") or "").strip() or _ERRO_DESCOBRIR
            self.descobertos = []
            self.selecionados = []
            return

        self.tag_key = (dados.get("tag_key") or "") if isinstance(dados, dict) else ""
        lista = dados.get("descobertos") if isinstance(dados, dict) else []
        self.descobertos = [
            _normalizar_descoberto(d) for d in (lista or []) if isinstance(d, dict)
        ]
        # Mantém selecionados apenas os que continuam novos.
        novos = self.codigos_novos
        self.selecionados = [c for c in self.selecionados if c in novos]

    # ---- Importação ----

    @rx.event
    async def importar(self):
        auth = await self._auth()
        if not auth.token:
            yield AuthState.handle_unauthenticated
            return
        if self.loading_importacao or self.total_selecionados == 0:
            return

        self.loading_importacao = True
        self.erro = ""
        self.mensagem_sucesso = ""
        yield

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{get_xano_app_base_url()}/provedores/{self.provedor_id}/importar-projetos",
                    json={"codigos": list(self.selecionados)},
                    headers={"Authorization": f"Bearer {auth.token}"},
                )
        except Exception:
            self.loading_importacao = False
            self.erro = _ERRO_IMPORTAR
            return

        self.loading_importacao = False

        if resp.status_code == 401:
            yield AuthState.handle_unauthenticated
            return
        if resp.status_code not in (200, 201):
            self.erro = _mensagem_sanitizada(resp, _ERRO_IMPORTAR)
            return

        try:
            dados = resp.json()
        except Exception:
            dados = {}

        criados = dados.get("criados") or [] if isinstance(dados, dict) else []
        ignorados = dados.get("ignorados") or [] if isinstance(dados, dict) else []
        self.mensagem_sucesso = _feedback_importacao(len(criados), len(ignorados))

        # Limpa a seleção e redescobre para refletir os importados como existentes.
        self.selecionados = []
        yield DescobertaState.descobrir


def _mensagem_sanitizada(resp: httpx.Response, fallback: str) -> str:
    """Extrai apenas a mensagem amigável do backend; nunca o diagnóstico técnico."""
    try:
        data = resp.json()
    except Exception:
        return fallback
    if isinstance(data, dict):
        msg = data.get("mensagem") or data.get("message") or data.get("error")
        if isinstance(msg, str) and msg.strip():
            return msg.strip()
    return fallback


def _feedback_importacao(qtd_criados: int, qtd_ignorados: int) -> str:
    if qtd_criados == 0:
        base = "Nenhum projeto novo importado"
    elif qtd_criados == 1:
        base = "1 projeto importado"
    else:
        base = f"{qtd_criados} projetos importados"
    if qtd_ignorados == 1:
        base += " (1 já existente foi ignorado)"
    elif qtd_ignorados > 1:
        base += f" ({qtd_ignorados} já existentes foram ignorados)"
    return base + "."

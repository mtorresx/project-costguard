"""Estado da página de Projetos — consome o backend Xano (api_group `app`).

Segue o padrão do `AuthState`: envia `Authorization: Bearer <token>` e, em HTTP
401, delega ao tratamento central de sessão (`AuthState.handle_unauthenticated`).

Os cards vêm de `GET /projetos-resumo-consumo-mtd`, que já traz o consumo MTD,
o percentual e a faixa calculados no backend. Este estado não recalcula regra:
confere o contrato da resposta e converte os valores recebidos em textos e cores
de exibição. Se o resumo falhar ou vier fora do contrato, a listagem vem de
`GET /projetos` com os cards em "Consumo indisponível".
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any, TypedDict

import httpx
import reflex as rx

from ..config import get_xano_app_base_url
from ..state import AuthState
from .projeto_detalhe_state import MOEDA_ORCAMENTO, formatar_valor

MENSAGEM_ERRO_PROJETOS = "Não foi possível carregar os projetos."
MENSAGEM_ERRO_CONSUMO = "Não foi possível carregar o consumo dos projetos."

# Faixa calculada pelo backend -> (cor Radix, rótulo exibido).
_FAIXAS = {
    "normal": ("green", "Normal"),
    "atencao": ("yellow", "Atenção"),
    "critico": ("orange", "Crítico"),
    "estourado": ("red", "Estourado"),
}

_NOTAS_CUSTO = {
    "sem_registros": "Sem custos classificados no mês até a data atual.",
    "moeda_incompativel": "Comparação com o orçamento em US$ não é feita.",
    "moedas_mistas": "Custos em moedas diferentes; não é possível somar.",
}


class Projeto(TypedDict):
    """Card de projeto: campos do projeto (usados pelo CRUD) e textos de exibição."""

    id: int
    nome: str
    codigo: str
    budget: float
    status: str
    custo_texto: str  # "" quando não há valor a exibir
    custo_nota: str  # estado do custo sem valor fabricado; "" quando não se aplica
    ultima_data_texto: str
    orcamento_texto: str
    mostra_consumo: bool  # percentual e barra só quando o backend enviou a faixa
    percentual_texto: str
    barra_valor: int  # largura visual da barra, limitada a 0–100
    faixa_cor: str
    faixa_rotulo: str


def _numero(valor: Any) -> float:
    try:
        return float(valor or 0)
    except (TypeError, ValueError):
        return 0.0


def _data_br(valor: Any) -> str:
    """`YYYY-MM-DD` -> `DD/MM/AAAA`; vazio quando ausente ou inválido."""
    partes = str(valor or "")[:10].split("-")
    if len(partes) != 3 or not all(p.isdigit() for p in partes):
        return ""
    return f"{partes[2]}/{partes[1]}/{partes[0]}"


def _card_base(bruto: dict) -> Projeto:
    """Campos do projeto e card sem consumo (base do fallback "Consumo indisponível")."""
    budget = _numero(bruto.get("budget"))
    return {
        "id": bruto.get("id", 0),
        "nome": bruto.get("nome") or "",
        "codigo": bruto.get("codigo") or "",
        "budget": budget,
        "status": bruto.get("status") or "ativo",
        "custo_texto": "",
        "custo_nota": "Consumo indisponível",
        "ultima_data_texto": "",
        "orcamento_texto": (
            f"Orçamento: {formatar_valor(budget, MOEDA_ORCAMENTO)}" if budget > 0 else "Sem orçamento definido"
        ),
        "mostra_consumo": False,
        "percentual_texto": "",
        "barra_valor": 0,
        "faixa_cor": "gray",
        "faixa_rotulo": "",
    }


_CUSTO_STATUS = ("ok", "sem_registros", "moeda_incompativel", "moedas_mistas")
_CAMPOS_RESUMO = (
    "id", "nome", "codigo", "status", "budget", "custo_status", "custo_mtd", "moeda",
    "ultima_data_com_custo", "percentual_usado", "faixa",
)


def _eh_numero(valor: Any) -> bool:
    """Número JSON finito (bool não conta como número)."""
    return isinstance(valor, (int, float)) and not isinstance(valor, bool) and math.isfinite(valor)


def _eh_data(valor: Any) -> bool:
    """Data de calendário real no formato `YYYY-MM-DD`."""
    if not isinstance(valor, str) or len(valor) != 10:
        return False
    try:
        date.fromisoformat(valor)
    except ValueError:
        return False
    return True


def _item_valido(item: Any) -> bool:
    """Confere um item do resumo contra o contrato da spec (presença, tipos e combinações).

    Tipos são conferidos antes de qualquer comparação ou consulta a dicionário,
    para que um valor inesperado (lista, objeto) nunca gere exceção.
    """
    if not isinstance(item, dict) or not all(c in item for c in _CAMPOS_RESUMO):
        return False
    pid = item["id"]
    if not (isinstance(pid, int) and not isinstance(pid, bool) and pid > 0):
        return False
    if not all(isinstance(item[c], str) for c in ("nome", "codigo", "status")):
        return False
    budget = item["budget"]
    if not _eh_numero(budget) or budget < 0:
        return False
    status_custo = item["custo_status"]
    if not isinstance(status_custo, str) or status_custo not in _CUSTO_STATUS:
        return False
    custo, moeda = item["custo_mtd"], item["moeda"]
    ultima = item["ultima_data_com_custo"]
    faixa, percentual = item["faixa"], item["percentual_usado"]

    # Percentual e faixa: presentes juntos, e somente com custo `ok` e orçamento > 0.
    deve_ter_faixa = status_custo == "ok" and budget > 0
    if deve_ter_faixa:
        if not (isinstance(faixa, str) and faixa in _FAIXAS and _eh_numero(percentual)):
            return False
    elif faixa is not None or percentual is not None:
        return False

    if status_custo == "sem_registros":
        return custo is None and moeda is None and ultima is None
    if status_custo == "moedas_mistas":
        return custo is None and moeda is None and _eh_data(ultima)
    # ok / moeda_incompativel: custo numérico, moeda e data presentes.
    if not (_eh_numero(custo) and isinstance(moeda, str) and moeda != "" and _eh_data(ultima)):
        return False
    return (moeda == "USD") == (status_custo == "ok")


def itens_do_resumo(corpo: Any) -> list[dict] | None:
    """Itens do resumo se a resposta inteira respeitar o contrato; senão None (vai ao fallback).

    Uma resposta HTTP 200 fora do contrato é tratada como falha: nada é exibido
    como consumo e nenhum valor inválido é convertido em zero. Qualquer exceção
    inesperada durante a checagem também leva ao fallback.
    """
    try:
        if not isinstance(corpo, dict):
            return None
        if not (_eh_data(corpo.get("data_inicio")) and _eh_data(corpo.get("data_fim"))):
            return None
        itens = corpo.get("projetos")
        if not isinstance(itens, list) or not all(_item_valido(p) for p in itens):
            return None
        return itens
    except Exception:
        return None


def card_de_resumo(item: dict) -> Projeto:
    """Converte um item de `GET /projetos-resumo-consumo-mtd` em card, sem recalcular regra."""
    card = _card_base(item)
    status_custo = item.get("custo_status") or ""
    custo = item.get("custo_mtd")
    moeda = item.get("moeda") or ""

    card["custo_nota"] = _NOTAS_CUSTO.get(status_custo, "")
    if status_custo in ("ok", "moeda_incompativel") and custo is not None:
        card["custo_texto"] = formatar_valor(_numero(custo), moeda)
    if ultima := _data_br(item.get("ultima_data_com_custo")):
        card["ultima_data_texto"] = f"Último custo classificado: {ultima}"

    faixa = item.get("faixa")
    percentual = item.get("percentual_usado")
    if faixa in _FAIXAS and percentual is not None:
        p = _numero(percentual)
        card["mostra_consumo"] = True
        card["percentual_texto"] = f"{p:.1f}%"
        card["barra_valor"] = int(round(min(max(p, 0.0), 100.0)))
        card["faixa_cor"], card["faixa_rotulo"] = _FAIXAS[faixa]
    return card


class ProjetosState(rx.State):
    """Lista de projetos reais e o formulário de criação/edição (admin)."""

    projetos: list[Projeto] = []
    loading: bool = False
    error_message: str = ""
    aviso_consumo: str = ""

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
        """on_load: carrega os cards pelo resumo de consumo; se falhar, pela lista simples."""
        auth = await self._auth()
        if not auth.token:
            # carregar é async generator (usa yield): encadear eventos com yield.
            yield AuthState.handle_unauthenticated
            return

        self.loading = True
        self.error_message = ""
        self.aviso_consumo = ""
        yield

        status, corpo = await _buscar("/projetos-resumo-consumo-mtd", auth.token)
        if status == 401:
            self.loading = False
            yield AuthState.handle_unauthenticated
            return
        itens = itens_do_resumo(corpo) if status == 200 else None
        if itens is not None:
            self.projetos = [card_de_resumo(p) for p in itens]
            self.loading = False
            return

        # Resumo indisponível ou fora do contrato: a listagem e o CRUD continuam,
        # sem fabricar consumo.
        self.aviso_consumo = MENSAGEM_ERRO_CONSUMO
        status, corpo = await _buscar("/projetos", auth.token)
        if status == 401:
            self.loading = False
            yield AuthState.handle_unauthenticated
            return
        if status != 200 or not isinstance(corpo, list):
            # Nenhum card: não manter cards de uma carga anterior como se fossem atuais.
            self.projetos = []
            self.loading = False
            self.aviso_consumo = ""
            self.error_message = MENSAGEM_ERRO_PROJETOS
            return
        self.projetos = [_card_base(p) for p in corpo if isinstance(p, dict)]
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


async def _buscar(caminho: str, token: str) -> tuple[int, Any]:
    """GET autenticado no api_group `app`. Falha de rede ou JSON inválido -> (0, None)."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{get_xano_app_base_url()}{caminho}",
                headers={"Authorization": f"Bearer {token}"},
            )
    except Exception:
        return 0, None
    if resp.status_code != 200:
        return resp.status_code, None
    try:
        return 200, resp.json()
    except Exception:
        return 0, None


def _mensagem_erro(resp: httpx.Response) -> str:
    """Extrai uma mensagem de erro simples do corpo retornado pelo backend."""
    try:
        data = resp.json()
    except Exception:
        return "Operação não permitida ou inválida."
    if isinstance(data, dict):
        return data.get("message") or data.get("erro") or data.get("error") or "Operação não permitida ou inválida."
    return "Operação não permitida ou inválida."

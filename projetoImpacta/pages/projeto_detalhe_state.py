"""Estado da página de detalhamento de projeto ("/projetos/[projeto_id]").

Consome somente endpoints reais já existentes (api_group `app`):
- GET /projetos/{id}
- GET /projetos/{id}/custos-equipe (janela = mês corrente até a data atual)
- GET /projetos/{id}/recursos
- GET /projetos/{id}/equipes

Não há dado fictício, projeção, tendência, custo por provedor nem custo por
recurso. Os blocos de custo e de recursos carregam de forma independente: uma
falha em um não esconde o outro.

O mês é determinado no fuso America/Sao_Paulo (ver `janela_mtd`). A semântica do
backend não muda: `data_inicio` é inclusiva e `data_fim` é exclusiva.

A autorização permanece no backend. O frontend não é mecanismo de segurança.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime, timedelta
from typing import Any, Optional, TypedDict
from zoneinfo import ZoneInfo

import httpx
import reflex as rx

from ..config import get_xano_app_base_url
from ..state import AuthState

FUSO_MTD = ZoneInfo("America/Sao_Paulo")
MOEDA_ORCAMENTO = "USD"

TEXTO_ERRO_PROJETO = "Não foi possível carregar o projeto."
TEXTO_ERRO_CUSTOS = "Não foi possível carregar os custos do período."
TEXTO_ERRO_RECURSOS = "Não foi possível carregar os recursos do projeto."
TEXTO_SEM_CUSTO = "Sem custos classificados no mês até a data atual."
TEXTO_RODAPE_CUSTO = "Custo já classificado no período. Não indica atualização até este instante."
TEXTO_SEM_RESPONSAVEL = "Sem responsável"

# Mapeamento decorativo: o serviço é texto livre vindo do inventário.
_ICONES_SERVICO: dict[str, tuple[str, str]] = {
    "ec2": ("server", "#f97316"),
    "ecs": ("container", "#14b8a6"),
    "rds": ("database", "#3b82f6"),
    "vpc": ("network", "#a855f7"),
    "s3": ("archive", "#22c55e"),
    "eks": ("boxes", "#f97316"),
}
_ICONE_PADRAO = ("cloud", "#94a3b8")


class EquipeCusto(TypedDict):
    chave: str
    nome: str
    recursos_texto: str
    total_texto: str
    largura: str


class RecursoDetalhe(TypedDict):
    nome: str
    arn: str
    servico: str
    servico_icone: str
    servico_cor: str
    regiao: str


class GrupoRecursos(TypedDict):
    chave: str
    equipe: str
    total_texto: str
    recursos: list[RecursoDetalhe]


def janela_mtd(agora: datetime) -> tuple[date, date]:
    """Retorna (data_inicio, data_fim) do mês corrente até a data atual.

    A data é a de America/Sao_Paulo, não a UTC. `data_fim` é o dia seguinte à data
    atual, porque o endpoint trata `data_fim` como exclusivo.

    Args:
        agora: instante com fuso (aware).

    Returns:
        Tupla (primeiro dia do mês, dia seguinte à data atual).
    """
    hoje = agora.astimezone(FUSO_MTD).date()
    return hoje.replace(day=1), hoje + timedelta(days=1)


def texto_periodo(inicio: date, fim: date) -> str:
    """Texto do período exibido ao usuário: início até a data atual (inclusiva)."""
    ultimo_dia = fim - timedelta(days=1)
    return f"Período: {inicio:%d/%m/%Y} a {ultimo_dia:%d/%m/%Y}"


def formatar_valor(valor: float, moeda: str) -> str:
    """Formata um valor monetário com duas casas e separador de milhar, sem abreviar."""
    sinal = "-" if valor < 0 else ""
    prefixo = "US$" if moeda == MOEDA_ORCAMENTO else moeda
    return f"{sinal}{prefixo} {abs(valor):,.2f}"


def nome_recurso(arn: str) -> str:
    """Último segmento do ARN (após `/` ou `:`). Sem separadores, o ARN inteiro."""
    partes = [p for p in re.split(r"[/:]", arn) if p]
    return partes[-1] if partes else arn


def icone_servico(servico: str) -> tuple[str, str]:
    """Ícone e cor decorativos para o serviço. Serviço não mapeado usa ícone genérico."""
    chave = servico.lower().replace("aws", "").strip()
    return _ICONES_SERVICO.get(chave, _ICONE_PADRAO)


def _texto_recursos(quantidade: int) -> str:
    return f"{quantidade} recurso" if quantidade == 1 else f"{quantidade} recursos"


def _numero(valor: Any) -> float:
    try:
        return float(valor or 0)
    except (TypeError, ValueError):
        return 0.0


async def _buscar(url: str, token: str, params: Optional[dict] = None) -> tuple[int, Any]:
    """GET autenticado no Xano. Devolve (status HTTP, corpo JSON ou None); status 0 = falha de rede."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                params=params,
            )
    except httpx.RequestError:
        return 0, None
    try:
        return resp.status_code, resp.json()
    except ValueError:
        return resp.status_code, None


class ProjetoDetalheState(rx.State):
    """Detalhamento de um projeto. `projeto_id` vem da rota dinâmica do Reflex."""

    # Projeto (GET /projetos/{id}).
    carregando: bool = True
    nao_encontrado: bool = False
    erro: str = ""
    nome: str = ""
    codigo: str = ""
    inativo: bool = False
    status_texto: str = ""
    budget: float = 0.0
    budget_texto: str = ""

    # Custos classificados no mês (GET /projetos/{id}/custos-equipe).
    periodo: str = ""
    carregando_custos: bool = True
    erro_custos: str = ""
    moeda: str = ""
    sem_custos: bool = False
    custo_texto: str = "—"
    rodape_custo: str = TEXTO_RODAPE_CUSTO
    restante_texto: str = "—"
    comparavel: bool = False
    percentual_texto: str = ""
    largura_barra: str = "0%"
    comparacao_texto: str = ""
    equipes_custo: list[EquipeCusto] = []
    sem_responsavel_custo_texto: str = ""

    # Inventário (GET /projetos/{id}/recursos e /equipes).
    carregando_recursos: bool = True
    erro_recursos: str = ""
    grupos: list[GrupoRecursos] = []
    total_sem_responsavel: int = 0
    bloco_sem_responsavel: bool = False
    equipes_recolhidas: list[str] = []

    async def _token(self) -> str:
        auth = await self.get_state(AuthState)
        return auth.token

    def _base(self) -> str:
        return f"{get_xano_app_base_url()}/projetos/{self.projeto_id}"

    @rx.event
    async def carregar(self):
        """on_load: carrega o projeto e encadeia os blocos de custo e de recursos."""
        token = await self._token()
        if not token:
            yield AuthState.handle_unauthenticated
            return

        self.carregando = True
        self.nao_encontrado = False
        self.erro = ""
        yield

        try:
            projeto_id = int(self.projeto_id)
        except (TypeError, ValueError):
            projeto_id = 0
        if projeto_id <= 0:
            self.carregando = False
            self.nao_encontrado = True
            return

        status, corpo = await _buscar(self._base(), token)
        self.carregando = False
        if status == 401:
            yield AuthState.handle_unauthenticated
            return
        if status == 404:
            self.nao_encontrado = True
            return
        if status != 200 or not isinstance(corpo, dict):
            self.erro = TEXTO_ERRO_PROJETO
            return

        self._preencher_projeto(corpo)
        yield ProjetoDetalheState.carregar_custos
        yield ProjetoDetalheState.carregar_recursos

    def _preencher_projeto(self, corpo: dict):
        self.nome = corpo.get("nome") or ""
        self.codigo = corpo.get("codigo") or ""
        self.inativo = (corpo.get("status") or "ativo") != "ativo"
        self.status_texto = "Inativo" if self.inativo else "Ativo"
        budget = _numero(corpo.get("budget"))
        self.budget = budget
        self.budget_texto = formatar_valor(budget, MOEDA_ORCAMENTO)

    @rx.event
    async def carregar_custos(self):
        """Bloco de custos: custos-equipe no mês corrente (fuso America/Sao_Paulo)."""
        token = await self._token()
        if not token:
            yield AuthState.handle_unauthenticated
            return

        self.carregando_custos = True
        self.erro_custos = ""
        inicio, fim = janela_mtd(datetime.now(FUSO_MTD))
        self.periodo = texto_periodo(inicio, fim)
        yield

        status, corpo = await _buscar(
            f"{self._base()}/custos-equipe",
            token,
            params={"data_inicio": inicio.isoformat(), "data_fim": fim.isoformat()},
        )
        self.carregando_custos = False
        if status == 401:
            yield AuthState.handle_unauthenticated
            return
        if status != 200 or not isinstance(corpo, dict):
            self.erro_custos = TEXTO_ERRO_CUSTOS
            return

        self._preencher_custos(corpo)

    def _preencher_custos(self, corpo: dict):
        moeda = corpo.get("moeda") or ""
        total = _numero(corpo.get("total_projeto"))
        sem_resp = corpo.get("sem_responsavel") or {}
        total_sem_resp = _numero(sem_resp.get("total") if isinstance(sem_resp, dict) else 0)
        budget = self.budget

        self.moeda = moeda
        self.sem_custos = not moeda
        self.comparavel = False
        self.percentual_texto = ""
        self.largura_barra = "0%"
        self.restante_texto = "—"

        if not moeda:
            self.custo_texto = "—"
            self.rodape_custo = TEXTO_SEM_CUSTO
            self.comparacao_texto = TEXTO_SEM_CUSTO
            self.equipes_custo = []
            self.sem_responsavel_custo_texto = ""
            return

        self.custo_texto = formatar_valor(total, moeda)
        self.rodape_custo = TEXTO_RODAPE_CUSTO
        self.sem_responsavel_custo_texto = (
            f"Custo acumulado sem responsável: {formatar_valor(total_sem_resp, moeda)}"
        )
        self.equipes_custo = [
            EquipeCusto(
                chave=str(item.get("equipe_id")),
                nome=item.get("nome") or item.get("codigo") or "",
                recursos_texto="",
                total_texto=formatar_valor(_numero(item.get("total")), moeda),
                largura=f"{round(_numero(item.get('total')) / total * 100) if total > 0 else 0}%",
            )
            for item in corpo.get("equipes") or []
            if isinstance(item, dict)
        ]

        if moeda != MOEDA_ORCAMENTO:
            self.comparacao_texto = (
                f"Comparação com o orçamento em US$ não é feita para custos em {moeda}."
            )
            return
        if budget <= 0:
            self.comparacao_texto = "Sem orçamento definido"
            return

        restante = round(budget - total, 2)
        percentual = round(total / budget * 100, 1)
        self.comparavel = True
        self.restante_texto = formatar_valor(restante, MOEDA_ORCAMENTO)
        self.percentual_texto = f"{percentual:.1f}% utilizado de {self.budget_texto}"
        self.largura_barra = f"{min(max(percentual, 0.0), 100.0)}%"
        self.comparacao_texto = ""

    @rx.event
    async def carregar_recursos(self):
        """Bloco de recursos: inventário agrupado por equipe, com nomes de /equipes."""
        token = await self._token()
        if not token:
            yield AuthState.handle_unauthenticated
            return

        self.carregando_recursos = True
        self.erro_recursos = ""
        yield

        status_r, recursos = await _buscar(f"{self._base()}/recursos", token)
        if status_r == 401:
            self.carregando_recursos = False
            yield AuthState.handle_unauthenticated
            return
        status_e, equipes = await _buscar(f"{self._base()}/equipes", token)
        if status_e == 401:
            self.carregando_recursos = False
            yield AuthState.handle_unauthenticated
            return

        self.carregando_recursos = False
        if status_r != 200 or status_e != 200 or not isinstance(recursos, list) or not isinstance(equipes, list):
            self.erro_recursos = TEXTO_ERRO_RECURSOS
            self.grupos = []
            self.total_sem_responsavel = 0
            self.bloco_sem_responsavel = False
            return

        self._montar_recursos(recursos, equipes)

    def _montar_recursos(self, recursos: list, equipes: list):
        nomes = {
            str(e.get("id")): (e.get("nome") or e.get("codigo") or "")
            for e in equipes
            if isinstance(e, dict)
        }
        ativos = [r for r in recursos if isinstance(r, dict) and r.get("ativo") is True]

        por_chave: dict[str, list[dict]] = {}
        for r in ativos:
            eid = r.get("equipe_id")
            chave = str(eid) if eid is not None else "sem"
            por_chave.setdefault(chave, []).append(r)

        grupos: list[GrupoRecursos] = []
        for chave, itens in por_chave.items():
            if chave == "sem":
                equipe = TEXTO_SEM_RESPONSAVEL
            else:
                equipe = nomes.get(chave) or itens[0].get("codigo_equipe_tag") or "Equipe sem nome"
            detalhes = []
            for r in sorted(itens, key=lambda x: nome_recurso(x.get("arn") or "")):
                arn = r.get("arn") or ""
                servico = r.get("servico") or ""
                icone, cor = icone_servico(servico)
                detalhes.append(
                    RecursoDetalhe(
                        nome=nome_recurso(arn),
                        arn=arn,
                        servico=servico,
                        servico_icone=icone,
                        servico_cor=cor,
                        regiao=r.get("regiao") or "",
                    )
                )
            grupos.append(
                GrupoRecursos(
                    chave=chave,
                    equipe=equipe,
                    total_texto=_texto_recursos(len(itens)),
                    recursos=detalhes,
                )
            )

        # Equipes por nome; "Sem responsável" sempre por último.
        grupos.sort(key=lambda g: (g["chave"] == "sem", g["equipe"].casefold()))
        self.grupos = grupos
        self.total_sem_responsavel = len(por_chave.get("sem", []))
        self.bloco_sem_responsavel = self.total_sem_responsavel > 0
        self.equipes_recolhidas = []

        # Contagem de recursos ativos por equipe, somente quando o inventário carregou.
        self.equipes_custo = [
            EquipeCusto(
                chave=item["chave"],
                nome=item["nome"],
                recursos_texto=f"({_texto_recursos(len(por_chave.get(item['chave'], [])))})",
                total_texto=item["total_texto"],
                largura=item["largura"],
            )
            for item in self.equipes_custo
        ]

    @rx.event
    def alternar_equipe_expandida(self, chave: str):
        if chave in self.equipes_recolhidas:
            self.equipes_recolhidas = [c for c in self.equipes_recolhidas if c != chave]
        else:
            self.equipes_recolhidas = [*self.equipes_recolhidas, chave]

    @rx.event
    def exportar_csv(self):
        """CSV somente com os dados reais carregados na tela (sem valores de custo)."""
        buffer = io.StringIO()
        escritor = csv.writer(buffer)
        escritor.writerow(["Equipe", "Recurso", "ARN", "Serviço", "Região"])
        for grupo in self.grupos:
            for recurso in grupo["recursos"]:
                escritor.writerow(
                    [grupo["equipe"], recurso["nome"], recurso["arn"], recurso["servico"], recurso["regiao"]]
                )
        return rx.download(
            data=buffer.getvalue(),
            filename=f"costguard-recursos-{self.codigo.lower() or 'projeto'}.csv",
        )

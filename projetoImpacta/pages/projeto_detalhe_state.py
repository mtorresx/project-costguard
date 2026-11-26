"""Estado da página de detalhamento de projeto ("/projetos/[projeto_id]").

Consome somente endpoints reais já existentes (api_group `app`):
- GET /projetos/{id}
- GET /projetos/{id}/custos-equipe (janela = mês corrente até a data atual)
- GET /projetos/{id}/recursos
- GET /projetos/{id}/equipes

Não há dado fictício, projeção, tendência nem custo por provedor. O custo por
recurso (`custo_mensal`, USD) é só exibido na tabela; os totais do projeto vêm de
custos-equipe e não são recalculados a partir dele. Os blocos de custo e de recursos carregam de forma independente: uma
falha em um não esconde o outro.

O mês é determinado no fuso America/Sao_Paulo (ver `janela_mtd`). A semântica do
backend não muda: `data_inicio` é inclusiva e `data_fim` é exclusiva.

A autorização permanece no backend. O frontend não é mecanismo de segurança.
"""

from __future__ import annotations

import asyncio
import math
import re
import time
from datetime import date, datetime, timedelta
from typing import Any, Optional, TypedDict
from zoneinfo import ZoneInfo

import httpx
import reflex as rx

from ..components.mensagens import sucesso

from .. import api
from ..formatadores import formatar_valor, numero_br, percentual_br
from ..api import cliente_xano
from ..config import get_xano_app_base_url
from ..components.periodo_state import PeriodoState, janela_mes
from ..sincronizacao_auto import recurso_novo
from ..state import AuthState

FUSO_MTD = ZoneInfo("America/Sao_Paulo")
MOEDA_ORCAMENTO = "USD"

TEXTO_ERRO_PROJETO = "Não foi possível carregar o projeto."
TEXTO_ERRO_CUSTOS = "Não foi possível carregar os custos do período."
TEXTO_ERRO_RECURSOS = "Não foi possível carregar os recursos do projeto."
TEXTO_SEM_CUSTO = "Sem custos classificados no mês até a data atual."
TEXTO_SEM_CUSTO_FECHADO = "Sem custos classificados neste mês."
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


ROTAS_NOTIFICACAO = {
    "orcamento": "notificar-devops",
    "recursos": "notificar-recursos-sem-equipe",
}


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
    novo: bool
    custo_mensal: str


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


def texto_custo_recurso(valor: Any) -> str:
    """Custo mensal do recurso em USD, formato pt-BR sem prefixo (o cabeçalho diz USD).

    Nulo, ausente, booleano, não numérico ou não finito: "—" (nunca "0,00" inventado).
    Zero real: "0,00". Aceita número ou string numérica ("6.5").
    """
    if valor is None or isinstance(valor, bool):
        return "—"
    try:
        numero = float(valor.strip() if isinstance(valor, str) else valor)
    except (TypeError, ValueError):
        return "—"
    if not math.isfinite(numero):
        return "—"
    return numero_br(numero)


async def _buscar(url: str, token: str, params: Optional[dict] = None) -> tuple[int, Any]:
    """GET autenticado no Xano. Devolve (status HTTP, corpo JSON ou None); status 0 = falha de rede."""
    try:
        async with cliente_xano(30) as client:
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
    tem_email_devops: bool = False
    enviando: str = ""
    bloqueados: list[str] = []
    avisos: dict[str, str] = {}
    dica_devops: str = ""
    _prazos: dict[str, float] = {}
    _projeto_devops: str = ""

    # Custos classificados no mês (GET /projetos/{id}/custos-equipe).
    periodo: str = ""
    mes_fechado: bool = False
    texto_sem_custo: str = TEXTO_SEM_CUSTO
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
    texto_sem_responsavel: str = ""
    equipes_recolhidas: list[str] = []
    # Recursos ativos por equipe na última carga do inventário (None = não carregou).
    # Guardado para que recarregar só os custos (troca de mês) não apague a contagem.
    _contagem_equipes: Optional[dict[str, int]] = None

    @rx.var
    def grupos_com_equipe_ou_tag(self) -> list[GrupoRecursos]:
        return [grupo for grupo in self.grupos if grupo["chave"] != "sem"]

    @rx.var
    def recursos_sem_equipe(self) -> list[RecursoDetalhe]:
        return next((grupo["recursos"] for grupo in self.grupos if grupo["chave"] == "sem"), [])

    def _texto_contagem(self, chave: str) -> str:
        if self._contagem_equipes is None:
            return ""
        return f"({_texto_recursos(self._contagem_equipes.get(chave, 0))})"

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
        self.tem_email_devops = False
        self.avisos = {}
        self.bloqueados = []
        self.dica_devops = "Carregando disponibilidade da notificação…"
        self._projeto_devops = ""
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

        # As quatro leituras são independentes: em paralelo.
        mes = (await self.get_state(PeriodoState)).preparar()
        inicio, fim, corrente = janela_mes(mes, datetime.now(FUSO_MTD))
        self.mes_fechado = not corrente
        self.texto_sem_custo = TEXTO_SEM_CUSTO if corrente else TEXTO_SEM_CUSTO_FECHADO
        self.periodo = texto_periodo(inicio, fim) + ("" if corrente else " (mês fechado)")
        self.carregando_custos = True
        self.carregando_recursos = True
        self.erro_custos = ""
        self.erro_recursos = ""
        base = self._base()
        (status, painel), (status_c, custos) = await asyncio.gather(
            _buscar(f"{base}/painel", token),
            _buscar(f"{base}/custos-equipe", token,
                    params={"data_inicio": inicio.isoformat(), "data_fim": fim.isoformat()}),
        )
        painel_ok = status == 200 and isinstance(painel, dict)
        corpo = painel.get("projeto") if painel_ok else None
        recursos = painel.get("recursos") if painel_ok else None
        equipes = painel.get("equipes") if painel_ok else None
        status_r = status_e = status
        self.carregando = False
        self.carregando_custos = False
        self.carregando_recursos = False
        if 401 in (status, status_c, status_r, status_e):
            yield AuthState.handle_unauthenticated
            return
        if status == 404:
            self.nao_encontrado = True
            return
        if status != 200 or not isinstance(corpo, dict):
            self.erro = TEXTO_ERRO_PROJETO
            return

        self._preencher_projeto(corpo)

        if status_c != 200 or not isinstance(custos, dict):
            self.erro_custos = TEXTO_ERRO_CUSTOS
        else:
            self._preencher_custos(custos)

        if status_r != 200 or status_e != 200 or not isinstance(recursos, list) or not isinstance(equipes, list):
            self.erro_recursos = TEXTO_ERRO_RECURSOS
            self.grupos = []
            self.total_sem_responsavel = 0
            self.bloco_sem_responsavel = False
            self._contagem_equipes = None
        else:
            self._montar_recursos(recursos, equipes)
        yield ProjetoDetalheState.carregar_devops

    @rx.event
    async def carregar_devops(self):
        # O painel agregado não inclui tem_email_devops. Só o detalhe aberto lê o cadastro.
        projeto = str(self.projeto_id)
        token = await self._token()
        if not token:
            yield AuthState.handle_unauthenticated
            return
        status, corpo = await api.requisitar("GET", f"/projetos/{projeto}", token)
        if status == 401:
            yield AuthState.handle_unauthenticated
            return
        self._projeto_devops = projeto
        agora = time.time()
        self._prazos = {k: fim for k, fim in self._prazos.items() if fim > agora}
        self.bloqueados = [tipo for tipo in ROTAS_NOTIFICACAO if f"{projeto}:{tipo}" in self._prazos]
        if (status != 200 or not isinstance(corpo, dict)
                or not isinstance(corpo.get("tem_email_devops"), bool)):
            self.tem_email_devops = False
            self.dica_devops = "Recurso indisponível no servidor agora."
            return
        self.tem_email_devops = corpo["tem_email_devops"]
        self.inativo = corpo.get("status") != "ativo"
        self.status_texto = "Inativo" if self.inativo else "Ativo"
        self.dica_devops = "" if self.tem_email_devops else "defina o e-mail do DevOps no projeto"
        for tipo in self.bloqueados:
            yield ProjetoDetalheState.liberar_notificacao(projeto, tipo)

    @rx.event(background=True)
    async def liberar_notificacao(self, projeto: str, tipo: str):
        chave = f"{projeto}:{tipo}"
        async with self:
            fim = self._prazos.get(chave, 0)
        await asyncio.sleep(max(0, fim - time.time()))
        async with self:
            if self._projeto_devops == projeto and self._prazos.get(chave, 0) <= time.time():
                self.bloqueados = [item for item in self.bloqueados if item != tipo]

    @rx.event
    async def notificar(self, tipo: str):
        projeto = str(self.projeto_id)
        if (tipo not in ROTAS_NOTIFICACAO or projeto != self._projeto_devops or self.inativo
                or not self.tem_email_devops or self.enviando or tipo in self.bloqueados):
            return
        if tipo == "recursos" and (self.carregando_recursos or self.erro_recursos or not self.total_sem_responsavel):
            return
        token = await self._token()
        if not token:
            yield AuthState.handle_unauthenticated
            return
        self.enviando = tipo
        self.avisos.pop(tipo, None)
        yield
        status, corpo = await api.requisitar("POST", f"/projetos/{projeto}/{ROTAS_NOTIFICACAO[tipo]}", token)
        self.enviando = ""
        if status == 401:
            yield AuthState.handle_unauthenticated
            return
        dados = corpo if isinstance(corpo, dict) else {}
        mensagem = ""
        if status == 200:
            if tipo == "orcamento" and dados.get("status") == "enviado":
                mensagem = dados.get("mensagem") or ""
            elif tipo == "recursos" and dados.get("enviado") is True:
                quantidade = dados.get("quantidade")
                destinatario = dados.get("destinatario_mascarado")
                if type(quantidade) is int and quantidade > 0 and isinstance(destinatario, str) and destinatario:
                    mensagem = f"Notificação enviada para {destinatario}. Recursos sem equipe: {quantidade}."
        if mensagem:
            segundos = 300
            yield sucesso(mensagem)
        else:
            aviso = dados.get("message") or "Recurso indisponível no servidor agora."
            self.avisos[tipo] = aviso
            segundos = api.segundos_restantes(dados) if status == 429 else None
            if status == 429 and aviso == "Limite diário de notificações atingido; tente amanhã.":
                agora = datetime.now(FUSO_MTD)
                amanha = (agora + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                segundos = (amanha - agora).total_seconds()
        if segundos:
            self._prazos[f"{projeto}:{tipo}"] = time.time() + segundos
            self.bloqueados.append(tipo)
            yield ProjetoDetalheState.liberar_notificacao(projeto, tipo)

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
        mes = (await self.get_state(PeriodoState)).preparar()
        inicio, fim, corrente = janela_mes(mes, datetime.now(FUSO_MTD))
        self.mes_fechado = not corrente
        self.texto_sem_custo = TEXTO_SEM_CUSTO if corrente else TEXTO_SEM_CUSTO_FECHADO
        self.periodo = texto_periodo(inicio, fim) + ("" if corrente else " (mês fechado)")
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
            self.rodape_custo = self.texto_sem_custo
            self.comparacao_texto = self.texto_sem_custo
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
                chave=f"eq:{item.get('equipe_id')}",
                nome=item.get("nome") or item.get("codigo") or "",
                recursos_texto=self._texto_contagem(f"eq:{item.get('equipe_id')}"),
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
        self.percentual_texto = f"{percentual_br(percentual)} utilizado de {self.budget_texto}"
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

        (status_r, recursos), (status_e, equipes) = await asyncio.gather(
            _buscar(f"{self._base()}/recursos", token),
            _buscar(f"{self._base()}/equipes", token),
        )
        if 401 in (status_r, status_e):
            self.carregando_recursos = False
            yield AuthState.handle_unauthenticated
            return

        self.carregando_recursos = False
        if status_r != 200 or status_e != 200 or not isinstance(recursos, list) or not isinstance(equipes, list):
            self.erro_recursos = TEXTO_ERRO_RECURSOS
            self.grupos = []
            self.total_sem_responsavel = 0
            self.bloco_sem_responsavel = False
            self._contagem_equipes = None
            return

        self._montar_recursos(recursos, equipes)

    def _montar_recursos(self, recursos: list, equipes: list):
        """Agrupa os recursos ativos pelo vínculo real com a equipe.

        Regras aprovadas (E2E, inconsistência de backend):
        - equipe_id > 0: grupo da equipe real (chave "eq:<id>");
        - equipe_id ausente ou 0 e tag vazia: "Sem responsável" (chave "sem");
        - equipe_id ausente ou 0 e tag preenchida: "Equipe não vinculada — <TAG>",
          um grupo por tag (chave "nv:<TAG>"), sem misturar tags nem criar equipe.
        """
        nomes = {
            str(e.get("id")): (e.get("nome") or e.get("codigo") or "")
            for e in equipes
            if isinstance(e, dict)
        }
        ativos = [r for r in recursos if isinstance(r, dict) and r.get("ativo") is True]
        agora_ms = int(time.time() * 1000)

        por_chave: dict[str, list[dict]] = {}
        rotulos: dict[str, str] = {}
        for r in ativos:
            eid = r.get("equipe_id")
            if isinstance(eid, int) and eid > 0:
                chave = f"eq:{eid}"
                rotulos[chave] = nomes.get(str(eid)) or "Equipe sem nome"
            else:
                tag = (r.get("codigo_equipe_tag") or "").strip()
                if tag:
                    chave = f"nv:{tag}"
                    rotulos[chave] = f"Equipe não vinculada — {tag}"
                else:
                    chave = "sem"
                    rotulos[chave] = TEXTO_SEM_RESPONSAVEL
            por_chave.setdefault(chave, []).append(r)

        grupos: list[GrupoRecursos] = []
        for chave, itens in por_chave.items():
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
                        novo=recurso_novo(r.get("descoberto_em"), agora_ms),
                        custo_mensal=texto_custo_recurso(r.get("custo_mensal")),
                    )
                )
            grupos.append(
                GrupoRecursos(
                    chave=chave,
                    equipe=rotulos[chave],
                    total_texto=_texto_recursos(len(itens)),
                    recursos=detalhes,
                )
            )

        # Ordem: equipes reais por nome, depois "Equipe não vinculada", "Sem responsável" por último.
        def ordem(g: GrupoRecursos) -> tuple[int, str]:
            if g["chave"] == "sem":
                return (2, "")
            if g["chave"].startswith("nv:"):
                return (1, g["equipe"].casefold())
            return (0, g["equipe"].casefold())

        grupos.sort(key=ordem)
        self.grupos = grupos
        self.total_sem_responsavel = len(por_chave.get("sem", []))
        self.bloco_sem_responsavel = self.total_sem_responsavel > 0
        self.texto_sem_responsavel = (
            f"{self.total_sem_responsavel} recurso" + ("" if self.total_sem_responsavel == 1 else "s")
            + " ativo" + ("" if self.total_sem_responsavel == 1 else "s") + " sem equipe e sem tag de equipe."
        )
        self.equipes_recolhidas = []

        # Contagem de recursos ativos por equipe real, somente quando o inventário carregou.
        self._contagem_equipes = {chave: len(itens) for chave, itens in por_chave.items()}
        self.equipes_custo = [
            EquipeCusto(
                chave=item["chave"],
                nome=item["nome"],
                recursos_texto=self._texto_contagem(item["chave"]),
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
    async def mudar_mes(self, valor: str):
        periodo = await self.get_state(PeriodoState)
        periodo.mes = valor
        yield ProjetoDetalheState.carregar_custos

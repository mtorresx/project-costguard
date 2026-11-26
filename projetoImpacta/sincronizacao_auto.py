"""Sincronização automática do inventário.

Duas peças, nenhuma com regra de negócio:

1. Gatilho: tarefa de ciclo de vida do servidor Reflex que, a cada
   intervalo, faz `POST /sincronizacao/automatica` no Xano com o segredo no
   cabeçalho `X-Sync-Key`. Quem escolhe o provedor, sincroniza, trava e
   registra falhas é o Xano. O ciclo NÃO consulta custos.

2. Acompanhamento da tela: evento em segundo plano por aba aberta,
   que consulta `GET /sincronizacao/estado` a cada 30 s e recarrega a página só
   quando `versao` muda. Para quando o cliente desconecta.

Variáveis de ambiente (`.env`):
- `COSTGUARD_SYNC_ATIVO`: `1` liga o ciclo. Ausente ou outro valor: desligado.
- `COSTGUARD_SYNC_KEY`: segredo do gatilho (igual a `SYNC_AGENT_KEY` no Xano).
  Nunca é impresso nem registrado em log.
- `COSTGUARD_SYNC_INTERVALO`: segundos entre ciclos (padrão 120, mínimo 30).
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone
from typing import Any, Mapping, Optional
from zoneinfo import ZoneInfo

import reflex as rx

from .api import cliente_xano, limpar_cache, requisitar
from .config import get_xano_app_base_url
from .state import AuthState

CABECALHO_CHAVE = "X-Sync-Key"
INTERVALO_PADRAO = 120
INTERVALO_MINIMO = 30
INTERVALO_TELA = 30
JANELA_NOVO_MS = 48 * 60 * 60 * 1000
TEXTO_NOVO = "Novo · custo ainda não disponível"
FUSO = ZoneInfo("America/Sao_Paulo")
_VALORES_LIGADO = ("1", "true", "sim", "on")


# ---------------------------------------------------------------------------
# Regras puras (testadas em tests/test_sincronizacao_auto.py)
# ---------------------------------------------------------------------------

def intervalo_ciclo(env: Optional[Mapping[str, str]] = None) -> int:
    """Segundos entre ciclos: `COSTGUARD_SYNC_INTERVALO`, padrão 120, mínimo 30."""
    bruto = (os.environ if env is None else env).get("COSTGUARD_SYNC_INTERVALO", "")
    try:
        valor = int(str(bruto).strip())
    except (TypeError, ValueError):
        return INTERVALO_PADRAO
    return max(INTERVALO_MINIMO, valor)


def ciclo_ligado(env: Optional[Mapping[str, str]] = None) -> tuple[bool, str]:
    """(ligado, motivo). Só liga com `COSTGUARD_SYNC_ATIVO=1` e a chave definida."""
    env = os.environ if env is None else env
    if str(env.get("COSTGUARD_SYNC_ATIVO", "")).strip().lower() not in _VALORES_LIGADO:
        return False, "COSTGUARD_SYNC_ATIVO não está ligado"
    if not str(env.get("COSTGUARD_SYNC_KEY", "")).strip():
        return False, "COSTGUARD_SYNC_KEY não está definida"
    return True, ""


def _ms(valor: Any) -> int:
    """Timestamp do Xano em ms; 0 quando ausente (o Xano devolve 0 para nulo)."""
    try:
        return int(valor or 0)
    except (TypeError, ValueError):
        return 0


def recurso_novo(descoberto_em: Any, agora_ms: int) -> bool:
    """Recurso descoberto há menos de 48 h. Sem data, não é novo."""
    ms = _ms(descoberto_em)
    return ms > 0 and 0 <= agora_ms - ms < JANELA_NOVO_MS


def _tempo_relativo(ms: int, agora_ms: int) -> str:
    segundos = max(0, (agora_ms - ms) // 1000)
    if segundos < 60:
        return "agora"
    minutos = segundos // 60
    if minutos < 60:
        return f"há {minutos} min"
    horas = minutos // 60
    if horas < 24:
        return f"há {horas} h"
    dias = horas // 24
    return "há 1 dia" if dias == 1 else f"há {dias} dias"


def _data_hora(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).astimezone(FUSO).strftime("%d/%m/%Y %H:%M")


def texto_sincronizacao(item: Any, agora_ms: int) -> dict[str, str]:
    """Textos do estado do inventário de um provedor para a página de provedores.

    `texto`: "Sincronizado há X min" (ou "Ainda não sincronizado"); vazio em erro.
    `erro`: mensagem sanitizada do backend quando a última execução falhou.
    `ultima_boa`: data e hora da última sincronização bem-sucedida, em erro.
    """
    vazio = {"texto": "", "erro": "", "ultima_boa": ""}
    if not isinstance(item, dict):
        return vazio
    tentativa = _ms(item.get("ultima_tentativa"))
    sucesso = _ms(item.get("ultimo_sucesso"))
    if tentativa == 0:
        return {**vazio, "texto": "Ainda não sincronizado"}
    if item.get("ultimo_status") == "erro":
        mensagem = str(item.get("ultima_mensagem") or "").strip() or "Falha na sincronização de recursos"
        boa = (
            f"Última sincronização boa: {_data_hora(sucesso)} ({_tempo_relativo(sucesso, agora_ms)})"
            if sucesso
            else "Nenhuma sincronização bem-sucedida até agora"
        )
        return {"texto": "", "erro": mensagem, "ultima_boa": boa}
    referencia = sucesso or tentativa
    relativo = _tempo_relativo(referencia, agora_ms)
    return {**vazio, "texto": "Sincronizado agora" if relativo == "agora" else f"Sincronizado {relativo}"}


def estado_por_provedor(corpo: Any, agora_ms: Optional[int] = None) -> dict[int, dict[str, str]]:
    """Resposta de `/sincronizacao/estado` -> {provedor_id: textos}."""
    if not isinstance(corpo, dict) or not isinstance(corpo.get("provedores"), list):
        return {}
    agora = agora_ms if agora_ms is not None else (_ms(corpo.get("agora")) or 0)
    saida: dict[int, dict[str, str]] = {}
    for item in corpo["provedores"]:
        if isinstance(item, dict) and isinstance(item.get("provedor_id"), int):
            saida[item["provedor_id"]] = texto_sincronizacao(item, agora)
    return saida


def versao_do_estado(corpo: Any) -> Optional[int]:
    if not isinstance(corpo, dict):
        return None
    try:
        return int(corpo.get("versao") or 0)
    except (TypeError, ValueError):
        return None


def resumo_ciclo(status: int, corpo: Any) -> str:
    """Linha de log de um ciclo. Só contadores e status; nunca a chave."""
    if status == 0:
        return "falha de rede"
    if status == 401:
        return "HTTP 401 (chave recusada pelo Xano)"
    if status != 200 or not isinstance(corpo, dict):
        return f"HTTP {status}"
    if not corpo.get("executou"):
        return f"nada a fazer ({corpo.get('motivo') or 'sem motivo'})"
    return (
        f"status={corpo.get('status')} criados={corpo.get('recursos_criados')} "
        f"alterados={corpo.get('recursos_alterados')} desativados={corpo.get('recursos_desativados')}"
    )


# ---------------------------------------------------------------------------
# Gatilho: tarefa de ciclo de vida
# ---------------------------------------------------------------------------

def _log(texto: str) -> None:
    print(f"[sinc] {texto}", file=sys.stderr, flush=True)


async def disparar_ciclo() -> tuple[int, Any]:
    """Um `POST /sincronizacao/automatica`. Devolve `(status, corpo)`; rede = `(0, None)`.

    Usa o transporte de `api.py`: entra na fila de vazão do plano Xano e, por ser
    escrita, limpa o cache de leitura (as telas passam a ler dados novos).
    """
    try:
        async with cliente_xano(120) as client:
            resp = await client.post(
                f"{get_xano_app_base_url()}/sincronizacao/automatica",
                headers={CABECALHO_CHAVE: os.environ.get("COSTGUARD_SYNC_KEY", "").strip()},
                json={},
            )
    except asyncio.CancelledError:
        raise
    except Exception:
        return 0, None
    try:
        corpo = resp.json()
    except Exception:
        corpo = None
    return resp.status_code, corpo


async def laco_sincronizacao() -> None:
    """Tarefa de ciclo de vida: dispara o ciclo a cada intervalo, enquanto o app roda.

    Desligada por padrão. Falha de rede ou do Xano nunca derruba o app: é
    registrada e o laço segue.
    """
    ligado, motivo = ciclo_ligado()
    if not ligado:
        _log(f"ciclo automático desligado: {motivo}")
        return
    intervalo = intervalo_ciclo()
    _log(f"ciclo automático ligado: um disparo a cada {intervalo} s")
    while True:
        try:
            status, corpo = await disparar_ciclo()
            _log(resumo_ciclo(status, corpo))
        except asyncio.CancelledError:
            raise
        except Exception as erro:  # nunca derruba o app
            _log(f"falha inesperada no disparo: {type(erro).__name__}")
        await asyncio.sleep(intervalo)


# ---------------------------------------------------------------------------
# Acompanhamento da tela
# ---------------------------------------------------------------------------

def _cliente_conectado(client_token: str) -> bool:
    """O navegador desta sessão ainda tem conexão aberta com o servidor?"""
    try:
        from reflex.utils.prerequisites import get_app

        return client_token in get_app().app.event_namespace.token_to_sid
    except Exception:
        return True  # sem como saber: segue; o laço também para sem token


def eventos_de_recarga(caminho: str) -> list:
    """Evento que recarrega os dados da página aberta quando o inventário muda."""
    from .pages.alertas_state import AlertasState
    from .pages.home_state import HomeState
    from .pages.projeto_detalhe_state import ProjetoDetalheState

    caminho = (caminho or "").rstrip("/") or "/"
    if caminho == "/inicio":
        return [HomeState.carregar]
    if caminho == "/alertas":
        return [AlertasState.carregar]
    if caminho.startswith("/projetos/"):
        return [ProjetoDetalheState.carregar_recursos]
    return []


class AcompanhamentoState(rx.State):
    """Consulta periódica do estado da sincronização, uma por aba aberta."""

    _acompanhando: bool = False
    _versao: int = -1

    @rx.event(background=True)
    async def acompanhar(self):
        from .pages.provedores_state import ProvedoresState

        async with self:
            if self._acompanhando:
                return
            self._acompanhando = True
        try:
            primeira = True
            while True:
                if not primeira:
                    await asyncio.sleep(INTERVALO_TELA)
                primeira = False

                async with self:
                    token = (await self.get_state(AuthState)).token
                    caminho = self.router.url.path
                    client_token = self.router.session.client_token
                    anterior = self._versao
                if not token or not _cliente_conectado(client_token):
                    return

                status, corpo = await requisitar("GET", "/sincronizacao/estado", token, forcar=True)
                if status == 401:
                    return
                versao = versao_do_estado(corpo) if status == 200 else None
                if versao is None:
                    continue  # falha passageira: tenta de novo no próximo intervalo

                async with self:
                    self._versao = versao
                if (caminho or "").rstrip("/") == "/provedores":
                    yield ProvedoresState.aplicar_estado(corpo)
                if anterior != -1 and versao != anterior:
                    limpar_cache()
                    for evento in eventos_de_recarga(caminho):
                        yield evento
        finally:
            async with self:
                self._acompanhando = False

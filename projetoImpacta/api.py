"""Chamadas HTTP ao api_group `app` do Xano, usadas pelos estados das páginas.

Cada função devolve `(status, corpo)`. Falha de rede ou JSON inválido vira
`(0, None)`, para que o estado mostre uma mensagem genérica sem vazar detalhes.
O tratamento de 401 continua em cada estado (`AuthState.handle_unauthenticated`).
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import sys
import time
from collections import deque
from typing import Any, Optional

import httpx

from .config import get_xano_app_base_url

ERRO_GENERICO = "Operação não permitida ou inválida."

# ---------------------------------------------------------------------------
# Desempenho. Todas as chamadas ao Xano
# passam por um único transporte que:
# 1) reaproveita conexões HTTPS (pool compartilhado, sem novo handshake);
# 2) controla a vazão no próprio app: o plano Xano aceita 10 requisições a cada
#    20 s; em vez de tomar HTTP 429 e esperar segundos, a requisição aguarda só
#    o tempo até abrir vaga na janela;
# 3) guarda por alguns segundos respostas 200 de leitura (GET), por token e URL,
#    para que navegar entre páginas não repita as mesmas consultas. Qualquer
#    escrita (POST/PATCH/DELETE) limpa o cache inteiro;
# 4) leituras (GET) ainda repetem após HTTP 429 (outros clientes no mesmo plano);
#    POST/PATCH/DELETE nunca repetem: o 429 volta na primeira resposta.
# ---------------------------------------------------------------------------
LIMITE_REQUISICOES = 10
JANELA_SEGUNDOS = 20.5  # pequena folga sobre os 20 s do plano
CACHE_SEGUNDOS = 60.0
CACHE_MAX_ITENS = 500
ESPERAS_429 = (2.0, 4.0, 8.0)
CABECALHO_FORCAR = "x-costguard-forcar"  # pede leitura sem cache (botão Atualizar)

_historico: deque[float] = deque()
_travas_vazao: dict[int, asyncio.Lock] = {}
_cache: dict[tuple[str, str], tuple[float, int, list, bytes]] = {}
_pools: dict[int, httpx.AsyncHTTPTransport] = {}
# Geração do cache: toda escrita incrementa no início e no fim. Uma leitura só é
# guardada se a geração não mudou enquanto ela estava em andamento (evita guardar
# um dado anterior a uma escrita concorrente).
_geracao = 0
# Diagnóstico opcional de desempenho: COSTGUARD_LOG_HTTP=1 imprime método, caminho
# (sem query string nem token), origem (cache/rede), espera na fila e duração.
_LOG_HTTP = os.getenv("COSTGUARD_LOG_HTTP") == "1"


def _log(request: httpx.Request, origem: str, espera: float, duracao: float, status: int) -> None:
    if _LOG_HTTP:
        print(f"[http] {request.method} {request.url.path} {origem} fila={espera:.2f}s dur={duracao:.2f}s -> {status}",
              file=sys.stderr, flush=True)


def limpar_cache() -> None:
    global _geracao
    _geracao += 1
    _cache.clear()


def _chave_token(autorizacao: str) -> str:
    """Hash do cabeçalho Authorization: o token bruto não fica retido no cache."""
    return hashlib.sha256(autorizacao.encode()).hexdigest() if autorizacao else ""


def _guardar(chave: tuple[str, str], valor: tuple[float, int, list, bytes]) -> None:
    agora = time.monotonic()
    for k in [k for k, v in _cache.items() if v[0] <= agora]:
        del _cache[k]
    while len(_cache) >= CACHE_MAX_ITENS:
        del _cache[next(iter(_cache))]  # remove a entrada mais antiga
    _cache[chave] = valor


def _pool() -> httpx.AsyncHTTPTransport:
    """Pool de conexões por event loop (reaproveita TLS entre requisições)."""
    loop_id = id(asyncio.get_running_loop())
    pool = _pools.get(loop_id)
    if pool is None:
        pool = httpx.AsyncHTTPTransport(limits=httpx.Limits(max_keepalive_connections=10, keepalive_expiry=60))
        _pools[loop_id] = pool
    return pool


async def _aguardar_vaga() -> None:
    """Fila FIFO: no máximo LIMITE_REQUISICOES por JANELA_SEGUNDOS."""
    loop_id = id(asyncio.get_running_loop())
    trava = _travas_vazao.get(loop_id)
    if trava is None:
        trava = _travas_vazao[loop_id] = asyncio.Lock()
    async with trava:
        while True:
            agora = time.monotonic()
            while _historico and agora - _historico[0] >= JANELA_SEGUNDOS:
                _historico.popleft()
            if len(_historico) < LIMITE_REQUISICOES:
                _historico.append(agora)
                return
            await asyncio.sleep(JANELA_SEGUNDOS - (agora - _historico[0]) + 0.05)


class _TransporteComRetentativa(httpx.AsyncBaseTransport):
    """Transporte compartilhado: cache de leitura, controle de vazão e nova tentativa em 429."""

    def __init__(self, esperas: tuple[float, ...] = ESPERAS_429):
        self._interno: Optional[httpx.AsyncBaseTransport] = None  # None = pool compartilhado
        self._esperas = esperas

    async def _enviar(self, request: httpx.Request) -> httpx.Response:
        t0 = time.monotonic()
        await _aguardar_vaga()
        t1 = time.monotonic()
        try:
            resposta = await (self._interno or _pool()).handle_async_request(request)
        except Exception as erro:
            if _LOG_HTTP:
                print(f"[http] {request.method} {request.url.path} falha de rede: {type(erro).__name__}",
                      file=sys.stderr, flush=True)
            raise
        _log(request, "rede", t1 - t0, time.monotonic() - t1, resposta.status_code)
        return resposta

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        forcar = CABECALHO_FORCAR in request.headers
        if forcar:
            del request.headers[CABECALHO_FORCAR]
        leitura = request.method == "GET"
        chave = (_chave_token(request.headers.get("authorization", "")), str(request.url))

        if leitura and not forcar:
            item = _cache.get(chave)
            if item and item[0] > time.monotonic():
                _, status, cabecalhos, conteudo = item
                _log(request, "cache", 0.0, 0.0, status)
                return httpx.Response(status, headers=cabecalhos, content=conteudo, request=request)
        if not leitura:
            limpar_cache()
        geracao_inicio = _geracao

        try:
            resposta = await self._enviar(request)
            # Só leitura (GET) repete após 429. Escrita devolve o 429 na primeira resposta:
            # repetir esconderia a mensagem (ex.: "aguarde N segundos") e poderia duplicar efeitos.
            for espera in self._esperas if leitura else ():
                if resposta.status_code != 429:
                    break
                await resposta.aclose()
                await asyncio.sleep(espera)
                resposta = await self._enviar(request)
        finally:
            if not leitura:
                # Leituras iniciadas durante a escrita não serão guardadas.
                limpar_cache()

        if leitura and resposta.status_code == 200:
            conteudo = await resposta.aread()
            cabecalhos = [(k, v) for k, v in resposta.headers.items()
                          if k.lower() not in ("content-encoding", "content-length", "transfer-encoding")]
            if _geracao == geracao_inicio:
                _guardar(chave, (time.monotonic() + CACHE_SEGUNDOS, 200, cabecalhos, conteudo))
            await resposta.aclose()
            return httpx.Response(200, headers=cabecalhos, content=conteudo, request=request)
        return resposta

    async def aclose(self) -> None:
        # O pool é compartilhado entre requisições: não fecha ao sair do `async with`.
        return None


def cliente_xano(timeout: float = 30, forcar: bool = False) -> httpx.AsyncClient:
    """Cliente HTTP para o Xano (cache curto, vazão controlada, nova tentativa em 429).

    `forcar=True` ignora o cache de leitura (ex.: botão Atualizar).
    """
    cabecalhos = {CABECALHO_FORCAR: "1"} if forcar else None
    return httpx.AsyncClient(timeout=timeout, transport=_TransporteComRetentativa(), headers=cabecalhos)


async def requisitar(
    metodo: str,
    caminho: str,
    token: str,
    corpo: Optional[dict] = None,
    params: Optional[dict] = None,
    timeout: float = 30,
    forcar: bool = False,
) -> tuple[int, Any]:
    """Faz a requisição autenticada e devolve `(status, json_ou_None)`."""
    try:
        async with cliente_xano(timeout, forcar) as client:
            resp = await client.request(
                metodo,
                f"{get_xano_app_base_url()}{caminho}",
                headers={"Authorization": f"Bearer {token}"},
                json=corpo,
                params=params,
            )
    except Exception as erro:
        if _LOG_HTTP:
            print(f"[http] {metodo} {caminho} falha: {type(erro).__name__}", file=sys.stderr, flush=True)
        return 0, None
    try:
        dados = resp.json()
    except Exception:
        dados = None
    return resp.status_code, dados


def segundos_restantes(corpo: Any) -> Optional[int]:
    """Segundos de espera de um 429 com limite próprio (1 a 300), ou None.

    Lê `segundos_restantes` do corpo; se não houver, extrai "Aguarde N segundos" da mensagem.
    """
    if not isinstance(corpo, dict):
        return None
    valor = corpo.get("segundos_restantes")
    if isinstance(valor, bool) or not isinstance(valor, int):
        texto = corpo.get("message")
        achado = re.search(r"Aguarde (\d+) segundos?", texto) if isinstance(texto, str) else None
        valor = int(achado.group(1)) if achado else None
    return None if valor is None else max(1, min(300, valor))


def mensagem_erro(corpo: Any, padrao: str = ERRO_GENERICO) -> str:
    """Mensagem curta vinda do backend (`message`), ou a mensagem padrão.

    Mensagens de limite de requisições do plano Xano viram um texto em português.
    """
    if isinstance(corpo, dict):
        if corpo.get("code") == "ERROR_CODE_TOO_MANY_REQUESTS":
            return "Muitas requisições em pouco tempo. Aguarde alguns segundos e tente novamente."
        texto = corpo.get("message") or corpo.get("erro") or corpo.get("error")
        if isinstance(texto, str) and texto.strip():
            return texto.strip()
    return padrao

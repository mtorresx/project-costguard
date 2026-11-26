"""Auxiliares dos testes: Xano falso (httpx.MockTransport) e árvore de estados do Reflex sem servidor.

As respostas gravadas ficam em `tests/fixtures/xano/`.
"""

from __future__ import annotations

import importlib
import inspect
import json
import pkgutil
from pathlib import Path
from typing import Any, Callable

import httpx
from reflex.state import State

import projetoImpacta
from projetoImpacta import api
from projetoImpacta.state import AuthState

FIXTURES = Path(__file__).parent / "fixtures" / "xano"
BASE_APP = "https://xano.teste/api:app"
BASE_AUTH = "https://xano.teste/api:auth"
TOKEN = "token-de-teste"


def gravada(nome: str) -> tuple[int, Any]:
    """(status, corpo) de uma resposta gravada do Xano."""
    dados = json.loads((FIXTURES / f"{nome}.json").read_text(encoding="utf-8"))
    return dados["status"], dados["corpo"]


class XanoFalso:
    """Responde por (método, caminho) e registra cada requisição recebida.

    O caminho é relativo ao api_group (`/painel`, `/me`). Rota não cadastrada
    devolve 404, para que o teste perceba uma chamada inesperada.
    """

    def __init__(self):
        self.rotas: dict[tuple[str, str], Any] = {}
        self.pedidos: list[httpx.Request] = []

    def responder(self, metodo: str, caminho: str, resposta: Any) -> None:
        """`resposta`: (status, corpo), nome de fixture, ou função(request) -> (status, corpo)."""
        self.rotas[(metodo, caminho)] = resposta

    def _caminho(self, request: httpx.Request) -> str:
        for base in (BASE_APP, BASE_AUTH):
            prefixo = httpx.URL(base).path
            if request.url.path.startswith(prefixo):
                return request.url.path[len(prefixo):]
        return request.url.path

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.pedidos.append(request)
        resposta = self.rotas.get((request.method, self._caminho(request)))
        if resposta is None:
            return httpx.Response(404, json={"message": "rota não gravada no teste"})
        if callable(resposta):
            resposta = resposta(request)
        if isinstance(resposta, str):
            resposta = gravada(resposta)
        status, corpo = resposta
        if isinstance(corpo, Exception):
            raise corpo
        return httpx.Response(status, json=corpo)

    def chamadas(self) -> list[tuple[str, str]]:
        return [(r.method, self._caminho(r)) for r in self.pedidos]

    def corpo(self, indice: int) -> Any:
        conteudo = self.pedidos[indice].content
        return json.loads(conteudo) if conteudo else None


def _modulos_do_app():
    yield projetoImpacta
    for info in pkgutil.walk_packages(projetoImpacta.__path__, "projetoImpacta."):
        yield importlib.import_module(info.name)


def instalar_xano_falso(monkeypatch) -> XanoFalso:
    """Troca o transporte e as URLs base em todos os módulos do app."""
    falso = XanoFalso()

    def cliente(timeout: float = 30, forcar: bool = False) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(falso), timeout=timeout)

    for modulo in _modulos_do_app():
        for nome, valor in (("cliente_xano", cliente),
                            ("get_xano_app_base_url", lambda: BASE_APP),
                            ("get_xano_base_url", lambda: BASE_AUTH)):
            if hasattr(modulo, nome):
                monkeypatch.setattr(modulo, nome, valor)
    api.limpar_cache()
    return falso


class Arvore:
    """Árvore de estados do Reflex montada em memória (sem servidor nem navegador)."""

    def __init__(self):
        self.raiz = State(_reflex_internal_init=True)
        self.de(AuthState).token = TOKEN

    def de(self, classe):
        return self.raiz.get_substate(classe.get_full_name().split("."))


async def rodar(evento: Callable, estado, *args) -> list:
    """Executa o handler real de um evento e devolve o que ele emitiu (yield/return)."""
    saida = evento.fn(estado, *args)
    emitidos = []
    if inspect.isasyncgen(saida):
        async for item in saida:
            emitidos.append(item)
    elif inspect.iscoroutine(saida):
        emitidos.append(await saida)
    else:
        emitidos.append(saida)
    return [e for e in emitidos if e is not None]


def nomes_eventos(emitidos: list) -> list[str]:
    """Nome curto de cada evento emitido (ex.: `handle_unauthenticated`)."""
    nomes = []
    for e in emitidos:
        for item in e if isinstance(e, list) else [e]:
            fn = getattr(item, "fn", None) or getattr(getattr(item, "handler", None), "fn", None)
            nomes.append(getattr(fn, "__name__", type(item).__name__))
    return nomes

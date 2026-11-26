"""Fixtures comuns: Xano falso e árvore de estados (ver `apoio.py`)."""

import pytest

from apoio import Arvore, XanoFalso, instalar_xano_falso


@pytest.fixture
def xano(monkeypatch) -> XanoFalso:
    return instalar_xano_falso(monkeypatch)


@pytest.fixture
def arvore() -> Arvore:
    return Arvore()


def pytest_addoption(parser):
    parser.addoption("--integracao", action="store_true", default=False,
                     help="roda os testes de tests/integracao contra o Xano real")

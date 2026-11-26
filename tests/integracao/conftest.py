"""Testes contra o Xano real. Só rodam com `--integracao`.

    .venv/Scripts/python -m pytest tests/integracao --integracao -v
"""

import pytest

from cliente import PREFIXO, Vivo


def pytest_collection_modifyitems(config, items):
    if config.getoption("--integracao"):
        return
    pular = pytest.mark.skip(reason="teste de integração: rode com --integracao")
    for item in items:
        if "integracao" in str(item.fspath):
            item.add_marker(pular)


@pytest.fixture(scope="session")
def vivo() -> Vivo:
    return Vivo()


@pytest.fixture(scope="session")
def provedores_antes(vivo):
    """Provedores que não são de teste, para conferir que nenhum foi tocado."""
    st, lista = vivo.x("GET", "/provedores")
    assert st == 200, st
    assert not [p for p in lista if p["apelido"].startswith(PREFIXO)], "há provedor TESTE_ de uma execução anterior"
    return sorted((p["id"], p["apelido"], p["status"]) for p in lista)


@pytest.fixture
def provedor_teste(vivo, provedores_antes, request):
    """Provedor TESTE_ com credencial fictícia (fica "pendente"), apagado ao final."""
    pid = vivo.criar_provedor_teste(request.node.name[:20].upper())
    try:
        yield pid
    finally:
        st, r = vivo.apagar_provedor_teste(pid)
        assert st == 200, ("limpeza do provedor de teste falhou", st, r)
        st, lista = vivo.x("GET", "/provedores")
        assert sorted((p["id"], p["apelido"], p["status"]) for p in lista) == provedores_antes

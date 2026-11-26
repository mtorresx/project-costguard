"""Transporte compartilhado de `api.py`: cache de leitura, escrita limpa o cache, 429 e fila de vazão."""

import asyncio

import httpx
import pytest

from projetoImpacta import api

URL = "https://xano.teste/api:app/painel"


@pytest.fixture(autouse=True)
def limpo(monkeypatch):
    api.limpar_cache()
    api._historico.clear()
    yield
    api.limpar_cache()
    api._historico.clear()


def _cliente(manipulador, esperas=(0.0, 0.0, 0.0), forcar=False) -> httpx.AsyncClient:
    transporte = api._TransporteComRetentativa(esperas)
    transporte._interno = httpx.MockTransport(manipulador)
    return httpx.AsyncClient(transport=transporte, headers={api.CABECALHO_FORCAR: "1"} if forcar else None)


async def _get(manipulador, token="a", **kw):
    async with _cliente(manipulador, **kw) as c:
        return await c.get(URL, headers={"Authorization": f"Bearer {token}"})


def test_leitura_repetida_vem_do_cache_e_forcar_ignora():
    chamadas = []

    def man(req):
        chamadas.append(req)
        return httpx.Response(200, json={"n": len(chamadas)})

    async def cenario():
        r1 = await _get(man)
        r2 = await _get(man)
        r3 = await _get(man, forcar=True)
        return r1.json(), r2.json(), r3.json()

    assert asyncio.run(cenario()) == ({"n": 1}, {"n": 1}, {"n": 2})
    assert api.CABECALHO_FORCAR not in chamadas[1].headers  # cabeçalho interno não sai para o Xano


def test_cache_separado_por_token():
    chamadas = []
    man = lambda req: chamadas.append(req) or httpx.Response(200, json={})

    async def cenario():
        await _get(man, token="a")
        await _get(man, token="b")

    asyncio.run(cenario())
    assert len(chamadas) == 2
    assert all("Bearer" not in k[0] for k in api._cache)  # só o hash do token fica retido


def test_escrita_limpa_o_cache():
    chamadas = []
    man = lambda req: chamadas.append(req.method) or httpx.Response(200, json={})

    async def cenario():
        await _get(man)
        async with _cliente(man) as c:
            await c.post(URL, json={})
        await _get(man)

    asyncio.run(cenario())
    assert chamadas == ["GET", "POST", "GET"]


def test_erro_nao_vai_para_o_cache():
    chamadas = []
    man = lambda req: chamadas.append(1) or httpx.Response(500, json={})

    async def cenario():
        await _get(man)
        await _get(man)

    asyncio.run(cenario())
    assert len(chamadas) == 2


def test_429_tenta_de_novo_e_desiste_depois_das_esperas():
    respostas = iter([429, 429, 200])
    man = lambda req: httpx.Response(next(respostas), json={})
    assert asyncio.run(_get(man)).status_code == 200

    sempre = lambda req: httpx.Response(429, json={"code": "ERROR_CODE_TOO_MANY_REQUESTS"})
    assert asyncio.run(_get(sempre, forcar=True)).status_code == 429
    assert api.mensagem_erro({"code": "ERROR_CODE_TOO_MANY_REQUESTS"}).startswith("Muitas requisições")


CORPO_LIMITE = {
    "code": "ERROR_CODE_TOO_MANY_REQUESTS",
    "message": "Já foi enviado um alerta deste projeto há pouco. Aguarde 42 segundos para enviar outro.",
    "segundos_restantes": 42,
}


@pytest.fixture
def dormidas(monkeypatch):
    """Registra os `asyncio.sleep` do módulo sem esperar de verdade."""
    registro = []

    async def dormir(segundos):
        registro.append(segundos)

    monkeypatch.setattr(api.asyncio, "sleep", dormir)
    return registro


def test_get_429_repete_com_espera_e_depois_sucede(dormidas):
    respostas = iter([429, 429, 200])
    chamadas = []

    def man(req):
        chamadas.append(req.method)
        return httpx.Response(next(respostas), json={"ok": True})

    resp = asyncio.run(_get(man, esperas=(2.0, 4.0, 8.0)))
    assert resp.status_code == 200
    assert chamadas == ["GET", "GET", "GET"]
    assert dormidas == [2.0, 4.0]


@pytest.mark.parametrize("metodo", ["POST", "PATCH", "DELETE"])
def test_escrita_429_nao_repete_nem_dorme(metodo, dormidas):
    chamadas = []

    def man(req):
        chamadas.append(req.method)
        return httpx.Response(429, json=CORPO_LIMITE)

    async def cenario():
        async with _cliente(man, esperas=(2.0, 4.0, 8.0)) as c:
            return await c.request(metodo, URL, json={}, headers={"Authorization": "Bearer a"})

    resp = asyncio.run(cenario())
    assert resp.status_code == 429
    assert chamadas == [metodo], "escrita deve fazer exatamente UMA chamada (sem reenvio)"
    assert dormidas == [], "escrita não deve dormir antes de devolver o 429"
    assert resp.json() == CORPO_LIMITE


@pytest.mark.parametrize("metodo", ["POST", "PATCH", "DELETE"])
def test_requisitar_escrita_429_preserva_status_mensagem_e_segundos(metodo, monkeypatch, dormidas):
    chamadas = []

    def man(req):
        chamadas.append(req.method)
        return httpx.Response(429, json=CORPO_LIMITE)

    monkeypatch.setattr(api, "get_xano_app_base_url", lambda: "https://xano.teste/api:app")
    monkeypatch.setattr(api, "cliente_xano", lambda timeout=30, forcar=False: _cliente(man, esperas=(2.0, 4.0, 8.0)))

    status, corpo = asyncio.run(api.requisitar(metodo, "/projetos/1/notificar-devops", "t", corpo={}))
    assert status == 429
    assert corpo["segundos_restantes"] == 42
    assert "Aguarde 42 segundos" in corpo["message"]
    assert chamadas == [metodo] and dormidas == []


def test_segundos_restantes_do_campo_ou_da_mensagem():
    assert api.segundos_restantes(CORPO_LIMITE) == 42
    # O Xano (precondition toomanyrequests) devolve só code/message: o número vem do texto.
    assert api.segundos_restantes({"code": "ERROR_CODE_TOO_MANY_REQUESTS",
                                   "message": "Já foi enviado. Aguarde 7 segundos para enviar outro."}) == 7
    assert api.segundos_restantes({"segundos_restantes": 9999}) == 300
    assert api.segundos_restantes({"segundos_restantes": 0}) == 1
    for invalido in (None, {}, {"message": "sem número"}, {"segundos_restantes": "x"},
                     {"segundos_restantes": True}, "texto", []):
        assert api.segundos_restantes(invalido) is None


def test_fila_espera_quando_a_janela_esta_cheia(monkeypatch):
    relogio = [1000.0]
    esperas = []

    async def dormir(segundos):
        esperas.append(round(segundos, 2))
        relogio[0] += segundos

    monkeypatch.setattr(api.time, "monotonic", lambda: relogio[0])
    monkeypatch.setattr(api.asyncio, "sleep", dormir)

    async def cenario():
        for _ in range(api.LIMITE_REQUISICOES + 1):
            await api._aguardar_vaga()

    asyncio.run(cenario())
    # 10 passam na hora; a 11ª espera a janela abrir (20,5 s + folga).
    assert esperas == [round(api.JANELA_SEGUNDOS + 0.05, 2)]


def test_requisitar_devolve_zero_em_falha_de_rede(monkeypatch):
    def quebra(req):
        raise httpx.ConnectError("sem rede")

    monkeypatch.setattr(api, "get_xano_app_base_url", lambda: "https://xano.teste/api:app")
    monkeypatch.setattr(api, "cliente_xano",
                        lambda timeout=30, forcar=False: httpx.AsyncClient(transport=httpx.MockTransport(quebra)))
    assert asyncio.run(api.requisitar("GET", "/painel", "t")) == (0, None)


def test_mensagem_erro():
    assert api.mensagem_erro({"message": " Acesso negado "}) == "Acesso negado"
    assert api.mensagem_erro({"erro": "x"}) == "x"
    assert api.mensagem_erro(None) == api.ERRO_GENERICO
    assert api.mensagem_erro({"message": ""}, "padrão") == "padrão"

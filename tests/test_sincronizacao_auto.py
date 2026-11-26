"""Sincronização automática no frontend (lote 3b-3): regras puras e o gatilho, sem rede real."""

import asyncio

import httpx
import pytest

from projetoImpacta import sincronizacao_auto as sa
from projetoImpacta.pages.alertas_state import AlertasState, normalizar_recurso
from projetoImpacta.pages.home_state import HomeState
from projetoImpacta.pages.projeto_detalhe_state import ProjetoDetalheState
from projetoImpacta.pages.provedores_state import _normalizar, com_estado

HORA = 60 * 60 * 1000
AGORA = 1_794_600_000_000
CHAVE = "chave-de-teste-nao-e-segredo"


# --- configuração do ciclo ---

def test_ciclo_desligado_por_padrao_e_sem_chave():
    assert sa.ciclo_ligado({}) == (False, "COSTGUARD_SYNC_ATIVO não está ligado")
    assert sa.ciclo_ligado({"COSTGUARD_SYNC_KEY": CHAVE})[0] is False
    assert sa.ciclo_ligado({"COSTGUARD_SYNC_ATIVO": "0", "COSTGUARD_SYNC_KEY": CHAVE})[0] is False
    assert sa.ciclo_ligado({"COSTGUARD_SYNC_ATIVO": "1"}) == (False, "COSTGUARD_SYNC_KEY não está definida")
    assert sa.ciclo_ligado({"COSTGUARD_SYNC_ATIVO": "1", "COSTGUARD_SYNC_KEY": "  "})[0] is False


def test_ciclo_liga_com_ativo_e_chave():
    assert sa.ciclo_ligado({"COSTGUARD_SYNC_ATIVO": "1", "COSTGUARD_SYNC_KEY": CHAVE}) == (True, "")
    assert sa.ciclo_ligado({"COSTGUARD_SYNC_ATIVO": " True ", "COSTGUARD_SYNC_KEY": CHAVE})[0] is True


def test_intervalo_padrao_minimo_e_valor_invalido():
    assert sa.intervalo_ciclo({}) == 120
    assert sa.intervalo_ciclo({"COSTGUARD_SYNC_INTERVALO": "300"}) == 300
    assert sa.intervalo_ciclo({"COSTGUARD_SYNC_INTERVALO": "5"}) == 30
    assert sa.intervalo_ciclo({"COSTGUARD_SYNC_INTERVALO": "abc"}) == 120


# --- selo de recurso novo (48 h) ---

def test_recurso_novo_so_dentro_de_48_horas():
    assert sa.recurso_novo(AGORA - 1 * HORA, AGORA) is True
    assert sa.recurso_novo(AGORA - 47 * HORA, AGORA) is True
    assert sa.recurso_novo(AGORA - 48 * HORA, AGORA) is False
    assert sa.recurso_novo(AGORA - 72 * HORA, AGORA) is False


def test_recurso_sem_data_de_descoberta_nao_e_novo():
    for valor in (None, 0, "", "abc"):
        assert sa.recurso_novo(valor, AGORA) is False


def test_nao_classificado_carrega_o_selo_e_nenhum_valor_monetario():
    r = normalizar_recurso(
        {"id": 1, "arn": "arn:aws:s3:::dados", "servico": "s3", "regiao": "sa-east-1",
         "provedor_nome": "TESTE_X", "codigo_projeto_tag": "", "descoberto_em": AGORA - HORA},
        AGORA,
    )
    assert r["novo"] is True and r["nome"] == "dados"
    assert not [k for k in r if "custo" in k or "valor" in k]
    antigo = normalizar_recurso({"id": 2, "arn": "arn:aws:s3:::velho", "descoberto_em": AGORA - 100 * HORA}, AGORA)
    assert antigo["novo"] is False


# --- estado por provedor ---

def test_texto_de_provedor_sincronizado():
    t = sa.texto_sincronizacao(
        {"ultima_tentativa": AGORA - 3 * 60_000, "ultimo_sucesso": AGORA - 3 * 60_000, "ultimo_status": "sucesso"}, AGORA
    )
    assert t == {"texto": "Sincronizado há 3 min", "erro": "", "ultima_boa": ""}
    t = sa.texto_sincronizacao({"ultima_tentativa": AGORA, "ultimo_sucesso": AGORA, "ultimo_status": "sucesso"}, AGORA)
    assert t["texto"] == "Sincronizado agora"


def test_texto_de_provedor_nunca_sincronizado():
    # O Xano devolve 0 para timestamp nulo.
    t = sa.texto_sincronizacao({"ultima_tentativa": 0, "ultimo_sucesso": 0, "ultimo_status": ""}, AGORA)
    assert t == {"texto": "Ainda não sincronizado", "erro": "", "ultima_boa": ""}


def test_texto_de_provedor_com_erro_mostra_a_ultima_sincronizacao_boa():
    t = sa.texto_sincronizacao(
        {"ultima_tentativa": AGORA - 60_000, "ultimo_sucesso": AGORA - 2 * HORA, "ultimo_status": "erro",
         "ultima_mensagem": "Falha na sincronização de recursos: fonte indisponível"},
        AGORA,
    )
    assert t["texto"] == "" and t["erro"].endswith("fonte indisponível")
    assert t["ultima_boa"].startswith("Última sincronização boa: ") and t["ultima_boa"].endswith("(há 2 h)")

    nunca = sa.texto_sincronizacao({"ultima_tentativa": AGORA, "ultimo_sucesso": 0, "ultimo_status": "erro"}, AGORA)
    assert nunca["erro"] == "Falha na sincronização de recursos"
    assert nunca["ultima_boa"] == "Nenhuma sincronização bem-sucedida até agora"


def test_estado_e_aplicado_so_ao_provedor_certo():
    corpo = {
        "versao": 5, "agora": AGORA,
        "provedores": [
            {"provedor_id": 2, "ultima_tentativa": AGORA - 60_000, "ultimo_sucesso": AGORA - 60_000, "ultimo_status": "sucesso"},
            {"provedor_id": 3, "ultima_tentativa": AGORA, "ultimo_sucesso": 0, "ultimo_status": "erro", "ultima_mensagem": "x"},
        ],
    }
    lista = com_estado([_normalizar({"id": i, "apelido": f"p{i}"}) for i in (1, 2, 3)], corpo)
    assert [(p["id"], p["sinc_texto"], p["sinc_erro"]) for p in lista] == [
        (1, "", ""), (2, "Sincronizado há 1 min", ""), (3, "", "x"),
    ]
    # resposta inválida não derruba a lista
    assert [p["sinc_texto"] for p in com_estado(lista, None)] == ["", "", ""]


def test_versao_do_estado():
    assert sa.versao_do_estado({"versao": 7}) == 7
    assert sa.versao_do_estado({"versao": None}) == 0
    assert sa.versao_do_estado([]) is None
    assert sa.versao_do_estado({"versao": "x"}) is None


def test_recarga_por_pagina():
    assert sa.eventos_de_recarga("/inicio") == [HomeState.carregar]
    assert sa.eventos_de_recarga("/alertas/") == [AlertasState.carregar]
    assert sa.eventos_de_recarga("/projetos/12") == [ProjetoDetalheState.carregar_recursos]
    # /provedores recebe só os textos de estado; /projetos e /usuarios não dependem do inventário
    assert sa.eventos_de_recarga("/provedores") == []
    assert sa.eventos_de_recarga("/projetos") == []
    assert sa.eventos_de_recarga("/usuarios") == []


def test_resumo_do_ciclo_nao_tem_dado_sensivel():
    assert sa.resumo_ciclo(0, None) == "falha de rede"
    assert "401" in sa.resumo_ciclo(401, {"message": "Não autorizado"})
    assert sa.resumo_ciclo(200, {"executou": False, "motivo": "intervalo_minimo"}) == "nada a fazer (intervalo_minimo)"
    texto = sa.resumo_ciclo(200, {"executou": True, "status": "sucesso", "recursos_criados": 1,
                                  "recursos_alterados": 0, "recursos_desativados": 2})
    assert texto == "status=sucesso criados=1 alterados=0 desativados=2"
    assert sa.resumo_ciclo(500, "erro") == "HTTP 500"


# --- gatilho ---

class _ClienteFalso:
    """Substitui `cliente_xano`: registra as requisições e responde o que o teste definir."""

    def __init__(self, manipulador):
        self._transporte = httpx.MockTransport(manipulador)

    def __call__(self, timeout=30, forcar=False):
        return httpx.AsyncClient(transport=self._transporte, timeout=timeout)


def _preparar(monkeypatch, manipulador):
    monkeypatch.setattr(sa, "cliente_xano", _ClienteFalso(manipulador))
    monkeypatch.setattr(sa, "get_xano_app_base_url", lambda: "https://xano.exemplo/api:app")
    monkeypatch.setenv("COSTGUARD_SYNC_KEY", CHAVE)


def test_disparo_envia_so_a_chave_no_cabecalho(monkeypatch):
    vistos = []

    def manipulador(request: httpx.Request) -> httpx.Response:
        vistos.append(request)
        return httpx.Response(200, json={"executou": True, "status": "sucesso"})

    _preparar(monkeypatch, manipulador)
    status, corpo = asyncio.run(sa.disparar_ciclo())
    assert (status, corpo["status"]) == (200, "sucesso")
    req = vistos[0]
    assert req.method == "POST" and str(req.url) == "https://xano.exemplo/api:app/sincronizacao/automatica"
    assert req.headers["X-Sync-Key"] == CHAVE and "authorization" not in req.headers
    assert req.content == b"{}"  # nenhum parâmetro: o backend escolhe o provedor
    assert CHAVE not in str(req.url)


def test_disparo_com_falha_de_rede_devolve_zero(monkeypatch):
    def manipulador(request):
        raise httpx.ConnectError("sem rede")

    _preparar(monkeypatch, manipulador)
    assert asyncio.run(sa.disparar_ciclo()) == (0, None)


def test_laco_desligado_nao_dispara(monkeypatch, capsys):
    chamadas = []
    _preparar(monkeypatch, lambda r: chamadas.append(r) or httpx.Response(200, json={}))
    monkeypatch.delenv("COSTGUARD_SYNC_ATIVO", raising=False)
    asyncio.run(sa.laco_sincronizacao())
    assert chamadas == []
    assert "desligado" in capsys.readouterr().err


def test_laco_ligado_dispara_segue_apos_falha_e_nao_loga_a_chave(monkeypatch, capsys):
    respostas = iter([
        httpx.Response(500, text="erro"),
        httpx.Response(200, json={"executou": False, "motivo": "intervalo_minimo"}),
        httpx.Response(200, json={"executou": True, "status": "sucesso", "recursos_criados": 1,
                                  "recursos_alterados": 0, "recursos_desativados": 0}),
    ])
    chamadas = []

    def manipulador(request):
        chamadas.append(request)
        if len(chamadas) == 2:
            raise httpx.ReadTimeout("lento")
        return next(respostas)

    _preparar(monkeypatch, manipulador)
    monkeypatch.setenv("COSTGUARD_SYNC_ATIVO", "1")
    monkeypatch.setenv("COSTGUARD_SYNC_INTERVALO", "45")
    esperas = []

    async def dormir(segundos):
        esperas.append(segundos)
        if len(esperas) == 4:
            raise asyncio.CancelledError

    monkeypatch.setattr(sa.asyncio, "sleep", dormir)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(sa.laco_sincronizacao())

    assert len(chamadas) == 4 and esperas == [45, 45, 45, 45]
    log = capsys.readouterr().err
    assert "a cada 45 s" in log and "HTTP 500" in log and "falha de rede" in log
    assert "nada a fazer (intervalo_minimo)" in log and "criados=1" in log
    assert CHAVE not in log

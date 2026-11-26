"""Regras puras do frontend corrigidas no Lote 1 (sem rede)."""

from datetime import date

from projetoImpacta.pages.home_state import resumo_custo
from projetoImpacta.pages.projetos_state import (
    CUSTO_INDISPONIVEL,
    card_de_resumo,
    itens_do_resumo,
)
from projetoImpacta.pages.provedores_state import _normalizar, mensagem_teste_conexao
from projetoImpacta.pages.sincronizacao_state import inicio_janela_custos


def _item(**extra) -> dict:
    base = {
        "id": 1, "nome": "Alfa", "codigo": "ALFA", "status": "ativo", "budget": 100,
        "custo_status": "ok", "custo_mtd": 80.0, "moeda": "USD",
        "ultima_data_com_custo": "2026-11-10", "percentual_usado": 80.0, "faixa": "atencao",
    }
    return {**base, **extra}


def _corpo(*itens) -> dict:
    return {"data_inicio": "2026-11-01", "data_fim": "2026-11-12", "projetos": list(itens)}


# --- P1-6: item fora do contrato não esconde os demais ---

def test_item_invalido_degrada_so_o_proprio_card():
    ruim = _item(id=2, nome="Beta", codigo="BETA", custo_status="moeda_incompativel", moeda="")
    itens = itens_do_resumo(_corpo(_item(), ruim))
    assert itens is not None and len(itens) == 2
    assert itens[0]["custo_status"] == "ok" and itens[0]["custo_mtd"] == 80.0
    assert itens[1]["custo_status"] == CUSTO_INDISPONIVEL
    assert itens[1]["custo_mtd"] is None and itens[1]["percentual_usado"] is None


def test_card_degradado_nao_mostra_valor_nem_zero():
    ruim = _item(custo_mtd="oitenta")
    card = card_de_resumo(itens_do_resumo(_corpo(ruim))[0])
    assert card["custo_texto"] == ""
    assert card["custo_nota"] == "Consumo indisponível"
    assert card["mostra_consumo"] is False


def test_projeto_invalido_ainda_leva_ao_fallback():
    assert itens_do_resumo(_corpo(_item(), _item(id="x"))) is None
    assert itens_do_resumo(_corpo(_item(), "lixo")) is None
    assert itens_do_resumo({"projetos": [_item()]}) is None


def test_home_nao_soma_item_indisponivel():
    itens = itens_do_resumo(_corpo(_item(), _item(id=2, moeda="")))
    r = resumo_custo(itens)
    assert r == {"total": 80.0, "com_custo": 1, "fora": 0, "indisponiveis": 1}


# --- P1-4: janela de custos enviada na sincronização ---

def test_janela_comeca_no_primeiro_dia_do_mes_anterior():
    assert inicio_janela_custos(date(2026, 11, 11)) == "2026-10-01"
    assert inicio_janela_custos(date(2026, 11, 1)) == "2026-10-01"
    assert inicio_janela_custos(date(2026, 3, 31)) == "2026-02-01"
    assert inicio_janela_custos(date(2027, 1, 5)) == "2026-12-01"


# --- P2-2: motivo da falha do teste de conexão ---

def test_teste_de_conexao_ok_nao_gera_mensagem():
    assert mensagem_teste_conexao({"conectado": True, "mensagem": "ok"}) == ""


def test_teste_de_conexao_falho_mostra_motivo_e_diagnostico():
    corpo = {
        "conectado": False,
        "mensagem": "Falha ao autenticar a credencial AWS",
        "diagnostico": {"http_status": 400, "error_code": "ValidationException", "error_msg": "Account not found"},
    }
    texto = mensagem_teste_conexao(corpo)
    assert "Falha ao autenticar a credencial AWS" in texto
    assert "ValidationException" in texto and "Account not found" in texto and "HTTP 400" in texto


def test_teste_de_conexao_sem_detalhes():
    assert mensagem_teste_conexao({"conectado": False}) == "Falha no teste de conexão."
    assert mensagem_teste_conexao("lixo") == ""


# --- P0-1: Tag Key de projeto padrão ---

def test_provedor_sem_tag_de_projeto_usa_prj():
    assert _normalizar({"id": 1})["tag_alocacao_projeto"] == "PRJ"
    assert _normalizar({"id": 1, "tag_alocacao_projeto": "  "})["tag_alocacao_projeto"] == "PRJ"
    assert _normalizar({"id": 1, "tag_alocacao_projeto": "Projeto"})["tag_alocacao_projeto"] == "Projeto"

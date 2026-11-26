"""Regras puras do frontend: faixas, contrato do resumo, janela de mês e formatação (sem rede)."""

import re
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from projetoImpacta.components.periodo_state import MES_ATUAL, janela_mes, opcoes_meses, parametro_mes
from projetoImpacta.pages.alertas_state import nome_recurso, normalizar_alerta, tempo_relativo
from projetoImpacta.pages.home_state import maiores_consumos, resumo_custo, texto_periodo
from projetoImpacta.formatadores import formatar_valor, ler_orcamento, mascarar_conta_aws, mascarar_orcamento, percentual_br
from projetoImpacta.pages.projeto_detalhe_state import janela_mtd
from projetoImpacta.pages.projeto_detalhe_state import texto_periodo as periodo_detalhe
from projetoImpacta.pages.projetos_state import (
    CUSTO_INDISPONIVEL,
    _data_br,
    card_de_resumo,
    itens_do_resumo,
    ordenar_itens,
)
from projetoImpacta.pages.sincronizacao_state import inicio_janela_custos
from projetoImpacta.pages.usuarios_state import iniciais, normalizar_usuario

XANO = Path(__file__).resolve().parent.parent / "xano" / "function" / "costguard"


def _item(**extra) -> dict:
    base = {
        "id": 1, "nome": "Alfa", "codigo": "ALFA", "status": "ativo", "budget": 100,
        "custo_status": "ok", "custo_mtd": 80.0, "moeda": "USD",
        "ultima_data_com_custo": "2026-11-10", "percentual_usado": 80.0, "faixa": "atencao",
    }
    return {**base, **extra}


def _corpo(*itens) -> dict:
    return {"data_inicio": "2026-11-01", "data_fim": "2026-11-14", "projetos": list(itens)}


# --- faixas 70/90/100 ---

def test_limites_das_faixas_no_xano_sao_70_90_100_nas_duas_regras():
    """A faixa é calculada no Xano (resumo e alertas); as duas cópias da regra devem coincidir."""
    padrao = re.compile(r">= (\d+)\) \{\s*var\.update \$faixa \{ value = \"(\w+)\" \}")
    for arquivo in ("resumo_consumo.xs", "avaliar_alertas.xs"):
        limites = padrao.findall((XANO / arquivo).read_text(encoding="utf-8"))
        assert limites == [("100", "estourado"), ("90", "critico"), ("70", "atencao")], arquivo


@pytest.mark.parametrize("faixa,pct,cor,rotulo", [
    ("normal", 50.0, "green", "Normal"),
    ("atencao", 70.0, "yellow", "Atenção"),
    ("critico", 90.0, "orange", "Crítico"),
    ("estourado", 100.0, "red", "Estourado"),
])
def test_card_mostra_a_faixa_enviada_pelo_backend(faixa, pct, cor, rotulo):
    card = card_de_resumo(_item(faixa=faixa, percentual_usado=pct, custo_mtd=pct))
    assert (card["faixa_cor"], card["faixa_rotulo"], card["mostra_consumo"]) == (cor, rotulo, True)
    assert card["percentual_texto"] == f"{int(pct)},0%"


def test_frontend_nao_recalcula_a_faixa():
    # 95% com faixa "atencao" vinda do backend: o card mantém a faixa recebida.
    card = card_de_resumo(_item(percentual_usado=95.0, faixa="atencao"))
    assert card["faixa_rotulo"] == "Atenção"


def test_barra_fica_entre_0_e_100():
    assert card_de_resumo(_item(percentual_usado=130.4, faixa="estourado"))["barra_valor"] == 100
    assert card_de_resumo(_item(percentual_usado=130.4, faixa="estourado"))["percentual_texto"] == "130,4%"
    assert card_de_resumo(_item(percentual_usado=0.0, faixa="normal"))["barra_valor"] == 0


def test_maiores_consumos_ordena_e_ignora_inativos_e_sem_faixa():
    itens = [
        _item(id=1, nome="A", percentual_usado=50.0, faixa="normal"),
        _item(id=2, nome="B", percentual_usado=120.0, faixa="estourado", custo_mtd=120.0),
        _item(id=3, nome="C", status="inativo", percentual_usado=99.0, faixa="critico"),
        _item(id=4, nome="D", custo_status="sem_registros", custo_mtd=None, moeda=None,
              ultima_data_com_custo=None, percentual_usado=None, faixa=None),
    ]
    saida = maiores_consumos(itens)
    assert [c["nome"] for c in saida] == ["B", "A"]
    assert saida[0]["custo_texto"] == "US$ 120,00" and saida[0]["barra_valor"] == 100


# --- contrato do resumo ---

@pytest.mark.parametrize("corpo", [
    None, [], {"projetos": []},
    {"data_inicio": "2026-11-01", "data_fim": "ontem", "projetos": []},
    {"data_inicio": "2026-02-30", "data_fim": "2026-03-01", "projetos": []},
    _corpo({"id": 1}),  # projeto sem os campos básicos
    _corpo(_item(id=True)),  # bool não é id
    _corpo(_item(budget=-1)),
])
def test_envelope_fora_do_contrato_vai_ao_fallback(corpo):
    assert itens_do_resumo(corpo) is None


@pytest.mark.parametrize("ruim", [
    _item(faixa=None),  # ok com orçamento: faixa obrigatória
    _item(faixa="laranja"),
    _item(percentual_usado=float("nan")),
    _item(budget=0),  # sem orçamento: não pode ter faixa
    _item(custo_mtd="80"),
    _item(moeda="BRL"),  # ok exige USD
    _item(custo_status="moeda_incompativel", moeda="USD", faixa=None, percentual_usado=None),
    _item(custo_status="sem_registros", custo_mtd=0, moeda=None, ultima_data_com_custo=None,
          faixa=None, percentual_usado=None),  # sem registros não leva zero
    _item(custo_status="moedas_mistas", custo_mtd=None, moeda=None, ultima_data_com_custo="x",
          faixa=None, percentual_usado=None),
    _item(custo_status="desconhecido"),
])
def test_item_fora_do_contrato_vira_indisponivel_sem_esconder_os_outros(ruim):
    itens = itens_do_resumo(_corpo(_item(id=9, nome="Bom"), {**ruim, "id": 2}))
    assert itens is not None and itens[0]["custo_status"] == "ok"
    assert itens[1]["custo_status"] == CUSTO_INDISPONIVEL and itens[1]["custo_mtd"] is None


def test_estados_validos_do_resumo():
    validos = [
        _item(),
        _item(budget=0, faixa=None, percentual_usado=None),
        _item(custo_status="moeda_incompativel", moeda="BRL", faixa=None, percentual_usado=None),
        _item(custo_status="sem_registros", custo_mtd=None, moeda=None, ultima_data_com_custo=None,
              faixa=None, percentual_usado=None),
        _item(custo_status="moedas_mistas", custo_mtd=None, moeda=None, faixa=None, percentual_usado=None),
    ]
    itens = itens_do_resumo(_corpo(*[{**v, "id": i + 1} for i, v in enumerate(validos)]))
    assert [i["custo_status"] for i in itens] == ["ok", "ok", "moeda_incompativel", "sem_registros", "moedas_mistas"]


def test_notas_dos_cards_sem_valor_fabricado():
    sem = card_de_resumo(_item(custo_status="sem_registros", custo_mtd=None, moeda=None,
                               ultima_data_com_custo=None, faixa=None, percentual_usado=None))
    assert sem["custo_texto"] == "" and sem["custo_nota"].startswith("Sem custos")
    fechado = card_de_resumo(_item(custo_status="sem_registros", custo_mtd=None, moeda=None,
                                   ultima_data_com_custo=None, faixa=None, percentual_usado=None), False)
    assert fechado["custo_nota"] == "Sem custos classificados neste mês."
    brl = card_de_resumo(_item(custo_status="moeda_incompativel", moeda="BRL", faixa=None, percentual_usado=None))
    assert brl["custo_texto"] == "BRL 80,00" and not brl["mostra_consumo"]


def test_ordem_dos_cards():
    itens = [
        _item(id=1, nome="b", percentual_usado=10.0, faixa="normal"),
        _item(id=2, nome="a", status="inativo"),
        _item(id=3, nome="c", percentual_usado=95.0, faixa="critico"),
        _item(id=4, nome="d", budget=0, faixa=None, percentual_usado=None, custo_mtd=500.0),
    ]
    assert [p["id"] for p in ordenar_itens(itens)] == [3, 1, 4, 2]


def test_resumo_do_custo_do_inicio():
    itens = itens_do_resumo(_corpo(
        _item(id=1, custo_mtd=10.005), _item(id=2, custo_mtd=5.0, percentual_usado=5.0, faixa="normal"),
        _item(id=3, custo_status="moeda_incompativel", moeda="BRL", faixa=None, percentual_usado=None),
        _item(id=4, faixa="laranja"),
    ))
    assert resumo_custo(itens) == {"total": 15.01, "com_custo": 2, "fora": 1, "indisponiveis": 1}


# --- janela de mês (America/Sao_Paulo) ---

def _sp(ano, mes, dia, hora=12):
    return datetime(ano, mes, dia, hora, tzinfo=timezone.utc)


def test_mes_atual_vai_do_dia_1_ate_amanha():
    assert janela_mes("", _sp(2026, 11, 13)) == (date(2026, 11, 1), date(2026, 11, 14), True)
    assert janela_mes(MES_ATUAL, _sp(2026, 11, 30)) == (date(2026, 11, 1), date(2026, 12, 1), True)


def test_mes_anterior_e_o_mes_fechado_inteiro():
    assert janela_mes("2026-10", _sp(2026, 11, 13)) == (date(2026, 10, 1), date(2026, 11, 1), False)
    assert janela_mes("2025-12", _sp(2026, 1, 5)) == (date(2025, 12, 1), date(2026, 1, 1), False)


@pytest.mark.parametrize("valor", ["2026-11", "2027-01", "abc", "2026-13", "2026"])
def test_mes_invalido_ou_futuro_vira_mes_atual(valor):
    assert janela_mes(valor, _sp(2026, 11, 13))[2] is True


def test_virada_do_mes_usa_o_fuso_de_sao_paulo():
    # 1º de dezembro, 02:00 UTC = 30 de novembro, 23:00 em São Paulo.
    agora = datetime(2026, 12, 1, 2, tzinfo=timezone.utc)
    assert janela_mes("", agora) == (date(2026, 11, 1), date(2026, 12, 1), True)
    assert janela_mtd(agora) == (date(2026, 11, 1), date(2026, 12, 1))


def test_opcoes_de_mes_atravessam_o_ano():
    opcoes = opcoes_meses(date(2026, 2, 10))
    assert [o["valor"] for o in opcoes] == [MES_ATUAL, "2026-01", "2025-12", "2025-11", "2025-10", "2025-09"]
    assert opcoes[0]["rotulo"] == "Fevereiro/2026 (mês atual)" and opcoes[2]["rotulo"] == "Dezembro/2025"


def test_parametro_mes_e_inicio_dos_custos():
    assert parametro_mes("") is None and parametro_mes(MES_ATUAL) is None
    assert parametro_mes("2026-10") == {"mes": "2026-10"}
    assert inicio_janela_custos(date(2026, 1, 15)) == "2025-12-01"
    assert inicio_janela_custos(date(2026, 11, 13)) == "2026-10-01"


# --- formatação ---

@pytest.mark.parametrize("valor,moeda,texto", [
    (0, "USD", "US$ 0,00"),
    (1234567.891, "USD", "US$ 1.234.567,89"),
    (-12.5, "USD", "-US$ 12,50"),
    (99.999, "EUR", "EUR 100,00"),
])
def test_formatar_valor(valor, moeda, texto):
    assert formatar_valor(valor, moeda) == texto


@pytest.mark.parametrize("digitado,mascara,valor", [
    ("1", "0,01", 0.01),
    ("000", "0,00", 0.0),
    ("500000", "5.000,00", 5000.0),
    ("5.000,00", "5.000,00", 5000.0),
    ("-500000", "-5.000,00", -5000.0),
])
def test_orcamento_mascarado_preserva_o_valor_numerico(digitado, mascara, valor):
    assert mascarar_orcamento(digitado) == mascara
    assert ler_orcamento(mascara) == valor


def test_apagar_orcamento_preserva_campo_vazio():
    assert mascarar_orcamento("") == ""
    with pytest.raises(ValueError):
        ler_orcamento("")


def test_percentual_brasileiro():
    assert percentual_br(12.5) == "12,5%"
    assert percentual_br(1200) == "1.200,0%"


def test_conta_aws_exibe_apenas_final_de_identificador_valido():
    assert mascarar_conta_aws("000000000000") == "•••• •••• 0000"
    assert mascarar_conta_aws("") == "—"
    assert mascarar_conta_aws("123") == "—"


def test_textos_de_periodo_usam_fim_exclusivo():
    assert texto_periodo("2026-11-01", "2026-11-14") == "01/11/2026 a 13/11/2026"
    assert texto_periodo("x", "2026-11-14") == ""
    assert periodo_detalhe(date(2026, 10, 1), date(2026, 11, 1)) == "Período: 01/10/2026 a 31/10/2026"


def test_datas_e_tempos_relativos():
    assert _data_br("2026-11-10") == "10/11/2026" and _data_br("2026-11-10T03:00:00Z") == "10/11/2026"
    assert _data_br(None) == "" and _data_br("10/11/2026") == ""
    agora = 10_000_000_000
    assert tempo_relativo(None, agora) == "—"
    assert tempo_relativo(agora - 30_000, agora) == "agora"
    assert tempo_relativo(agora - 5 * 60_000, agora) == "há 5 min"
    assert tempo_relativo(agora - 3 * 3_600_000, agora) == "há 3 h"
    assert tempo_relativo(agora - 26 * 3_600_000, agora) == "há 1 dia"
    assert tempo_relativo(agora + 60_000, agora) == "agora"  # relógio adiantado não fica negativo


def test_nomes_de_recurso_e_iniciais():
    assert nome_recurso("arn:aws:ec2:us-east-1:123:instance/i-abc") == "i-abc"
    assert nome_recurso("arn:aws:s3:::meu-bucket") == "meu-bucket"
    assert nome_recurso("arn:aws:lambda:sa-east-1:1:function:fn-1") == "fn-1"
    assert iniciais("Ana Maria Souza", "ana") == "AS" and iniciais("", "jo") == "JO"


def test_normalizacao_descarta_itens_fora_do_contrato():
    assert normalizar_alerta({"id": "1", "tipo": "erro", "nivel": "erro"}, 0) is None
    assert normalizar_alerta({"id": 1, "tipo": "outro", "nivel": "erro"}, 0) is None
    resolvido = normalizar_alerta({"id": 1, "tipo": "orcamento", "nivel": "critico", "resolvido": True,
                                   "resolucao": "automatica", "resolvido_em": 0, "criado_em": 0}, 3_600_000)
    assert resolvido["resolucao_texto"] == "Resolvido automaticamente (há 1 h)"
    assert resolvido["nivel_rotulo"] == "Aviso" and resolvido["tipo_rotulo"] == "Orçamento"
    u = normalizar_usuario({"id": 3, "nome": "X", "role": "root", "status": "?"})
    assert (u["role"], u["status"]) == ("leitura", "inativo")  # papel desconhecido nunca vira admin

"""Coluna "Custo (USD)" por recurso no detalhe do projeto (somente interface).

Usa dicts inline: não depende das fixtures gravadas do Xano. O total do topo
continua vindo de custos-equipe e não é recalculado a partir do custo por recurso.
"""

import pytest

from projetoImpacta.pages.projeto_detalhe_state import ProjetoDetalheState, texto_custo_recurso

_EQUIPES = [{"id": 12, "nome": "WEB", "codigo": "WEB"}]
_CUSTOS = {
    "projeto_id": 5, "moeda": "USD", "total_projeto": 30.0, "sem_responsavel": {"total": 4.0},
    "equipes": [{"equipe_id": 12, "nome": "WEB", "total": 26.0}],
}


def _recurso(rid, **extra):
    return {"id": rid, "arn": f"arn:aws:ec2:us-east-1:1:instance/i-{rid}", "regiao": "us-east-1",
            "servico": "ec2", "equipe_id": 12, "codigo_equipe_tag": "WEB", "ativo": True,
            "descoberto_em": 1, **extra}


@pytest.mark.parametrize("valor,esperado", [
    (6.0, "6,00"), (2, "2,00"), (0, "0,00"), (0.0, "0,00"), ("6.5", "6,50"), (" 7 ", "7,00"),
    (1234.5, "1.234,50"), (None, "—"), ("abc", "—"), ("", "—"), (True, "—"), ([], "—"),
    (float("nan"), "—"), (float("inf"), "—"),
])
def test_texto_custo_recurso(valor, esperado):
    assert texto_custo_recurso(valor) == esperado


def test_item_normalizado_traz_custo_mensal_e_campo_ausente_vira_traco(arvore):
    estado = arvore.de(ProjetoDetalheState)
    estado._montar_recursos(
        [_recurso(1, custo_mensal=6.0), _recurso(2, custo_mensal=0), _recurso(3, custo_mensal=None),
         _recurso(4), _recurso(5, custo_mensal="abc"), _recurso(6, custo_mensal="6.5")],
        _EQUIPES,
    )
    por_nome = {r["nome"]: r for g in estado.grupos for r in g["recursos"]}
    assert all("custo_mensal" in r for r in por_nome.values())
    assert {n: r["custo_mensal"] for n, r in por_nome.items()} == {
        "i-1": "6,00", "i-2": "0,00", "i-3": "—", "i-4": "—", "i-5": "—", "i-6": "6,50"}


def test_recurso_sem_equipe_tambem_recebe_o_custo(arvore):
    estado = arvore.de(ProjetoDetalheState)
    estado._montar_recursos([_recurso(1, equipe_id=None, codigo_equipe_tag="", custo_mensal=3)], _EQUIPES)
    assert [(g["chave"], g["recursos"][0]["custo_mensal"]) for g in estado.grupos] == [("sem", "3,00")]
    assert estado.recursos_sem_equipe[0]["custo_mensal"] == "3,00"


def test_total_do_topo_nao_muda_com_custo_por_recurso(arvore):
    def topo(recursos):
        estado = arvore.de(ProjetoDetalheState)
        estado.budget = 100.0
        estado._preencher_custos(dict(_CUSTOS))
        estado._montar_recursos(recursos, _EQUIPES)
        return (estado.custo_texto, estado.restante_texto, estado.percentual_texto, estado.largura_barra,
                estado.sem_responsavel_custo_texto, [dict(e) for e in estado.equipes_custo])

    sem_coluna = topo([_recurso(1), _recurso(2)])
    com_coluna = topo([_recurso(1, custo_mensal=900.0), _recurso(2, custo_mensal=0.5)])
    assert sem_coluna == com_coluna
    assert sem_coluna[0] == "US$ 30,00" and sem_coluna[1] == "US$ 70,00"

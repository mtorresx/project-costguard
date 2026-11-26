"""P2-3: eventos longos (sincronizar, testar conexão, descobrir, importar, avaliar) em segundo plano.

Os handlers reais rodam sobre a árvore de estados em memória; ali `async with self`
não faz nada, então o teste confere a lógica e o contrato de cada chamada.
"""

import asyncio

import pytest

from apoio import nomes_eventos, rodar
from projetoImpacta.pages.alertas_state import AlertasState
from projetoImpacta.pages.descoberta_state import DescobertaState
from projetoImpacta.pages.provedores_state import ProvedoresState
from projetoImpacta.pages.sincronizacao_state import SincronizacaoState


def _executar(evento, estado, *args):
    return asyncio.run(rodar(evento, estado, *args))


@pytest.mark.parametrize("evento", [
    SincronizacaoState.sincronizar, ProvedoresState.testar_conexao,
    DescobertaState.descobrir, DescobertaState.importar, AlertasState.avaliar,
])
def test_eventos_longos_rodam_em_segundo_plano(evento):
    assert evento.is_background is True


def test_testar_conexao_recusada_mostra_o_motivo_e_recarrega(xano, arvore):
    xano.responder("POST", "/provedores/2/testar-conexao", (200, {
        "conectado": False, "mensagem": "Credencial recusada", "diagnostico": {"http_status": 403}}))
    estado = arvore.de(ProvedoresState)
    emitidos = _executar(ProvedoresState.testar_conexao, estado, 2)
    assert estado.testando_id == 0 and estado.falha_teste == "Credencial recusada (HTTP 403)"
    assert nomes_eventos(emitidos) == ["carregar"]


def test_testar_conexao_com_erro_http_e_401(xano, arvore):
    xano.responder("POST", "/provedores/2/testar-conexao", (400, {"message": "Provedor inativo"}))
    estado = arvore.de(ProvedoresState)
    assert _executar(ProvedoresState.testar_conexao, estado, 2) == []
    assert estado.error_message == "Provedor inativo" and estado.testando_id == 0

    xano.responder("POST", "/provedores/2/testar-conexao", (401, {}))
    assert "handle_unauthenticated" in nomes_eventos(_executar(ProvedoresState.testar_conexao, estado, 2))


def test_testar_conexao_ignora_segundo_clique_em_andamento(xano, arvore):
    estado = arvore.de(ProvedoresState)
    estado.testando_id = 3
    assert _executar(ProvedoresState.testar_conexao, estado, 2) == [] and xano.pedidos == []


def test_descobrir_e_importar(xano, arvore):
    xano.responder("POST", "/provedores/2/descobrir-projetos", (200, {
        "tag_key": "PRJ", "descobertos": [{"codigo": "NOVO", "existente": False},
                                         {"codigo": "PORTAL", "existente": True, "projeto_id": 5}]}))
    xano.responder("POST", "/provedores/2/importar-projetos", (200, {"criados": [{"codigo": "NOVO"}], "ignorados": []}))
    estado = arvore.de(DescobertaState)
    estado.provedor_id = 2
    _executar(DescobertaState.descobrir, estado)
    assert estado.codigos_novos == ["NOVO"] and estado.tag_key == "PRJ" and not estado.loading_descoberta

    estado.selecionados = ["NOVO"]
    emitidos = _executar(DescobertaState.importar, estado)
    assert xano.corpo(1) == {"codigos": ["NOVO"]}
    assert estado.selecionados == []
    aviso, recarga = emitidos
    assert "1 projeto importado." in str(aviso.args)
    assert nomes_eventos([recarga]) == ["descobrir"]


def test_descoberta_de_outro_provedor_nao_sobrescreve_o_modal(xano, arvore):
    estado = arvore.de(DescobertaState)
    estado.provedor_id = 2

    def troca_de_provedor(request):
        estado.provedor_id = 3  # usuário abriu o modal de outro provedor durante a chamada
        return 200, {"descobertos": [{"codigo": "DE_OUTRO", "existente": False}]}

    xano.responder("POST", "/provedores/2/descobrir-projetos", troca_de_provedor)
    _executar(DescobertaState.descobrir, estado)
    assert estado.descobertos == [] and estado.loading_descoberta is False


def test_avaliar_alertas_falha_mostra_erro(xano, arvore):
    xano.responder("POST", "/alertas/avaliar", (500, {"message": "Falha ao avaliar"}))
    estado = arvore.de(AlertasState)
    assert _executar(AlertasState.avaliar, estado) == []
    assert estado.erro_acao == "Falha ao avaliar" and estado.avaliando is False

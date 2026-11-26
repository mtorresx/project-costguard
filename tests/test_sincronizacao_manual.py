"""Modal "Sincronizar agora": interpretação das respostas de cada etapa (sem rede)."""

from projetoImpacta.pages.sincronizacao_state import (
    AVISO_OCUPADO,
    AVISO_OCUPADO_CUSTOS,
    resultado_alertas,
    resultado_custos,
    resultado_inventario,
    sincronizacao_em_andamento,
)

OCUPADO = {"code": "ERROR_CODE_INPUT_ERROR",
           "message": "Já existe uma sincronização de recursos em andamento para este provedor."}


def test_trava_tomada_vira_aviso_neutro_e_nao_falha():
    assert sincronizacao_em_andamento(400, OCUPADO) is True
    assert resultado_inventario(400, OCUPADO) == ("ocupado", AVISO_OCUPADO)


def test_outro_400_continua_erro():
    corpo = {"message": "Credencial AWS ausente"}
    assert sincronizacao_em_andamento(400, corpo) is False
    assert resultado_inventario(400, corpo) == ("erro", "Credencial AWS ausente")
    # mesma mensagem com outro status não é tratada como trava
    assert resultado_inventario(500, OCUPADO)[0] == "erro"


def test_inventario_com_sucesso_e_com_falha_da_fonte():
    ok = {"status": "sucesso", "recursos_ativos": 3, "recursos_desativados": 1,
          "sem_responsavel": 0, "projetos_desconhecidos": 2}
    estado, msg = resultado_inventario(200, ok)
    assert estado == "sucesso" and msg.startswith("3 recursos ativos, 1 desativados")
    assert resultado_inventario(200, {"status": "erro", "mensagem": "fonte fora"}) == ("erro", "fonte fora")
    assert resultado_inventario(0, None)[0] == "erro"


def test_custos_com_aviso_e_alertas():
    estado, msg = resultado_custos(200, {"status": "sucesso", "registros_gravados": 4, "aviso": "parcial"})
    assert estado == "aviso" and msg.endswith("Aviso: parcial")
    assert resultado_alertas(200, {"criar": [1, 2], "resolver": []}) == (
        "sucesso", "2 alertas novos, 0 encerrados automaticamente.")


def test_classificacao_de_custos_em_andamento_vira_aviso_neutro():
    corpo = {"message": "Já existe uma classificação de custos em andamento para este provedor."}
    assert resultado_custos(400, corpo) == ("ocupado", AVISO_OCUPADO_CUSTOS)
    assert resultado_custos(400, {"message": "Provedor não está conectado (status != ok)"})[0] == "erro"

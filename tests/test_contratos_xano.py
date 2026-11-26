"""Contratos das chamadas ao Xano: eventos reais do Reflex contra respostas gravadas.

Cada teste roda o handler do evento sobre a árvore de estados em memória, com o
transporte HTTP trocado por `httpx.MockTransport`. Confere o que foi pedido
(método, caminho, parâmetros, cabeçalho, corpo) e o que a tela recebeu.
"""

import asyncio
from datetime import date, datetime

import pytest

from apoio import TOKEN, gravada, nomes_eventos, rodar
from projetoImpacta.components.periodo_state import FUSO, PeriodoState
from projetoImpacta.pages import sincronizacao_state
from projetoImpacta.pages.alertas_state import AlertasState
from projetoImpacta.pages.home_state import ERRO_CONSUMO, HomeState
from projetoImpacta.pages.projeto_detalhe_state import ProjetoDetalheState
from projetoImpacta.pages.projetos_state import MENSAGEM_ERRO_CONSUMO, ProjetosState
from projetoImpacta.pages.provedores_state import ProvedoresState
from projetoImpacta.pages.sincronizacao_state import AVISO_OCUPADO, SincronizacaoState
from projetoImpacta.pages.usuarios_state import UsuariosState
from projetoImpacta.state import AuthState


def _executar(evento, estado, *args):
    return asyncio.run(rodar(evento, estado, *args))


def _abertos(alertas):
    return [a for a in alertas if not a["resolvido"]]


# --- autenticação ---

def test_toda_chamada_leva_o_token_no_cabecalho(xano, arvore):
    xano.responder("GET", "/painel", "painel")
    _executar(HomeState.carregar, arvore.de(HomeState))
    assert xano.pedidos and all(r.headers["authorization"] == f"Bearer {TOKEN}" for r in xano.pedidos)


def test_me_gravado_define_usuario_e_papel(xano, arvore):
    xano.responder("GET", "/me", "me")
    auth = arvore.de(AuthState)
    assert _executar(AuthState.require_auth, auth) == []
    assert (auth.role, auth.username, auth.validacao_pendente) == ("admin", "usuario_exemplo", False)


@pytest.mark.parametrize("status,limpa", [(401, True), (403, True), (429, False), (500, False)])
def test_me_recusado_ou_indisponivel(xano, arvore, status, limpa):
    xano.responder("GET", "/me", (status, {"message": "x"}))
    auth = arvore.de(AuthState)
    emitidos = _executar(AuthState.require_auth, auth)
    assert ("handle_unauthenticated" in nomes_eventos(emitidos)) is limpa
    assert auth.validacao_pendente is (not limpa)


# --- Início ---

def test_inicio_usa_o_painel_gravado_numa_chamada_so(xano, arvore):
    xano.responder("GET", "/painel", "painel")
    home = arvore.de(HomeState)
    _executar(HomeState.carregar, home)

    assert xano.chamadas() == [("GET", "/painel")]
    assert dict(xano.pedidos[0].url.params) == {}  # mês atual: sem parâmetro
    _, painel = gravada("painel")
    assert home.erro_consumo == home.erro_alertas == home.erro_recursos == ""
    assert home.projetos_ativos == len([p for p in painel["resumo"]["projetos"] if p["status"] == "ativo"])
    assert home.alertas_abertos == len([a for a in painel["alertas"] if not a["resolvido"]])
    assert home.recursos_nao_classificados == len(painel["recursos_nao_classificados"])
    assert home.loading is False


def test_inicio_sem_painel_cai_nas_tres_leituras_individuais(xano, arvore):
    xano.responder("GET", "/painel", (500, {"message": "erro"}))
    xano.responder("GET", "/projetos-resumo-consumo-mtd", "projetos_resumo")
    xano.responder("GET", "/alertas", "alertas")
    xano.responder("GET", "/recursos-nao-classificados", "recursos_nao_classificados")
    home = arvore.de(HomeState)
    _executar(HomeState.carregar, home)

    assert sorted(xano.chamadas()[1:]) == [
        ("GET", "/alertas"), ("GET", "/projetos-resumo-consumo-mtd"), ("GET", "/recursos-nao-classificados")]
    assert home.erro_consumo == ""
    assert home.alertas_abertos == len([a for a in gravada("alertas")[1] if not a["resolvido"]])
    assert home.recursos_nao_classificados == len(gravada("recursos_nao_classificados")[1])


def test_inicio_mes_anterior_envia_o_parametro_mes(xano, arvore):
    xano.responder("GET", "/painel", "painel")
    periodo = arvore.de(PeriodoState)
    periodo.mes = periodo.opcoes[1]["valor"]
    _executar(HomeState.carregar, arvore.de(HomeState))
    assert dict(xano.pedidos[0].url.params) == {"mes": periodo.opcoes[1]["valor"]}


def test_inicio_resumo_fora_do_contrato_mostra_erro_e_nao_zero(xano, arvore):
    _, painel = gravada("painel")
    painel = {**painel, "resumo": {"projetos": "quebrado"}}
    xano.responder("GET", "/painel", (200, painel))
    home = arvore.de(HomeState)
    _executar(HomeState.carregar, home)
    assert home.erro_consumo == ERRO_CONSUMO and home.custo_texto == ""


def test_inicio_401_encerra_a_sessao(xano, arvore):
    xano.responder("GET", "/painel", (401, {"message": "Token inválido"}))
    emitidos = _executar(HomeState.carregar, arvore.de(HomeState))
    assert "handle_unauthenticated" in nomes_eventos(emitidos)
    assert xano.chamadas() == [("GET", "/painel")]


# --- Projetos ---

def test_projetos_pelo_painel_com_inativo_no_fim(xano, arvore):
    xano.responder("GET", "/painel", "painel")
    estado = arvore.de(ProjetosState)
    _executar(ProjetosState.carregar, estado)
    assert xano.chamadas() == [("GET", "/painel")]
    assert estado.aviso_consumo == "" and estado.error_message == ""
    assert [p["status"] for p in estado.projetos][-1] == "inativo"
    # resumo gravado sem custos no mês: nota de "sem registros", nenhum valor fabricado
    assert all(p["custo_texto"] == "" and p["custo_nota"] for p in estado.projetos)


def test_projetos_sem_resumo_valido_lista_sem_consumo(xano, arvore):
    xano.responder("GET", "/painel", (500, {}))
    xano.responder("GET", "/projetos-resumo-consumo-mtd", (200, {"data_inicio": "x"}))
    xano.responder("GET", "/projetos", "projetos")
    estado = arvore.de(ProjetosState)
    _executar(ProjetosState.carregar, estado)
    assert [c[1] for c in xano.chamadas()] == ["/painel", "/projetos-resumo-consumo-mtd", "/projetos"]
    assert estado.aviso_consumo == MENSAGEM_ERRO_CONSUMO
    assert len(estado.projetos) == len(gravada("projetos")[1])
    assert all(p["custo_nota"] == "Consumo indisponível" and not p["mostra_consumo"] for p in estado.projetos)


# --- Alertas ---

def test_alertas_pelo_painel_gravado(xano, arvore):
    xano.responder("GET", "/painel", "painel")
    estado = arvore.de(AlertasState)
    _executar(AlertasState.carregar, estado)
    _, painel = gravada("painel")
    assert len(estado.alertas) == len(painel["alertas"])
    assert len(estado.recursos) == len(painel["recursos_nao_classificados"])
    assert all(r["nome"] and r["provedor_nome"] for r in estado.recursos)


def test_resolver_alerta_posta_no_caminho_do_alerta(xano, arvore):
    xano.responder("POST", "/alertas/7/resolver", (200, {"id": 7, "resolvido": True}))
    emitidos = _executar(AlertasState.resolver, arvore.de(AlertasState), 7)
    assert xano.chamadas() == [("POST", "/alertas/7/resolver")]
    assert "carregar" in nomes_eventos(emitidos)


def test_avaliar_alertas_nunca_simula(xano, arvore):
    xano.responder("POST", "/alertas/avaliar", (200, {"criar": [1], "resolver": []}))
    _executar(AlertasState.avaliar, arvore.de(AlertasState))
    assert xano.corpo(0) == {"simular": False}


# --- Detalhe do projeto ---

def test_detalhe_do_projeto_agrupa_recursos_gravados_por_equipe(xano, arvore):
    xano.responder("GET", "/projetos/5/painel", "projeto_painel")
    xano.responder("GET", "/projetos/5/custos-equipe", "projeto_custos_equipe")
    estado = arvore.de(ProjetoDetalheState)
    estado.router.page.params["projeto_id"] = "5"  # rota dinâmica
    _executar(ProjetoDetalheState.carregar, estado)

    assert sorted(xano.chamadas()) == [("GET", "/projetos/5/custos-equipe"), ("GET", "/projetos/5/painel")]
    custos = [r for r in xano.pedidos if r.url.path.endswith("/custos-equipe")][0]
    hoje = datetime.now(FUSO).date()
    assert custos.url.params["data_inicio"] == hoje.replace(day=1).isoformat()
    assert date.fromisoformat(custos.url.params["data_fim"]) > hoje  # fim exclusivo
    assert (estado.nome, estado.erro, estado.erro_recursos) == ("Portal Web", "", "")
    assert [g["equipe"] for g in estado.grupos] == ["BACKEND", "WEB"]
    assert sum(len(g["recursos"]) for g in estado.grupos) == len(gravada("projeto_painel")[1]["recursos"])
    assert estado.sem_custos is True and estado.custo_texto == "—"  # sem custo no mês: nunca US$ 0,00


def test_detalhe_de_projeto_inexistente(xano, arvore):
    xano.responder("GET", "/projetos/99/painel", (404, {"message": "Projeto não encontrado"}))
    xano.responder("GET", "/projetos/99/custos-equipe", (404, {}))
    estado = arvore.de(ProjetoDetalheState)
    estado.router.page.params["projeto_id"] = "99"
    _executar(ProjetoDetalheState.carregar, estado)
    assert estado.nao_encontrado is True


def test_notificacoes_do_projeto_tem_limites_independentes(xano, arvore):
    estado = arvore.de(ProjetoDetalheState)
    estado.router.page.params["projeto_id"] = "5"
    estado._projeto_devops = "5"
    estado.tem_email_devops = True
    estado.carregando_recursos = False
    estado.total_sem_responsavel = 1
    orcamento = "/projetos/5/notificar-devops"
    recursos = "/projetos/5/notificar-recursos-sem-equipe"
    aviso = "Aguarde 42 segundos para enviar outro."
    xano.responder("POST", orcamento, (429, {"message": aviso}))
    xano.responder("POST", recursos, (200, {
        "enviado": True, "destinatario_mascarado": "d***@e***", "quantidade": 1,
    }))

    _executar(ProjetoDetalheState.notificar, estado, "orcamento")
    _executar(ProjetoDetalheState.notificar, estado, "orcamento")
    assert estado.avisos == {"orcamento": aviso}
    assert estado.bloqueados == ["orcamento"]
    feedback, liberar = _executar(ProjetoDetalheState.notificar, estado, "recursos")
    assert "d***@e***" in str(feedback.args) and "Recursos sem equipe: 1" in str(feedback.args)
    assert nomes_eventos([liberar]) == ["liberar_notificacao"]
    assert estado.avisos == {"orcamento": aviso}
    assert xano.chamadas() == [("POST", orcamento), ("POST", recursos)]
    assert xano.corpo(0) == xano.corpo(1)


def test_notificacao_sem_recursos_respeita_a_contagem_e_o_400_do_servidor(xano, arvore):
    estado = arvore.de(ProjetoDetalheState)
    estado.router.page.params["projeto_id"] = "5"
    estado._projeto_devops = "5"
    estado.tem_email_devops = True
    estado.carregando_recursos = False
    _executar(ProjetoDetalheState.notificar, estado, "recursos")
    assert xano.chamadas() == []

    estado.total_sem_responsavel = 1
    mensagem = "Nenhum recurso sem equipe neste projeto no mês."
    xano.responder("POST", "/projetos/5/notificar-recursos-sem-equipe", (400, {"message": mensagem}))
    _executar(ProjetoDetalheState.notificar, estado, "recursos")
    assert estado.avisos == {"recursos": mensagem}
    assert estado.bloqueados == []


# --- Provedores ---

def test_provedores_gravados_com_estado_da_sincronizacao(xano, arvore):
    xano.responder("GET", "/provedores", "provedores")
    xano.responder("GET", "/sincronizacao/estado", "sincronizacao_estado")
    estado = arvore.de(ProvedoresState)
    _executar(ProvedoresState.carregar, estado)
    assert xano.chamadas() == [("GET", "/provedores"), ("GET", "/sincronizacao/estado")]
    por_apelido = {p["apelido"]: p for p in estado.provedores}
    assert por_apelido["prdo"]["tag_alocacao_projeto"] == "PRJ"  # tag vazia no Xano: padrão
    assert all(p["sinc_texto"].startswith("Sincronizado") for p in estado.provedores)


def test_provedores_sem_estado_ainda_mostra_a_lista(xano, arvore):
    xano.responder("GET", "/provedores", "provedores")
    xano.responder("GET", "/sincronizacao/estado", (500, {}))
    estado = arvore.de(ProvedoresState)
    _executar(ProvedoresState.carregar, estado)
    assert len(estado.provedores) == 3 and estado.error_message == ""


def test_editar_provedor_sem_segredo_nao_envia_o_campo(xano, arvore):
    xano.responder("PATCH", "/provedores/2", (200, {"id": 2}))
    estado = arvore.de(ProvedoresState)
    estado.form_modo, estado.form_id = "editar", 2
    estado.form_apelido, estado.form_identificador_conta, estado.form_tag_projeto = "AWS-DEV", "<CONTA_ID>", "PRJ"
    _executar(ProvedoresState.salvar, estado)
    corpo = xano.corpo(0)
    assert "aws_secret_access_key" not in corpo and "aws_access_key_id" not in corpo
    assert corpo == {"apelido": "AWS-DEV", "identificador_conta": "<CONTA_ID>", "tag_alocacao_projeto": "PRJ"}
    assert "usar_mock" not in corpo and "ambiente" not in corpo


def test_segredo_sai_do_estado_mesmo_com_erro(xano, arvore):
    xano.responder("POST", "/provedores", (400, {"message": "Identificador de conta inválido"}))
    estado = arvore.de(ProvedoresState)
    estado.form_modo = "criar"
    estado.form_apelido, estado.form_identificador_conta = "TESTE_X", "123"
    estado.form_access_key_id, estado.form_secret_access_key = "AKIAEXEMPLO", "segredo-ficticio"
    _executar(ProvedoresState.salvar, estado)
    assert xano.corpo(0)["aws_secret_access_key"] == "segredo-ficticio"
    assert estado.form_secret_access_key == "" and estado.form_error == "Identificador de conta inválido"


# --- Usuários ---

def test_usuarios_gravados(xano, arvore):
    xano.responder("GET", "/usuarios", "usuarios")
    estado = arvore.de(UsuariosState)
    _executar(UsuariosState.carregar, estado)
    assert [(u["role"], u["status"]) for u in estado.usuarios] == [
        (u["role"], u["status"]) for u in gravada("usuarios")[1]]


def test_usuarios_para_quem_nao_e_admin(xano, arvore):
    xano.responder("GET", "/usuarios", (403, {"message": "Acesso negado"}))
    estado = arvore.de(UsuariosState)
    _executar(UsuariosState.carregar, estado)
    assert estado.acesso_negado is True and estado.usuarios == []


# --- Sincronização manual ---

@pytest.fixture
def sem_pausa(monkeypatch):
    async def nada(_):
        return None
    monkeypatch.setattr(sincronizacao_state.asyncio, "sleep", nada)


def test_sincronizar_chama_as_tres_etapas_em_ordem(xano, arvore, sem_pausa):
    xano.responder("POST", "/provedores/2/sincronizar-recursos", (200, {"status": "sucesso", "recursos_ativos": 5}))
    xano.responder("POST", "/provedores/2/classificar-custos-equipe", (200, {"status": "sucesso"}))
    xano.responder("POST", "/alertas/avaliar", (200, {"criar": [], "resolver": []}))
    estado = arvore.de(SincronizacaoState)
    _executar(SincronizacaoState.sincronizar, estado, 2, "AWS-DEV")

    assert xano.chamadas() == [("POST", "/provedores/2/sincronizar-recursos"),
                               ("POST", "/provedores/2/classificar-custos-equipe"),
                               ("POST", "/alertas/avaliar")]
    assert xano.corpo(1) == {"data_inicio": sincronizacao_state.inicio_janela_custos(datetime.now(FUSO).date())}
    assert xano.corpo(2) == {"simular": False}
    assert [e["estado"] for e in estado.etapas] == ["sucesso", "sucesso", "sucesso"]
    assert estado.executando is False and estado.concluida_com_falha is False


def test_sincronizar_com_trava_tomada_mostra_aviso_neutro(xano, arvore, sem_pausa):
    xano.responder("POST", "/provedores/2/sincronizar-recursos", (400, {
        "code": "ERROR_CODE_INPUT_ERROR",
        "message": "Já existe uma sincronização de recursos em andamento para este provedor."}))
    xano.responder("POST", "/provedores/2/classificar-custos-equipe", (200, {"status": "sucesso"}))
    xano.responder("POST", "/alertas/avaliar", (200, {"criar": [], "resolver": []}))
    estado = arvore.de(SincronizacaoState)
    _executar(SincronizacaoState.sincronizar, estado, 2, "AWS-DEV")
    assert estado.etapas[0]["estado"] == "ocupado" and estado.etapas[0]["mensagem"] == AVISO_OCUPADO
    assert estado.concluida_com_falha is False  # sem o banner vermelho


def test_sincronizar_401_fecha_o_modal(xano, arvore, sem_pausa):
    xano.responder("POST", "/provedores/2/sincronizar-recursos", (401, {}))
    estado = arvore.de(SincronizacaoState)
    emitidos = _executar(SincronizacaoState.sincronizar, estado, 2, "AWS-DEV")
    assert "handle_unauthenticated" in nomes_eventos(emitidos)
    assert len(xano.pedidos) == 1 and estado.aberto is False


def test_trocar_o_mes_preserva_a_contagem_de_recursos_por_equipe(xano, arvore):
    """P2-6: recarregar só os custos não apaga a contagem vinda do inventário."""
    custos = {"projeto_id": 5, "moeda": "USD", "total_projeto": 30.0, "sem_responsavel": {"total": 0},
              "equipes": [{"equipe_id": 12, "nome": "WEB", "total": 20.0},
                          {"equipe_id": 13, "nome": "BACKEND", "total": 10.0}]}
    xano.responder("GET", "/projetos/5/painel", "projeto_painel")
    xano.responder("GET", "/projetos/5/custos-equipe", (200, custos))
    estado = arvore.de(ProjetoDetalheState)
    estado.router.page.params["projeto_id"] = "5"
    _executar(ProjetoDetalheState.carregar, estado)
    contagem = {e["nome"]: e["recursos_texto"] for e in estado.equipes_custo}
    assert contagem == {"WEB": "(2 recursos)", "BACKEND": "(1 recurso)"}

    periodo = arvore.de(PeriodoState)
    periodo.mes = periodo.opcoes[1]["valor"]
    _executar(ProjetoDetalheState.carregar_custos, estado)
    assert xano.chamadas()[-1] == ("GET", "/projetos/5/custos-equipe")
    assert {e["nome"]: e["recursos_texto"] for e in estado.equipes_custo} == contagem

    # inventário com erro: sem contagem (não mostra número velho)
    xano.responder("GET", "/projetos/5/recursos", (500, {}))
    xano.responder("GET", "/projetos/5/equipes", "projeto_equipes")
    _executar(ProjetoDetalheState.carregar_recursos, estado)
    _executar(ProjetoDetalheState.carregar_custos, estado)
    assert {e["recursos_texto"] for e in estado.equipes_custo} == {""}


def test_kpis_da_home_so_saem_do_carregamento_depois_da_primeira_carga(xano, arvore):
    """P2-4: antes da carga os KPIs não mostram o 0 inicial; trocar o mês volta ao carregamento."""
    xano.responder("GET", "/painel", (500, {}))  # mesmo com falha a carga termina (com "Indisponível")
    home = arvore.de(HomeState)
    assert home.carregado is False
    _executar(HomeState.carregar, home)
    assert home.carregado is True and home.erro_consumo == ERRO_CONSUMO

    emitidos = _executar(HomeState.mudar_mes, home, "2026-10")
    assert home.carregado is False and "carregar" in nomes_eventos(emitidos)

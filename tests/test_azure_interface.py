"""Contrato do formulário e dos eventos Azure, usando o transporte isolado da suíte."""

import asyncio
import json
import time
from uuid import uuid4

import pytest

from apoio import FIXTURES, nomes_eventos, rodar
from projetoImpacta.pages.azure_state import AzureState, _cooldown
from projetoImpacta.pages.provedores import _form_azure
from projetoImpacta.pages.provedores_state import ProvedoresState
from projetoImpacta.state import AuthState


def executar(evento, estado, *args):
    return asyncio.run(rodar(evento, estado, *args))


@pytest.fixture
def modal(arvore):
    arvore.de(AuthState).role = "admin"
    estado = arvore.de(ProvedoresState)
    estado.abrir_criar()
    estado.selecionar_provedor("Azure")
    return estado


def credenciais():
    return {campo: uuid4().hex for campo in ("tenant_id", "client_id", "client_secret", "subscription_id")}


def test_form_azure_tem_quatro_senhas_sem_estado_e_reset_no_envio():
    form = _form_azure().children[0]
    jsx = str(form)
    assert jsx.count('type:"password"') == 4
    assert jsx.index('name:"apelido"') < jsx.index('name:"tenant_id"')
    assert 'placeholder:"Ex.: Azure Corporativo"' in jsx
    assert jsx.count('placeholder:"00000000-0000-0000-0000-000000000000"') == 3
    assert all(f'name:"{campo}"' in jsx for campo in credenciais())
    assert "onChange:" not in jsx and "value:" not in jsx and "defaultValue:" not in jsx
    assert "localStorage" not in jsx and "sessionStorage" not in jsx
    assert str(form.reset_on_submit) == "true"
    assert "$form.reset()" in "".join(form._get_all_hooks())


def test_conectar_envia_apelido_e_quatro_credenciais_e_recarrega(xano, arvore, modal, capsys):
    dados = credenciais()
    formulario = {**dados, "apelido": "Equipe", "extra": "ignorar"}
    xano.responder("POST", "/azure/conexao", (200, {"conectado": True}))
    eventos = executar(ProvedoresState.conectar_azure, modal, formulario)
    assert xano.chamadas() == [("POST", "/azure/conexao")]
    assert xano.corpo(0) == {**dados, "apelido": "Equipe"}
    assert not formulario and not modal.form_aberto and not modal.form_loading
    assert nomes_eventos(eventos)[-1] == "carregar"
    azure = arvore.de(AzureState)
    assert azure.carregando and not azure.conectado
    capturado = capsys.readouterr()
    for valor in dados.values():
        assert valor not in repr(modal.dict()) + repr(azure.dict()) + repr(eventos) + str(capturado)


@pytest.mark.parametrize("eco", [False, True])
def test_erro_limpa_campos_e_preserva_apenas_mensagem_segura(xano, modal, eco):
    dados = credenciais()
    mensagem = "Credencial recusada"
    if eco:
        mensagem += ": " + " / ".join(dados.values())
    xano.responder("POST", "/azure/conexao", (400, {"message": mensagem}))
    formulario = dados.copy()
    versao = modal.versao_form_azure
    executar(ProvedoresState.conectar_azure, modal, formulario)
    assert not formulario and modal.versao_form_azure > versao and modal.form_aberto
    assert modal.form_error == ("Credencial recusada: " + " / ".join(["[oculto]"] * 4) if eco else mensagem)
    assert all(v not in repr(modal.dict()) for v in dados.values())
    modal.alterar_abertura(False)
    assert not modal.form_aberto and not modal.form_error


def test_form_incompleto_ou_sem_permissao_nao_envia(xano, arvore, modal):
    dados = credenciais()
    dados["tenant_id"] = ""
    executar(ProvedoresState.conectar_azure, modal, dados)
    assert not dados and modal.form_error
    arvore.de(AuthState).role = "leitura"
    dados = credenciais()
    executar(ProvedoresState.conectar_azure, modal, dados)
    assert not dados and xano.chamadas() == []


@pytest.mark.parametrize("origem,role,permitido", [
    ("servidor", "admin", False), ("", "admin", False),
    ("tela", "leitura", False), ("tela", "admin", True),
])
def test_desconectar_exige_admin_e_origem_do_get(xano, arvore, origem, role, permitido):
    arvore.de(AuthState).role = role
    estado = arvore.de(AzureState)
    corpo = {"provedor": "azure", "nao_alocado": True, "status": "sem_dados", "origem": origem}
    xano.responder("GET", "/azure/custo", (200, corpo))
    executar(AzureState.carregar, estado)
    assert estado.origem == origem and estado.conectado
    # A origem da resposta de sincronização descreve a leitura de custo na versão anterior.
    estado._aplicar(200, {**corpo, "origem": "azure"}, leitura=False)
    xano.responder("DELETE", "/azure/conexao", (204, None))
    eventos = executar(AzureState.desconectar, estado)
    if permitido:
        assert xano.chamadas()[-1] == ("DELETE", "/azure/conexao")
        assert not estado.conectado and not estado.origem and nomes_eventos(eventos)[-1] == "carregar"
    else:
        assert xano.chamadas() == [("GET", "/azure/custo")]


@pytest.mark.parametrize("corpo,espera", [
    ({"proxima_leitura_em": 1000 + 14_400_000}, 0),
    ({"proxima_leitura_em": 1000 + 59_100}, 60),
    ({"proxima_leitura_em": 999}, 0),
    ({"segundos_restantes": 24}, 24),
    ({"segundos_restantes": 90}, 60),
    ({"message": "Aguarde 3 segundos."}, 3),
])
def test_janela_de_sincronizacao(corpo, espera):
    assert _cooldown(corpo, 1000) == espera


@pytest.mark.parametrize("arquivo,titulo,detalhe", [
    ("nao_configurado", "Azure não configurado.", ""),
    ("sem_dados", "Conectado ao Azure", "Sem consumo registrado neste mês."),
    ("ok", "Conectado ao Azure", "US$ 123,45"),
    ("indisponivel_com_valor", "Azure indisponível agora.", "Último valor conhecido"),
    ("desatualizado", "O último valor é de 2026-10. Sincronize para ler o mês atual.", ""),
])
def test_leitura_preserva_estados_de_custo(arvore, arquivo, titulo, detalhe):
    corpo = json.loads((FIXTURES / f"azure_custo_get_{arquivo}.json").read_text(encoding="utf-8"))
    estado = arvore.de(AzureState)
    estado._aplicar(200, corpo)
    assert estado.titulo == titulo and detalhe in estado.detalhe
    assert estado.origem == (corpo.get("origem") or "")


def test_sincronizacao_respeita_429_e_libera_ao_vencer(xano, arvore):
    arvore.de(AuthState).role = "admin"
    estado = arvore.de(AzureState)
    estado.carregando = False
    xano.responder("POST", "/azure/custo/sincronizar", (429, {"segundos_restantes": 1}))
    eventos = executar(AzureState.sincronizar, estado)
    assert estado.segundos == 1 and nomes_eventos(eventos) == ["contar_segundos"]
    executar(AzureState.sincronizar, estado)
    assert len(xano.pedidos) == 1
    estado._liberar_em = time.monotonic() - 1
    executar(AzureState.contar_segundos, estado, estado._liberar_em)
    assert estado.segundos == 0


@pytest.mark.parametrize("sufixo,conta", [("0ab4", "•••• •••• 0ab4"), (None, "•••• ••••"), ("", "•••• ••••")])
def test_linha_azure_usa_identidade_do_get(arvore, sufixo, conta):
    estado = arvore.de(AzureState)
    corpo = json.loads((FIXTURES / "azure_custo_get_ok.json").read_text(encoding="utf-8"))
    estado._aplicar(200, {**corpo, "custo_mes_total": 0, "apelido": "Equipe", "tenant_final": sufixo})
    assert estado.conectado and estado.apelido == "Equipe" and estado.conta_mascarada == conta
    assert estado.detalhe == "Não alocado: US$ 0,00"
    estado._aplicar(200, corpo, leitura=False)
    assert estado.apelido == "Equipe" and estado.conta_mascarada == conta
    estado._aplicar(200, {**corpo, "configurado": False, "status": "nao_configurado"})
    assert not estado.conectado

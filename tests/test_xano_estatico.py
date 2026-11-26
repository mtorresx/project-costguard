"""Verificações estáticas (sem rede) dos .xs migrados na remoção do Mock.

Leem os arquivos de `xano/` como texto e conferem trechos que protegem regras de segurança e
integridade. São testes de regressão do TEXTO local: não provam que o Xano publicado se comporta
assim (isso exige publicar e testar com `--integracao`).
"""

import re
from pathlib import Path

import pytest

XANO = Path(__file__).resolve().parent.parent / "xano"
APP = XANO / "api" / "app"

# Conta fictícia de teste: mesmo valor de CONTA_TESTE em tests/integracao/cliente.py.
CONTA_TESTE = "000000000000"

# Os 12 arquivos migrados que não podem mais conter ramo Mock.
ARQUIVOS_SEM_MOCK = [
    APP / "classificar_custos_equipe_provedor_POST.xs",
    APP / "classificar_custos_provedor_POST.xs",
    APP / "coletar_custos_provedor_POST.xs",
    APP / "criar_provedor_POST.xs",
    APP / "descobrir_projetos_provedor_POST.xs",
    APP / "detalhe_provedor_GET.xs",
    APP / "editar_provedor_PATCH.xs",
    APP / "excluir_provedor_teste_POST.xs",
    APP / "listar_provedores_GET.xs",
    APP / "sincronizar_recursos_provedor_POST.xs",
    APP / "testar_conexao_provedor_POST.xs",
    XANO / "function" / "costguard" / "sincronizar_inventario.xs",
]

# `table/provedores.xs` fica fora da lista: mantém a coluna legada `usar_mock` (apenas comentário/schema).


def _ler(caminho: Path) -> str:
    return caminho.read_text(encoding="utf-8")


def _sem_comentarios(texto: str) -> str:
    return "\n".join(l for l in texto.splitlines() if not l.strip().startswith("//"))


# --- a) editar_provedor_PATCH: troca de credencial volta o provedor a "pendente" ---

def test_editar_provedor_credencial_mudou_combina_as_tres_condicoes():
    texto = _ler(APP / "editar_provedor_PATCH.xs")
    m = re.search(r"var \$credencial_mudou \{\s*value =(.*?)\n\s*\}", texto, re.S)
    assert m, "editar_provedor: bloco `$credencial_mudou` não encontrado"
    corpo = m.group(1)
    assert "$secret_enviado" in corpo, "credencial_mudou deve considerar o secret enviado"
    assert re.search(r"\$input\.aws_access_key_id != \$provedor_alvo\.aws_access_key_id", corpo), (
        "credencial_mudou deve comparar a chave de acesso enviada com a gravada")
    assert re.search(r"\$input\.identificador_conta != \$provedor_alvo\.identificador_conta", corpo), (
        "credencial_mudou deve comparar a conta enviada com a gravada")
    assert corpo.count("||") == 2, "as três condições devem ser combinadas com OR (||)"


def test_editar_provedor_so_vira_pendente_quando_nao_inativo():
    texto = _ler(APP / "editar_provedor_PATCH.xs")
    assert re.search(
        r'if \(\$credencial_mudou && \$provedor_alvo\.status != "inativo"\) \{\s*'
        r'var\.update \$novo_status \{ value = "pendente" \}',
        texto), "editar_provedor: a troca para 'pendente' deve exigir credencial_mudou e status != 'inativo'"
    assert re.search(r"status\s*:\s*\$novo_status", texto), "editar_provedor: o status gravado deve ser $novo_status"


def test_editar_provedor_nao_aceita_usar_mock_nem_ambiente():
    codigo = _sem_comentarios(_ler(APP / "editar_provedor_PATCH.xs"))
    for proibido in ("$input.usar_mock", "$input.ambiente"):
        assert proibido not in codigo, f"editar_provedor não pode referenciar {proibido}"


# --- b) criar_provedor ---

def test_criar_provedor_nasce_pendente_e_nao_aceita_usar_mock():
    texto = _ler(APP / "criar_provedor_POST.xs")
    assert re.search(r'status\s*:\s*"pendente"', texto), "criar_provedor deve gravar status 'pendente'"
    m = re.search(r"\n  input \{(.*?)\n  \}", texto, re.S)
    assert m, "criar_provedor: bloco input não encontrado"
    assert "usar_mock" not in m.group(1), "criar_provedor não pode declarar input `usar_mock`"
    assert "$input.usar_mock" not in texto, "criar_provedor não pode ler $input.usar_mock"


# --- c) travas atômicas e trava órfã ---

@pytest.mark.parametrize("arquivo", [
    XANO / "function" / "costguard" / "sincronizar_inventario.xs",
    APP / "classificar_custos_equipe_provedor_POST.xs",
])
def test_trava_atomica_na_tabela_travas_com_tratamento_de_orfa(arquivo):
    texto = _ler(arquivo)
    nome = arquivo.name
    assert re.search(r"db\.add travas \{\s*data = \{nome: \$trava_nome, adquirida_em: \$agora_trava\}", texto), (
        f"{nome}: a aquisição da trava deve ser um db.add na tabela `travas`")
    assert re.search(r"\$idade_trava > 900000 && \$tentativa == 1", texto), (
        f"{nome}: trava órfã (> 900000 ms = 15 min, só na 1ª tentativa) não encontrada")
    assert re.search(r"db\.del travas \{\s*field_name = \"id\"\s*field_value = \$trava_atual\.id", texto), (
        f"{nome}: a trava órfã deve ser removida (db.del travas pelo id da trava atual)")
    assert re.search(r"var\.update \$ocupado \{ value = true \}", texto), (
        f"{nome}: trava recente deve marcar o provedor como ocupado")
    assert "foreach ([1, 2])" in texto, f"{nome}: devem existir exatamente 2 tentativas de aquisição"


# --- d) testar_conexao: provedor inativo é recusado antes de qualquer escrita ---

def test_testar_conexao_bloqueia_inativo_sem_alterar_status():
    texto = _ler(APP / "testar_conexao_provedor_POST.xs")
    m = re.search(
        r'precondition \(\$provedor\.status != "inativo"\) \{\s*error_type = "inputerror"', texto)
    assert m, "testar_conexao: precondition de provedor inativo (inputerror = HTTP 400) não encontrada"
    primeira_escrita = re.search(r"db\.(edit|add|del)\b", texto)
    assert primeira_escrita, "testar_conexao: db.edit esperado para gravar o resultado do teste"
    assert m.start() < primeira_escrita.start(), (
        "testar_conexao: a recusa do inativo deve vir ANTES de qualquer escrita no banco")


# --- e) excluir_provedor_teste ---

def test_excluir_provedor_teste_exige_prefixo_e_conta_ficticia_sem_mock():
    texto = _ler(APP / "excluir_provedor_teste_POST.xs")
    codigo = _sem_comentarios(texto)
    assert re.search(r'precondition \(\$usuario_logado\.status == "ativo" && \$usuario_logado\.role == "admin"\)', codigo), (
        "excluir_provedor_teste: deve exigir admin ativo")
    assert re.search(r'precondition \(\$apelido_alvo\|starts_with:"TESTE_"\)', codigo), (
        "excluir_provedor_teste: deve exigir o prefixo TESTE_ (sensível a maiúsculas)")
    assert re.search(rf'precondition \(\$conta_alvo == "{CONTA_TESTE}"\)', codigo), (
        "excluir_provedor_teste: deve exigir a conta fictícia de teste")
    assert re.search(r"\$conta_alvo \{ value = \(\$provedor_alvo\.identificador_conta \?\? \"\"\) \}", codigo), (
        "excluir_provedor_teste: $conta_alvo deve vir de provedor_alvo.identificador_conta")
    assert "usar_mock" not in texto and "mock" not in texto.lower(), (
        "excluir_provedor_teste não pode depender de usar_mock/Mock")
    # As barreiras precisam vir antes da primeira exclusão.
    assert codigo.index("$conta_alvo ==") < codigo.index("db.del"), (
        "excluir_provedor_teste: as barreiras devem preceder qualquer db.del")


def test_conta_ficticia_do_xano_coincide_com_a_dos_testes_de_integracao():
    cliente = (Path(__file__).resolve().parent / "integracao" / "cliente.py").read_text(encoding="utf-8")
    assert f'CONTA_TESTE = "{CONTA_TESTE}"' in cliente, (
        "CONTA_TESTE de tests/integracao/cliente.py divergiu da conta usada em excluir_provedor_teste_POST.xs")


# --- f) ausência de Mock nos arquivos migrados ---

@pytest.mark.parametrize("arquivo", ARQUIVOS_SEM_MOCK, ids=lambda p: p.name)
def test_arquivos_migrados_nao_contem_mock(arquivo):
    texto = _ler(arquivo)
    assert "usar_mock" not in texto, f"{arquivo.name}: não deve ler nem gravar `usar_mock`"
    assert "mock" not in texto.lower(), f"{arquivo.name}: ainda contém referência a Mock"
    assert "MOCK_BASE_URL" not in texto, f"{arquivo.name}: ainda referencia MOCK_BASE_URL"


# --- g) constantes SigV4 do ramo real (Cost Explorer) declaradas no nível do stack ---

CONSTANTES_SIGV4_CE = [
    r'var \$sig_host \{ value = "ce\.us-east-1\.amazonaws\.com" \}',
    r'var \$canonical_uri \{ value = "/" \}',
    r'var \$sig_endpoint \{ value = "https://ce\.us-east-1\.amazonaws\.com/" \}',
]


def _constantes_sigv4_ausentes(texto: str) -> list[str]:
    """Padrões não encontrados no nível do `stack` (4 espaços) e antes do 1º `conditional`."""
    primeiro_conditional = re.search(r"^\s*conditional\b", texto, re.M)
    limite = primeiro_conditional.start() if primeiro_conditional else len(texto)
    ausentes = []
    for padrao in CONSTANTES_SIGV4_CE:
        m = re.search(rf"^ {{4}}{padrao}[ \t]*$", texto, re.M)
        if not m or m.start() >= limite:
            ausentes.append(padrao)
    return ausentes


@pytest.mark.parametrize("arquivo", [APP / "coletar_custos_provedor_POST.xs", APP / "classificar_custos_provedor_POST.xs"], ids=lambda p: p.name)
def test_constantes_sigv4_do_cost_explorer_fora_de_conditional(arquivo):
    ausentes = _constantes_sigv4_ausentes(_ler(arquivo))
    assert not ausentes, f"{arquivo.name}: constantes SigV4 ausentes ou dentro de conditional: {ausentes}"


@pytest.mark.parametrize("arquivo", [APP / "coletar_custos_provedor_POST.xs", APP / "classificar_custos_provedor_POST.xs"], ids=lambda p: p.name)
@pytest.mark.parametrize("indice", range(len(CONSTANTES_SIGV4_CE)))
def test_verificacao_das_constantes_sigv4_detecta_remocao(arquivo, indice):
    """Meta-teste em memória: sem a constante (ou dentro de um conditional) a verificação deve acusar."""
    texto = _ler(arquivo)
    padrao = CONSTANTES_SIGV4_CE[indice]
    removido = re.sub(rf"^ {{4}}{padrao}[ \t]*\n", "", texto, count=1, flags=re.M)
    assert removido != texto, "pré-condição: a linha deveria existir para ser removida"
    assert _constantes_sigv4_ausentes(removido) == [padrao]
    # Movida para dentro de um conditional: também deve ser acusada.
    linha = re.search(rf"^ {{4}}({padrao})[ \t]*$", texto, re.M).group(1)
    dentro = removido.replace("    conditional {", f"    conditional {{\n        {linha}", 1) if "    conditional {" in removido else removido
    assert padrao in _constantes_sigv4_ausentes(dentro)


@pytest.mark.parametrize("arquivo", [APP / "listar_provedores_GET.xs", APP / "detalhe_provedor_GET.xs"], ids=lambda p: p.name)
def test_leituras_de_provedor_nao_devolvem_usar_mock(arquivo):
    assert "usar_mock" not in _ler(arquivo), f"{arquivo.name}: não deve devolver `usar_mock`"

"""Conexão do Azure cadastrada PELA TELA (cifrada no banco): verificações estáticas, sem rede.

Mesmo padrão de `test_azure_custo_estatico.py`: leem os `.xs` locais como TEXTO e conferem, com
expressões regulares ancoradas, as regras do contrato. Cada conjunto de regras é uma função
`problemas_*` que devolve a lista de regras VIOLADAS; o arquivo real precisa devolver lista vazia e
cada MUTAÇÃO (alteração deliberada do texto, em memória) precisa violar a regra correspondente.

Arquivos cobertos:
  - xano/table/azure_conexao.xs                       (tabela nova e aditiva, UMA linha, 4 campos cifrados + apelido e tenant_final em texto simples)
  - xano/api/app/azure_conexao_POST.xs                (cadastra/substitui; admin; token ANTES de gravar; apelido opcional e tenant_final = 4 últimos)
  - xano/api/app/azure_conexao_DELETE.xs              (remove; admin; idempotente)
  - xano/function/costguard/azure_config_estado.xs    (ordem banco -> variáveis; nenhum segredo devolvido)
  - xano/api/app/azure_custo_sincronizar_POST.xs      (decifra dentro do endpoint; sem cache de 4 h)
As regras do sincronizar/GET/estado ficam em `test_azure_custo_estatico.py`.

O que estes testes NÃO provam:
  - nada sobre o comportamento do Xano PUBLICADO: `jwe_encode`/`jwe_decode` de QUATRO campos (a
    credencial AWS usa um só), `sensitive`/`visibility` em coluna `int`, `verb=DELETE` (sem precedente
    no repositório), `filters=trim` junto de `{ sensitive = true }` em input, `api.request` com corpo
    form-urlencoded, `response.headers`, `foreach` com `db.del` dentro de `try_catch` — NÃO VERIFICADO;
  - o que o Xano registra no HISTÓRICO DE REQUISIÇÕES: a documentação do Xano diz que guarda
    entrada/corpo, cabeçalhos e resposta de APIs e funções por 24 h (configurável por branch e por
    objeto) e não menciona mascarar campos sensíveis. Nenhum teste prova que o histórico está desligado;
  - se o corpo da chamada externa (`api.request`) ao Azure entra no histórico: NÃO VERIFICADO;
  - `substr` com início em variável (`$tenant|substr:$tenant_corte`, precedente em formatar_numero_br.xs), o
    `function.run` de costguard/limpar_texto_linha (escapes de CR/LF/tab em string) e `db.edit` com "" em
    coluna `text?` — NÃO VERIFICADO no Xano publicado;
  - o espelho em Python usa `re` do Python, que pode diferir do Xano.
Nenhum teste chama o Azure, o Xano ou qualquer rede. Valores de teste: GUID zerado e segredo
fictício óbvio, em `tests/fixtures/xano/conexao_azure_*.json`.
"""

import json
import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
XANO = RAIZ / "xano"
APP = XANO / "api" / "app"
FUNCOES = XANO / "function" / "costguard"
TABELAS = XANO / "table"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "xano"

POST = APP / "azure_conexao_POST.xs"
DELETE = APP / "azure_conexao_DELETE.xs"
TABELA = TABELAS / "azure_conexao.xs"
CONFIG = FUNCOES / "azure_config_estado.xs"
ESTADO = FUNCOES / "azure_custo_estado.xs"
SINCRONIZAR = APP / "azure_custo_sincronizar_POST.xs"
ARQUIVOS_CONEXAO = (POST, DELETE, TABELA, CONFIG, ESTADO, SINCRONIZAR)

JWE = ':{}:$env.PROV_ENC_KEY:"A256KW":"A256CBC-HS512"'
CAMPOS_CIFRADOS = ["tenant_id_cifrado", "client_id_cifrado", "client_secret_cifrado", "subscription_id_cifrado"]
MSG_TOKEN = "Não foi possível autenticar no Azure com os dados informados."
MSG_APELIDO = "Apelido inválido: use de 1 a 60 caracteres."
# Colunas de exibição (NÃO são segredo): texto simples, sem sensitive, sem cifragem.
CAMPOS_EXIBICAO = ["apelido", "tenant_final"]


# ---------------------------------------------------------------------------
# Utilitários
# ---------------------------------------------------------------------------

def _ler(caminho: Path) -> str:
    return caminho.read_text(encoding="utf-8")


def _codigo(caminho: Path) -> str:
    return "\n".join(l for l in _ler(caminho).splitlines() if not l.strip().startswith("//"))


def _ler_doc_interno(caminho: Path) -> str:
    """Le um documento de `docs/interno/`. Essa pasta e ignorada pelo Git (nao existe num clone limpo do repositorio
    publico): sem o arquivo, o teste e PULADO, nunca reprovado. Com o arquivo, a verificacao e a mesma de sempre."""
    if not caminho.exists():
        pytest.skip("docs/interno não faz parte do repositório público")
    return _ler(caminho)


def _fim_do_bloco(texto: str, inicio: int) -> int:
    nivel, i = 1, inicio
    while nivel:
        if texto[i] == "{":
            nivel += 1
        elif texto[i] == "}":
            nivel -= 1
        i += 1
    return i


def _bloco(texto: str, abertura: str) -> str:
    inicio = texto.index(abertura) + len(abertura)
    return texto[inicio:_fim_do_bloco(texto, inicio) - 1]


def _bloco_re(texto: str, padrao: str) -> str:
    """Como `_bloco`, mas devolve "" se o trecho sumiu (a regra que depende dele falha, sem abortar o teste)."""
    m = re.search(padrao, texto)
    if not m:
        return ""
    return texto[m.end():_fim_do_bloco(texto, m.end()) - 1]


def _chaves(texto: str) -> list[str]:
    return re.findall(r"^\s*(\w+)\s*:", texto, re.M)


def _mutar(texto: str, antigo: str, novo: str) -> str:
    assert antigo in texto, f"mutação inválida, trecho ausente: {antigo!r}"
    assert antigo != novo
    return texto.replace(antigo, novo, 1)


class _Regras:
    def __init__(self):
        self.violadas: list[str] = []

    def exigir(self, condicao, nome: str):
        if not condicao:
            self.violadas.append(nome)


def _precondicao_pos(codigo: str, condicao: str, tipo: str, mensagem: str | None = None) -> int:
    padrao = (r"precondition \(" + re.escape(condicao) + r'\) \{\s*error_type = "' + re.escape(tipo) + r'"\s*error = '
              + (re.escape(mensagem) if mensagem is not None else r"[^\n]+") + r"\s*\}")
    m = re.search(padrao, codigo)
    return m.start() if m else -1


def _mensagens_de_erro(codigo: str) -> list[str]:
    return re.findall(r"error = ([^\n]+)", codigo)


# Regex de GUID e do segredo, exatamente como em costguard/azure_config_estado (fonte da regra).
def _regex_guid_da_config() -> str:
    m = re.search(r'var \$tenant_ok \{ value = .*?"(/\^\[0-9a-fA-F\].*?\$/)"\|regex_matches', _codigo(CONFIG))
    return m.group(1)


REGEX_SEGREDO = '"/^[!-~]+$/"'


# ---------------------------------------------------------------------------
# Regras: tabela azure_conexao
# ---------------------------------------------------------------------------

def problemas_tabela(codigo: str) -> list[str]:
    r = _Regras()
    ex = r.exigir
    ex("table azure_conexao {" in codigo, "nome_da_tabela")
    colunas = re.findall(r"^\s*(?:int|text|decimal|bool|timestamp|enum)\s+(\w+)", codigo, re.M)
    ex(colunas == ["id", "chave"] + CAMPOS_CIFRADOS + CAMPOS_EXIBICAO + ["atualizado_em", "atualizado_por", "criado_em"], "colunas_esperadas")
    # apelido e tenant_final: texto simples anulável (aditivo), sem `sensitive`, sem cifragem e sem sufixo cifrado
    ex(re.search(r"^\s*text apelido\?\s*$", codigo, re.M) and re.search(r"^\s*text tenant_final\?\s*$", codigo, re.M), "apelido_e_tenant_final_texto_simples_anulavel")
    ex(not re.search(r"(apelido|tenant_final)\w*\??\s*\{[^}]*sensitive", codigo) and "apelido_cifrado" not in codigo and "tenant_final_cifrado" not in codigo, "apelido_e_tenant_final_nao_sensiveis")
    # nada em claro: nenhuma coluna chamada tenant_id/client_id/client_secret/subscription_id sem o sufixo cifrado
    ex(not set(colunas) & {"tenant_id", "client_id", "client_secret", "subscription_id", "segredo", "token", "senha"}, "nenhuma_coluna_em_claro")
    # UMA única conexão: chave fixa com índice único
    ex('{type: "btree|unique", field: [{name: "chave", op: "asc"}]}' in codigo and re.search(r"^\s*text chave filters=trim\s*$", codigo, re.M), "chave_unica")
    # os quatro campos cifrados: sensível e privado (precedente: usuarios.senha_hash, provedores.aws_secret_cifrado)
    for campo in CAMPOS_CIFRADOS:
        ex(re.search(r"text " + campo + r"\? \{\s*sensitive = true\s*visibility = \"private\"\s*\}", codigo), f"sensivel_e_privado_{campo}")
    ex(re.search(r"int atualizado_em\?=0 \{\s*visibility = \"private\"\s*\}", codigo) and re.search(r"int atualizado_por\? \{\s*visibility = \"private\"\s*\}", codigo),
       "auditoria_privada")
    ex("auth = false" in codigo, "tabela_sem_auth_propria")
    return r.violadas


def test_tabela_cumpre_todas_as_regras():
    assert problemas_tabela(_codigo(TABELA)) == []


MUTACOES_TABELA = [
    ("coluna_em_claro", "    int id\n", "    int id\n    text client_secret?\n", "nenhuma_coluna_em_claro"),
    ("coluna_em_claro_na_lista", "    text chave filters=trim\n", "    text chave filters=trim\n    text tenant_id?\n", "colunas_esperadas"),
    ("sem_indice_unico", "btree|unique", "btree", "chave_unica"),
    ("chave_sem_trim", "text chave filters=trim", "text chave", "chave_unica"),
    ("segredo_sem_sensivel", "text client_secret_cifrado? {\n      sensitive = true\n", "text client_secret_cifrado? {\n", "sensivel_e_privado_client_secret_cifrado"),
    ("segredo_publico", 'text client_secret_cifrado? {\n      sensitive = true\n      visibility = "private"', "text client_secret_cifrado? {\n      sensitive = true", "sensivel_e_privado_client_secret_cifrado"),
    ("tenant_publico", 'text tenant_id_cifrado? {\n      sensitive = true\n      visibility = "private"', "text tenant_id_cifrado? {\n      sensitive = true", "sensivel_e_privado_tenant_id_cifrado"),
    ("assinatura_sem_sensivel", "text subscription_id_cifrado? {\n      sensitive = true\n", "text subscription_id_cifrado? {\n", "sensivel_e_privado_subscription_id_cifrado"),
    ("apelido_sensivel", "    text apelido?\n", "    text apelido? {\n      sensitive = true\n    }\n", "apelido_e_tenant_final_texto_simples_anulavel"),
    ("apelido_sensivel_na_regra_de_sensiveis", "    text apelido?\n", "    text apelido? {\n      sensitive = true\n    }\n", "apelido_e_tenant_final_nao_sensiveis"),
    ("tenant_final_sensivel", "    text tenant_final?\n", "    text tenant_final? {\n      sensitive = true\n    }\n", "apelido_e_tenant_final_nao_sensiveis"),
    ("apelido_obrigatorio", "    text apelido?\n", "    text apelido\n", "apelido_e_tenant_final_texto_simples_anulavel"),
    ("tenant_final_obrigatorio", "    text tenant_final?\n", "    text tenant_final\n", "apelido_e_tenant_final_texto_simples_anulavel"),
    ("apelido_renomeado_para_cifrado", "    text apelido?\n", "    text apelido_cifrado?\n", "colunas_esperadas"),
    ("tenant_final_removido", "    text tenant_final?\n", "", "colunas_esperadas"),
    ("coluna_a_menos", "    text client_id_cifrado? {\n      sensitive = true\n      visibility = \"private\"\n    }\n", "", "colunas_esperadas"),
    ("auditoria_publica", 'int atualizado_por? {\n      visibility = "private"\n    }', "int atualizado_por?", "auditoria_privada"),
]


@pytest.mark.parametrize("nome,antigo,novo,regra", MUTACOES_TABELA, ids=[m[0] for m in MUTACOES_TABELA])
def test_mutacao_da_tabela_e_detectada(nome, antigo, novo, regra):
    assert regra in problemas_tabela(_mutar(_codigo(TABELA), antigo, novo)), nome


def test_tabela_nova_e_aditiva_nenhuma_tabela_existente_foi_alterada():
    """Menor risco: tabela NOVA. `provedores` (AWS/sync) e `provedor_externo_leitura` (leitura guardada) não ganham colunas de segredo."""
    for nome in ("provedores.xs", "provedor_externo_leitura.xs", "travas.xs", "usuarios.xs"):
        codigo = _codigo(TABELAS / nome)
        assert "azure_conexao" not in codigo and "tenant_id" not in codigo and "client_secret" not in codigo, nome
    assert "azure" not in _codigo(TABELAS / "provedores.xs").lower()


# ---------------------------------------------------------------------------
# Regras: POST /azure/conexao
# ---------------------------------------------------------------------------

def _trava_ok(codigo: str) -> list[str]:
    """Regras da trava de exclusão mútua (a MESMA do sincronizar), comuns ao POST e ao DELETE."""
    faltas = []
    if 'var $trava_nome { value = "azure_custo_sincronizar" }' not in codigo:
        faltas.append("trava_compartilhada_com_o_sincronizar")
    if not re.search(r"db\.add travas \{\s*data = \{nome: \$trava_nome, adquirida_em: \$agora_trava\}", codigo):
        faltas.append("trava_na_tabela_travas")
    if not re.search(r"\$idade_trava > 120000 && \$tentativa == 1\) \{\s*db\.del travas \{\s*field_name = \"id\"\s*field_value = \$trava_atual\.id", codigo):
        faltas.append("trava_orfa_curta")
    fin = _bloco_re(codigo, r"finally \{")
    if not re.search(r'if \(\$trava_id != null\) \{\s*db\.del travas \{\s*field_name = "id"\s*field_value = \$trava_id', fin):
        faltas.append("trava_liberada_no_finally")
    if _precondicao_pos(codigo, "$trava_id != null", "toomanyrequests",
                        '"Já existe uma operação de conexão ou sincronização do Azure em andamento. Tente novamente em instantes."') < 0:
        faltas.append("trava_ocupada_429")
    if not re.search(r"catch \{\s*var\.update \$falha \{ value = true \}\s*\}\s*finally \{", codigo):
        faltas.append("falha_inesperada_vira_erro_generico")
    return faltas


def problemas_post(codigo: str) -> list[str]:
    r = _Regras()
    ex = r.exigir

    # --- rota, autenticação, admin-only (401 / 403 "Acesso negado" como o sincronizar) ---
    ex('query "azure/conexao" verb=POST' in codigo and 'api_group = "app"' in codigo and 'auth = "usuarios"' in codigo, "rota_post_autenticada")
    entrada = _bloco(codigo, "input {")
    ex(re.findall(r"^\s*text (\w+)\??", entrada, re.M) == ["tenant_id", "client_id", "client_secret", "subscription_id", "apelido"], "so_os_quatro_inputs_e_o_apelido")
    ex(len(re.findall(r"filters=trim", entrada)) == 5, "todos_os_inputs_com_trim")
    ex(re.search(r"^\s*text apelido\? filters=trim\s*$", entrada, re.M), "apelido_input_opcional_com_trim_sem_sensitive")
    ex(re.search(r"text client_secret\? filters=trim \{\s*sensitive = true\s*\}", entrada), "segredo_marcado_sensivel_no_input")
    p_token = _precondicao_pos(codigo, "$usuario_logado != null", "unauthorized", '"Token inválido ou expirado"')
    p_admin = _precondicao_pos(
        codigo, '$usuario_logado.status == "ativo" && $usuario_logado.role == "admin"', "accessdenied", '"Acesso negado"')
    ex(p_token >= 0 and p_admin > p_token, "admin_ativo_exigido")
    primeiro_efeito = min(i for i in (codigo.find("db.add travas"), codigo.find("api.request"), codigo.find("db.add azure_conexao"),
                                      codigo.find("db.del provedor_externo_leitura")) if i >= 0)
    ex(0 <= p_admin < primeiro_efeito, "admin_antes_de_qualquer_efeito")
    ex(re.search(r'if \(\$solicitante_atual == null \|\| \$solicitante_atual\.status != "ativo" \|\| '
                 r'\$solicitante_atual\.role != "admin"\) \{\s*var\.update \$estado \{ value = "negado" \}', codigo), "admin_relido_na_trava")
    ex(_precondicao_pos(codigo, '$estado != "negado"', "accessdenied", '"Acesso negado"') > codigo.find("finally {"), "negado_vira_403_apos_liberar_trava")

    # --- validação ANTES de qualquer efeito: trim, GUID (mesma regex da config), segredo ---
    for nome, campo in (("tenant", "tenant_id"), ("client", "client_id"), ("segredo", "client_secret"), ("assinatura", "subscription_id")):
        ex(f'var ${nome} {{ value = (($input.{campo} ?? "")|trim) }}' in codigo, f"trim_{campo}")
    guid = _regex_guid_da_config()
    for nome in ("tenant", "client", "assinatura"):
        ex(f'var ${nome}_ok {{ value = (($' + nome + f'|strlen) == 36 && ("{guid}"|regex_matches:${nome})) }}' in codigo, f"guid_{nome}_igual_ao_da_config")
    ex(f'var $segredo_ok {{ value = (($segredo|strlen) >= 8 && ($segredo|strlen) <= 256 && ({REGEX_SEGREDO}|regex_matches:$segredo)) }}' in codigo,
       "segredo_igual_ao_da_config")
    pos_val = []
    for var, campo in (("tenant", "tenant_id"), ("client", "client_id"), ("assinatura", "subscription_id"), ("segredo", "client_secret")):
        pos = _precondicao_pos(codigo, f"${var}_ok == true", "inputerror", f'"Dados de conexão inválidos. Verifique o campo {campo}."')
        ex(pos >= 0, f"validacao_400_{campo}")
        pos_val.append(pos)
    ex(all(0 <= p < codigo.find("db.add travas") for p in pos_val) and all(0 <= p < codigo.find("api.request") for p in pos_val), "validacao_antes_da_trava_e_do_azure")

    # --- apelido (opcional, não é segredo): limpar_texto_linha, tamanho medido no texto JÁ limpo, rejeita (nunca trunca) ---
    m_limpa = re.search(r'function\.run "costguard/limpar_texto_linha" \{\s*input = \{texto: \(\$input\.apelido \?\? ""\)\}\s*\} as \$apelido\b', codigo)
    ex(m_limpa, "apelido_passa_por_limpar_texto_linha")
    ex("var $apelido_ok { value = (($apelido|strlen) <= 60) }" in codigo, "apelido_limite_60_medido_no_texto_limpo")
    ex(not re.search(r"var\.update \$apelido\b|\$apelido\|(substr|trim|replace)|\$input\.apelido\|", codigo) and codigo.count("$input.apelido") == 1, "apelido_nunca_truncado_nem_remedido")
    p_apelido = _precondicao_pos(codigo, "$apelido_ok == true", "inputerror", f'"{MSG_APELIDO}"')
    ex(p_apelido >= 0, "apelido_400_generico")
    ex(m_limpa is not None and 0 <= m_limpa.start() < codigo.find("var $apelido_ok") < p_apelido
       and p_apelido > max(pos_val), "apelido_validado_na_etapa_das_entradas")
    ex(0 <= p_apelido < codigo.find("db.add travas") and 0 <= p_apelido < codigo.find("api.request") and 0 <= p_apelido < codigo.find("db.del provedor_externo_leitura"),
       "apelido_validado_antes_da_trava_e_do_azure")
    ex(codigo.count("function.run") == 1, "sem_function_run_com_segredo_como_input")

    # --- tenant_final: SÓ os últimos 4 caracteres do tenant já validado (36), nunca o ID inteiro ---
    ex("var $tenant_corte { value = ($tenant|strlen) - 4 }\n    var $tenant_final { value = $tenant|substr:$tenant_corte }" in codigo and codigo.count("substr") == 1,
       "tenant_final_ultimos_4_caracteres")
    ex(_precondicao_pos(codigo, "$tenant_ok == true", "inputerror") < codigo.find("var $tenant_corte") < codigo.find("db.add travas"), "tenant_final_calculado_apos_validar_o_tenant")
    ex(len([l for l in codigo.splitlines() if "$tenant_final" in l]) == 3, "tenant_final_so_na_declaracao_e_nas_duas_gravacoes")
    usos_tenant = [l.strip() for l in codigo.splitlines() if re.search(r"\$tenant\b", l)]
    permitido_tenant = [l for l in usos_tenant if l.startswith(("var $tenant {", "var $tenant_ok {", "url = ", "var $tenant_cifrado {", "var $tenant_corte {", "var $tenant_final {"))
                        or l.startswith("precondition ($tenant_ok")]
    ex(len(usos_tenant) == len(permitido_tenant), "tenant_inteiro_so_em_validacao_url_cifra_e_corte")

    # --- token ANTES de gravar; sem gravar em falha; 400 genérico; 429 com retry-after ---
    ex(codigo.count("api.request") == 1, "uma_unica_chamada_ao_azure")
    urls = re.findall(r"url = ([^\n]+)", codigo)
    ex(urls == ['"https://login.microsoftonline.com/" ~ $tenant ~ "/oauth2/v2.0/token"'], "url_so_do_token")
    ex("management.azure.com/subscriptions" not in codigo and "Microsoft.CostManagement" not in codigo, "nao_consulta_custo_nem_valida_assinatura")
    ex(re.search(r'params = \{client_id: \$client, client_secret: \$segredo, scope: "https://management\.azure\.com/\.default", grant_type: "client_credentials"\}', codigo)
       and 'method = "POST"' in codigo and '"Content-Type: application/x-www-form-urlencoded"' in codigo and "timeout = 10" in codigo, "pedido_de_token_igual_ao_do_sincronizar")
    ex("$assinatura" not in "\n".join(l for l in codigo.splitlines() if "url =" in l or "params =" in l or "headers" in l), "assinatura_nao_vai_ao_azure")
    pos_req = codigo.find("api.request")
    escritas = [codigo.find(s) for s in ("db.add azure_conexao", "db.edit azure_conexao", "db.del provedor_externo_leitura", "var $tenant_cifrado")]
    ex(all(e > pos_req for e in escritas) and all(e >= 0 for e in escritas), "token_antes_de_gravar")
    ex(codigo.count("db.add azure_conexao") == 1 and codigo.count("db.edit azure_conexao") == 1 and codigo.count("db.del provedor_externo_leitura") == 1,
       "gravacao_so_no_ramo_de_sucesso")
    ex(re.search(r'if \(\$t_status == 429\) \{\s*var\.update \$estado \{ value = "limite" \}\s*\}\s*elseif \(\$token_ok == false\) \{\s*var\.update \$estado \{ value = "recusado" \}', codigo),
       "falha_do_token_nao_grava")
    bloco_escrita = _bloco_re(codigo, r'\{\s*if \(\$estado == ""\) \{\s*var \$tenant_cifrado')
    ex(bloco_escrita != "" and all(s in bloco_escrita for s in ("db.add azure_conexao", "db.edit azure_conexao", "db.del provedor_externo_leitura")),
       "escrita_so_com_estado_vazio_depois_do_token")
    ex("var $token_ok { value = ($t_status == 200 && ($t_token|strlen) >= 20 && ($t_token|strlen) <= 8192 && (($t_token|trim)|strlen) == ($t_token|strlen) && ("
       '"/^[A-Za-z0-9._~-]+$/"|regex_matches:$t_token)) }' in codigo, "token_valido_exigido")
    ex(_precondicao_pos(codigo, '$estado != "recusado"', "inputerror", f'"{MSG_TOKEN}"') > codigo.find("finally {"), "token_recusado_400_generico_apos_liberar_trava")
    ex(_precondicao_pos(codigo, '$estado == "salvo"', "standard", '"Não foi possível salvar a conexão do Azure agora. Tente novamente em instantes."') > 0, "so_salvo_chega_ao_sucesso")
    ex(codigo.count('var.update $estado { value = "salvo" }') == 1 and codigo.find('value = "salvo"') > codigo.find("db.edit azure_conexao"), "salvo_so_depois_de_gravar")
    # 429 do token: segundos = maior retry-after (contém), 1..3600, padrão 60; HTTP 429 com os segundos; sem gravar
    ex('($cab_nome|contains:"retry-after")' in codigo and '"/^[0-9]{1,9}$/"' in codigo and "var.update $segundos_restantes { value = 60 }" in codigo, "429_maior_retry_after_padrao_60")
    ex(re.search(r"if \(\$segundos_restantes < 1\) \{\s*var\.update \$segundos_restantes \{ value = 1 \}\s*\}\s*elseif \(\$segundos_restantes > 3600\) \{\s*var\.update \$segundos_restantes \{ value = 3600 \}", codigo),
       "429_entre_1_e_3600")
    ex(re.search(r'var \$msg_limite \{\s*value = "O Azure limitou as requisições\. Aguarde " ~ \(\$segundos_restantes\|to_text\) ~ " segundos para tentar de novo\."\s*\}', codigo), "mensagem_do_429")
    ex(_precondicao_pos(codigo, '$estado != "limite"', "toomanyrequests", "$msg_limite") > codigo.find("finally {"), "http_429_apos_liberar_trava")

    # --- cifragem: os QUATRO campos, mesmo mecanismo da AWS, nada em claro no banco ---
    ex(codigo.count("|jwe_encode" + JWE) == 4 and codigo.count("jwe_encode") == 4, "cifra_os_quatro_campos_com_prov_enc_key")
    ex(not re.search(r"jwe_encode[^\n]*\$(apelido|tenant_final)|\$(apelido|tenant_final)\|jwe", codigo), "apelido_e_tenant_final_nao_sao_cifrados")
    for var, origem in (("tenant_cifrado", "tenant"), ("client_cifrado", "client"), ("segredo_cifrado", "segredo"), ("assinatura_cifrada", "assinatura")):
        ex(f"var ${var} {{ value = ${origem}|jwe_encode{JWE} }}" in codigo, f"cifra_{origem}")
    add = _bloco(_bloco(codigo, "db.add azure_conexao {"), "data = {")
    edit = _bloco(_bloco(codigo, "db.edit azure_conexao {"), "data = {")
    ex(_chaves(add) == ["chave"] + CAMPOS_CIFRADOS + CAMPOS_EXIBICAO + ["atualizado_em", "atualizado_por"], "db_add_so_campos_da_tabela")
    ex(_chaves(edit) == CAMPOS_CIFRADOS + CAMPOS_EXIBICAO + ["atualizado_em", "atualizado_por"], "db_edit_so_campos_da_tabela")
    for bloco_dados in (add, edit):
        ex(re.search(r"tenant_id_cifrado\s*: \$tenant_cifrado\s+client_id_cifrado\s*: \$client_cifrado\s+client_secret_cifrado\s*: \$segredo_cifrado\s+subscription_id_cifrado\s*: \$assinatura_cifrada",
                     bloco_dados), "dados_gravados_sao_os_cifrados")
        ex(re.search(r"atualizado_por\s*: \$solicitante_atual\.id", bloco_dados) and re.search(r"atualizado_em\s*: \$agora_ms", bloco_dados), "grava_quando_e_quem")
        # apelido (limpo, "" quando vazio: db.edit ignora null) e tenant_final: texto simples, SEMPRE sobrescritos na substituição
        ex(re.search(r"subscription_id_cifrado\s*: \$assinatura_cifrada\s+apelido\s*: \$apelido\n\s+tenant_final\s*: \$tenant_final\n\s+atualizado_em", bloco_dados),
           "apelido_e_tenant_final_gravados_em_texto_simples")
    ex(re.search(r'chave\s*: "azure"', add) is not None and codigo.count('"azure"') >= 3, "chave_fixa_azure")
    ex(re.search(r'db\.get azure_conexao \{\s*field_name = "chave"\s*field_value = "azure"\s*\} as \$existente\s*conditional \{\s*if \(\$existente == null\) \{\s*db\.add azure_conexao', codigo),
       "upsert_unico")
    ex(codigo.find("db.add azure_conexao") < codigo.find("finally {") and codigo.find("db.get azure_conexao") < codigo.find("finally {"), "upsert_sob_trava")
    posicoes_cifra = [codigo.find(f"var ${v} {{") for v in ("tenant_cifrado", "client_cifrado", "segredo_cifrado", "assinatura_cifrada")]
    ex(all(0 <= pc < codigo.find("db.del provedor_externo_leitura") for pc in posicoes_cifra), "cifra_antes_de_apagar_qualquer_coisa")

    # --- invalida a leitura guardada do Azure ANTES de gravar a conexão nova ---
    ex(re.search(r'db\.query provedor_externo_leitura \{\s*where = \$db\.provedor_externo_leitura\.provedor == "azure"\s*return = \{type: "list"\}\s*\} as \$leituras_antigas\s*'
                 r'foreach \(\$leituras_antigas\) \{\s*each as \$leitura_antiga \{\s*db\.del provedor_externo_leitura \{\s*field_name = "id"\s*field_value = \$leitura_antiga\.id', codigo),
       "invalida_a_leitura_guardada")
    ex(codigo.find("db.del provedor_externo_leitura") < codigo.find("db.add azure_conexao") and codigo.find("db.del provedor_externo_leitura") < codigo.find("db.edit azure_conexao"),
       "invalida_antes_de_gravar")

    # --- resposta exata, sem eco ---
    ex(re.search(r"var \$resposta \{\s*value = \{conectado: true\}\s*\}", codigo) and "response = $resposta" in codigo and codigo.count("$resposta") == 2, "resposta_exata_conectado_true")
    mensagens = _mensagens_de_erro(codigo)
    ex(all(("$" not in m) or m == "$msg_limite" for m in mensagens), "mensagens_sem_eco_de_valor")
    ex(re.search(r"\$msg_limite \{\s*value = \"[^$]*\" ~ \(\$segundos_restantes\|to_text\) ~ \"[^$]*\"\s*\}", codigo), "msg_limite_so_com_segundos")
    ex(not re.search(r"error = [^\n]*\$(input|tenant|client|segredo|assinatura|apelido|t_token|resp_token)", codigo), "erro_nao_cita_entrada_nem_resposta_do_azure")
    linhas_resp = [l.strip() for l in codigo.splitlines() if "$resp_token" in l]
    ex(all(l.startswith("var.update $t_") or l.startswith("} as $resp_token") for l in linhas_resp), "resposta_do_azure_so_em_variaveis_internas")
    ex(not re.search(r"\$resp_token\.response\.(result\.error|body)", codigo), "nao_le_o_erro_do_azure")
    ex(codigo.count("$t_token") == len(re.findall(r"\$t_token", "\n".join(l for l in codigo.splitlines()
                                                                         if "var $t_token" in l or "var.update $t_token" in l or "strlen" in l or "regex_matches" in l))), "token_nunca_e_guardado_nem_devolvido")

    # --- segredo: só validação, corpo do token e cifragem; nunca função, log, debug ---
    usos_segredo = [l.strip() for l in codigo.splitlines() if re.search(r"\$segredo\b", l)]
    permitido = [l for l in usos_segredo if l.startswith("var $segredo {") or l.startswith("var $segredo_ok {") or l.startswith("params = {client_id: $client")
                 or l.startswith("var $segredo_cifrado {")]
    ex(len(usos_segredo) == len(permitido) == 4, "segredo_so_em_validacao_token_e_cifragem")
    ex(not re.search(r"debug|util\.log|\blog\b|print|echo", codigo, re.I), "sem_log_nem_debug")
    ex(set(re.findall(r"\$env\.(\w+)", codigo)) == {"PROV_ENC_KEY"}, "env_so_a_chave_de_cifragem")
    ex(not re.search(r"^\s*history\s*=", codigo, re.M), "sem_atributo_de_historico_inventado")

    # --- não dispara sincronização nem toca na leitura além de apagá-la ---
    ex("azure_custo_sincronizar" in codigo.split("var $trava_nome")[1].split("\n")[0] and "db.add provedor_externo_leitura" not in codigo
       and "db.edit provedor_externo_leitura" not in codigo and "azure/custo" not in codigo, "nao_dispara_sincronizacao")
    for falta in _trava_ok(codigo):
        r.violadas.append(falta)
    ex(_precondicao_pos(codigo, "$falha == false", "standard", '"Não foi possível salvar a conexão do Azure agora. Tente novamente em instantes."') > codigo.find("finally {"),
       "erro_generico_apos_liberar_trava")
    return r.violadas


def test_post_cumpre_todas_as_regras():
    assert problemas_post(_codigo(POST)) == []


MUTACOES_POST = [
    # autorização
    ("sem_admin", '$usuario_logado.status == "ativo" && $usuario_logado.role == "admin"', '$usuario_logado.status == "ativo"', "admin_ativo_exigido"),
    ("admin_relido_removido", 'if ($solicitante_atual == null || $solicitante_atual.status != "ativo" || $solicitante_atual.role != "admin") {',
     "if ($solicitante_atual == null) {", "admin_relido_na_trava"),
    ("negado_sem_403", 'precondition ($estado != "negado") {\n      error_type = "accessdenied"', 'precondition ($estado != "negado") {\n      error_type = "standard"', "negado_vira_403_apos_liberar_trava"),
    ("sem_401", 'precondition ($usuario_logado != null) {\n      error_type = "unauthorized"', 'precondition ($usuario_logado != null) {\n      error_type = "standard"', "admin_ativo_exigido"),
    # entrada: trim e validação
    ("input_sem_trim", "text tenant_id? filters=trim", "text tenant_id?", "todos_os_inputs_com_trim"),
    ("segredo_input_sem_sensivel", "text client_secret? filters=trim {\n      sensitive = true\n    }", "text client_secret? filters=trim", "segredo_marcado_sensivel_no_input"),
    ("input_a_mais", "text apelido? filters=trim", "text apelido? filters=trim\n    text extra?", "so_os_quatro_inputs_e_o_apelido"),
    ("apelido_input_sem_trim", "text apelido? filters=trim", "text apelido?", "apelido_input_opcional_com_trim_sem_sensitive"),
    ("apelido_input_sensivel", "text apelido? filters=trim", "text apelido? filters=trim {\n      sensitive = true\n    }", "apelido_input_opcional_com_trim_sem_sensitive"),
    ("apelido_input_obrigatorio", "text apelido? filters=trim", "text apelido filters=trim", "apelido_input_opcional_com_trim_sem_sensitive"),
    ("sem_trim_no_tenant", 'var $tenant { value = (($input.tenant_id ?? "")|trim) }', 'var $tenant { value = ($input.tenant_id ?? "") }', "trim_tenant_id"),
    ("sem_trim_no_segredo", 'var $segredo { value = (($input.client_secret ?? "")|trim) }', 'var $segredo { value = ($input.client_secret ?? "") }', "trim_client_secret"),
    ("guid_sem_tamanho", "var $tenant_ok { value = (($tenant|strlen) == 36 && ", "var $tenant_ok { value = (", "guid_tenant_igual_ao_da_config"),
    ("guid_sem_regex", '("/^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/"|regex_matches:$client)', "true", "guid_client_igual_ao_da_config"),
    ("guid_assinatura_frouxo", '("/^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/"|regex_matches:$assinatura)', '("/^[0-9a-fA-F-]+$/"|regex_matches:$assinatura)', "guid_assinatura_igual_ao_da_config"),
    ("segredo_vazio_aceito", "($segredo|strlen) >= 8 && ", "", "segredo_igual_ao_da_config"),
    ("segredo_sem_limite", "($segredo|strlen) <= 256 && ", "", "segredo_igual_ao_da_config"),
    ("segredo_com_espaco_ou_controle", '"/^[!-~]+$/"|regex_matches:$segredo', '"/^.+$/"|regex_matches:$segredo', "segredo_igual_ao_da_config"),
    ("sem_validacao_do_segredo", 'precondition ($segredo_ok == true) {', 'precondition ($segredo_ok == false) {', "validacao_400_client_secret"),
    ("validacao_ecoa_o_valor", 'error = "Dados de conexão inválidos. Verifique o campo tenant_id."', 'error = "Dados de conexão inválidos: " ~ $tenant', "validacao_400_tenant_id"),
    ("validacao_ecoa_o_valor_na_regra_de_mensagens", 'error = "Dados de conexão inválidos. Verifique o campo client_id."', 'error = "Inválido " ~ $client', "mensagens_sem_eco_de_valor"),
    ("validacao_ecoa_o_segredo", 'error = "Dados de conexão inválidos. Verifique o campo client_secret."', 'error = $segredo', "mensagens_sem_eco_de_valor"),
    ("validacao_400_vira_500", 'error_type = "inputerror"\n      error = "Dados de conexão inválidos. Verifique o campo client_id."', 'error_type = "standard"\n      error = "Dados de conexão inválidos. Verifique o campo client_id."', "validacao_400_client_id"),
    ("validacao_depois_da_trava", 'precondition ($tenant_ok == true) {', 'precondition ($trava_id == 0) {', "validacao_400_tenant_id"),
    # token antes de gravar; falha não grava
    ("grava_antes_do_token", "var $t_token { value = \"\" }", 'var $t_token { value = "" }\n    db.add azure_conexao {\n      data = {chave: "azure"}\n    }', "token_antes_de_gravar"),
    ("apaga_leitura_antes_do_token", "var $t_token { value = \"\" }", 'var $t_token { value = "" }\n    db.del provedor_externo_leitura {\n      field_name = "id"\n      field_value = 1\n    }', "token_antes_de_gravar"),
    ("token_recusado_grava", 'elseif ($token_ok == false) {\n                var.update $estado { value = "recusado" }', 'elseif ($token_ok == false) {\n                var.update $estado { value = "" }', "falha_do_token_nao_grava"),
    ("429_grava", 'if ($t_status == 429) {\n                var.update $estado { value = "limite" }', 'if ($t_status == 4290) {\n                var.update $estado { value = "limite" }', "falha_do_token_nao_grava"),
    ("token_sem_validacao", "($t_token|strlen) >= 20 && ", "", "token_valido_exigido"),
    ("sem_token_e_so_status", ' && ("/^[A-Za-z0-9._~-]+$/"|regex_matches:$t_token))', ")", "token_valido_exigido"),
    ("escrita_sem_gate_de_estado", 'if ($estado == "") {\n            var $tenant_cifrado', 'if ($estado != "xx") {\n            var $tenant_cifrado',
     "escrita_so_com_estado_vazio_depois_do_token"),
    ("salvo_antes_de_gravar", 'var.update $estado { value = "salvo" }', 'var.update $estado { value = "salvo" }\n            var.update $estado { value = "salvo" }', "salvo_so_depois_de_gravar"),
    ("recusado_vira_500", f'error_type = "inputerror"\n      error = "{MSG_TOKEN}"', f'error_type = "standard"\n      error = "{MSG_TOKEN}"', "token_recusado_400_generico_apos_liberar_trava"),
    ("recusado_ecoa_o_azure", f'error = "{MSG_TOKEN}"', 'error = "Falha: " ~ $t_token', "token_recusado_400_generico_apos_liberar_trava"),
    ("recusado_ecoa_o_azure_na_regra_de_mensagens", f'error = "{MSG_TOKEN}"', 'error = "Falha: " ~ $resp_token.response.result', "mensagens_sem_eco_de_valor"),
    ("sucesso_sem_confirmar", 'precondition ($estado == "salvo") {', 'precondition ($estado != "x") {', "so_salvo_chega_ao_sucesso"),
    ("subscription_vai_ao_azure", 'params = {client_id: $client, client_secret: $segredo,', 'params = {subscription: $assinatura, client_id: $client, client_secret: $segredo,', "assinatura_nao_vai_ao_azure"),
    ("consulta_de_custo_extra", 'timeout = 10', 'timeout = 10\n                } as $x\n                api.request {\n                  url = "https://management.azure.com/subscriptions/" ~ $assinatura', "uma_unica_chamada_ao_azure"),
    ("url_do_token_com_input_cru", '"https://login.microsoftonline.com/" ~ $tenant ~', '"https://login.microsoftonline.com/" ~ $input.tenant_id ~', "url_so_do_token"),
    ("pedido_de_token_get", 'method = "POST"', 'method = "GET"', "pedido_de_token_igual_ao_do_sincronizar"),
    # 429
    ("429_sem_retry_after", '($cab_nome|contains:"retry-after")', '($cab_nome|contains:"x-ms")', "429_maior_retry_after_padrao_60"),
    ("429_padrao_zero", "var.update $segundos_restantes { value = 60 }", "var.update $segundos_restantes { value = 0 }", "429_maior_retry_after_padrao_60"),
    ("429_sem_teto", "elseif ($segundos_restantes > 3600) {\n                var.update $segundos_restantes { value = 3600 }", "elseif ($segundos_restantes > 360000) {\n                var.update $segundos_restantes { value = 360000 }", "429_entre_1_e_3600"),
    ("429_sem_http_429", 'precondition ($estado != "limite") {\n      error_type = "toomanyrequests"', 'precondition ($estado != "limite") {\n      error_type = "standard"', "http_429_apos_liberar_trava"),
    ("429_sem_segundos", '"O Azure limitou as requisições. Aguarde " ~ ($segundos_restantes|to_text) ~ " segundos para tentar de novo."', '"O Azure limitou as requisições."', "mensagem_do_429"),
    # cifragem
    ("cifra_so_tres", "var $assinatura_cifrada { value = $assinatura|jwe_encode" + JWE + " }", "var $assinatura_cifrada { value = $assinatura }", "cifra_os_quatro_campos_com_prov_enc_key"),
    ("segredo_em_claro_no_banco", "client_secret_cifrado  : $segredo_cifrado\n                    subscription_id_cifrado: $assinatura_cifrada\n                    apelido                : $apelido\n                    tenant_final           : $tenant_final\n                    atualizado_em          : $agora_ms\n                    atualizado_por         : $solicitante_atual.id\n                  }\n                }\n              }\n            }",
     "client_secret_cifrado  : $segredo\n                    subscription_id_cifrado: $assinatura_cifrada\n                    apelido                : $apelido\n                    tenant_final           : $tenant_final\n                    atualizado_em          : $agora_ms\n                    atualizado_por         : $solicitante_atual.id\n                  }\n                }\n              }\n            }", "dados_gravados_sao_os_cifrados"),
    ("tenant_em_claro_no_add", "tenant_id_cifrado      : $tenant_cifrado", "tenant_id_cifrado      : $tenant", "dados_gravados_sao_os_cifrados"),
    ("cifra_com_outra_chave", "$client|jwe_encode:{}:$env.PROV_ENC_KEY", "$client|jwe_encode:{}:$env.AZURE_CLIENT_SECRET", "cifra_os_quatro_campos_com_prov_enc_key"),
    ("cifra_com_outro_algoritmo", '$tenant|jwe_encode:{}:$env.PROV_ENC_KEY:"A256KW":"A256CBC-HS512"', '$tenant|jwe_encode:{}:$env.PROV_ENC_KEY:"A128KW":"A128CBC-HS256"', "cifra_tenant"),
    ("campo_a_mais_no_banco", 'chave                  : "azure"', 'chave                  : "azure"\n                    token_acesso           : $t_token', "db_add_so_campos_da_tabela"),
    ("sem_auditoria", "atualizado_por         : $solicitante_atual.id\n", "", "grava_quando_e_quem"),
    ("cifra_depois_de_apagar", "var $tenant_cifrado { value = $tenant|jwe_encode" + JWE + " }\n", "", "cifra_antes_de_apagar_qualquer_coisa"),
    # upsert, lock, invalidação
    ("sem_chave_fixa", 'chave                  : "azure"', 'chave                  : "outra"', "chave_fixa_azure"),
    ("upsert_sem_leitura_previa", "if ($existente == null) {", "if ($tenant == null) {", "upsert_unico"),
    ("sempre_add", "if ($existente == null) {", "if (true) {", "upsert_unico"),
    ("trava_propria", 'var $trava_nome { value = "azure_custo_sincronizar" }', 'var $trava_nome { value = "azure_conexao" }', "trava_compartilhada_com_o_sincronizar"),
    ("sem_trava_ocupada_429", 'precondition ($trava_id != null) {\n      error_type = "toomanyrequests"', 'precondition ($trava_id != null) {\n      error_type = "standard"', "trava_ocupada_429"),
    ("trava_orfa_longa", "$idade_trava > 120000", "$idade_trava > 9000000", "trava_orfa_curta"),
    ("trava_nao_liberada", 'if ($trava_id != null) {\n            db.del travas {', 'if ($trava_id == 0) {\n            db.del travas {', "trava_liberada_no_finally"),
    ("falha_sem_erro_generico", "catch {\n        var.update $falha { value = true }", "catch {\n        var.update $falha { value = false }", "falha_inesperada_vira_erro_generico"),
    ("erro_generico_antes_de_liberar", 'precondition ($falha == false) {', 'precondition ($falha == false || true) {', "erro_generico_apos_liberar_trava"),
    ("sem_invalidar_a_leitura", 'where = $db.provedor_externo_leitura.provedor == "azure"', 'where = $db.provedor_externo_leitura.provedor == "x"', "invalida_a_leitura_guardada"),
    ("invalida_depois_de_gravar", "db.del provedor_externo_leitura {", "db.edit provedor_externo_leitura {", "invalida_a_leitura_guardada"),
    # resposta e segredos
    ("resposta_com_eco", "value = {conectado: true}", "value = {conectado: true, tenant: $tenant}", "resposta_exata_conectado_true"),
    ("resposta_com_segredo_cifrado", "value = {conectado: true}", "value = {conectado: true, x: $segredo_cifrado}", "resposta_exata_conectado_true"),
    ("resposta_false", "value = {conectado: true}", "value = {conectado: false}", "resposta_exata_conectado_true"),
    ("segredo_em_function_run", "var $tenant_ok {", "function.run \"costguard/x\" {\n      input = {segredo: $segredo}\n    } as $y\n    var $tenant_ok {", "sem_function_run_com_segredo_como_input"),
    # --- apelido e tenant_final (item 10) ---
    ("apelido_sem_limpar_texto_linha", 'function.run "costguard/limpar_texto_linha" {\n      input = {texto: ($input.apelido ?? "")}\n    } as $apelido',
     'var $apelido { value = (($input.apelido ?? "")|trim) }', "apelido_passa_por_limpar_texto_linha"),
    ("apelido_limite_61", "($apelido|strlen) <= 60", "($apelido|strlen) <= 61", "apelido_limite_60_medido_no_texto_limpo"),
    ("apelido_limite_59", "($apelido|strlen) <= 60", "($apelido|strlen) <= 59", "apelido_limite_60_medido_no_texto_limpo"),
    ("apelido_medido_antes_da_limpeza", "var $apelido_ok { value = (($apelido|strlen) <= 60) }", 'var $apelido_ok { value = ((($input.apelido ?? "")|strlen) <= 60) }', "apelido_limite_60_medido_no_texto_limpo"),
    ("apelido_medido_antes_da_limpeza_na_regra_de_remedicao", "var $apelido_ok { value = (($apelido|strlen) <= 60) }", 'var $apelido_ok { value = ((($input.apelido ?? "")|strlen) <= 60) }', "apelido_nunca_truncado_nem_remedido"),
    ("apelido_truncado_em_vez_de_rejeitado", "var $apelido_ok { value = (($apelido|strlen) <= 60) }", "var.update $apelido { value = $apelido|substr:0:60 }\n    var $apelido_ok { value = true }", "apelido_nunca_truncado_nem_remedido"),
    ("apelido_truncado_em_vez_de_rejeitado_na_regra_do_limite", "var $apelido_ok { value = (($apelido|strlen) <= 60) }", "var.update $apelido { value = $apelido|substr:0:60 }\n    var $apelido_ok { value = true }", "apelido_limite_60_medido_no_texto_limpo"),
    ("apelido_retrim_depois_da_limpeza", "var $apelido_ok { value = (($apelido|strlen) <= 60) }", "var.update $apelido { value = ($apelido|trim) }\n    var $apelido_ok { value = (($apelido|strlen) <= 60) }", "apelido_nunca_truncado_nem_remedido"),
    ("apelido_sem_precondicao", "precondition ($apelido_ok == true) {", "precondition ($apelido_ok == false) {", "apelido_400_generico"),
    ("apelido_vira_500", f'error_type = "inputerror"\n      error = "{MSG_APELIDO}"', f'error_type = "standard"\n      error = "{MSG_APELIDO}"', "apelido_400_generico"),
    ("apelido_ecoado_na_mensagem", f'error = "{MSG_APELIDO}"', 'error = "Apelido inválido: " ~ $apelido', "apelido_400_generico"),
    ("apelido_ecoado_na_mensagem_regra_de_mensagens", f'error = "{MSG_APELIDO}"', 'error = "Apelido inválido: " ~ $apelido', "mensagens_sem_eco_de_valor"),
    ("apelido_ecoado_na_mensagem_regra_de_entrada", f'error = "{MSG_APELIDO}"', 'error = "Apelido inválido: " ~ $apelido', "erro_nao_cita_entrada_nem_resposta_do_azure"),
    ("apelido_ecoado_na_resposta", "value = {conectado: true}", "value = {conectado: true, apelido: $apelido}", "resposta_exata_conectado_true"),
    ("apelido_gravado_cifrado", "apelido                : $apelido\n", "apelido                : $apelido|jwe_encode" + JWE + "\n", "apelido_e_tenant_final_nao_sao_cifrados"),
    ("apelido_gravado_cifrado_na_regra_dos_quatro", "apelido                : $apelido\n", "apelido                : $apelido|jwe_encode" + JWE + "\n", "cifra_os_quatro_campos_com_prov_enc_key"),
    ("apelido_bruto_gravado", "apelido                : $apelido\n", 'apelido                : $input.apelido\n', "apelido_e_tenant_final_gravados_em_texto_simples"),
    ("edit_sem_apelido_mantem_o_anterior", "                    subscription_id_cifrado: $assinatura_cifrada\n                    apelido                : $apelido\n                    tenant_final           : $tenant_final\n                    atualizado_em          : $agora_ms\n                    atualizado_por         : $solicitante_atual.id\n                  }\n                }\n              }\n            }",
     "                    subscription_id_cifrado: $assinatura_cifrada\n                    tenant_final           : $tenant_final\n                    atualizado_em          : $agora_ms\n                    atualizado_por         : $solicitante_atual.id\n                  }\n                }\n              }\n            }", "db_edit_so_campos_da_tabela"),
    ("tenant_final_com_5_caracteres", "($tenant|strlen) - 4 }", "($tenant|strlen) - 5 }", "tenant_final_ultimos_4_caracteres"),
    ("tenant_final_com_8_caracteres", "($tenant|strlen) - 4 }", "($tenant|strlen) - 8 }", "tenant_final_ultimos_4_caracteres"),
    ("tenant_final_do_inicio", "$tenant|substr:$tenant_corte }", "$tenant|substr:0:4 }", "tenant_final_ultimos_4_caracteres"),
    ("tenant_final_do_inicio_com_corte_zero", "var $tenant_corte { value = ($tenant|strlen) - 4 }", "var $tenant_corte { value = 0 }", "tenant_final_ultimos_4_caracteres"),
    ("tenant_final_e_o_tenant_inteiro_na_variavel", "var $tenant_final { value = $tenant|substr:$tenant_corte }", "var $tenant_final { value = $tenant }", "tenant_final_ultimos_4_caracteres"),
    ("tenant_final_inteiro_gravado_no_add", "tenant_final           : $tenant_final", "tenant_final           : $tenant", "apelido_e_tenant_final_gravados_em_texto_simples"),
    ("tenant_final_inteiro_gravado_no_add_regra_do_tenant", "tenant_final           : $tenant_final", "tenant_final           : $tenant", "tenant_inteiro_so_em_validacao_url_cifra_e_corte"),
    ("tenant_final_decifrado_gravado", "tenant_final           : $tenant_final", "tenant_final           : $tenant_cifrado", "apelido_e_tenant_final_gravados_em_texto_simples"),
    ("tenant_final_nao_calculado", "var $tenant_corte { value = ($tenant|strlen) - 4 }\n    var $tenant_final { value = $tenant|substr:$tenant_corte }\n", "", "tenant_final_ultimos_4_caracteres"),
    ("tenant_inteiro_na_resposta", "value = {conectado: true}", "value = {conectado: true, tenant_final: $tenant}", "resposta_exata_conectado_true"),
    ("tenant_inteiro_na_resposta_regra_do_tenant", "value = {conectado: true}", "value = {conectado: true, tenant_final: $tenant}", "tenant_inteiro_so_em_validacao_url_cifra_e_corte"),
    ("tenant_final_cifrado", "tenant_final           : $tenant_final", "tenant_final           : $tenant_final|jwe_encode" + JWE, "apelido_e_tenant_final_nao_sao_cifrados"),
    ("segredo_em_log", "var $tenant_ok {", "debug.log { value = $segredo }\n    var $tenant_ok {", "sem_log_nem_debug"),
    ("segredo_usado_em_outro_lugar", "var $tenant_ok {", "var $copia { value = $segredo }\n    var $tenant_ok {", "segredo_so_em_validacao_token_e_cifragem"),
    ("historico_inventado", "  api_group = \"app\"", "  api_group = \"app\"\n  history = false", "sem_atributo_de_historico_inventado"),
    ("le_variavel_azure", "var $tenant {", "var $x { value = $env.AZURE_TENANT_ID }\n    var $tenant {", "env_so_a_chave_de_cifragem"),
    ("dispara_sincronizacao", "var $resposta {", "db.add provedor_externo_leitura {\n      data = {provedor: \"azure\"}\n    }\n    var $resposta {", "nao_dispara_sincronizacao"),
    ("token_devolvido", "value = {conectado: true}", "value = {conectado: true, t: $t_token}", "token_nunca_e_guardado_nem_devolvido"),
]


@pytest.mark.parametrize("nome,antigo,novo,regra", MUTACOES_POST, ids=[m[0] for m in MUTACOES_POST])
def test_mutacao_do_post_e_detectada(nome, antigo, novo, regra):
    assert regra in problemas_post(_mutar(_codigo(POST), antigo, novo)), nome


_BLOCO_LIMPEZA_APELIDO = (
    'function.run "costguard/limpar_texto_linha" {\n      input = {texto: ($input.apelido ?? "")}\n    } as $apelido\n\n'
    '    var $apelido_ok { value = (($apelido|strlen) <= 60) }\n\n'
    '    precondition ($apelido_ok == true) {\n      error_type = "inputerror"\n      error = "' + MSG_APELIDO + '"\n    }\n')


def _mover_validacao_do_apelido(codigo: str, antes_de: str) -> str:
    """Mutação composta: tira a limpeza + validação do apelido da etapa de entradas e a recoloca ANTES de `antes_de`."""
    sem = _mutar(codigo, _BLOCO_LIMPEZA_APELIDO, "")
    return _mutar(sem, antes_de, _BLOCO_LIMPEZA_APELIDO + "    " + antes_de.lstrip())


MUTACOES_COMPOSTAS_POST = [
    # a validação do apelido só roda DEPOIS da chamada ao Azure (gastaria um token à toa) ou depois da trava
    ("apelido_validado_depois_da_chamada_ao_azure", lambda c: _mover_validacao_do_apelido(c, '    var $token_ok {'), "apelido_validado_antes_da_trava_e_do_azure"),
    ("apelido_validado_depois_da_trava", lambda c: _mover_validacao_do_apelido(c, '    var $t_status { value = 0 }'), "apelido_validado_antes_da_trava_e_do_azure"),
    ("apelido_validado_depois_de_gravar", lambda c: _mover_validacao_do_apelido(c, '    var $resposta {'), "apelido_validado_antes_da_trava_e_do_azure"),
    ("apelido_validado_na_etapa_errada", lambda c: _mover_validacao_do_apelido(c, '    precondition ($tenant_ok == true) {'), "apelido_validado_na_etapa_das_entradas"),
]


def test_mutacao_composta_sanidade_o_texto_original_cumpre_as_regras():
    assert problemas_post(_codigo(POST)) == []
    assert _BLOCO_LIMPEZA_APELIDO in _codigo(POST)


@pytest.mark.parametrize("nome,mutar,regra", MUTACOES_COMPOSTAS_POST, ids=[m[0] for m in MUTACOES_COMPOSTAS_POST])
def test_mutacao_composta_do_post_e_detectada(nome, mutar, regra):
    assert regra in problemas_post(mutar(_codigo(POST))), nome


# ---------------------------------------------------------------------------
# Regras: DELETE /azure/conexao
# ---------------------------------------------------------------------------

def problemas_delete(codigo: str) -> list[str]:
    r = _Regras()
    ex = r.exigir
    ex('query "azure/conexao" verb=DELETE' in codigo and 'api_group = "app"' in codigo and 'auth = "usuarios"' in codigo, "rota_delete_autenticada")
    ex(_bloco(codigo, "input {").strip() == "" and "$input" not in codigo, "sem_input")
    p_token = _precondicao_pos(codigo, "$usuario_logado != null", "unauthorized", '"Token inválido ou expirado"')
    p_admin = _precondicao_pos(
        codigo, '$usuario_logado.status == "ativo" && $usuario_logado.role == "admin"', "accessdenied", '"Acesso negado"')
    ex(p_token >= 0 and p_admin > p_token and p_admin < codigo.find("db.add travas"), "admin_ativo_exigido")
    ex(re.search(r'if \(\$solicitante_atual == null \|\| \$solicitante_atual\.status != "ativo" \|\| '
                 r'\$solicitante_atual\.role != "admin"\) \{\s*var\.update \$estado \{ value = "negado" \}', codigo), "admin_relido_na_trava")
    ex(_precondicao_pos(codigo, '$estado != "negado"', "accessdenied", '"Acesso negado"') > codigo.find("finally {"), "negado_vira_403_apos_liberar_trava")
    # idempotente: sem cadastro nada é apagado (nem a leitura guardada) e a resposta é a mesma
    ex(re.search(r'db\.get azure_conexao \{\s*field_name = "chave"\s*field_value = "azure"\s*\} as \$cadastro\s*conditional \{\s*if \(\$cadastro != null\) \{', codigo), "idempotente_sem_cadastro")
    apagar = _bloco_re(codigo, r"if \(\$cadastro != null\) \{")
    ex(apagar.count("db.del") == 2 and "db.del azure_conexao" in apagar and "db.del provedor_externo_leitura" in apagar, "apaga_cadastro_e_leitura_so_com_cadastro")
    ex(0 <= apagar.find("db.del provedor_externo_leitura") < apagar.find("db.del azure_conexao"), "apaga_a_leitura_antes_do_cadastro")
    ex(re.search(r'db\.query provedor_externo_leitura \{\s*where = \$db\.provedor_externo_leitura\.provedor == "azure"', apagar), "apaga_a_leitura_do_azure")
    ex(re.search(r"var \$resposta \{\s*value = \{conectado: false\}\s*\}", codigo) and "response = $resposta" in codigo and codigo.count("$resposta") == 2, "resposta_conectado_false")
    # nenhum segredo, nenhuma chamada externa, nenhuma variável de ambiente
    ex("api.request" not in codigo and "$env" not in codigo and "jwe_" not in codigo and "function.run" not in codigo, "sem_azure_sem_segredo")
    ex(not re.search(r"_cifrado|client_secret|tenant|segredo", codigo), "nao_le_o_cadastro_cifrado")
    ex(all("$" not in m for m in _mensagens_de_erro(codigo)), "mensagens_fixas")
    ex(not re.search(r"^\s*history\s*=", codigo, re.M), "sem_atributo_de_historico_inventado")
    for falta in _trava_ok(codigo):
        r.violadas.append(falta)
    ex(_precondicao_pos(codigo, "$falha == false", "standard", '"Não foi possível remover a conexão do Azure agora. Tente novamente em instantes."') > codigo.find("finally {"),
       "erro_generico_apos_liberar_trava")
    return r.violadas


def test_delete_cumpre_todas_as_regras():
    assert problemas_delete(_codigo(DELETE)) == []


MUTACOES_DELETE = [
    ("sem_admin", '$usuario_logado.status == "ativo" && $usuario_logado.role == "admin"', '$usuario_logado.status == "ativo"', "admin_ativo_exigido"),
    ("admin_relido_removido", 'if ($solicitante_atual == null || $solicitante_atual.status != "ativo" || $solicitante_atual.role != "admin") {',
     "if ($solicitante_atual == null) {", "admin_relido_na_trava"),
    ("input_de_corpo", "  input {\n  }", "  input {\n    text qualquer?\n  }", "sem_input"),
    ("apaga_sem_checar_o_cadastro", "if ($cadastro != null) {", "if (true) {", "idempotente_sem_cadastro"),
    ("apaga_cadastro_antes_da_leitura", "db.del azure_conexao {", "db.del provedor_externo_leitura {", "apaga_cadastro_e_leitura_so_com_cadastro"),
    ("nao_apaga_a_leitura", 'where = $db.provedor_externo_leitura.provedor == "azure"', 'where = $db.provedor_externo_leitura.provedor == "x"', "apaga_a_leitura_do_azure"),
    ("resposta_true", "value = {conectado: false}", "value = {conectado: true}", "resposta_conectado_false"),
    ("resposta_com_eco", "value = {conectado: false}", "value = {conectado: false, id: $cadastro.id}", "resposta_conectado_false"),
    ("chama_o_azure", "var $estado { value = \"\" }", "var $estado { value = \"\" }\n    api.request {\n      url = \"https://x.invalid\"\n    } as $r", "sem_azure_sem_segredo"),
    ("le_o_cadastro_cifrado", "var $estado { value = \"\" }", "var $estado { value = \"\" }\n    var $x { value = $cadastro.client_secret_cifrado }", "nao_le_o_cadastro_cifrado"),
    ("decifra", "var $estado { value = \"\" }", "var $estado { value = $y|jwe_decode:{}:$env.PROV_ENC_KEY:\"A256KW\":\"A256CBC-HS512\" }", "sem_azure_sem_segredo"),
    ("mensagem_com_eco", 'error = "Acesso negado"', 'error = "Acesso negado " ~ $usuario_logado.email', "mensagens_fixas"),
    ("trava_propria", 'var $trava_nome { value = "azure_custo_sincronizar" }', 'var $trava_nome { value = "azure_conexao" }', "trava_compartilhada_com_o_sincronizar"),
    ("trava_nao_liberada", 'if ($trava_id != null) {\n            db.del travas {', 'if ($trava_id == 0) {\n            db.del travas {', "trava_liberada_no_finally"),
    ("sem_trava_ocupada_429", 'precondition ($trava_id != null) {\n      error_type = "toomanyrequests"', 'precondition ($trava_id != null) {\n      error_type = "standard"', "trava_ocupada_429"),
    ("trava_orfa_longa", "$idade_trava > 120000", "$idade_trava > 9000000", "trava_orfa_curta"),
    ("negado_sem_403", 'precondition ($estado != "negado") {\n      error_type = "accessdenied"', 'precondition ($estado != "negado") {\n      error_type = "standard"', "negado_vira_403_apos_liberar_trava"),
    ("historico_inventado", "  api_group = \"app\"", "  api_group = \"app\"\n  history = false", "sem_atributo_de_historico_inventado"),
]


@pytest.mark.parametrize("nome,antigo,novo,regra", MUTACOES_DELETE, ids=[m[0] for m in MUTACOES_DELETE])
def test_mutacao_do_delete_e_detectada(nome, antigo, novo, regra):
    assert regra in problemas_delete(_mutar(_codigo(DELETE), antigo, novo)), nome


# ---------------------------------------------------------------------------
# Regras: ordem das credenciais e nenhum segredo devolvido por FUNÇÃO
# ---------------------------------------------------------------------------

def problemas_config_conexao(codigo: str) -> list[str]:
    r = _Regras()
    ex = r.exigir
    # banco primeiro; se o cadastro existe e não decifra => configuracao_invalida, SEM cair nas variáveis
    ex(re.search(r'db\.get azure_conexao \{\s*field_name = "chave"\s*field_value = "azure"\s*\} as \$cadastro', codigo), "le_o_cadastro_primeiro")
    ex(re.search(r'if \(\$cadastro != null\) \{\s*var\.update \$origem \{ value = "tela" \}', codigo), "cadastro_existente_e_origem_tela")
    tela = _bloco_re(codigo, r"if \(\$cadastro != null\) \{")
    # a funcao (a cada GET de qualquer autenticado) decifra SO o tenant: segredo, client_id e assinatura ficam cifrados
    ex(tela.count("|jwe_decode" + JWE) == 1 and "$cadastro.tenant_id_cifrado|jwe_decode" in tela and "$env.AZURE_" not in tela, "cadastro_decifrado_com_prov_enc_key_sem_variaveis")
    ex(not re.search(r"client_secret_cifrado|client_id_cifrado|subscription_id_cifrado", codigo), "funcao_nao_toca_no_segredo_client_nem_assinatura")
    ex(re.search(r"catch \{\s*var\.update \$decifrou \{ value = false \}\s*\}", tela), "falha_ao_decifrar_marca_decifrou_false")
    ex(re.search(r'if \(\$origem == "tela" && \$decifrou == false\) \{\s*var\.update \$estado \{ value = "configuracao_invalida" \}', codigo), "nao_decifra_vira_configuracao_invalida")
    # a primeira ramificação do estado é a do cadastro: nenhuma variável pode "salvar" um cadastro quebrado
    ex(codigo.find('$origem == "tela" && $decifrou == false') < codigo.find("$presentes == false && $origem == null"), "invalida_antes_de_nao_configurado")
    ex(re.search(r"\}\s*else \{\s*var\.update \$tenant \{ value = \(\(\$env\.AZURE_TENANT_ID", codigo) and codigo.count("$env.AZURE_TENANT_ID") == 1, "variaveis_so_no_else")
    # a função só devolve estado, origem e versão
    resultado = _bloco(codigo, "var $resultado {\n      value = {")
    ex(_chaves(resultado) == ["estado", "origem", "versao_api", "apelido", "tenant_final"], "devolve_so_estado_origem_e_versao")
    # apelido/tenant_final saem das colunas em texto simples do cadastro; nada decifrado nem derivado do tenant/variável
    ex(re.search(r"apelido\s*: \$apelido_exibido\s+tenant_final: \$tenant_final\s*$", resultado)
       and re.search(r'if \(\(\$cadastro\.apelido \?\? ""\) != ""\) \{\s*var\.update \$apelido_exibido \{ value = \$cadastro\.apelido \}', tela)
       and re.search(r'if \(\(\$cadastro\.tenant_final \?\? ""\) != ""\) \{\s*var\.update \$tenant_final \{ value = \$cadastro\.tenant_final \}', tela),
       "apelido_e_tenant_final_so_colunas_guardadas")
    ex(not re.search(r"\$(tenant|client|segredo|assinatura|cadastro)\b", resultado), "nenhum_segredo_na_resposta_da_funcao")
    ex(codigo.count("response = $resultado") == 1 and "response = $tenant" not in codigo, "response_unica")
    ex("input {\n  }" in codigo, "funcao_sem_input")
    ex(not re.search(r"^\s*history\s*=", codigo, re.M), "sem_atributo_de_historico_inventado")
    return r.violadas


def test_config_cumpre_a_ordem_banco_variaveis():
    assert problemas_config_conexao(_codigo(CONFIG)) == []


MUTACOES_CONFIG = [
    ("variaveis_antes_do_banco", "if ($cadastro != null) {", "if ($cadastro == null) {", "cadastro_existente_e_origem_tela"),
    ("sem_origem_tela", 'var.update $origem { value = "tela" }', 'var.update $origem { value = "x" }', "cadastro_existente_e_origem_tela"),
    ("fallback_silencioso", "catch {\n            var.update $decifrou { value = false }",
     'catch {\n            var.update $tenant { value = (($env.AZURE_TENANT_ID ?? "")|trim) }', "cadastro_decifrado_com_prov_enc_key_sem_variaveis"),
    ("nao_decifra_ignorado", "catch {\n            var.update $decifrou { value = false }", "catch {\n            var.update $decifrou { value = true }", "falha_ao_decifrar_marca_decifrou_false"),
    ("nao_decifra_vira_ok", 'if ($origem == "tela" && $decifrou == false) {', 'if ($origem == "tela" && $decifrou == "x") {', "nao_decifra_vira_configuracao_invalida"),
    ("nao_decifra_vira_nao_configurado", 'if ($origem == "tela" && $decifrou == false) {\n        var.update $estado { value = "configuracao_invalida" }',
     'if ($origem == "tela" && $decifrou == false) {\n        var.update $estado { value = "nao_configurado" }', "nao_decifra_vira_configuracao_invalida"),
    ("tenant_decifrado_com_variavel", '(($cadastro.tenant_id_cifrado|jwe_decode:{}:$env.PROV_ENC_KEY:"A256KW":"A256CBC-HS512")|trim)', '(($env.AZURE_TENANT_ID ?? "")|trim)',
     "cadastro_decifrado_com_prov_enc_key_sem_variaveis"),
    ("chave_errada", '$cadastro.tenant_id_cifrado|jwe_decode:{}:$env.PROV_ENC_KEY', '$cadastro.tenant_id_cifrado|jwe_decode:{}:$env.AZURE_CLIENT_ID', "cadastro_decifrado_com_prov_enc_key_sem_variaveis"),
    ("decifra_o_segredo_na_funcao", "var.update $tenant { value = (($cadastro.tenant_id_cifrado|jwe_decode:{}:$env.PROV_ENC_KEY:\"A256KW\":\"A256CBC-HS512\")|trim) }",
     "var.update $tenant { value = (($cadastro.tenant_id_cifrado|jwe_decode:{}:$env.PROV_ENC_KEY:\"A256KW\":\"A256CBC-HS512\")|trim) }\n"
     "            var.update $segredo { value = (($cadastro.client_secret_cifrado|jwe_decode:{}:$env.PROV_ENC_KEY:\"A256KW\":\"A256CBC-HS512\")|trim) }",
     "funcao_nao_toca_no_segredo_client_nem_assinatura"),
    ("decifra_o_client_id_na_funcao", "var.update $tenant { value = (($cadastro.tenant_id_cifrado|jwe_decode:{}:$env.PROV_ENC_KEY:\"A256KW\":\"A256CBC-HS512\")|trim) }",
     "var.update $tenant { value = (($cadastro.tenant_id_cifrado|jwe_decode:{}:$env.PROV_ENC_KEY:\"A256KW\":\"A256CBC-HS512\")|trim) }\n"
     "            var.update $client { value = (($cadastro.client_id_cifrado|jwe_decode:{}:$env.PROV_ENC_KEY:\"A256KW\":\"A256CBC-HS512\")|trim) }",
     "funcao_nao_toca_no_segredo_client_nem_assinatura"),
    ("decifra_a_assinatura_na_funcao", "var.update $tenant { value = (($cadastro.tenant_id_cifrado|jwe_decode:{}:$env.PROV_ENC_KEY:\"A256KW\":\"A256CBC-HS512\")|trim) }",
     "var.update $tenant { value = (($cadastro.tenant_id_cifrado|jwe_decode:{}:$env.PROV_ENC_KEY:\"A256KW\":\"A256CBC-HS512\")|trim) }\n"
     "            var.update $assinatura { value = (($cadastro.subscription_id_cifrado|jwe_decode:{}:$env.PROV_ENC_KEY:\"A256KW\":\"A256CBC-HS512\")|trim) }",
     "funcao_nao_toca_no_segredo_client_nem_assinatura"),
    ("devolve_o_segredo", "origem      : $origem\n        versao_api", "origem      : $origem\n        segredo     : $segredo\n        versao_api", "devolve_so_estado_origem_e_versao"),
    ("devolve_o_segredo_na_regra_de_segredo", "versao_api  : ($estado == \"ok\") ? $versao_api : \"\"", "versao_api  : $segredo", "nenhum_segredo_na_resposta_da_funcao"),
    ("devolve_o_cadastro_cifrado", "origem      : $origem\n        versao_api", "origem      : $cadastro\n        versao_api", "nenhum_segredo_na_resposta_da_funcao"),
    ("tenant_final_e_o_tenant_inteiro", "tenant_final: $tenant_final", "tenant_final: $tenant", "nenhum_segredo_na_resposta_da_funcao"),
    ("tenant_final_e_o_tenant_inteiro_regra_de_colunas", "tenant_final: $tenant_final", "tenant_final: $tenant", "apelido_e_tenant_final_so_colunas_guardadas"),
    ("tenant_final_decifrado", "value = $cadastro.tenant_final }", 'value = ($cadastro.tenant_id_cifrado|jwe_decode:{}:$env.PROV_ENC_KEY:"A256KW":"A256CBC-HS512") }', "apelido_e_tenant_final_so_colunas_guardadas"),
    ("apelido_decifrado", "value = $cadastro.apelido }", 'value = ($cadastro.client_id_cifrado|jwe_decode:{}:$env.PROV_ENC_KEY:"A256KW":"A256CBC-HS512") }', "apelido_e_tenant_final_so_colunas_guardadas"),
    ("response_devolve_o_segredo", "response = $resultado", "response = $segredo", "response_unica"),
    ("input_com_segredo", "input {\n  }", "input {\n    text segredo?\n  }", "funcao_sem_input"),
    ("historico_inventado", "  response = $resultado", "  response = $resultado\n  history = false", "sem_atributo_de_historico_inventado"),
    ("variaveis_em_dois_lugares", "var $versao_api {", 'var $x { value = (($env.AZURE_TENANT_ID ?? "")|trim) }\n    var $versao_api {', "variaveis_so_no_else"),
]


@pytest.mark.parametrize("nome,antigo,novo,regra", MUTACOES_CONFIG, ids=[m[0] for m in MUTACOES_CONFIG])
def test_mutacao_da_config_e_detectada(nome, antigo, novo, regra):
    assert regra in problemas_config_conexao(_mutar(_codigo(CONFIG), antigo, novo)), nome


def test_so_a_funcao_de_configuracao_toca_o_cadastro_e_nenhuma_funcao_devolve_segredo():
    """Nenhum segredo (decifrado ou cifrado) é resposta de FUNÇÃO: o histórico do Xano guarda a resposta de funções."""
    for arquivo in sorted(FUNCOES.glob("*.xs")):
        codigo = _codigo(arquivo)
        if arquivo != CONFIG:
            assert "azure_conexao" not in codigo, f"{arquivo.name} lê o cadastro cifrado do Azure"
        if arquivo not in (CONFIG, FUNCOES / "sincronizar_inventario.xs"):
            assert "jwe_decode" not in codigo and "jwe_encode" not in codigo, f"{arquivo.name} decifra/cifra"
    # as funções do Azure: nenhum campo cifrado/decifrado e nenhum $c_/$segredo em `response`
    for arquivo in (CONFIG, ESTADO):
        codigo = _codigo(arquivo)
        resposta = re.search(r"response = (\$\w+)", codigo).group(1)
        corpo = _bloco(codigo, f"var {resposta} {{\n      value = {{")
        assert not re.search(r"cifrad|segredo|secret|\$tenant\b|\$client|\$assinatura|\$cadastro|token", corpo, re.I), arquivo.name


def test_o_sincronizar_decifra_dentro_do_endpoint_e_nao_passa_segredo_a_funcoes():
    codigo = _codigo(SINCRONIZAR)
    assert codigo.count("|jwe_decode" + JWE) == 4
    chamadas = re.findall(r'function\.run "([^"]+)" \{\s*input = (\{[^}]*\})', codigo)
    assert chamadas == [("costguard/azure_config_estado", "{}"), ("costguard/azure_custo_estado", "{}")]


# ---------------------------------------------------------------------------
# Todos os arquivos: nenhum segredo/ID real, nenhuma mensagem com eco, nenhum atributo inventado
# ---------------------------------------------------------------------------

def test_mensagens_de_erro_dos_endpoints_e_funcoes_do_azure_nunca_ecoam_valores():
    for arquivo in (POST, DELETE, SINCRONIZAR):
        for m in _mensagens_de_erro(_codigo(arquivo)):
            assert "$" not in m or m in ("$msg_limite",), f"{arquivo.name}: {m}"
        # $msg_limite só leva os segundos
        for corpo in re.findall(r"var \$msg_limite \{\s*value = ([^\n]+)", _codigo(arquivo)):
            assert re.findall(r"\$\w+", corpo) == ["$segundos_restantes"], arquivo.name


def test_catch_dos_endpoints_nao_ecoa_nada():
    """O `catch` só marca uma variável (nada de mensagem, input ou resposta do Azure)."""
    for arquivo in (POST, DELETE, SINCRONIZAR):
        for corpo in re.findall(r"catch \{([^{}]*)\}", _codigo(arquivo)):
            assert not re.search(r"\$input|\$resp_|\$c_|\$segredo|\$tenant|\$cadastro|\.message|\.error", corpo), arquivo.name


def test_arquivos_novos_nao_trazem_guid_real_nem_segredo_literal():
    guid = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
    alvos = list(ARQUIVOS_CONEXAO) + sorted(FIXTURES.glob("conexao_azure_*.json")) + sorted(FIXTURES.glob("azure_conexao_*.json"))
    for arquivo in alvos:
        texto = _ler(arquivo)
        for g in guid.findall(texto):
            assert set(g.replace("-", "")) == {"0"}, f"{arquivo.name}: GUID não genérico"
        assert not re.search(r"eyJ[A-Za-z0-9_-]{10,}", texto), f"{arquivo.name}: parece JWT"
        assert not re.search(r"\b[A-Za-z0-9~._-]{3}[0-9]Q~[A-Za-z0-9~._-]{20,}", texto), f"{arquivo.name}: parece client secret do Azure"
        assert not re.search(r"client_secret\s*[:=]\s*\"[^\"$]", _codigo(arquivo) if arquivo.suffix == ".xs" else "", re.I), f"{arquivo.name}: segredo literal"


def test_nenhum_outro_xs_conhece_a_conexao_do_azure():
    permitidos = set(ARQUIVOS_CONEXAO) | {FUNCOES / "azure_custo_estado.xs", APP / "azure_custo_GET.xs"}
    for arquivo in XANO.rglob("*.xs"):
        if arquivo in permitidos:
            continue
        codigo = _codigo(arquivo)
        for proibido in ("azure_conexao", "azure/conexao", "tenant_id_cifrado", "client_secret_cifrado"):
            assert proibido not in codigo, f"{arquivo.relative_to(XANO)} usa `{proibido}`"


def test_ciclo_automatico_e_painel_nao_usam_o_cadastro():
    for nome in ("sincronizacao_automatica_POST.xs", "painel_GET.xs", "painel_projeto_GET.xs", "projetos_resumo_consumo_mtd_GET.xs"):
        assert "azure" not in _codigo(APP / nome).lower(), nome


# ---------------------------------------------------------------------------
# ESPELHO em Python da validação (regex extraídas do .xs) com as fixtures fictícias
# ---------------------------------------------------------------------------

def _fixture(nome: str):
    return json.loads(_ler(FIXTURES / nome))


def _guid_valido(texto: str) -> bool:
    """Espelho: trim, tamanho 36 e regex da função de configuração (o `$` do Python também aceita \\n final, daí o tamanho)."""
    t = texto.strip()
    return len(t) == 36 and re.search(_regex_guid_da_config()[1:-1], t) is not None


def _segredo_valido(texto: str) -> bool:
    t = texto.strip()
    return 8 <= len(t) <= 256 and re.search(r"^[!-~]+$", t) is not None


def limpar_texto_linha(texto: str | None) -> str:
    """Espelho de costguard/limpar_texto_linha: CR/LF/tab viram espaço, trim, corte em 120."""
    limpo = (texto or "").replace("\r", " ").replace("\n", " ").replace("\t", " ")
    return limpo.strip()[:120]


def apelido_para_gravar(texto: str | None) -> str | None:
    """Espelho do POST: texto limpo SEM novo trim; > 60 caracteres => None (400), nunca truncado. Vazio => "" (sem apelido)."""
    limpo = limpar_texto_linha((texto or "").strip())
    return limpo if len(limpo) <= 60 else None


def tenant_final_para_gravar(tenant: str) -> str:
    """Espelho do POST: os 4 últimos caracteres do tenant já validado (36)."""
    t = tenant.strip()
    assert len(t) == 36
    return t[len(t) - 4:]


def test_espelho_entrada_ficticia_valida():
    d = _fixture("conexao_azure_entrada_ficticia.json")
    assert sorted(d) == ["apelido", "client_id", "client_secret", "subscription_id", "tenant_id"]
    assert apelido_para_gravar(d["apelido"]) == d["apelido"]
    for campo in ("tenant_id", "client_id", "subscription_id"):
        assert d[campo] == "00000000-0000-0000-0000-000000000000" and _guid_valido(d[campo])
    assert "FICTICIO" in d["client_secret"] and _segredo_valido(d["client_secret"])
    assert _guid_valido("  " + d["tenant_id"] + "  ")  # trim


@pytest.mark.parametrize("valor", _fixture("conexao_azure_entradas_invalidas.json")["tenant_id"])
def test_espelho_guid_invalido_e_recusado(valor):
    assert not _guid_valido(valor)


@pytest.mark.parametrize("valor", _fixture("conexao_azure_entradas_invalidas.json")["client_secret"])
def test_espelho_segredo_invalido_e_recusado(valor):
    assert not _segredo_valido(valor)


def test_post_e_config_usam_exatamente_as_mesmas_regras_de_formato():
    """O cadastro salvo pelo POST nunca pode virar `configuracao_invalida` na função de configuração."""
    post, config = _codigo(POST), _codigo(CONFIG)
    for nome in ("tenant", "client", "assinatura"):
        a = re.search(r"var \$" + nome + r"_ok \{ value = .*", post).group(0)
        b = re.search(r"var \$" + nome + r"_ok \{ value = .*", config).group(0)
        assert a == b, nome
    assert re.search(r"var \$segredo_ok \{ value = .*", post).group(0) == re.search(r"var \$segredo_ok \{ value = .*", config).group(0)


def test_sincronizar_revalida_o_formato_com_as_mesmas_regras_do_post():
    """Depois de decifrar DENTRO do endpoint, o sincronizar confere GUIDs e segredo com a regra do POST (so os nomes das variaveis mudam)."""
    post, sinc = _codigo(POST), _codigo(SINCRONIZAR)
    for nome in ("tenant", "client", "assinatura", "segredo"):
        a = re.search(r"var \$" + nome + r"_ok \{ value = (.*) \}$", post, re.M).group(1)
        b = re.search(r"var \$c_" + nome + r"_ok \{ value = (.*) \}$", sinc, re.M).group(1)
        assert a.replace("$" + nome, "$c_" + nome) == b, nome


def test_pedido_de_token_e_calculo_do_429_do_post_sao_os_do_sincronizar():
    post, sinc = _codigo(POST), _codigo(SINCRONIZAR)
    for trecho in (r"params = \{client_id: [^\n]+", r"timeout = 10", r'"Content-Type: application/x-www-form-urlencoded"',
                   r'"User-Agent: costguard-xano/1.0"', r"var \$token_ok \{ value = [^\n]+"):
        a = re.search(trecho, post).group(0).replace("$client,", "$c_client,").replace("$segredo,", "$c_segredo,")
        b = re.search(trecho, sinc).group(0)
        assert a.replace("$client", "$c_client").replace("$segredo", "$c_segredo") == b.replace("$client", "$c_client").replace("$segredo", "$c_segredo"), trecho
    for trecho in (r'\(\$cab_nome\|contains:"retry-after"\)', r'"/\^\[0-9\]\{1,9\}\$/"', r"var\.update \$segundos_restantes \{ value = 60 \}",
                   r"\$segundos_restantes > 3600"):
        assert re.search(trecho, post) and re.search(trecho, sinc), trecho


def test_mensagens_das_fixtures_de_erro_sao_as_dos_xs():
    erros = _fixture("conexao_azure_erros.json")
    post = _codigo(POST)
    for campo in ("tenant_id", "client_id", "subscription_id", "client_secret"):
        assert f'error = "{erros["campo_invalido_" + campo]["message"]}"' in post
        assert erros["campo_invalido_" + campo]["http"] == 400
    assert f'error = "{erros["azure_recusou"]["message"]}"' in post and erros["azure_recusou"]["http"] == 400
    assert erros["trava"]["message"] in post and erros["falha_interna"]["message"] in post
    assert erros["azure_429"]["http"] == 429 and re.sub(r"\d+", "N", erros["azure_429"]["message"]) == "O Azure limitou as requisições. Aguarde N segundos para tentar de novo."
    assert erros["nao_admin"] == {"http": 403, "message": "Acesso negado"}
    assert erros["apelido_invalido"] == {"http": 400, "message": MSG_APELIDO} and f'error = "{MSG_APELIDO}"' in post
    assert "$" not in MSG_APELIDO
    for e in erros.values():
        assert "00000000" not in e["message"] and "SEGREDO" not in e["message"], "mensagem sem eco de valores"


_APELIDOS = _fixture("conexao_azure_apelidos.json")


@pytest.mark.parametrize("caso", _APELIDOS["validos"], ids=[c["nome"] for c in _APELIDOS["validos"]])
def test_espelho_apelido_valido_e_gravado_limpo(caso):
    assert apelido_para_gravar(caso["entrada"]) == caso["gravado"]
    assert len(caso["gravado"]) <= 60


@pytest.mark.parametrize("caso", _APELIDOS["invalidos"], ids=[c["nome"] for c in _APELIDOS["invalidos"]])
def test_espelho_apelido_acima_de_60_e_rejeitado_nunca_truncado(caso):
    assert apelido_para_gravar(caso["entrada"]) is None


def test_espelho_o_corte_de_120_da_limpeza_nunca_esconde_excesso():
    """Sem novo trim: 60 letras + espaços + 1 letra (mais de 120 no total) NÃO pode virar um apelido de 60 em silêncio."""
    caso = "x" * 10 + " " * 115 + "z"
    assert len(caso) > 120 and apelido_para_gravar(caso) is None
    # com re-trim depois da limpeza (a regra proibida) o texto seria aceito e truncado em silêncio
    assert limpar_texto_linha(caso).strip() == "x" * 10


def test_espelho_tenant_final_sao_os_quatro_ultimos_e_nunca_o_id_inteiro():
    sintetico = "01234567-89ab-cdef-0123-456789abcdef"  # sequência óbvia, não é ID real
    assert tenant_final_para_gravar(sintetico) == "cdef" and tenant_final_para_gravar("  " + sintetico + "\t") == "cdef"
    assert len(tenant_final_para_gravar(sintetico)) == 4 and tenant_final_para_gravar(sintetico) != sintetico[:4]
    gravado = _fixture("conexao_azure_gravacao_ficticia.json")
    entrada = _fixture("conexao_azure_entrada_ficticia.json")
    assert gravado == {"apelido": apelido_para_gravar(entrada["apelido"]), "tenant_final": tenant_final_para_gravar(entrada["tenant_id"])}
    assert all(entrada[c] not in json.dumps(gravado) for c in ("client_secret",)) and entrada["tenant_id"] not in json.dumps(gravado)


def test_respostas_das_fixtures_do_cadastro():
    assert _fixture("azure_conexao_post_ok.json") == {"conectado": True}
    assert _fixture("azure_conexao_delete_ok.json") == {"conectado": False}


# ---------------------------------------------------------------------------
# Contrato e guia de configuração
# ---------------------------------------------------------------------------

def test_contrato_azure_documenta_o_cadastro_pela_tela_e_o_fim_do_cache():
    texto = _ler_doc_interno(RAIZ / "docs" / "interno" / "CONTRATO_API_AZURE.md")
    for trecho in ("POST /azure/conexao", "DELETE /azure/conexao", '{"conectado": true}', '{"conectado": false}', "origem_credencial", '"tela"', '"servidor"',
                   "Dados de conexão inválidos", MSG_TOKEN, "NÃO valida o `subscription_id`", "sem_leitura", "idempotente", "PROV_ENC_KEY", "A256KW",
                   "Cooldown de 60 s", "Não há mais cache de 4 h", "cooldown", "histórico de requisições", "24 h", "NÃO VERIFICADO", "Branch Defaults",
                   "Disabled", "verb=DELETE", "configuracao_invalida", "desatualizado", "ordem das credenciais",
                   "apelido", "tenant_final", MSG_APELIDO, "limpar_texto_linha", "últimos 4 caracteres", "NÃO é mantido"):
        assert trecho in texto, f"o contrato do Azure não menciona: {trecho}"
    # o contrato antigo (cache de 4 h e origem "cache") não pode ficar como vigente
    assert '`"cache"` (usou o estado guardado, sem chamar o Azure: cache de 4 h' not in texto
    assert "devolve o estado guardado com `origem: \"cache\"`" not in texto


def test_contrato_azure_historico_do_xano_cobre_get_funcoes_authorization_e_precedente_aws():
    texto = _ler_doc_interno(RAIZ / "docs" / "interno" / "CONTRATO_API_AZURE.md")
    historico = texto.split("## 7. O que o Xano registra")[1].split("## 8. Estados de carregamento")[0]
    for trecho in ("BRANCH INTEIRA", "Branch Defaults", "Disabled", "GET /azure/custo", "azure_config_estado", "azure_custo_estado", "POST /azure/conexao/remover",
                   "POST /azure/custo/sincronizar", "DELETE /azure/conexao", "Authorization", "JWT do admin", "aws_secret_access_key", "criar_provedor_POST",
                   "editar_provedor_PATCH", "24 h", "NÃO envie o client secret real", "exposto", "gire o client secret"):
        assert trecho in historico, f"a seção do histórico não menciona: {trecho}"
    # a afirmação antiga ("o GET não tem segredo / só o estado já exibido") não pode voltar
    assert "só o estado já exibido (sem segredo)" not in texto
    assert "Nenhum segredo é entrada nem resposta" not in texto


def test_contrato_azure_inativo_recebe_403_nos_endpoints_admin():
    texto = _ler_doc_interno(RAIZ / "docs" / "interno" / "CONTRATO_API_AZURE.md")
    assert "admin inativo" in texto and "INATIVO" in texto
    assert "usuário removido/desativado (também relido com a trava)" not in texto
    assert "admin relido com a trava (401/403)" not in texto
    # o código dos endpoints: a 1ª checagem só testa `usuario != null` (401); admin ativo é checado a seguir (403)
    for arquivo in (POST, DELETE, SINCRONIZAR):
        codigo = _codigo(arquivo)
        assert re.search(r'precondition \(\$usuario_logado != null\) \{\s*error_type = "unauthorized"', codigo), arquivo.name
        assert re.search(r'precondition \(\$usuario_logado\.status == "ativo" && \$usuario_logado\.role == "admin"\) \{\s*error_type = "accessdenied"', codigo), arquivo.name


def test_contrato_azure_riscos_aceitos_e_ordem_de_publicacao():
    texto = _ler_doc_interno(RAIZ / "docs" / "interno" / "CONTRATO_API_AZURE.md")
    riscos = texto.split("## 12. Riscos aceitos")[1]
    for trecho in ("zera o cooldown e o bloqueio de 429", "contornar o cooldown de 60 s", "throttle próprio", "1 chamada de token por clique", "não é um oráculo",
                   "depois da chamada de token", "falha tarde", "TEXTO PURO", "rx.html", "largura limitada", "qualquer perfil autenticado", "Decisão do usuário"):
        assert trecho in riscos, f"os riscos aceitos não mencionam: {trecho}"
    ordem = texto.split("## 10. Publicação e estado intermediário")[1].split("## 11. PROVADO")[0]
    posicoes = [ordem.index(x) for x in ("`xano/table/azure_conexao.xs`", "azure_config_estado.xs` e `azure_custo_estado.xs`", "`xano/api/app/azure_custo_sincronizar_POST.xs`",
                                         "`xano/api/app/azure_conexao_POST.xs`", "`azure_conexao_DELETE.xs`")]
    assert posicoes == sorted(posicoes), "ordem de publicação: tabela, funções, sincronizar, cadastro (POST e depois DELETE)"
    for trecho in ("NÃO republicar", "azure_custo_GET.xs", "provedor_externo_leitura.xs", "e-mails do DevOps", "Plano B", "POST /azure/conexao/remover"):
        assert trecho in ordem, f"a ordem de publicação não menciona: {trecho}"
    assert "Não cadastre a conexão pela tela antes do passo 4" not in texto  # a ordem antiga (cadastro no passo 3) saiu


def test_guia_de_configuracao_historico_e_ordem_de_publicacao():
    texto = _ler_doc_interno(RAIZ / "docs" / "interno" / "AZURE_CONFIGURACAO.md")
    for trecho in ("Branch Defaults", "Disabled", "GET /azure/custo", "azure_config_estado", "Authorization", "aws_secret_access_key", "POST /azure/conexao/remover",
                   "Não envie o client secret real", "exposto", "Ordem de publicação", "por último", "não** são republicados"):
        assert trecho in texto, f"o guia não menciona: {trecho}"
    assert "(seção 8)" not in texto  # o passo de girar o secret é a seção 9


def test_textos_de_erro_do_azure_nao_dizem_credenciais_configuradas_no_servidor():
    """`sem_permissao` e demais estados valem para as duas origens: o texto e neutro (a UI usa `origem` para orientar)."""
    for arquivo in ARQUIVOS_CONEXAO + (APP / "azure_custo_GET.xs",):
        assert "configuradas no servidor" not in _ler(arquivo), arquivo.name
    assert 'var.update $erro_texto { value = "O Azure recusou as credenciais." }' in _codigo(SINCRONIZAR)


def test_guia_de_configuracao_descreve_o_fluxo_pela_tela_sem_ids_reais():
    texto = _ler_doc_interno(RAIZ / "docs" / "interno" / "AZURE_CONFIGURACAO.md")
    for trecho in ("pela tela", "reserva", "PROV_ENC_KEY", "histórico", "Disabled", "NÃO VERIFICADO", "client secret", "apelido", "4 últimos"):
        assert trecho in texto, f"o guia não menciona: {trecho}"
    guid = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
    for g in guid.findall(texto):
        assert set(g.replace("-", "")) == {"0"}, "o guia não pode trazer ID real"
    assert "cache de 4" not in texto.lower().replace("sem cache de 4", "").replace("não há mais cache de 4", "")

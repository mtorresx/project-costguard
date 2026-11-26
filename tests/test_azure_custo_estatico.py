"""Custo do Azure (somente leitura, custo NÃO ALOCADO): verificações estáticas, sem rede.

Mesmo padrão de `test_notificar_devops_estatico.py`: leem os `.xs` locais como TEXTO e
conferem, com expressões regulares ancoradas, as regras do contrato. Cada conjunto de
regras é uma função `problemas_*` que devolve a lista de regras VIOLADAS; o arquivo real
precisa devolver lista vazia e cada MUTAÇÃO (alteração deliberada do texto) precisa
violar a regra correspondente. Assim o teste prova que pega regressões, e não só que
passa.

Há também um ESPELHO em Python da leitura da resposta do Azure (colunas por nome, linhas,
nextLink, cabeçalhos do 429), da validação de GUID, do cooldown de 60 s (SEM cache de 4 h),
da gravação do desfecho e do estado devolvido pelo GET. Os parâmetros do espelho (nomes de
coluna, teto de 3600 s, padrão de 60 s, cooldown, regex do GUID) são EXTRAÍDOS do
`.xs`, e os dados vêm das fixtures `tests/fixtures/xano/azure_*.json` (genéricas, GUIDs
zerados, sem valores reais). O cadastro da conexão pela tela (tabela, POST, DELETE) e a ordem
banco -> variáveis ficam em `test_azure_conexao_estatico.py`.

O que estes testes NÃO provam:
  - nada sobre o comportamento do Xano PUBLICADO: `api.request` com corpo
    form-urlencoded, leitura de `response.headers` (formato de lista de textos é só a
    suposição), `$env`, `get` por índice numérico, `json_decode`, `starts_with`,
    `regex_matches` com `$`, `format_timestamp` em UTC, `precondition`/`db.add` dentro de
    `conditional`/`finally` — NÃO VERIFICADO;
  - nada sobre o Azure real além do que o usuário PROVOU por fora destes testes (Insomnia):
    api-version 2023-11-01, corpo ActualCost com agregação sobre `Cost`, colunas `Cost` e
    `Currency`, HTTP 200 com rows vazia (e sem moeda) num mês sem consumo, e os cabeçalhos
    do 429. Continuam NÃO VERIFICADOS o papel RBAC em outras assinaturas, o 204, as cotas, o
    fechamento do mês em UTC e a gratuidade da Query API;
  - o espelho em Python usa `re`/`int` do Python, que podem diferir do Xano.
Nenhum teste chama o Azure, o Xano ou qualquer rede.
"""

import json
import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
XANO = RAIZ / "xano"
APP = XANO / "api" / "app"
FUNCOES = XANO / "function" / "costguard"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "xano"

SINCRONIZAR = APP / "azure_custo_sincronizar_POST.xs"
OBTER = APP / "azure_custo_GET.xs"
CONFIG = FUNCOES / "azure_config_estado.xs"
ESTADO = FUNCOES / "azure_custo_estado.xs"
TABELA = XANO / "table" / "provedor_externo_leitura.xs"
# Cadastro da conexão pela tela: tabela, POST e DELETE.
TABELA_CONEXAO = XANO / "table" / "azure_conexao.xs"
CONEXAO_POST = APP / "azure_conexao_POST.xs"
CONEXAO_DELETE = APP / "azure_conexao_DELETE.xs"
ARQUIVOS_AZURE = (SINCRONIZAR, OBTER, CONFIG, ESTADO, TABELA, TABELA_CONEXAO, CONEXAO_POST, CONEXAO_DELETE)

GUID_ZERO = "00000000-0000-0000-0000-000000000000"
REGEX_GUID = '("/^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/"'
# Texto FIXO do cadastro da tela quebrado: gravado pelo sincronizar (status "indisponivel") e reconhecido por azure_custo_estado.
MSG_CADASTRO_QUEBRADO = "O cadastro do Azure guardado no servidor não pôde ser lido. Cadastre a conexão novamente."

# Corpo da consulta usado nos testes REAIS do usuário (HTTP 200): o código tem de enviar este texto,
# idêntico (type ActualCost, agregação Sum sobre a coluna `Cost`), e a api-version abaixo.
CORPO_CONSULTA_TESTADO = ('{"type":"ActualCost","timeframe":"MonthToDate","dataset":{"granularity":"None",'
                          '"aggregation":{"totalCost":{"name":"Cost","function":"Sum"}}}}')
API_VERSION_TESTADA = "2023-11-01"


# ---------------------------------------------------------------------------
# Utilitários
# ---------------------------------------------------------------------------

def _ler(caminho: Path) -> str:
    return caminho.read_text(encoding="utf-8")


def _sem_comentarios(texto: str) -> str:
    return "\n".join(l for l in texto.splitlines() if not l.strip().startswith("//"))


def _codigo(caminho: Path) -> str:
    return _sem_comentarios(_ler(caminho))


def _fim_do_bloco(texto: str, inicio: int) -> int:
    """Índice logo após a `}` que fecha o bloco cuja `{` de abertura está ANTES de `inicio`."""
    nivel, i = 1, inicio
    while nivel:
        if texto[i] == "{":
            nivel += 1
        elif texto[i] == "}":
            nivel -= 1
        i += 1
    return i


def _bloco(texto: str, abertura: str) -> str:
    """Conteúdo do bloco `{...}` que começa em `abertura` (literal terminado em `{`)."""
    inicio = texto.index(abertura) + len(abertura)
    return texto[inicio:_fim_do_bloco(texto, inicio) - 1]


def _bloco_re(texto: str, padrao: str) -> str:
    m = re.search(padrao, texto)
    assert m, f"trecho não encontrado: {padrao}"
    return texto[m.end():_fim_do_bloco(texto, m.end()) - 1]


def _bloco_re_seguro(texto: str, padrao: str) -> str:
    """Como `_bloco_re`, mas devolve "" se o trecho sumiu (a regra que depende dele falha, sem abortar o teste)."""
    try:
        return _bloco_re(texto, padrao)
    except (AssertionError, IndexError):
        return ""


def _blocos_foreach(codigo: str) -> list[str]:
    return [codigo[m.end():_fim_do_bloco(codigo, m.end()) - 1] for m in re.finditer(r"foreach \([^\n]*\) \{", codigo)]


def _chaves_do_objeto(texto: str) -> list[str]:
    return re.findall(r"^\s*(\w+)\s*:", texto, re.M)


def _mutar(texto: str, antigo: str, novo: str) -> str:
    """Troca `antigo` por `novo` e exige que `antigo` exista (mutação não pode ser vazia)."""
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


# ---------------------------------------------------------------------------
# Regras: POST de sincronização
# ---------------------------------------------------------------------------

CHAVES_RESPOSTA = ["provedor", "configurado", "status", "nao_alocado", "custo_mes_total", "moeda", "atualizado_em",
                   "mes_referencia", "erro_resumo", "proxima_leitura_em"]
# GET: + `origem` ("tela" | "servidor" | null: de onde vêm as credenciais), + `apelido` (o guardado
# no cadastro da tela ou o padrão "Azure") e `tenant_final` (4 últimos do tenant da tela ou null).
CHAVES_GET = CHAVES_RESPOSTA + ["origem", "apelido", "tenant_final"]
# POST de sincronização: + `origem` (como foi a resposta: "azure" | "cooldown" | null) e
# `origem_credencial` (a `origem` do GET, renomeada para não colidir).
CHAVES_POST = CHAVES_RESPOSTA + ["origem", "origem_credencial"]
ENV_PERMITIDAS = {"AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET", "AZURE_SUBSCRIPTION_ID"}
# O sincronizar também decifra o cadastro da tela (mesma chave da credencial AWS).
ENV_SINCRONIZAR = ENV_PERMITIDAS | {"PROV_ENC_KEY"}
JWE = ':{}:$env.PROV_ENC_KEY:"A256KW":"A256CBC-HS512"'

CAMPOS_ADD = ["provedor", "mes_referencia", "custo_mes_total", "moeda", "atualizado_em", "tem_valor", "status",
              "erro_resumo", "tentativa_em", "bloqueado_ate"]
CAMPOS_EDIT = CAMPOS_ADD[2:]


def problemas_sincronizar(codigo: str) -> list[str]:
    r = _Regras()
    ex = r.exigir

    # --- rota, autenticação, admin-only e sem input ---
    ex('query "azure/custo/sincronizar" verb=POST' in codigo, "rota_post")
    ex('api_group = "app"' in codigo and 'auth = "usuarios"' in codigo, "grupo_app_auth_usuarios")
    entrada = _bloco(codigo, "input {")
    ex(entrada.strip() == "", "sem_campos_de_input")
    ex("$input" not in codigo, "nao_le_input")
    p_token = _precondicao_pos(codigo, "$usuario_logado != null", "unauthorized", '"Token inválido ou expirado"')
    p_admin = _precondicao_pos(
        codigo, '$usuario_logado.status == "ativo" && $usuario_logado.role == "admin"', "accessdenied", '"Acesso negado"')
    ex(p_token >= 0 and p_admin > p_token, "admin_ativo_exigido")
    primeiro_efeito = min(i for i in (codigo.find("db.add travas"), codigo.find("api.request"),
                                      codigo.find("db.add provedor_externo_leitura"),
                                      codigo.find("db.edit provedor_externo_leitura")) if i >= 0)
    ex(p_admin >= 0 and p_admin < primeiro_efeito, "admin_antes_de_qualquer_efeito")
    # admin relido já dentro da trava
    ex(re.search(r'if \(\$solicitante_atual == null \|\| \$solicitante_atual\.status != "ativo" \|\| '
                 r'\$solicitante_atual\.role != "admin"\) \{\s*var\.update \$estado \{ value = "negado" \}', codigo),
       "admin_relido_na_trava")
    ex(_precondicao_pos(codigo, '$estado != "negado"', "accessdenied", '"Acesso negado"') > codigo.find("finally {"),
       "negado_vira_403_apos_liberar_trava")

    # --- configuração: formato validado ANTES de montar URL; sem config nada é chamado ---
    # a função de configuração é chamada DENTRO da trava (e da seção crítica), nunca antes dela
    ex(re.search(r'function\.run "costguard/azure_config_estado" \{\s*input = \{\}\s*\} as \$config', codigo), "usa_funcao_de_config")
    ex(codigo.count('function.run "costguard/azure_config_estado"') == 1, "config_chamada_uma_vez")
    ex(re.search(r'if \(\$config\.estado != "ok"\) \{\s*var\.update \$estado \{ value = "sem_config" \}', codigo), "sem_config_marca_estado")
    ex(re.search(r'if \(\$trava_id == null && \$trava_ocupada == false\) \{', codigo), "trava_tomada_antes_da_config")
    pos_config = codigo.find('as $config')
    pos_req = codigo.find("api.request")
    ex(0 <= codigo.find("db.add travas") < pos_config < pos_req, "config_dentro_da_trava_antes_da_chamada")
    ex(0 <= pos_config < codigo.find("finally {"), "config_na_secao_critica")
    # a função só devolve estado/origem/versão: o segredo NUNCA é input nem resposta de função
    ex(not re.search(r'function\.run "[^"]+" \{\s*input = \{[^}]*\$(c_|segredo|tenant)', codigo), "funcao_sem_segredo_no_input")
    ex("var.update $origem_cred { value = $config.origem }" in codigo and "var.update $versao_api { value = $config.versao_api }" in codigo,
       "origem_e_versao_vem_da_funcao")
    # ORDEM DAS CREDENCIAIS: cadastro da tela (decifrado AQUI) primeiro; variáveis do servidor só como reserva
    cred = _bloco_re_seguro(codigo, r'if \(\$origem_cred == "tela"\) \{')
    ex(re.search(r'db\.get azure_conexao \{\s*field_name = "chave"\s*field_value = "azure"', cred) is not None, "banco_primeiro")
    ex(cred.count("jwe_decode" + JWE) == 4, "decifra_os_quatro_campos_com_prov_enc_key")
    # falha ao decifrar = "cadastro_invalido" (gravado adiante), nunca fallback nas variáveis nem 200 silencioso com sem_config
    ex(re.search(r"catch \{\s*var\.update \$estado \{ value = \"cadastro_invalido\" \}\s*\}", cred) is not None
       and "$env.AZURE_" not in cred and "else" not in cred and "sem_config" not in cred, "falha_ao_decifrar_sem_fallback_silencioso")
    # REVALIDA o formato depois de decifrar dentro do endpoint (as MESMAS regras do POST /azure/conexao; ver também test_azure_conexao_estatico)
    ex(all(f"var $c_{n}_ok {{ value = (($c_{n}|strlen) == 36 && {REGEX_GUID}|regex_matches:$c_{n})) }}" in cred for n in ("tenant", "client", "assinatura"))
       and 'var $c_segredo_ok { value = (($c_segredo|strlen) >= 8 && ($c_segredo|strlen) <= 256 && ("/^[!-~]+$/"|regex_matches:$c_segredo)) }' in cred,
       "revalida_formato_do_cadastro_decifrado")
    ex(re.search(r'if \(\$c_tenant_ok == false \|\| \$c_client_ok == false \|\| \$c_assinatura_ok == false \|\| \$c_segredo_ok == false\) \{\s*'
                 r'var\.update \$estado \{ value = "cadastro_invalido" \}', cred)
       and cred.find("jwe_decode") < cred.find("var $c_tenant_ok"), "formato_invalido_vira_cadastro_invalido")
    ex(re.search(r'\}\s*else \{\s*var\.update \$c_tenant \{ value = \(\(\$env\.AZURE_TENANT_ID \?\? ""\)\|trim\) \}', codigo),
       "variaveis_do_servidor_so_como_reserva")
    ex(re.search(r'var\.update \$c_tenant \{ value = \(\(\$env\.AZURE_TENANT_ID \?\? ""\)\|trim\) \}', codigo), "le_tenant_do_env")
    ex(re.search(r'var\.update \$c_segredo \{ value = \(\(\$env\.AZURE_CLIENT_SECRET \?\? ""\)\|trim\) \}', codigo), "le_segredo_do_env")
    # credenciais só preenchidas depois da função de configuração e do gate `$estado == ""`
    ex(codigo.find("var.update $c_tenant") > pos_config and re.search(r'if \(\$estado == ""\) \{\s*conditional \{\s*if \(\$origem_cred == "tela"\)', codigo),
       "credenciais_lidas_apos_config_e_gate")
    ex(set(re.findall(r"\$env\.(\w+)", codigo)) == ENV_SINCRONIZAR, "env_somente_as_quatro_variaveis_e_a_chave")
    ex("AZURE_COST_API_VERSION" not in codigo, "versao_da_api_so_na_funcao_de_config")

    # --- chamadas: exatamente duas (token + consulta), sem laço, sem paginação ---
    ex(codigo.count("api.request") == 2, "exatamente_duas_chamadas")
    urls = re.findall(r'url = ([^\n]+)', codigo)
    ex(urls == [
        '"https://login.microsoftonline.com/" ~ $c_tenant ~ "/oauth2/v2.0/token"',
        '"https://management.azure.com/subscriptions/" ~ $c_assinatura ~ "/providers/Microsoft.CostManagement/query?api-version=" ~ $versao_api',
    ], "urls_fixas_so_com_variaveis_validadas")
    ex(codigo.count('method = "POST"') == 2 and 'method = "GET"' not in codigo, "somente_post_de_consulta")
    ex("\n".join(_blocos_foreach(codigo)).count("api.request") == 0, "chamada_fora_de_laco")
    ex(len(_blocos_foreach(codigo)) == 3, "tres_lacos_travas_colunas_cabecalhos")
    ex(not re.search(r"\b(while|for)\b", codigo) and "util.sleep" not in codigo, "sem_while_nem_sleep")
    ex("nextLink" in codigo and "$q_proximo" in codigo, "detecta_nextlink")
    # o nextLink nunca é usado como URL, nem entra em api.request
    bloco_reqs = "".join(_bloco(codigo, "api.request {") for _ in range(1))
    ex("$q_proximo" not in bloco_reqs and "nextLink" not in "".join(urls) and "$q_proximo" not in "".join(urls), "nao_segue_nextlink")
    ex(re.search(r'if \(\$q_proximo != ""\) \{[^}]*?var\.update \$desfecho \{ value = "resposta_incompleta" \}', codigo, re.S), "nextlink_vira_resposta_incompleta")
    ex(re.search(r"timeout = (\d+)", _bloco(codigo, "api.request {")) and
       all(0 < int(t) <= 20 for t in re.findall(r"timeout = (\d+)", codigo)), "timeouts_curtos")

    # --- cabeçalhos/corpo: token só em Authorization, segredo só no corpo do token ---
    ex(re.search(r'"Authorization: Bearer " ~ \$t_token', codigo), "bearer_com_token")
    usos_token = [l.strip() for l in codigo.splitlines() if "$t_token" in l]
    ex(all(("var $t_token" in l or "var.update $t_token" in l or "strlen" in l or "regex_matches" in l
            or "Authorization: Bearer" in l) for l in usos_token), "token_nunca_e_guardado_nem_devolvido")
    # `$c_segredo`: declarado, atribuído (cadastro decifrado / variável) e usado UMA vez, no corpo do token
    usos_segredo = [l.strip() for l in codigo.splitlines() if re.search(r"\$c_segredo(?![\w])", l)]
    ex(sum(not (l.startswith("var $c_segredo") or l.startswith("var.update $c_segredo")) for l in usos_segredo) == 1
       and sum(l.startswith("params = {client_id: $c_client, client_secret: $c_segredo,") for l in usos_segredo) == 1, "segredo_so_no_corpo_do_token")
    ex(re.search(r'params = \{client_id: \$c_client, client_secret: \$c_segredo, scope: "https://management\.azure\.com/\.default", grant_type: "client_credentials"\}', codigo), "corpo_do_token")
    corpo = re.search(r'value = "(\{\\"type\\".*?\})"\|json_decode', codigo)
    ex(corpo is not None, "corpo_da_consulta_presente")
    if corpo:
        try:
            texto_corpo = json.loads('"' + corpo.group(1) + '"')
            ex(texto_corpo == CORPO_CONSULTA_TESTADO, "corpo_da_consulta_identico_ao_testado")
            ex(json.loads(texto_corpo)["dataset"]["aggregation"]["totalCost"]["function"] == "Sum"
               and json.loads(texto_corpo)["type"] == "ActualCost", "corpo_da_consulta_so_leitura")
        except (ValueError, KeyError):
            ex(False, "corpo_da_consulta_json_valido")
    ex(re.search(r"\$c_segredo|\$t_token|\$c_tenant|\$c_client|\$c_assinatura", "\n".join(
        re.findall(r"error = [^\n]+", codigo))) is None, "erros_sem_credenciais")

    # --- a resposta do Azure só é lida para variáveis internas e nunca devolvida ---
    linhas_resp = [l.strip() for l in codigo.splitlines() if "$resp_custo" in l or "$resp_token" in l]
    ex(all(l.startswith("var.update $q_") or l.startswith("var.update $t_") or l.startswith("} as $resp_") for l in linhas_resp),
       "resposta_do_azure_so_em_variaveis_internas")
    ex(not re.search(r"\$resp_(custo|token)\.response\.(result\.error|body)", codigo), "nao_le_erro_do_azure")
    ex(_chaves_do_objeto(_bloco(codigo, "var $resposta {\n      value = {")) == CHAVES_POST, "resposta_so_com_campos_do_contrato")
    # `origem` do POST = como foi a resposta ("azure" | "cooldown" | null); NUNCA "cache". A de credencial tem outro nome.
    ex('var $origem { value = ($estado == "cooldown") ? "cooldown" : (($estado == "consultado") ? "azure" : null) }' in codigo
       and '"cache"' not in codigo and "origem_credencial : $guardado.origem" in codigo, "origem_do_post_sem_cache_e_origem_credencial")
    ex(codigo.count("$resposta") == 2, "resposta_unica")

    # --- gravação: apenas o último valor, sem credenciais ---
    add = _bloco(_bloco(codigo, "db.add provedor_externo_leitura {"), "data = {")
    edits = [_bloco(_bloco_re(codigo[m.start():], r"db\.edit provedor_externo_leitura \{"), "data = {")
             for m in re.finditer(r"db\.edit provedor_externo_leitura \{", codigo)]
    ex(_chaves_do_objeto(add) == CAMPOS_ADD, "db_add_so_campos_permitidos")
    ex(len(edits) == 3 and _chaves_do_objeto(edits[0]) == ["tentativa_em"] and _chaves_do_objeto(edits[1]) == CAMPOS_EDIT
       and _chaves_do_objeto(edits[2]) == ["status", "erro_resumo"], "db_edit_so_campos_permitidos")
    ex(codigo.count("db.add provedor_externo_leitura") == 2 and codigo.count("db.edit provedor_externo_leitura") == 3,
       "gravacao_so_na_tentativa_no_final_e_no_cadastro_invalido")
    # cadastro quebrado (detectado aqui): nada chamado no Azure; grava SÓ o desfecho genérico (texto fixo, sem eco), dentro da trava
    inv = _bloco_re_seguro(codigo, r'if \(\$estado == "cadastro_invalido"\) \{')
    add_inv = _bloco(inv, "db.add provedor_externo_leitura {") if "db.add provedor_externo_leitura {" in inv else ""
    ex(inv != "" and "api.request" not in inv and "$c_" not in inv and "$input" not in inv and "$env" not in inv
       and codigo.find('if ($estado == "cadastro_invalido") {') > pos_req and 0 < codigo.find('if ($estado == "cadastro_invalido") {') < codigo.find("finally {"),
       "cadastro_invalido_nao_chama_azure_e_grava_dentro_da_trava")
    ex(inv.count(MSG_CADASTRO_QUEBRADO) == 2 and re.findall(r'status\s*: "(\w+)"', inv) == ["indisponivel", "indisponivel"],
       "cadastro_invalido_grava_indisponivel_com_texto_fixo")
    ex(_chaves_do_objeto(_bloco(add_inv, "data = {")) == CAMPOS_ADD and "tem_valor     : false" in add_inv and "atualizado_em : 0" in add_inv
       and "tentativa_em  : 0" in add_inv and "bloqueado_ate : 0" in add_inv and "custo_mes_total: null" in add_inv, "cadastro_invalido_linha_nova_sem_valor")
    ex('where = $db.provedor_externo_leitura.provedor == "azure" && $db.provedor_externo_leitura.mes_referencia == $mes_inv' in inv
       and '$agora_inv|format_timestamp:"Y-m":"UTC"' in inv, "cadastro_invalido_so_o_mes_corrente_em_utc")
    ex("sem_config" not in codigo.split('if ($config.estado != "ok") {')[0] and codigo.count('"sem_config"') == 1, "sem_config_so_para_estado_da_funcao")
    # tentativa gravada ANTES de qualquer chamada ao Azure; linha nova sem inventar valor
    pos_add = codigo.find("db.add provedor_externo_leitura")
    pos_edit1 = codigo.find("db.edit provedor_externo_leitura")
    ex(0 <= pos_add < pos_req and 0 <= pos_edit1 < pos_req, "grava_tentativa_antes_do_azure")
    ex(re.search(r"custo_mes_total: null\s+moeda\s+: \"\"\s+atualizado_em : 0\s+tem_valor\s+: false\s+status\s+: \"sem_leitura\"", add) is not None
       and "tentativa_em  : $agora_ms" in add, "pre_gravacao_sem_inventar_valor")
    ex("data = {tentativa_em: $agora_ms}" in codigo, "pre_gravacao_so_tentativa_em")
    # a gravação final é sempre db.edit na linha do mês (a linha já existe)
    ex(codigo.find("db.edit provedor_externo_leitura", pos_edit1 + 10) > codigo.find('if ($desfecho == "ok") {'), "gravacao_final_apos_desfecho")

    # --- SEM cache de 4 h: só o bloqueio por 429 e o cooldown de 60 s impedem a chamada ---
    ex("janela_cache_ms" not in codigo and "14400000" not in codigo
       and not re.search(r"\$agora_ms - \$linha\.atualizado_em", codigo), "sem_cache_de_4_horas")
    ex(re.search(r'where = \$db\.provedor_externo_leitura\.provedor == "azure" && \$db\.provedor_externo_leitura\.mes_referencia == \$mes_atual', codigo),
       "leitura_so_do_mesmo_mes")
    ex(re.search(r'if \(\$linha != null && \$linha\.bloqueado_ate > \$agora_ms\) \{', codigo), "respeita_bloqueio_do_429")
    ex(codigo.find('value = "limite"') < codigo.find('value = "cooldown"') < pos_req, "bloqueio_e_cooldown_antes_da_chamada")
    # cooldown de 60 s após qualquer tentativa (sucesso OU falha): não chama o Azure e devolve o estado guardado
    ex("var $cooldown_ms { value = 60000 }" in codigo, "cooldown_de_60s")
    ex(re.search(r'elseif \(\$linha != null && \(\$linha\.tentativa_em \?\? 0\) > 0 && \(\$agora_ms - \$linha\.tentativa_em\) < \$cooldown_ms\) \{\s*'
                 r'var\.update \$estado \{ value = "cooldown" \}', codigo), "cooldown_sem_chamar_azure")
    ex(codigo.find("$linha.bloqueado_ate > $agora_ms") < codigo.find("< $cooldown_ms") < pos_req, "cooldown_depois_do_bloqueio")
    ex(re.search(r'var \$mes_atual \{ value = \$agora_ms\|format_timestamp:"Y-m":"UTC" \}', codigo), "mes_em_utc")
    ex(re.search(r"var\.update \$n_bloqueio \{ value = \$agora_ms \+ \(\$segundos_restantes \* 1000\) \}", codigo), "grava_bloqueio_do_429")

    # --- 429: sem repetir, segundos 1..3600, cabeçalhos corretos, HTTP 429 ao usuário ---
    # cabeçalho cujo nome CONTÉM retry-after (não só "termina em"): Retry-After, ...clienttype-retry-after, ...qpu-retry-after
    ex('($cab_nome|contains:"retry-after")' in codigo and "starts_with" not in codigo and "ends_with" not in codigo, "cabecalhos_do_429")
    ex("var $cab_baixo { value = (($cabecalho|to_text)|to_lower) }" in codigo, "cabecalho_sem_diferenciar_maiusculas")
    ex(re.search(r"if \(\(\$cab_valor\|to_int\) > \$seg_max\) \{\s*var\.update \$seg_max \{ value = \$cab_valor\|to_int \}", codigo)
       and "$seg_qpu" not in codigo and "$seg_ra" not in codigo, "usa_o_maior_retry_after")
    ex(re.search(r"elseif \(\$q_status == 429\) \{\s*var\.update \$l_cabecalhos \{ value = \$q_cabecalhos \}\s*var\.update \$desfecho \{ value = \"limite\" \}", codigo), "trata_429")
    ex(re.search(r"if \(\$t_status == 429\) \{\s*var\.update \$l_cabecalhos \{ value = \$t_cabecalhos \}\s*var\.update \$desfecho \{ value = \"limite\" \}", codigo)
       and "var.update $t_cabecalhos { value = ($resp_token.response.headers ?? []) }" in codigo, "429_do_token_vira_limite")
    # o 429 do token impede a consulta (desfecho != "") e usa o mesmo cálculo de segundos
    ex(re.search(r'if \(\$desfecho == ""\) \{\s*var \$corpo_consulta', codigo), "429_do_token_nao_consulta")
    ex(re.search(r"var\.update \$segundos_restantes \{ value = 60 \}", codigo), "padrao_60_segundos")
    ex(len(re.findall(r"if \(\$segundos_restantes < 1\) \{\s*var\.update \$segundos_restantes \{ value = 1 \}\s*\}\s*"
                      r"elseif \(\$segundos_restantes > 3600\) \{\s*var\.update \$segundos_restantes \{ value = 3600 \}", codigo)) == 2,
       "segundos_entre_1_e_3600_nos_dois_caminhos")
    ex("/^[0-9]{1,9}$/" in codigo and "|to_int" in codigo, "segundos_inteiros")
    ex(re.search(r'var \$msg_limite \{\s*value = "O Azure limitou as consultas de custo\. Aguarde " ~ \(\$segundos_restantes\|to_text\) ~ " segundos para tentar de novo\."\s*\}', codigo), "mensagem_do_429")
    ex(_precondicao_pos(codigo, '$estado != "limite"', "toomanyrequests", "$msg_limite") > codigo.find("var $msg_limite"), "http_429_com_segundos")
    ex(_precondicao_pos(codigo, '$estado != "limite"', "toomanyrequests", "$msg_limite") > codigo.find("finally {"), "429_apos_liberar_trava")

    # --- demais desfechos ---
    ex(re.search(r'elseif \(\$q_status == 401 \|\| \$q_status == 403\) \{\s*var\.update \$desfecho \{ value = "sem_permissao" \}', codigo), "401_403_sem_permissao")
    ex(re.search(r'elseif \(\$q_status == 204\) \{\s*var\.update \$desfecho \{ value = "sem_dados" \}', codigo), "204_sem_dados")
    ex(re.search(r'elseif \(\(\$q_linhas\|count\) == 0\) \{\s*var\.update \$desfecho \{ value = "sem_dados" \}', codigo), "sem_linhas_sem_dados")
    ex(re.search(r'elseif \(\(\$q_linhas\|count\) > 1\) \{\s*var\.update \$desfecho \{ value = "resposta_incompleta" \}', codigo), "mais_de_uma_linha_incompleta")
    ex(re.search(r'else \{\s*// 5xx[^\n]*\n\s*var\.update \$desfecho \{ value = "indisponivel" \}', _ler(SINCRONIZAR)), "5xx_timeout_indisponivel")
    ex(re.search(r'catch \{\s*var\.update \$q_status \{ value = 0 \}', codigo) and re.search(r'catch \{\s*var\.update \$t_status \{ value = 0 \}', codigo),
       "excecao_de_rede_vira_status_0")
    sem_dados = _bloco_re_seguro(codigo, r'elseif \(\$desfecho == "sem_dados"\) \{')
    ex("var.update $n_tem_valor { value = false }" in sem_dados and "var.update $n_custo { value = null }" in sem_dados
       and "$novo_custo" not in sem_dados and not re.search(r"\$n_custo \{ value = 0", sem_dados), "sem_dados_nao_vira_zero")
    # sem_dados NÃO é erro: leitura bem-sucedida (guarda o instante, sem erro_resumo, sem bloqueio, moeda vazia)
    ex("var.update $n_atualizado { value = $agora_ms }" in sem_dados and 'var.update $n_erro { value = "" }' in sem_dados
       and "var.update $n_bloqueio { value = 0 }" in sem_dados and 'var.update $n_moeda { value = "" }' in sem_dados
       and 'var.update $n_status { value = "sem_dados" }' in sem_dados and "$erro_texto" not in sem_dados, "sem_dados_e_leitura_bem_sucedida")
    ok = _bloco_re_seguro(codigo, r'if \(\$desfecho == "ok"\) \{')
    ex("var.update $n_tem_valor { value = true }" in ok and "var.update $n_custo { value = $novo_custo }" in ok, "ok_guarda_valor")
    indisp = _bloco_re_seguro(codigo, r'elseif \(\$desfecho == "indisponivel"\) \{')
    ex("$n_custo" not in indisp and "$n_tem_valor" not in indisp and "$n_atualizado" not in indisp, "indisponivel_mantem_ultimo_valor")
    perm = _bloco_re_seguro(codigo, r'elseif \(\$desfecho == "sem_permissao" \|\| \$desfecho == "resposta_incompleta"\) \{')
    ex("var.update $n_tem_valor { value = false }" in perm and "var.update $n_custo { value = null }" in perm, "sem_permissao_e_incompleta_nao_guardam_valor")
    # sem leitura bem-sucedida: zera atualizado_em (senão o cache de 4 h seguraria uma falha)
    ex("var.update $n_atualizado { value = 0 }" in perm, "sem_permissao_e_incompleta_zeram_atualizado_em")
    # custo: só o ramo ok atribui número; os ramos sem valor atribuem null (nunca 0)
    ex(re.findall(r"var\.update \$n_custo \{ value = ([^}]+?) \}", codigo) == ["$novo_custo", "null", "null"] 
       and re.findall(r"var\.update \$n_atualizado \{ value = ([^}]+?) \}", codigo) == ["$agora_ms", "$agora_ms", "0"],
       "valor_so_muda_no_ramo_ok")
    ex("var $n_custo { value = ($linha != null) ? $linha.custo_mes_total : null }" in codigo, "custo_nasce_null_sem_linha")
    ex(re.search(r'"/\^-\?\[0-9\]\+.*?\$/"\|regex_matches:\$valor_txt', codigo) and re.search(r'"/\^\[A-Za-z\]\{3\}\$/"\|regex_matches:\$moeda_txt', codigo), "valida_valor_e_moeda")
    # o `$` do regex aceita quebra de linha final: o tamanho fecha a brecha
    ex("($moeda_txt|strlen) == 3" in codigo, "moeda_exatamente_3_caracteres")
    ex("(($valor_txt|trim)|strlen) == ($valor_txt|strlen)" in codigo and "($valor_txt|strlen) <= 40" in codigo, "valor_sem_espaco_nem_quebra")
    ex("(($t_token|trim)|strlen) == ($t_token|strlen)" in codigo, "token_sem_espaco_nem_quebra")
    ex(re.search(r'if \(\$nome_coluna == "cost"\)', codigo) and re.search(r'elseif \(\$nome_coluna == "currency"\)', codigo), "colunas_por_nome")
    ex("|get:$idx_custo:" in codigo and "|get:$idx_moeda:" in codigo and "$idx_custo >= 0 && $idx_moeda >= 0" in codigo, "indice_so_se_coluna_encontrada")
    ex("pretaxcost" not in codigo.lower() and "Usage" not in codigo and "2025-03-01" not in codigo, "sem_nomes_antigos_do_azure")
    ex(not re.search(r"\$q_linhas\|first\)\|get:0|\[0\]\[1\]|\$linha_azure\.0|\$linha_azure\[", codigo), "nunca_posicao_fixa")

    # --- parse da resposta em try_catch próprio: exceção vira "indisponivel", nunca 500 ---
    ex(re.search(r'if \(\$q_status == 200\) \{\s*try_catch \{\s*try \{\s*conditional \{\s*if \(\$q_proximo != ""\)', codigo), "parse_em_try_catch")
    ex(re.search(r'catch \{\s*var\.update \$desfecho \{ value = "indisponivel" \}\s*var\.update \$erro_texto \{ value = "A resposta do Azure veio em formato inesperado\." \}\s*\}\s*\}\s*\}\s*elseif \(\$q_status == 204\)', codigo),
       "parse_com_falha_vira_indisponivel")

    # --- trava anti-concorrência, órfã curta e liberação ---
    ex('var $trava_nome { value = "azure_custo_sincronizar" }' in codigo, "nome_da_trava")
    ex(re.search(r"db\.add travas \{\s*data = \{nome: \$trava_nome, adquirida_em: \$agora_trava\}", codigo), "trava_na_tabela_travas")
    ex(re.search(r"\$idade_trava > 120000 && \$tentativa == 1\) \{\s*db\.del travas \{\s*field_name = \"id\"\s*field_value = \$trava_atual\.id", codigo), "trava_orfa_curta")
    ex("foreach ([1, 2]) {" in codigo, "duas_tentativas_de_trava")
    fin = _bloco(codigo, "finally {")
    ex(re.search(r'if \(\$trava_id != null\) \{\s*db\.del travas \{\s*field_name = "id"\s*field_value = \$trava_id', fin), "trava_liberada_no_finally")
    ex(_precondicao_pos(codigo, '$trava_id != null', "toomanyrequests",
                        '"Já existe uma sincronização do custo do Azure em andamento. Tente novamente em instantes."') >= 0, "trava_ocupada_429")
    ex(re.search(r"catch \{\s*var\.update \$falha \{ value = true \}\s*\}\s*finally \{", codigo), "falha_inesperada_vira_erro_generico")
    ex(_precondicao_pos(codigo, "$falha == false", "standard",
                        '"Não foi possível sincronizar o custo do Azure agora. Tente novamente em instantes."') > codigo.find("finally {"),
       "erro_generico_apos_liberar_trava")
    # a gravação do valor fica dentro da seção crítica (try ... finally)
    ex(codigo.find("db.add provedor_externo_leitura") < codigo.find("finally {"), "gravacao_dentro_da_trava")
    return r.violadas


def test_sincronizar_cumpre_todas_as_regras():
    assert problemas_sincronizar(_codigo(SINCRONIZAR)) == []


MUTACOES_SINCRONIZAR = [
    ("sem_admin", '$usuario_logado.status == "ativo" && $usuario_logado.role == "admin"', "$usuario_logado.status == \"ativo\"", "admin_ativo_exigido"),
    ("admin_relido_removido", 'if ($solicitante_atual == null || $solicitante_atual.status != "ativo" || $solicitante_atual.role != "admin") {',
     "if ($solicitante_atual == null) {", "admin_relido_na_trava"),
    ("le_input", "  input {\n  }", "  input {\n    text qualquer?\n  }", "sem_campos_de_input"),
    ("sem_gate_de_config", 'if ($config.estado != "ok") {', 'if ($config.estado == "xx") {', "sem_config_marca_estado"),
    # a configuração (e as credenciais) só valem DENTRO da trava: mutação = chamar a função antes de tomar a trava
    ("config_fora_da_trava", '    var $estado { value = "" }\n    var $falha { value = false }',
     '    function.run "costguard/azure_config_estado" {\n      input = {}\n    } as $config\n    var $estado { value = "" }\n    var $falha { value = false }',
     "config_dentro_da_trava_antes_da_chamada"),
    ("trava_com_gate_de_config", 'if ($trava_id == null && $trava_ocupada == false) {', 'if ($estado == "" && $trava_id == null && $trava_ocupada == false) {', "trava_tomada_antes_da_config"),
    ("segredo_como_input_de_funcao", '} as $config', '} as $config\n    function.run "costguard/x" {\n      input = {s: $c_segredo}\n    } as $y', "funcao_sem_segredo_no_input"),
    ("config_chamada_duas_vezes", 'var.update $versao_api { value = $config.versao_api }',
     'var.update $versao_api { value = $config.versao_api }\n            function.run "costguard/azure_config_estado" {\n              input = {}\n            } as $config2', "config_chamada_uma_vez"),
    ("origem_da_credencial_perdida", "var.update $origem_cred { value = $config.origem }", "var.update $origem_cred { value = null }", "origem_e_versao_vem_da_funcao"),
    # ordem das credenciais: banco primeiro, variáveis só como reserva, sem fallback silencioso
    ("variaveis_primeiro", 'if ($origem_cred == "tela") {', 'if ($origem_cred == "servidor") {', "banco_primeiro"),
    ("sem_cadastro_na_leitura", "db.get azure_conexao {", "db.get azure_conexao_antiga {", "banco_primeiro"),
    ("falha_ao_decifrar_cai_nas_variaveis", 'catch {\n                    var.update $estado { value = "cadastro_invalido" }',
     'catch {\n                    var.update $c_tenant { value = (($env.AZURE_TENANT_ID ?? "")|trim) }', "falha_ao_decifrar_sem_fallback_silencioso"),
    ("falha_ao_decifrar_ignorada", 'catch {\n                    var.update $estado { value = "cadastro_invalido" }', 'catch {\n                    var.update $falha { value = false }',
     "falha_ao_decifrar_sem_fallback_silencioso"),
    # falha ao decifrar NÃO pode voltar a ser o 200 silencioso "sem_config" (mensagem de nao_configurado para cadastro quebrado)
    ("falha_ao_decifrar_vira_sem_config", 'catch {\n                    var.update $estado { value = "cadastro_invalido" }', 'catch {\n                    var.update $estado { value = "sem_config" }',
     "falha_ao_decifrar_sem_fallback_silencioso"),
    # revalidação do formato depois de decifrar
    ("revalida_sem_guid_do_tenant", '("/^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/"|regex_matches:$c_tenant)', "true",
     "revalida_formato_do_cadastro_decifrado"),
    ("revalida_sem_guid_do_client", '(($c_client|strlen) == 36 && ', "(", "revalida_formato_do_cadastro_decifrado"),
    ("revalida_sem_guid_da_assinatura", '("/^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/"|regex_matches:$c_assinatura)', "true",
     "revalida_formato_do_cadastro_decifrado"),
    ("revalida_segredo_aceita_espaco", '"/^[!-~]+$/"|regex_matches:$c_segredo', '"/^.+$/"|regex_matches:$c_segredo', "revalida_formato_do_cadastro_decifrado"),
    ("revalida_segredo_sem_tamanho_minimo", "($c_segredo|strlen) >= 8 && ", "", "revalida_formato_do_cadastro_decifrado"),
    ("revalida_ignora_o_segredo", " || $c_segredo_ok == false) {", ") {", "formato_invalido_vira_cadastro_invalido"),
    ("revalida_ignora_a_assinatura", " || $c_assinatura_ok == false", "", "formato_invalido_vira_cadastro_invalido"),
    ("formato_invalido_segue_em_frente", 'if ($c_tenant_ok == false || $c_client_ok == false || $c_assinatura_ok == false || $c_segredo_ok == false) {\n                        var.update $estado { value = "cadastro_invalido" }',
     'if ($c_tenant_ok == false || $c_client_ok == false || $c_assinatura_ok == false || $c_segredo_ok == false) {\n                        var.update $estado { value = "sem_config" }',
     "formato_invalido_vira_cadastro_invalido"),
    # cadastro quebrado: grava o desfecho genérico, sem chamar o Azure e sem eco de valores
    ("cadastro_invalido_chama_o_azure", 'if ($estado == "cadastro_invalido") {\n            var $agora_inv',
     'if ($estado == "cadastro_invalido") {\n            api.request { url = "https://x.invalid" }\n            var $agora_inv', "cadastro_invalido_nao_chama_azure_e_grava_dentro_da_trava"),
    ("cadastro_invalido_ecoa_o_segredo", '"O cadastro do Azure guardado no servidor não pôde ser lido. Cadastre a conexão novamente."\n                  }',
     '"O cadastro do Azure guardado no servidor não pôde ser lido. " ~ $c_segredo\n                  }', "cadastro_invalido_nao_chama_azure_e_grava_dentro_da_trava"),
    ("cadastro_invalido_texto_diferente", 'erro_resumo: "O cadastro do Azure guardado no servidor não pôde ser lido. Cadastre a conexão novamente."',
     'erro_resumo: "Cadastro quebrado."', "cadastro_invalido_grava_indisponivel_com_texto_fixo"),
    ("cadastro_invalido_status_errado", 'status     : "indisponivel"', 'status     : "sem_permissao"', "cadastro_invalido_grava_indisponivel_com_texto_fixo"),
    ("cadastro_invalido_linha_nova_com_valor", "tem_valor     : false\n                    status        : \"indisponivel\"", "tem_valor     : true\n                    status        : \"indisponivel\"",
     "cadastro_invalido_linha_nova_sem_valor"),
    ("cadastro_invalido_mexe_na_tentativa", 'erro_resumo: "O cadastro do Azure guardado no servidor não pôde ser lido. Cadastre a conexão novamente."\n                  }',
     'erro_resumo: "O cadastro do Azure guardado no servidor não pôde ser lido. Cadastre a conexão novamente."\n                    tentativa_em: 0\n                  }', "db_edit_so_campos_permitidos"),
    ("cadastro_invalido_qualquer_mes", 'where = $db.provedor_externo_leitura.provedor == "azure" && $db.provedor_externo_leitura.mes_referencia == $mes_inv',
     'where = $db.provedor_externo_leitura.provedor == "azure"', "cadastro_invalido_so_o_mes_corrente_em_utc"),
    ("decifra_so_tres_campos", 'var.update $c_assinatura { value = (($cadastro.subscription_id_cifrado|jwe_decode:{}:$env.PROV_ENC_KEY:"A256KW":"A256CBC-HS512")|trim) }',
     'var.update $c_assinatura { value = (($env.AZURE_SUBSCRIPTION_ID ?? "")|trim) }', "decifra_os_quatro_campos_com_prov_enc_key"),
    ("decifra_com_outra_chave", '$cadastro.client_secret_cifrado|jwe_decode:{}:$env.PROV_ENC_KEY', '$cadastro.client_secret_cifrado|jwe_decode:{}:$env.AZURE_CLIENT_SECRET',
     "decifra_os_quatro_campos_com_prov_enc_key"),
    ("decifra_com_outro_algoritmo", '$cadastro.tenant_id_cifrado|jwe_decode:{}:$env.PROV_ENC_KEY:"A256KW":"A256CBC-HS512"', '$cadastro.tenant_id_cifrado|jwe_decode:{}:$env.PROV_ENC_KEY:"A128KW":"A128CBC-HS256"',
     "decifra_os_quatro_campos_com_prov_enc_key"),
    ("credencial_antes_da_config", 'var $origem_cred { value = null }', 'var $origem_cred { value = null }\n    var.update $c_tenant { value = "x" }', "credenciais_lidas_apos_config_e_gate"),
    ("le_variavel_extra_do_ambiente", '$env.AZURE_CLIENT_ID ?? ""', '$env.AZURE_OUTRA ?? ""', "env_somente_as_quatro_variaveis_e_a_chave"),
    ("origem_cache_volta", '? "cooldown" : ', '? "cache" : ', "origem_do_post_sem_cache_e_origem_credencial"),
    ("origem_credencial_removida", "        origem_credencial : $guardado.origem\n", "", "origem_do_post_sem_cache_e_origem_credencial"),
    ("origem_credencial_removida_da_resposta", "        origem_credencial : $guardado.origem\n", "", "resposta_so_com_campos_do_contrato"),
    ("terceira_chamada", "} as $resp_token", "} as $resp_token\n                    api.request { url = \"https://x.invalid\" }", "exatamente_duas_chamadas"),
    ("chamada_em_laco", "foreach ($q_colunas) {", 'foreach ($q_colunas) {\n api.request { url = "https://x.invalid" }', "chamada_fora_de_laco"),
    ("url_com_input", '"/providers/Microsoft.CostManagement/query?api-version=" ~ $versao_api',
     '"/providers/Microsoft.CostManagement/query?api-version=" ~ $versao_api ~ $q_proximo', "urls_fixas_so_com_variaveis_validadas"),
    ("segue_nextlink", 'url = "https://management.azure.com/subscriptions/"', 'url = $q_proximo ~ "https://management.azure.com/subscriptions/"', "urls_fixas_so_com_variaveis_validadas"),
    ("nextlink_ignorado", 'var.update $desfecho { value = "resposta_incompleta" }\n                                  var.update $erro_texto { value = "A resposta do Azure veio paginada',
     'var.update $desfecho { value = "ok" }\n                                  var.update $erro_texto { value = "A resposta do Azure veio paginada', "nextlink_vira_resposta_incompleta"),
    ("metodo_get", 'method = "POST"\n                      params = {client_id', 'method = "GET"\n                      params = {client_id', "somente_post_de_consulta"),
    ("corpo_com_escrita", '\\"function\\":\\"Sum\\"', '\\"function\\":\\"Max\\"', "corpo_da_consulta_identico_ao_testado"),
    ("corpo_type_usage", '\\"type\\":\\"ActualCost\\"', '\\"type\\":\\"Usage\\"', "corpo_da_consulta_identico_ao_testado"),
    ("corpo_type_usage_so_leitura", '\\"type\\":\\"ActualCost\\"', '\\"type\\":\\"Usage\\"', "corpo_da_consulta_so_leitura"),
    ("corpo_coluna_pretaxcost", '\\"name\\":\\"Cost\\"', '\\"name\\":\\"PreTaxCost\\"', "corpo_da_consulta_identico_ao_testado"),
    ("corpo_timeframe", '\\"timeframe\\":\\"MonthToDate\\"', '\\"timeframe\\":\\"BillingMonthToDate\\"', "corpo_da_consulta_identico_ao_testado"),
    ("corpo_granularidade", '\\"granularity\\":\\"None\\"', '\\"granularity\\":\\"Daily\\"', "corpo_da_consulta_identico_ao_testado"),
    ("api_version_antiga_no_codigo", "var $cooldown_ms { value = 60000 }", 'var $cooldown_ms { value = 60000 }\n            var $v { value = "2025-03-01" }', "sem_nomes_antigos_do_azure"),
    ("timeout_longo", "timeout = 15", "timeout = 300", "timeouts_curtos"),
    ("segredo_no_erro", 'var.update $erro_texto { value = "O Azure recusou as credenciais." }',
     'var.update $erro_texto { value = "falha " ~ $c_segredo }', "segredo_so_no_corpo_do_token"),
    ("segredo_em_erro_http", 'error = "Acesso negado"\n    }\n\n    var $msg_limite', 'error = $c_segredo\n    }\n\n    var $msg_limite', "erros_sem_credenciais"),
    ("devolve_corpo_do_azure", 'var.update $n_status { value = "indisponivel" }\n                    var.update $n_erro { value = $erro_texto }',
     'var.update $n_status { value = "indisponivel" }\n                    var.update $n_erro { value = $resp_custo.response.result }', "resposta_do_azure_so_em_variaveis_internas"),
    ("grava_campo_extra", "tentativa_em  : $n_tentativa\n", "tentativa_em  : $n_tentativa\n                    segredo : $c_segredo\n", "db_edit_so_campos_permitidos"),
    ("grava_campo_extra_na_linha_nova", 'moeda         : ""\n', 'moeda         : ""\n                        segredo : $c_segredo\n', "db_add_so_campos_permitidos"),
    ("resposta_com_assinatura", "origem            : $origem", "origem            : $origem\n        assinatura: $c_assinatura", "resposta_so_com_campos_do_contrato"),
    # SEM cache de 4 h: qualquer volta dele (janela, comparação com atualizado_em, estado "cache") tem de ser detectada
    ("cache_volta_com_a_janela", "var $cooldown_ms { value = 60000 }", "var $cooldown_ms { value = 60000 }\n            var $janela_cache_ms { value = 14400000 }", "sem_cache_de_4_horas"),
    ("cache_volta_pelo_valor_da_janela", "var $cooldown_ms { value = 60000 }", "var $cooldown_ms { value = 14400000 }", "sem_cache_de_4_horas"),
    ("cache_volta_pela_comparacao", "if ($linha != null && $linha.bloqueado_ate > $agora_ms) {",
     "if ($linha != null && ($linha.atualizado_em ?? 0) > 0 && ($agora_ms - $linha.atualizado_em) < 60000) {", "sem_cache_de_4_horas"),
    ("cache_de_qualquer_mes", "$db.provedor_externo_leitura.provedor == \"azure\" && $db.provedor_externo_leitura.mes_referencia == $mes_atual",
     "$db.provedor_externo_leitura.provedor == \"azure\"", "leitura_so_do_mesmo_mes"),
    ("ignora_bloqueio", "if ($linha != null && $linha.bloqueado_ate > $agora_ms) {", "if ($linha != null && $linha.bloqueado_ate > 99999999999999) {", "respeita_bloqueio_do_429"),
    ("teto_do_429", "elseif ($segundos_restantes > 3600) {\n                    var.update $segundos_restantes { value = 3600 }",
     "elseif ($segundos_restantes > 360000) {\n                    var.update $segundos_restantes { value = 360000 }", "segundos_entre_1_e_3600_nos_dois_caminhos"),
    ("cabecalho_qualquer", 'contains:"retry-after"', 'contains:"x-ms-ratelimit"', "cabecalhos_do_429"),
    ("cabecalho_so_no_fim_do_nome", 'contains:"retry-after"', 'ends_with:"retry-after"', "cabecalhos_do_429"),
    ("cabecalho_com_diferenca_de_maiusculas", "(($cabecalho|to_text)|to_lower)", "($cabecalho|to_text)", "cabecalho_sem_diferenciar_maiusculas"),
    ("precedencia_fixa_em_vez_do_maior", "if (($cab_valor|to_int) > $seg_max) {", "if (true) {", "usa_o_maior_retry_after"),
    ("429_do_token_sem_bloqueio", "if ($t_status == 429) {", "if ($t_status == 4290) {", "429_do_token_vira_limite"),
    ("429_do_token_nao_guarda_cabecalhos", "var.update $t_cabecalhos { value = ($resp_token.response.headers ?? []) }", "var.update $t_cabecalhos { value = [] }", "429_do_token_vira_limite"),
    ("429_da_consulta_sem_bloqueio", "elseif ($q_status == 429) {", "elseif ($q_status == 4290) {", "trata_429"),
    # item 1: tentativa gravada antes do Azure e parse protegido
    ("sem_pre_gravacao_da_tentativa", "data = {tentativa_em: $agora_ms}", "data = {moeda: $n_moeda}", "pre_gravacao_so_tentativa_em"),
    ("pre_gravacao_inventa_valor", "custo_mes_total: null\n", "custo_mes_total: 0\n", "pre_gravacao_sem_inventar_valor"),
    ("pre_gravacao_com_status_ok", 'status        : "sem_leitura"', 'status        : "ok"', "pre_gravacao_sem_inventar_valor"),
    ("pre_gravacao_depois_do_azure", "var.update $n_tentativa { value = $agora_ms }", "var.update $n_tentativa { value = $agora_ms }\n                api.request { url = \"https://x.invalid\" }", "grava_tentativa_antes_do_azure"),
    ("parse_sem_try_catch", "if ($q_status == 200) {\n                        try_catch {", "if ($q_status == 200) {\n                        conditional {", "parse_em_try_catch"),
    ("parse_com_falha_vira_500", 'catch {\n                            var.update $desfecho { value = "indisponivel" }', 'catch {\n                            var.update $falha { value = true }', "parse_com_falha_vira_indisponivel"),
    # item 2: cooldown
    ("sem_cooldown", "< $cooldown_ms) {", "< 0) {", "cooldown_sem_chamar_azure"),
    ("cooldown_devolve_cache", 'var.update $estado { value = "cooldown" }', 'var.update $estado { value = "cache" }', "cooldown_sem_chamar_azure"),
    ("cooldown_longo", "var $cooldown_ms { value = 60000 }", "var $cooldown_ms { value = 6000000 }", "cooldown_de_60s"),
    ("cooldown_sobrepoe_o_bloqueio", "elseif ($linha != null && ($linha.tentativa_em ?? 0) > 0", "if ($linha != null && ($linha.tentativa_em ?? 0) > 0", "cooldown_sem_chamar_azure"),
    # item 5 e 7
    ("moeda_com_quebra_de_linha", "($moeda_txt|strlen) == 3 && ", "", "moeda_exatamente_3_caracteres"),
    ("valor_com_quebra_de_linha", "(($valor_txt|trim)|strlen) == ($valor_txt|strlen) && ", "", "valor_sem_espaco_nem_quebra"),
    ("token_com_quebra_de_linha", "(($t_token|trim)|strlen) == ($t_token|strlen) && ", "", "token_sem_espaco_nem_quebra"),
    ("sem_dados_grava_zero", 'var.update $n_custo { value = null }', 'var.update $n_custo { value = 0 }', "sem_dados_nao_vira_zero"),
    ("sem_permissao_grava_zero", 'var.update $n_erro { value = $erro_texto }\n                    var.update $n_custo { value = null }',
     'var.update $n_erro { value = $erro_texto }\n                    var.update $n_custo { value = 0 }', "sem_permissao_e_incompleta_nao_guardam_valor"),
    ("custo_nasce_zero", "var $n_custo { value = ($linha != null) ? $linha.custo_mes_total : null }", "var $n_custo { value = ($linha != null) ? ($linha.custo_mes_total ?? 0) : 0 }", "custo_nasce_null_sem_linha"),
    ("padrao_do_429", "var.update $segundos_restantes { value = 60 }", "var.update $segundos_restantes { value = 0 }", "padrao_60_segundos"),
    ("429_sem_http_429", 'precondition ($estado != "limite") {\n      error_type = "toomanyrequests"', 'precondition ($estado != "limite") {\n      error_type = "standard"', "http_429_com_segundos"),
    ("401_vira_indisponivel", 'elseif ($q_status == 401 || $q_status == 403) {\n                        var.update $desfecho { value = "sem_permissao" }',
     'elseif ($q_status == 401 || $q_status == 403) {\n                        var.update $desfecho { value = "indisponivel" }', "401_403_sem_permissao"),
    ("204_vira_ok", 'elseif ($q_status == 204) {\n                        var.update $desfecho { value = "sem_dados" }',
     'elseif ($q_status == 204) {\n                        var.update $desfecho { value = "ok" }', "204_sem_dados"),
    ("sem_dados_vira_zero", 'var.update $n_tem_valor { value = false }\n                    var.update $n_status { value = "sem_dados" }',
     'var.update $n_tem_valor { value = true }\n                    var.update $n_custo { value = 0 }\n                    var.update $n_status { value = "sem_dados" }', "sem_dados_nao_vira_zero"),
    ("indisponivel_apaga_valor", 'var.update $n_status { value = "indisponivel" }\n                    var.update $n_erro',
     'var.update $n_tem_valor { value = false }\n                    var.update $n_status { value = "indisponivel" }\n                    var.update $n_erro', "indisponivel_mantem_ultimo_valor"),
    ("coluna_por_posicao", 'if ($nome_coluna == "cost") {', 'if ($idx_atual == 0) {', "colunas_por_nome"),
    ("coluna_antiga_pretaxcost", 'if ($nome_coluna == "cost") {', 'if ($nome_coluna == "pretaxcost") {', "colunas_por_nome"),
    ("coluna_antiga_pretaxcost_nome_antigo", 'if ($nome_coluna == "cost") {', 'if ($nome_coluna == "pretaxcost") {', "sem_nomes_antigos_do_azure"),
    ("sem_linhas_vira_erro", 'elseif (($q_linhas|count) == 0) {\n                                  var.update $desfecho { value = "sem_dados" }',
     'elseif (($q_linhas|count) == 0) {\n                                  var.update $desfecho { value = "indisponivel" }', "sem_linhas_sem_dados"),
    ("sem_dados_nao_guarda_o_instante", 'var.update $n_atualizado { value = $agora_ms }\n                    var.update $n_moeda { value = "" }', 'var.update $n_moeda { value = "" }',
     "sem_dados_e_leitura_bem_sucedida"),
    ("sem_dados_vira_erro_gravado", 'var.update $n_status { value = "sem_dados" }\n                    var.update $n_erro { value = "" }',
     'var.update $n_status { value = "sem_dados" }\n                    var.update $n_erro { value = $erro_texto }', "sem_dados_e_leitura_bem_sucedida"),
    ("sem_dados_com_status_errado", 'var.update $n_status { value = "sem_dados" }', 'var.update $n_status { value = "sem_leitura" }', "sem_dados_e_leitura_bem_sucedida"),
    ("sem_permissao_nao_zera_atualizado", "var.update $n_atualizado { value = 0 }", "var.update $n_atualizado { value = $agora_ms }", "sem_permissao_e_incompleta_zeram_atualizado_em"),
    ("sem_permissao_sem_linha_do_atualizado", "var.update $n_atualizado { value = 0 }\n", "", "sem_permissao_e_incompleta_zeram_atualizado_em"),
    ("sem_valida_valor", '"/^[A-Za-z]{3}$/"|regex_matches:$moeda_txt', "true", "valida_valor_e_moeda"),
    ("trava_orfa_longa", "$idade_trava > 120000", "$idade_trava > 9000000", "trava_orfa_curta"),
    ("trava_nao_liberada", 'if ($trava_id != null) {\n            db.del travas {', 'if ($trava_id == 0) {\n            db.del travas {', "trava_liberada_no_finally"),
    ("trava_sem_precondicao", 'precondition ($trava_id != null) {', 'precondition ($trava_id == null) {', "trava_ocupada_429"),
    ("mes_em_outro_fuso", '"Y-m":"UTC"', '"Y-m":"America/Sao_Paulo"', "mes_em_utc"),
    ("le_variavel_fora_da_lista", "$env.AZURE_TENANT_ID ?? \"\"", "$env.AZURE_OUTRA ?? \"\"", "env_somente_as_quatro_variaveis_e_a_chave"),
]


@pytest.mark.parametrize("nome,antigo,novo,regra", MUTACOES_SINCRONIZAR, ids=[m[0] for m in MUTACOES_SINCRONIZAR])
def test_mutacao_do_sincronizar_e_detectada(nome, antigo, novo, regra):
    mutado = _mutar(_codigo(SINCRONIZAR), antigo, novo)
    assert regra in problemas_sincronizar(mutado), f"a mutação '{nome}' não violou '{regra}'"


# ---------------------------------------------------------------------------
# Regras: função de configuração, função de estado, GET e tabela
# ---------------------------------------------------------------------------

def problemas_config(codigo: str) -> list[str]:
    r = _Regras()
    ex = r.exigir
    ex(set(re.findall(r"\$env\.(\w+)", codigo)) == ENV_SINCRONIZAR | {"AZURE_COST_API_VERSION"}, "env_conhecido")
    # api-version provada no Azure real (HTTP 200): 2023-11-01; a de 2025-03-01 NÃO pode voltar
    ex(f'var.update $versao_api {{ value = "{API_VERSION_TESTADA}" }}' in codigo and "2025-03-01" not in codigo, "versao_padrao_2023_11_01")
    for nome in ("tenant", "client", "assinatura"):
        ex(re.search(r"var \$" + nome + r"_ok \{ value = \(\(\$" + nome + r"\|strlen\) == 36 && \(\"/\^\[0-9a-fA-F\]\{8\}-\[0-9a-fA-F\]\{4\}-"
                     r"\[0-9a-fA-F\]\{4\}-\[0-9a-fA-F\]\{4\}-\[0-9a-fA-F\]\{12\}\$/\"\|regex_matches:\$" + nome + r"\)\) \}", codigo),
           f"guid_{nome}")
    ex(re.search(r'var \$segredo_ok \{ value = \(\(\$segredo\|strlen\) >= 8 && \(\$segredo\|strlen\) <= 256', codigo), "segredo_tamanho")
    ex('"/^[!-~]+$/"|regex_matches:$segredo' in codigo, "segredo_ascii_visivel")
    ex(re.search(r'var \$versao_ok \{ value = \(\(\$versao_api\|strlen\) <= 20 && \("/\^\[0-9\]\{4\}-\[0-9\]\{2\}-\[0-9\]\{2\}\(-preview\)\?\$/"\|regex_matches:\$versao_api\)\) \}', codigo), "versao_validada")
    ex(re.search(r'var \$presentes \{ value = \(\$tenant != "" && \$client != "" && \$segredo != "" && \$assinatura != ""\) \}', codigo), "presenca_das_quatro")
    # cadastro da tela: nao decifra = invalido; decifrando, so o TENANT (GUID) e a versao sao conferidos AQUI (client/segredo/assinatura: POST e sincronizar)
    ex(re.search(r'if \(\$origem == "tela" && \$decifrou == false\) \{\s*var\.update \$estado \{ value = "configuracao_invalida" \}\s*\}\s*'
                 r'elseif \(\$origem == "tela"\) \{\s*conditional \{\s*if \(\$tenant_ok == false \|\| \$versao_ok == false\) \{\s*var\.update \$estado \{ value = "configuracao_invalida" \}\s*\}\s*\}\s*\}\s*'
                 r'elseif \(\$presentes == false && \$origem == null\) \{\s*var\.update \$estado \{ value = "nao_configurado" \}\s*\}\s*'
                 r'elseif \(\$presentes == false \|\| \$tenant_ok == false \|\| \$client_ok == false \|\| \$assinatura_ok == false \|\| \$segredo_ok == false \|\| \$versao_ok == false\) \{\s*'
                 r'var\.update \$estado \{ value = "configuracao_invalida" \}', codigo), "estados_nao_configurado_e_invalida")
    resultado = _bloco(codigo, "var $resultado {\n      value = {")
    # NENHUM segredo (decifrado ou cifrado) na resposta da função: só estado, origem e versão
    ex(_chaves_do_objeto(resultado) == ["estado", "origem", "versao_api", "apelido", "tenant_final"], "devolve_so_estado_origem_e_versao")
    # apelido/tenant_final: colunas em texto simples do cadastro da tela (nada decifrado); padrão "Azure" e null fora da tela
    ex('var $apelido_exibido { value = "Azure" }' in codigo and "var $tenant_final { value = null }" in codigo, "padroes_apelido_azure_e_tenant_final_null")
    ex(re.search(r"apelido\s*: \$apelido_exibido\s+tenant_final: \$tenant_final\s*$", resultado), "resposta_apelido_e_tenant_final_guardados")
    tela_exib = _bloco_re_seguro(codigo, r'if \(\$cadastro != null\) \{')
    ex(re.search(r'if \(\(\$cadastro\.apelido \?\? ""\) != ""\) \{\s*var\.update \$apelido_exibido \{ value = \$cadastro\.apelido \}', tela_exib)
       and re.search(r'if \(\(\$cadastro\.tenant_final \?\? ""\) != ""\) \{\s*var\.update \$tenant_final \{ value = \$cadastro\.tenant_final \}', tela_exib),
       "apelido_e_tenant_final_so_do_cadastro_da_tela_sem_decifrar")
    ex(codigo.count("var.update $apelido_exibido") == 1 and codigo.count("var.update $tenant_final") == 1 and "AZURE_TENANT_ID" not in tela_exib
       and not re.search(r"\$tenant_final \{ value = [^\n]*\$(tenant|env)\b", codigo), "tenant_final_nunca_derivado_do_tenant_ou_da_variavel")
    ex(not re.search(r"\$(tenant|client|segredo|assinatura|cadastro)\b", resultado.replace("$estado", "")), "funcao_nao_devolve_segredo")
    # ORDEM: banco (decifrado com a chave do servidor) primeiro; variáveis do servidor só no `else`
    tela = _bloco_re_seguro(codigo, r'if \(\$cadastro != null\) \{')
    ex(re.search(r'db\.get azure_conexao \{\s*field_name = "chave"\s*field_value = "azure"\s*\} as \$cadastro', codigo)
       and 'var.update $origem { value = "tela" }' in tela, "banco_primeiro")
    # MINIMO: a funcao (chamada a cada GET de qualquer autenticado) decifra SO o tenant; segredo, client_id e assinatura nunca
    ex(tela.count("jwe_decode" + JWE) == 1 and "$cadastro.tenant_id_cifrado|jwe_decode" + JWE in tela and "$env.AZURE_" not in tela, "decifra_so_o_tenant_com_prov_enc_key")
    ex(not re.search(r"client_secret_cifrado|client_id_cifrado|subscription_id_cifrado", codigo) and codigo.count("jwe_decode") == 1, "funcao_nao_decifra_segredo_client_nem_assinatura")
    ex(re.search(r'catch \{\s*var\.update \$decifrou \{ value = false \}', tela) is not None, "cadastro_que_nao_decifra_e_invalido")
    ex(re.search(r'\}\s*else \{\s*var\.update \$tenant \{ value = \(\(\$env\.AZURE_TENANT_ID', codigo) is not None
       and codigo.count("$env.AZURE_TENANT_ID") == 1, "variaveis_so_como_reserva")
    ex('var.update $origem { value = "servidor" }' in codigo and re.search(r'if \(\$origem == null && \$estado != "nao_configurado"\)', codigo), "origem_servidor")
    ex(re.search(r'versao_api\s*: \(\$estado == "ok"\) \? \$versao_api : ""', codigo), "versao_so_se_ok")
    return r.violadas


def test_config_cumpre_todas_as_regras():
    assert problemas_config(_codigo(CONFIG)) == []


DEC_T = 'var.update $tenant { value = (($cadastro.tenant_id_cifrado|jwe_decode:{}:$env.PROV_ENC_KEY:"A256KW":"A256CBC-HS512")|trim) }'
EXTRA_SEGREDO = '\n            var.update $segredo { value = (($cadastro.client_secret_cifrado|jwe_decode:{}:$env.PROV_ENC_KEY:"A256KW":"A256CBC-HS512")|trim) }'
EXTRA_CLIENT = '\n            var.update $client { value = (($cadastro.client_id_cifrado|jwe_decode:{}:$env.PROV_ENC_KEY:"A256KW":"A256CBC-HS512")|trim) }'
EXTRA_ASSIN = '\n            var.update $assinatura { value = (($cadastro.subscription_id_cifrado|jwe_decode:{}:$env.PROV_ENC_KEY:"A256KW":"A256CBC-HS512")|trim) }'

MUTACOES_CONFIG = [
    ("tenant_sem_guid", '("/^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/"|regex_matches:$tenant)', "true", "guid_tenant"),
    ("client_sem_tamanho", "(($client|strlen) == 36 && ", "(", "guid_client"),
    ("assinatura_sem_guid", '("/^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/"|regex_matches:$assinatura)', "true", "guid_assinatura"),
    ("versao_sem_validacao", "var $versao_ok { value = (($versao_api|strlen) <= 20 && ", "var $versao_ok { value = (true || ", "versao_validada"),
    ("segredo_aceita_espaco", '"/^[!-~]+$/"', '"/^.+$/"', "segredo_ascii_visivel"),
    ("vazio_vira_ok", 'elseif ($presentes == false && $origem == null) {', 'elseif ($presentes == true && $origem == null) {', "estados_nao_configurado_e_invalida"),
    ("cadastro_que_nao_decifra_cai_nas_variaveis", 'if ($origem == "tela" && $decifrou == false) {', 'if ($origem == "xx" && $decifrou == false) {', "estados_nao_configurado_e_invalida"),
    ("cadastro_que_nao_decifra_vira_ok", "catch {\n            var.update $decifrou { value = false }", "catch {\n            var.update $decifrou { value = true }", "cadastro_que_nao_decifra_e_invalido"),
    ("devolve_tenant", "estado      : $estado\n        origem      : $origem", "estado      : $estado\n        tenant      : $tenant\n        origem      : $origem", "devolve_so_estado_origem_e_versao"),
    ("devolve_segredo_decifrado", "versao_api  : ($estado == \"ok\") ? $versao_api : \"\"", "versao_api  : $segredo", "funcao_nao_devolve_segredo"),
    ("devolve_o_cadastro_cifrado", "origem      : $origem\n        versao_api", "origem      : $cadastro\n        versao_api", "funcao_nao_devolve_segredo"),
    ("origem_sumiu", "origem      : $origem\n        versao_api", "versao_api", "devolve_so_estado_origem_e_versao"),
    # apelido e tenant_final (item 10)
    ("tenant_final_vira_o_tenant_inteiro", "tenant_final: $tenant_final", "tenant_final: $tenant", "funcao_nao_devolve_segredo"),
    ("tenant_final_vira_o_tenant_inteiro_na_regra_de_chaves", "tenant_final: $tenant_final", "tenant_final: $tenant", "resposta_apelido_e_tenant_final_guardados"),
    ("apelido_padrao_ausente", 'var $apelido_exibido { value = "Azure" }', 'var $apelido_exibido { value = "" }', "padroes_apelido_azure_e_tenant_final_null"),
    ("apelido_padrao_null", 'var $apelido_exibido { value = "Azure" }', "var $apelido_exibido { value = null }", "padroes_apelido_azure_e_tenant_final_null"),
    ("tenant_final_nao_null_fora_da_tela", "var $tenant_final { value = null }", 'var $tenant_final { value = "0000" }', "padroes_apelido_azure_e_tenant_final_null"),
    ("tenant_final_derivado_da_variavel", "var $tenant_final { value = null }", 'var $tenant_final { value = (($env.AZURE_TENANT_ID ?? "")|substr:0:4) }', "tenant_final_nunca_derivado_do_tenant_ou_da_variavel"),
    ("apelido_lido_fora_do_cadastro", 'if (($cadastro.apelido ?? "") != "") {', 'if (($env.AZURE_X ?? "") != "") {', "apelido_e_tenant_final_so_do_cadastro_da_tela_sem_decifrar"),
    ("tenant_final_decifrado", "value = $cadastro.tenant_final }", 'value = ($cadastro.tenant_id_cifrado|jwe_decode:{}:$env.PROV_ENC_KEY:"A256KW":"A256CBC-HS512") }', "apelido_e_tenant_final_so_do_cadastro_da_tela_sem_decifrar"),
    ("apelido_sem_guardado", "var.update $apelido_exibido { value = $cadastro.apelido }", 'var.update $apelido_exibido { value = "Azure" }', "apelido_e_tenant_final_so_do_cadastro_da_tela_sem_decifrar"),
    ("apelido_nao_devolvido", "        apelido     : $apelido_exibido\n", "", "devolve_so_estado_origem_e_versao"),
    ("variaveis_antes_do_banco", "if ($cadastro != null) {", "if ($cadastro == null) {", "banco_primeiro"),
    ("decifra_o_segredo_na_funcao", DEC_T, DEC_T + EXTRA_SEGREDO, "funcao_nao_decifra_segredo_client_nem_assinatura"),
    ("decifra_o_segredo_na_funcao_conta_decifragens", DEC_T, DEC_T + EXTRA_SEGREDO, "decifra_so_o_tenant_com_prov_enc_key"),
    ("decifra_o_client_id_na_funcao", DEC_T, DEC_T + EXTRA_CLIENT, "funcao_nao_decifra_segredo_client_nem_assinatura"),
    ("decifra_a_assinatura_na_funcao", DEC_T, DEC_T + EXTRA_ASSIN, "funcao_nao_decifra_segredo_client_nem_assinatura"),
    ("decifra_o_tenant_com_chave_errada", '$cadastro.tenant_id_cifrado|jwe_decode:{}:$env.PROV_ENC_KEY', '$cadastro.tenant_id_cifrado|jwe_decode:{}:$env.AZURE_CLIENT_ID',
     "decifra_so_o_tenant_com_prov_enc_key"),
    ("tela_nao_valida_o_tenant", "if ($tenant_ok == false || $versao_ok == false) {\n            var.update $estado", "if ($versao_ok == false) {\n            var.update $estado",
     "estados_nao_configurado_e_invalida"),
    ("tela_cai_na_regra_das_variaveis", 'elseif ($origem == "tela") {', 'elseif ($origem == "xx") {', "estados_nao_configurado_e_invalida"),
    ("variaveis_lidas_tambem_no_cadastro", 'var.update $tenant { value = (($cadastro.tenant_id_cifrado|jwe_decode:{}:$env.PROV_ENC_KEY:"A256KW":"A256CBC-HS512")|trim) }',
     'var.update $tenant { value = (($env.AZURE_TENANT_ID ?? "")|trim) }', "variaveis_so_como_reserva"),
    ("origem_servidor_perdida", 'var.update $origem { value = "servidor" }', 'var.update $origem { value = "x" }', "origem_servidor"),
    ("versao_padrao_errada", 'value = "2023-11-01"', 'value = "2020-01-01"', "versao_padrao_2023_11_01"),
    ("versao_padrao_antiga_2025", 'value = "2023-11-01"', 'value = "2025-03-01"', "versao_padrao_2023_11_01"),
    ("versao_padrao_sem_valor", 'var.update $versao_api { value = "2023-11-01" }', 'var.update $versao_api { value = "" }', "versao_padrao_2023_11_01"),
]


@pytest.mark.parametrize("nome,antigo,novo,regra", MUTACOES_CONFIG, ids=[m[0] for m in MUTACOES_CONFIG])
def test_mutacao_da_config_e_detectada(nome, antigo, novo, regra):
    assert regra in problemas_config(_mutar(_codigo(CONFIG), antigo, novo)), nome


def problemas_estado(codigo: str) -> list[str]:
    r = _Regras()
    ex = r.exigir
    ex("api.request" not in codigo and "$env" not in codigo and not re.search(r"\bdb\.(add|edit|del)\b", codigo), "somente_leitura_sem_azure")
    ex("azure_conexao" not in codigo and "jwe_" not in codigo, "estado_nao_toca_no_segredo")
    resultado = _bloco(codigo, "var $resultado {\n      value = {")
    ex(_chaves_do_objeto(resultado) == CHAVES_GET, "campos_do_contrato")
    ex("origem            : $config.origem" in resultado, "origem_vem_da_config")
    ex("apelido           : $config.apelido" in resultado and "tenant_final      : $config.tenant_final" in resultado, "apelido_e_tenant_final_vem_da_config")
    # erro de configuração inválida muda conforme a origem (cadastro da tela x variáveis do servidor)
    ex(f'var $msg_cadastro {{ value = "{MSG_CADASTRO_QUEBRADO}" }}' in codigo, "texto_fixo_do_cadastro_quebrado")
    ex(re.search(r'if \(\$config\.origem == "tela"\) \{\s*var\.update \$erro_resumo \{ value = \$msg_cadastro \}'
                 r'\s*\}\s*else \{\s*var\.update \$erro_resumo \{ value = "As variáveis de ambiente do Azure no servidor estão em formato inválido\." \}', codigo),
       "erro_de_configuracao_por_origem")
    ex('provedor          : "azure"' in resultado and "nao_alocado       : true" in resultado, "provedor_azure_nao_alocado")
    ex("var $custo { value = null }" in codigo, "custo_nasce_null")
    # custo só é atribuído dentro do bloco `tem_valor == true`, nunca por 0
    # (o segundo `$custo` e o `null` do cadastro quebrado)
    ex(re.findall(r"var\.update \$custo \{ value = ([^}]+?) \}", codigo) == ["$ultima.custo_mes_total", "null"], "custo_so_em_um_ponto")
    bloco_valor = _bloco_re_seguro(codigo, r"if \(\$ultima\.tem_valor == true\) \{")
    ex("var.update $custo { value = $ultima.custo_mes_total }" in bloco_valor, "custo_so_com_tem_valor")
    ex(re.search(r"\$custo \{ value = 0|\$custo \{ value = \(.*\?\? 0", codigo) is None, "custo_nunca_zero_por_padrao")
    # atualizado_em = última leitura bem-sucedida (ok OU sem_dados): vale com atualizado_em > 0, não com tem_valor.
    # SEM cache de 4 h: o atualizado_em NÃO entra mais no cálculo da próxima leitura.
    bloco_leitura = _bloco_re_seguro(codigo, r"if \(\(\$ultima\.atualizado_em \?\? 0\) > 0\) \{")
    ex("var.update $atualizado_em { value = $ultima.atualizado_em }" in bloco_leitura and "$proxima" not in bloco_leitura
       and re.findall(r"var\.update \$atualizado_em \{ value = ([^}]+?) \}", codigo) == ["$ultima.atualizado_em", "null"]
       and "$ultima.atualizado_em +" not in codigo, "atualizado_em_da_leitura_bem_sucedida")
    # cadastro da tela quebrado (achado pelo sincronizar: status "indisponivel" + texto fixo) vira configuracao_invalida, sem custo/hora/mes/proxima leitura
    quebrado = _bloco_re_seguro(codigo, r'if \(\$status == "indisponivel" && \$erro_resumo == \$msg_cadastro\) \{')
    ex(all(f in quebrado for f in ('var.update $status { value = "configuracao_invalida" }', "var.update $configurado { value = false }",
                                   "var.update $custo { value = null }", "var.update $moeda { value = null }", "var.update $atualizado_em { value = null }",
                                   "var.update $mes_ref { value = null }", "var.update $proxima { value = null }")),
       "cadastro_quebrado_vira_configuracao_invalida")
    ex(codigo.find('if ($status == "indisponivel" && $erro_resumo == $msg_cadastro)') > codigo.find("var.update $proxima { value = $ultima.bloqueado_ate }")
       and codigo.find('if ($status == "indisponivel" && $erro_resumo == $msg_cadastro)') < codigo.find("var $resultado {"), "cadastro_quebrado_decidido_apos_o_calculo")
    ex("atualizado_em" not in bloco_valor and "$proxima" not in bloco_valor and "$moeda" in bloco_valor, "valor_so_custo_e_moeda_com_tem_valor")
    ex(re.search(r"elseif \(\$ultima\.mes_referencia != \$mes_atual\) \{\s*var\.update \$status \{ value = \"desatualizado\" \}", codigo), "desatualizado_quando_virou_o_mes")
    desat = _bloco_re_seguro(codigo, r"elseif \(\$ultima\.mes_referencia != \$mes_atual\) \{")
    ex(desat != "" and "$custo" not in desat and "$ultima.custo_mes_total" not in desat, "desatualizado_nao_exibe_custo")
    # mês anterior (inclusive um sem_dados antigo): sem hora de mês velho como se fosse a atual
    ex(desat != "" and "$atualizado_em" not in desat and "$ultima.atualizado_em" not in desat and "$proxima" not in desat,
       "desatualizado_nao_exibe_atualizado_em")
    ex(re.search(r'if \(\$ultima == null\) \{\s*var\.update \$status \{ value = "sem_leitura" \}', codigo), "sem_leitura")
    ex(re.search(r"var \$mes_atual \{ value = \$agora_ms\|format_timestamp:\"Y-m\":\"UTC\" \}", codigo), "mes_em_utc")
    ex(re.search(r'if \(\$config\.estado == "configuracao_invalida"\)', codigo) and "var $status { value = $config.estado }" in codigo, "estados_de_config")
    ex(re.search(r"var \$configurado \{ value = \(\$config\.estado == \"ok\"\) \}", codigo), "configurado_so_se_ok")
    ex("janela_cache_ms" not in codigo and "14400000" not in codigo, "sem_cache_de_4h_na_proxima_leitura")
    ex(re.search(r"sort = \{mes_referencia: \"desc\"\}", codigo), "ordena_pelo_mes")
    # próxima leitura = o MAIOR entre o cooldown de 60 s e o bloqueio por 429 (SEM cache de 4 h)
    ex("var $cooldown_ms { value = 60000 }" in codigo, "cooldown_de_60s")
    ex(re.search(r"if \(\(\$ultima\.tentativa_em \?\? 0\) > 0\) \{\s*"
                 r"var\.update \$proxima \{ value = \$ultima\.tentativa_em \+ \$cooldown_ms \}", codigo), "proxima_e_o_cooldown")
    ex(re.search(r"if \(\(\$ultima\.bloqueado_ate \?\? 0\) > \$agora_ms && \(\$proxima == null \|\| \$ultima\.bloqueado_ate > \$proxima\)\) \{\s*"
                 r"var\.update \$proxima \{ value = \$ultima\.bloqueado_ate \}", codigo), "bloqueio_so_se_maior")
    return r.violadas


def test_estado_cumpre_todas_as_regras():
    assert problemas_estado(_codigo(ESTADO)) == []


MUTACOES_ESTADO = [
    ("custo_zero_por_padrao", "var $custo { value = null }", "var $custo { value = 0 }", "custo_nasce_null"),
    ("custo_sem_tem_valor", "if ($ultima.tem_valor == true) {", "if ($ultima.status != \"x\") {", "custo_so_com_tem_valor"),
    ("desatualizado_mostra_custo", 'var.update $status { value = "desatualizado" }',
     'var.update $status { value = "desatualizado" }\n            var.update $custo { value = $ultima.custo_mes_total }', "custo_so_em_um_ponto"),
    ("atualizado_em_so_com_valor", "if (($ultima.atualizado_em ?? 0) > 0) {", "if ($ultima.tem_valor == true) {", "atualizado_em_da_leitura_bem_sucedida"),
    ("cache_volta_na_proxima_leitura", "var.update $atualizado_em { value = $ultima.atualizado_em }",
     "var.update $atualizado_em { value = $ultima.atualizado_em }\n                var.update $proxima { value = $ultima.atualizado_em + 14400000 }", "atualizado_em_da_leitura_bem_sucedida"),
    ("cache_volta_com_a_janela", "var $cooldown_ms { value = 60000 }", "var $cooldown_ms { value = 60000 }\n    var $janela_cache_ms { value = 14400000 }", "sem_cache_de_4h_na_proxima_leitura"),
    ("origem_removida_do_estado", "        origem            : $config.origem\n", "", "campos_do_contrato"),
    ("origem_fixa", "origem            : $config.origem", 'origem            : "tela"', "origem_vem_da_config"),
    ("apelido_fixo", "apelido           : $config.apelido", 'apelido           : "Azure"', "apelido_e_tenant_final_vem_da_config"),
    ("tenant_final_fixo", "tenant_final      : $config.tenant_final", 'tenant_final      : "0000"', "apelido_e_tenant_final_vem_da_config"),
    ("apelido_removido_do_estado", "        apelido           : $config.apelido\n", "", "campos_do_contrato"),
    ("tenant_final_removido_do_estado", "        tenant_final      : $config.tenant_final\n", "", "campos_do_contrato"),
    ("estado_le_o_cadastro_para_o_tenant_final", "var $agora_ms { value = now|to_int }", "var $agora_ms { value = now|to_int }\n    db.get azure_conexao {\n      field_name = \"chave\"\n      field_value = \"azure\"\n    } as $c", "estado_nao_toca_no_segredo"),
    ("estado_decifra_segredo", "var $agora_ms { value = now|to_int }", "var $agora_ms { value = now|to_int }\n    var $x { value = $y|jwe_decode:{}:$env.PROV_ENC_KEY:\"A256KW\":\"A256CBC-HS512\" }", "estado_nao_toca_no_segredo"),
    ("erro_igual_para_as_duas_origens", 'if ($config.origem == "tela") {', 'if ($config.origem == "xx") {', "erro_de_configuracao_por_origem"),
    ("texto_do_cadastro_quebrado_diferente", 'var $msg_cadastro { value = "O cadastro do Azure guardado', 'var $msg_cadastro { value = "Cadastro guardado', "texto_fixo_do_cadastro_quebrado"),
    ("cadastro_quebrado_mantem_o_custo", "        var.update $custo { value = null }\n        var.update $moeda", "        var.update $moeda", "cadastro_quebrado_vira_configuracao_invalida"),
    ("cadastro_quebrado_continua_configurado", "        var.update $configurado { value = false }\n", "", "cadastro_quebrado_vira_configuracao_invalida"),
    ("cadastro_quebrado_nao_reconhecido", 'if ($status == "indisponivel" && $erro_resumo == $msg_cadastro) {', 'if ($status == "indisponivel" && $erro_resumo == "x") {',
     "cadastro_quebrado_vira_configuracao_invalida"),
    ("cadastro_quebrado_qualquer_indisponivel", 'if ($status == "indisponivel" && $erro_resumo == $msg_cadastro) {', 'if ($status == "indisponivel") {',
     "cadastro_quebrado_vira_configuracao_invalida"),
    ("atualizado_em_dentro_do_bloco_do_valor", "var.update $moeda { value = $ultima.moeda }\n",
     "var.update $moeda { value = $ultima.moeda }\n                var.update $atualizado_em { value = $ultima.atualizado_em }\n", "valor_so_custo_e_moeda_com_tem_valor"),
    ("desatualizado_mostra_hora_antiga", 'var.update $mes_ref { value = $ultima.mes_referencia }\n            var.update $erro_resumo { value = "O último valor',
     'var.update $mes_ref { value = $ultima.mes_referencia }\n            var.update $atualizado_em { value = $ultima.atualizado_em }\n            var.update $erro_resumo { value = "O último valor',
     "desatualizado_nao_exibe_atualizado_em"),
    ("virou_o_mes_ignorado", "elseif ($ultima.mes_referencia != $mes_atual) {", "elseif ($ultima.mes_referencia == \"x\") {", "desatualizado_quando_virou_o_mes"),
    ("chama_azure", "var $agora_ms { value = now|to_int }", "var $agora_ms { value = now|to_int }\n    api.request { url = \"https://x.invalid\" }", "somente_leitura_sem_azure"),
    ("campo_extra", "proxima_leitura_em: $proxima", "proxima_leitura_em: $proxima\n        tenant            : $env.AZURE_TENANT_ID", "campos_do_contrato"),
    ("campo_extra_com_cadastro", "origem            : $config.origem", "origem            : $config.origem\n        segredo           : $config.segredo", "campos_do_contrato"),
    ("configurado_sempre", 'var $configurado { value = ($config.estado == "ok") }', "var $configurado { value = true }", "configurado_so_se_ok"),
    ("mes_em_outro_fuso", '"Y-m":"UTC"', '"Y-m":"America/Sao_Paulo"', "mes_em_utc"),
    ("proxima_sem_cooldown", "if (($ultima.tentativa_em ?? 0) > 0) {", "if (($ultima.tentativa_em ?? 0) > 99999999999999) {", "proxima_e_o_cooldown"),
    ("cooldown_de_1h", "var $cooldown_ms { value = 60000 }", "var $cooldown_ms { value = 3600000 }", "cooldown_de_60s"),
    ("bloqueio_encurta", "($proxima == null || $ultima.bloqueado_ate > $proxima)", "true", "bloqueio_so_se_maior"),
]


@pytest.mark.parametrize("nome,antigo,novo,regra", MUTACOES_ESTADO, ids=[m[0] for m in MUTACOES_ESTADO])
def test_mutacao_do_estado_e_detectada(nome, antigo, novo, regra):
    assert regra in problemas_estado(_mutar(_codigo(ESTADO), antigo, novo)), nome


def problemas_get(codigo: str) -> list[str]:
    r = _Regras()
    ex = r.exigir
    ex('query "azure/custo" verb=GET' in codigo and 'api_group = "app"' in codigo and 'auth = "usuarios"' in codigo, "rota_get_autenticada")
    ex(_precondicao_pos(codigo, '$usuario_sessao != null && $usuario_sessao.status == "ativo"', "unauthorized", '"Token inválido ou expirado"') >= 0, "usuario_ativo")
    ex("role" not in codigo, "qualquer_usuario_autenticado")
    ex("api.request" not in codigo and "$env" not in codigo and not re.search(r"\bdb\.(add|edit|del)\b", codigo), "nao_chama_azure_nem_grava")
    ex(re.search(r'function\.run "costguard/azure_custo_estado" \{\s*input = \{\}\s*\} as \$resposta', codigo) and "response = $resposta" in codigo, "devolve_o_estado_guardado")
    # o GET só repassa a função (que traz `origem`): nada de credencial nem de cadastro
    ex("azure_conexao" not in codigo and "jwe_" not in codigo and "PROV_ENC_KEY" not in codigo, "get_nao_toca_no_cadastro")
    return r.violadas


def test_get_cumpre_todas_as_regras():
    assert problemas_get(_codigo(OBTER)) == []


MUTACOES_GET = [
    ("sem_usuario_ativo", '$usuario_sessao != null && $usuario_sessao.status == "ativo"', "$usuario_sessao != null", "usuario_ativo"),
    ("chama_azure", "stack {", 'stack {\n    api.request { url = "https://x.invalid" }', "nao_chama_azure_nem_grava"),
    ("exige_admin", "$usuario_sessao != null && $usuario_sessao.status == \"ativo\"", "$usuario_sessao.role == \"admin\"", "usuario_ativo"),
    ("le_env", "stack {", "stack {\n    var $x { value = $env.AZURE_TENANT_ID }", "nao_chama_azure_nem_grava"),
]


@pytest.mark.parametrize("nome,antigo,novo,regra", MUTACOES_GET, ids=[m[0] for m in MUTACOES_GET])
def test_mutacao_do_get_e_detectada(nome, antigo, novo, regra):
    assert regra in problemas_get(_mutar(_codigo(OBTER), antigo, novo)), nome


def problemas_tabela(codigo: str) -> list[str]:
    r = _Regras()
    ex = r.exigir
    ex("table provedor_externo_leitura {" in codigo, "nome_da_tabela")
    colunas = re.findall(r"^\s*(?:int|text|decimal|bool|timestamp|enum)\s+(\w+)", codigo, re.M)
    ex(colunas == ["id", "provedor", "mes_referencia", "custo_mes_total", "moeda", "atualizado_em", "tem_valor", "status",
                   "erro_resumo", "tentativa_em", "bloqueado_ate", "criado_em"], "colunas_esperadas")
    ex(not re.search(r"tenant|client|secret|segredo|subscription|assinatura|token|senha|password", "\n".join(colunas), re.I), "sem_dados_de_assinatura_ou_segredo")
    ex('{type: "btree|unique", field: [{name: "provedor", op: "asc"}, {name: "mes_referencia", op: "asc"}]}' in codigo, "uma_linha_por_provedor_e_mes")
    ex("bool tem_valor?=false" in codigo, "tem_valor_distingue_sem_valor_de_zero")
    # custo anulável (sem padrão 0): linha nova sem valor guarda null
    ex(re.search(r"^\s*decimal custo_mes_total\?\s*$", codigo, re.M) is not None, "custo_anulavel_sem_padrao_zero")
    # status: conjunto fechado (enum), não texto livre
    ex(re.search(r'enum status\?=sem_leitura \{\s*values = \["sem_leitura", "ok", "sem_dados", "sem_permissao", "indisponivel", "resposta_incompleta"\]\s*\}', codigo) is not None,
       "status_enum_fechado")
    return r.violadas


def test_tabela_cumpre_todas_as_regras():
    assert problemas_tabela(_codigo(TABELA)) == []


MUTACOES_TABELA = [
    ("coluna_de_segredo", "    int id\n", "    int id\n    text client_secret?\n", "sem_dados_de_assinatura_ou_segredo"),
    ("coluna_assinatura", "    int id\n", "    int id\n    text assinatura_id?\n", "sem_dados_de_assinatura_ou_segredo"),
    ("sem_indice_unico", "btree|unique", "btree", "uma_linha_por_provedor_e_mes"),
    ("sem_tem_valor", "bool tem_valor?=false", "bool tem_valor2?=false", "tem_valor_distingue_sem_valor_de_zero"),
    ("custo_com_padrao_zero", "decimal custo_mes_total?", "decimal custo_mes_total?=0", "custo_anulavel_sem_padrao_zero"),
    ("status_texto_livre", "enum status?=sem_leitura {", "enum status_x?=sem_leitura {", "status_enum_fechado"),
    ("status_com_valor_a_mais", '"resposta_incompleta"]', '"resposta_incompleta", "qualquer"]', "status_enum_fechado"),
]


@pytest.mark.parametrize("nome,antigo,novo,regra", MUTACOES_TABELA, ids=[m[0] for m in MUTACOES_TABELA])
def test_mutacao_da_tabela_e_detectada(nome, antigo, novo, regra):
    assert regra in problemas_tabela(_mutar(_codigo(TABELA), antigo, novo)), nome


# ---------------------------------------------------------------------------
# Isolamento: o Azure não entra no ciclo automático nem em nenhum outro fluxo
# ---------------------------------------------------------------------------

def _outros_arquivos_xano():
    return [p for p in XANO.rglob("*.xs") if p not in ARQUIVOS_AZURE]


def test_nenhum_outro_xs_usa_azure_nem_a_tabela_nem_as_funcoes():
    outros = _outros_arquivos_xano()
    assert outros, "esperava encontrar os demais .xs"
    for arquivo in outros:
        codigo = _codigo(arquivo)
        for proibido in ("azure_custo_estado", "azure_config_estado", "provedor_externo_leitura", "AZURE_", "azure/custo",
                         "management.azure.com", "login.microsoftonline.com"):
            assert proibido not in codigo, f"{arquivo.name} não pode usar `{proibido}`"


def test_ciclo_automatico_nao_chama_o_azure():
    codigo = _codigo(APP / "sincronizacao_automatica_POST.xs")
    assert "azure" not in codigo.lower()
    assert re.findall(r'function\.run "([^"]+)"', codigo) == ["costguard/sincronizar_inventario"]
    assert 'tipo == "aws"' in codigo, "o ciclo automático só percorre provedores AWS"


def test_painel_e_resumos_nao_misturam_o_custo_azure():
    for nome in ("painel_GET.xs", "painel_projeto_GET.xs", "projetos_resumo_consumo_mtd_GET.xs"):
        assert "azure" not in _codigo(APP / nome).lower(), nome
    for nome in ("resumo_consumo.xs", "avaliar_alertas.xs", "lista_alertas.xs", "recursos_nao_classificados.xs"):
        assert "azure" not in _codigo(FUNCOES / nome).lower(), nome


# ---------------------------------------------------------------------------
# Segredos e IDs: nada real em .xs, fixtures ou testes
# ---------------------------------------------------------------------------

GUID_RE = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")


def test_arquivos_azure_nao_trazem_guid_real_nem_segredo():
    alvos = list(ARQUIVOS_AZURE) + sorted(FIXTURES.glob("azure_*.json"))
    for arquivo in alvos:
        texto = _ler(arquivo)
        for guid in GUID_RE.findall(texto):
            # GUIDs de exemplo zerados; no próprio teste só a máscara genérica de regex/exemplos permitidos.
            assert set(guid.replace("-", "")) == {"0"}, f"{arquivo.name}: GUID não genérico"
        assert not re.search(r"client_secret\s*[:=]\s*\"[^\"$]", texto), f"{arquivo.name}: segredo literal"
        assert not re.search(r"eyJ[A-Za-z0-9_-]{10,}", texto), f"{arquivo.name}: parece JWT real"
        assert not re.search(r"\b[A-Za-z0-9~._-]{3}[0-9]Q~[A-Za-z0-9~._-]{20,}", texto), f"{arquivo.name}: parece client secret do Azure"


def test_fixtures_so_com_valores_genericos():
    for arquivo in sorted(FIXTURES.glob("azure_*.json")):
        json.loads(_ler(arquivo))  # JSON válido
    token = json.loads(_ler(FIXTURES / "azure_token_ok.json"))
    assert "ficticio" in token["access_token"]
    assert not any(".invalid" not in v for v in re.findall(r'https?://[^"]+', _ler(FIXTURES / "azure_query_nextlink.json")) if "management.azure.com" in v)


# ---------------------------------------------------------------------------
# ESPELHO em Python (parâmetros extraídos do .xs; dados nas fixtures)
# ---------------------------------------------------------------------------

def _fixture(nome: str):
    return json.loads(_ler(FIXTURES / nome))


def _parametros():
    codigo = _codigo(SINCRONIZAR)
    return {
        "coluna_custo": re.search(r'if \(\$nome_coluna == "(\w+)"\)', codigo).group(1),
        "coluna_moeda": re.search(r'elseif \(\$nome_coluna == "(\w+)"\)', codigo).group(1),
        "padrao_429": int(re.search(r"var\.update \$segundos_restantes \{ value = (\d+) \}\n\s*conditional \{\s*if \(\$seg_max", codigo).group(1)),
        "teto_429": int(re.search(r"\$segundos_restantes > (\d+)\) \{", codigo).group(1)),
        "trecho_retry": re.search(r'\|contains:"([^"]+)"', codigo).group(1),
        "cooldown_ms": int(re.search(r"var \$cooldown_ms \{ value = (\d+) \}", codigo).group(1)),
        "moeda_tamanho": int(re.search(r"\(\$moeda_txt\|strlen\) == (\d+)", codigo).group(1)),
        "re_token": re.search(r'"(/\^\[A-Za-z0-9._~-\]\+\$/)"\|regex_matches:\$t_token', codigo).group(1)[1:-1],
        "re_valor": re.search(r'"(/\^-\?\[0-9\]\+.*?\$/)"\|regex_matches:\$valor_txt', codigo).group(1)[1:-1],
        "re_moeda": re.search(r'"(/\^\[A-Za-z\]\{3\}\$/)"\|regex_matches:\$moeda_txt', codigo).group(1)[1:-1],
    }


def interpretar_resposta(status: int, resultado: dict | None):
    """Espelho da leitura da consulta: devolve (desfecho, custo, moeda)."""
    p = _parametros()
    props = ((resultado or {}).get("properties") or {})
    colunas, linhas, proximo = props.get("columns") or [], props.get("rows") or [], str(props.get("nextLink") or "")
    if status == 200:
        if proximo != "":
            return "resposta_incompleta", None, None
        if len(linhas) == 0:
            return "sem_dados", None, None
        if len(linhas) > 1:
            return "resposta_incompleta", None, None
        i_custo = i_moeda = -1
        for i, c in enumerate(colunas):
            nome = str(c.get("name") or "").lower()
            if nome == p["coluna_custo"]:
                i_custo = i
            elif nome == p["coluna_moeda"]:
                i_moeda = i
        valor = moeda = ""
        if i_custo >= 0 and i_moeda >= 0:
            valor, moeda = str(linhas[0][i_custo]), str(linhas[0][i_moeda])
        if re.fullmatch(p["re_valor"], valor) and re.fullmatch(p["re_moeda"], moeda):
            return "ok", float(valor), moeda.upper()
        return "indisponivel", None, None
    if status == 204:
        return "sem_dados", None, None
    if status in (401, 403):
        return "sem_permissao", None, None
    if status == 429:
        return "limite", None, None
    return "indisponivel", None, None


def segundos_do_429(cabecalhos: list[str]) -> int:
    """Espelho: MAIOR valor entre TODOS os cabeçalhos cujo NOME CONTÉM `retry-after` (sem diferenciar maiúsculas); sem nenhum, 60; limitado a 1..3600."""
    p = _parametros()
    maior = -1
    for h in cabecalhos:
        baixo = h.lower()
        nome = baixo.split(":")[0].strip()
        valor = baixo.split(":")[-1].strip()
        if p["trecho_retry"] in nome and re.fullmatch(r"[0-9]{1,9}", valor):
            maior = max(maior, int(valor))
    seg = maior if maior >= 0 else p["padrao_429"]
    return max(1, min(p["teto_429"], seg))


def moeda_valida(texto: str) -> bool:
    """Espelho: tamanho exato E regex. `re.search` com `$` aceita "\\n" final, como se supõe do Xano (NÃO VERIFICADO)."""
    p = _parametros()
    return len(texto) == p["moeda_tamanho"] and re.search(p["re_moeda"], texto) is not None


def token_valido(texto: str) -> bool:
    p = _parametros()
    return 20 <= len(texto) <= 8192 and len(texto.strip()) == len(texto) and re.search(p["re_token"], texto) is not None


def decidir_gate(linha: dict | None, agora: int) -> str:
    """Espelho da ordem do gate do POST (SEM cache de 4 h): bloqueio 429 > cooldown 60 s > consulta."""
    p = _parametros()
    if linha is not None and linha.get("bloqueado_ate", 0) > agora:
        return "limite"
    if linha is not None and linha.get("tentativa_em", 0) > 0 and (agora - linha["tentativa_em"]) < p["cooldown_ms"]:
        return "cooldown"
    return "consulta"


def proxima_leitura(linha: dict, agora: int):
    """Espelho de azure_custo_estado: o MAIOR entre o cooldown e o bloqueio por 429; instante passado vira None."""
    cooldown = int(re.search(r"var \$cooldown_ms \{ value = (\d+) \}", _codigo(ESTADO)).group(1))
    proxima = linha["tentativa_em"] + cooldown if linha.get("tentativa_em", 0) > 0 else None
    if linha.get("bloqueado_ate", 0) > agora and (proxima is None or linha["bloqueado_ate"] > proxima):
        proxima = linha["bloqueado_ate"]
    return None if proxima is not None and proxima <= agora else proxima


def aplicar_desfecho(linha: dict, desfecho: str, agora: int, custo=None, moeda=None, segundos=60) -> dict:
    """Espelho do passo (3) do POST: o que é gravado na linha do mês conforme o desfecho."""
    n = dict(linha)
    n["tentativa_em"] = agora
    if desfecho == "ok":
        n.update(custo_mes_total=custo, moeda=moeda, atualizado_em=agora, tem_valor=True, status="ok", erro_resumo="", bloqueado_ate=0)
    elif desfecho == "sem_dados":
        n.update(custo_mes_total=None, moeda="", atualizado_em=agora, tem_valor=False, status="sem_dados", erro_resumo="", bloqueado_ate=0)
    elif desfecho in ("sem_permissao", "resposta_incompleta"):
        n.update(custo_mes_total=None, atualizado_em=0, tem_valor=False, status=desfecho, erro_resumo="erro")
    elif desfecho == "indisponivel":
        n.update(status="indisponivel", erro_resumo="erro")  # mantém valor, tem_valor e atualizado_em
    elif desfecho == "limite":
        n.update(bloqueado_ate=agora + segundos * 1000)
    return n


def exibicao_do_cadastro(origem: str | None, cadastro: dict | None) -> tuple[str, str | None]:
    """Espelho de azure_config_estado: (apelido, tenant_final). Só o cadastro da tela conta; padrão "Azure" e null."""
    if origem != "tela" or not cadastro:
        return "Azure", None
    return (cadastro.get("apelido") or "Azure"), (cadastro.get("tenant_final") or None)


def resposta_do_get(linha: dict | None, mes_atual: str, agora: int, origem: str | None = "servidor", cadastro: dict | None = None) -> dict:
    """Espelho de azure_custo_estado para uma linha de provedor_externo_leitura (configuração ok)."""
    apelido, tenant_final = exibicao_do_cadastro(origem, cadastro)
    r = {"provedor": "azure", "configurado": True, "status": "sem_leitura", "nao_alocado": True, "custo_mes_total": None,
         "moeda": None, "atualizado_em": None, "mes_referencia": None, "erro_resumo": None, "proxima_leitura_em": None,
         "origem": origem, "apelido": apelido, "tenant_final": tenant_final}
    if linha is None:
        return r
    if linha["mes_referencia"] != mes_atual:
        r.update(status="desatualizado", mes_referencia=linha["mes_referencia"],
                 erro_resumo="O último valor guardado é de um mês anterior. Sincronize para ler o mês atual.")
        return r
    r.update(status=linha["status"], mes_referencia=linha["mes_referencia"], erro_resumo=linha.get("erro_resumo") or None)
    if linha.get("tem_valor"):
        r.update(custo_mes_total=linha["custo_mes_total"], moeda=linha["moeda"])
    if linha.get("atualizado_em", 0) > 0:
        r["atualizado_em"] = linha["atualizado_em"]
    r["proxima_leitura_em"] = proxima_leitura(linha, agora)
    return r


def aplicar_cadastro_quebrado(r: dict) -> dict:
    """Espelho do bloco final de azure_custo_estado: `indisponivel` + texto fixo (gravado pelo sincronizar) vira configuracao_invalida."""
    if r["status"] == "indisponivel" and r["erro_resumo"] == MSG_CADASTRO_QUEBRADO:
        r = {**r, "status": "configuracao_invalida", "configurado": False, "custo_mes_total": None, "moeda": None,
             "atualizado_em": None, "mes_referencia": None, "proxima_leitura_em": None}
    return r


def test_cadastro_quebrado_achado_pelo_sincronizar_vira_configuracao_invalida_sem_custo_nem_200_silencioso():
    t0 = 1_790_000_000_000
    # a linha tinha valor ok; o cadastro quebrou depois: o sincronizar grava so status + texto fixo (valor e hora ficam na linha)
    linha = {**aplicar_desfecho(LINHA_VAZIA, "ok", t0, 123.45, "USD"), "status": "indisponivel", "erro_resumo": MSG_CADASTRO_QUEBRADO}
    get = aplicar_cadastro_quebrado(resposta_do_get(linha, MES, t0 + 5_000, "tela", {"apelido": "Azure produção", "tenant_final": "0000"}))
    assert get == _fixture("azure_custo_get_configuracao_invalida_tela.json")
    # o mesmo estado na resposta do POST (origem null: nada foi consultado; origem_credencial "tela")
    post = _fixture("azure_custo_sincronizar_cadastro_invalido.json")
    assert {k: v for k, v in post.items() if k not in ("origem", "origem_credencial")} == {k: v for k, v in get.items() if k not in ("origem", "apelido", "tenant_final")}
    assert post["origem"] is None and post["origem_credencial"] == "tela" and post["status"] == "configuracao_invalida"
    # um indisponivel do Azure (5xx/timeout) NAO e cadastro quebrado: segue mantendo o ultimo valor
    outro = {**linha, "erro_resumo": "O Azure não respondeu agora. Mostrando o último valor guardado, se houver."}
    r = aplicar_cadastro_quebrado(resposta_do_get(outro, MES, t0 + 5_000))
    assert r["status"] == "indisponivel" and r["custo_mes_total"] == 123.45


def test_texto_fixo_do_cadastro_quebrado_e_o_mesmo_na_funcao_de_estado_e_no_sincronizar():
    assert f'var $msg_cadastro {{ value = "{MSG_CADASTRO_QUEBRADO}" }}' in _codigo(ESTADO)
    assert _codigo(SINCRONIZAR).count(MSG_CADASTRO_QUEBRADO) == 2


def test_espelho_le_colunas_pelo_nome_independente_da_posicao():
    assert interpretar_resposta(200, _fixture("azure_query_200.json")) == ("ok", 123.45, "USD")
    assert interpretar_resposta(200, _fixture("azure_query_200_colunas_invertidas.json")) == ("ok", 67.5, "USD")


def test_espelho_sem_linhas_ou_204_e_sem_dados_e_nunca_zero():
    for status, corpo in ((200, _fixture("azure_query_sem_linhas.json")), (204, None)):
        desfecho, custo, moeda = interpretar_resposta(status, corpo)
        assert desfecho == "sem_dados" and custo is None and moeda is None


def test_caso_real_mes_sem_consumo_200_com_rows_vazia_e_sem_coluna_de_moeda():
    corpo = _fixture("azure_query_sem_linhas.json")
    assert corpo["properties"]["rows"] == []
    assert [c["name"] for c in corpo["properties"]["columns"]] == ["Cost"]  # a moeda NÃO vem
    assert interpretar_resposta(200, corpo) == ("sem_dados", None, None)


def test_colunas_reais_cost_e_currency_sem_diferenciar_maiusculas():
    for nomes in (["Cost", "Currency"], ["cost", "currency"], ["COST", "CURRENCY"], ["Currency", "COST"]):
        colunas = [{"name": n} for n in nomes]
        valores = {"cost": 9.5, "currency": "BRL"}
        linha = [valores[n.lower()] for n in nomes]
        corpo = {"properties": {"columns": colunas, "rows": [linha]}}
        assert interpretar_resposta(200, corpo) == ("ok", 9.5, "BRL"), nomes


def test_com_linhas_mas_sem_moeda_ou_com_nome_antigo_e_indisponivel_sem_adivinhar_moeda():
    for nome in ("azure_query_sem_moeda.json", "azure_query_coluna_pretaxcost.json", "azure_query_coluna_ausente.json"):
        assert interpretar_resposta(200, _fixture(nome)) == ("indisponivel", None, None), nome


@pytest.mark.parametrize("valor", ["abc", "", "1,5", "1 2", "NaN", "12\n"])
def test_com_linhas_e_valor_invalido_e_indisponivel(valor):
    corpo = {"properties": {"columns": [{"name": "Cost"}, {"name": "Currency"}], "rows": [[valor, "USD"]]}}
    assert interpretar_resposta(200, corpo) == ("indisponivel", None, None)


def test_espelho_nextlink_e_mais_de_uma_linha_nao_paginam_nem_guardam_valor():
    for nome in ("azure_query_nextlink.json", "azure_query_duas_linhas.json"):
        assert interpretar_resposta(200, _fixture(nome)) == ("resposta_incompleta", None, None)


def test_espelho_coluna_ausente_nao_inventa_valor():
    assert interpretar_resposta(200, _fixture("azure_query_coluna_ausente.json")) == ("indisponivel", None, None)


@pytest.mark.parametrize("status,esperado", [(401, "sem_permissao"), (403, "sem_permissao"), (429, "limite"),
                                             (500, "indisponivel"), (503, "indisponivel"), (0, "indisponivel"), (404, "indisponivel")])
def test_espelho_mapeia_status_http(status, esperado):
    assert interpretar_resposta(status, None)[0] == esperado


@pytest.mark.parametrize("caso,esperado", [
    ("real_clienttype_retry_after", 7), ("somente_qpu", 25), ("qpu_e_retry_after", 90), ("somente_retry_after", 30), ("sem_cabecalho", 60),
    ("acima_do_teto", 3600), ("zero", 1), ("retry_after_data_http", 60), ("valor_nao_numerico", 60),
    ("qpu_maior_que_retry_after", 120), ("maior_entre_clienttype_qpu_e_padrao", 15), ("retry_after_no_meio_do_nome", 40),
    ("remaining_nao_conta", 60), ("retry_after_ms_conta_como_segundos", 3600), ("token_e_consulta_mesmo_calculo", 45),
])
def test_espelho_segundos_do_429_entre_1_e_3600(caso, esperado):
    assert segundos_do_429(_fixture("azure_429_cabecalhos.json")[caso]) == esperado


def test_espelho_parametros_do_xs():
    p = _parametros()
    assert (p["coluna_custo"], p["coluna_moeda"]) == ("cost", "currency")
    assert (p["padrao_429"], p["teto_429"]) == (60, 3600)
    assert "janela_ms" not in p, "não há mais cache de 4 h"
    assert (p["cooldown_ms"], p["moeda_tamanho"], p["trecho_retry"]) == (60_000, 3, "retry-after")


def test_api_version_padrao_e_a_testada_no_azure_real():
    assert re.search(r'var\.update \$versao_api \{ value = "([^"]+)" \}', _codigo(CONFIG)).group(1) == API_VERSION_TESTADA == "2023-11-01"
    # a versão sai da função de configuração e vai na URL da consulta
    assert "$config.versao_api" in _codigo(SINCRONIZAR) and "2025-03-01" not in "".join(_ler(a) for a in ARQUIVOS_AZURE)


@pytest.mark.parametrize("texto,esperado", [
    ("USD", True), ("brl", True), ("USD\n", False), ("US", False), ("USDD", False), ("U D", False), ("", False),
])
def test_espelho_moeda_exige_tres_caracteres_e_recusa_quebra_final(texto, esperado):
    assert moeda_valida(texto) is esperado


@pytest.mark.parametrize("texto,esperado", [
    ("a" * 20, True), ("abc.def-ghi_jkl~mnop", True), ("a" * 19, False), ("a" * 8193, False),
    ("a" * 20 + "\n", False), ("a" * 20 + " ", False), (" " + "a" * 20, False), ("a" * 10 + " " + "a" * 10, False),
    ("a" * 10 + "\r\n" + "a" * 10, False),
])
def test_espelho_token_sem_espaco_nem_quebra(texto, esperado):
    assert token_valido(texto) is esperado


def _re_guid() -> "re.Pattern[str]":
    m = re.search(r'var \$tenant_ok \{ value = .*?regex_matches:\$tenant\)\) \}', _codigo(CONFIG))
    padrao = re.search(r'"/(\^.*?\$)/"', m.group(0)).group(1)
    return re.compile(padrao)


def valida_guid(texto: str) -> bool:
    """Espelho: trim, tamanho 36 e regex (o `$` do Python também aceita \\n final, daí o tamanho)."""
    t = texto.strip()
    return len(t) == 36 and _re_guid().search(t) is not None


@pytest.mark.parametrize("valor", [GUID_ZERO, "ABCDEF01-2345-6789-abcd-ef0123456789", f"  {GUID_ZERO}  "])
def test_espelho_guid_valido(valor):
    assert valida_guid(valor)


@pytest.mark.parametrize("valor", [
    "", "contoso.onmicrosoft.com", "../../etc/passwd", f"{GUID_ZERO}/../x", f"{GUID_ZERO}?x=1", f"{GUID_ZERO}#x", f"{GUID_ZERO}\nX",
    f"{GUID_ZERO[:-1]}g", GUID_ZERO.replace("-", ""), GUID_ZERO + "0", "{" + GUID_ZERO + "}", "%2e%2e" + GUID_ZERO[6:],
])
def test_espelho_guid_invalido_nao_chega_a_url(valor):
    assert not valida_guid(valor)


def test_sem_cache_de_4_horas_leitura_recente_nao_segura_a_consulta():
    """Uma leitura bem-sucedida de 1 s atrás NÃO impede nova consulta: só o cooldown de 60 s (da TENTATIVA) vale."""
    agora = 1_790_000_000_000
    linha = {"tem_valor": True, "atualizado_em": agora - 1_000, "tentativa_em": agora - 61_000}
    assert decidir_gate(linha, agora) == "consulta"
    assert decidir_gate({**linha, "tentativa_em": agora - 59_999}, agora) == "cooldown"


# ---------------------------------------------------------------------------
# Contrato das respostas do GET/POST (fixtures)
# ---------------------------------------------------------------------------

FIXTURES_GET = ["azure_custo_get_nao_configurado.json", "azure_custo_get_ok.json", "azure_custo_get_ok_origem_tela.json",
                "azure_custo_get_ok_origem_tela_sem_apelido.json",
                "azure_custo_get_sem_dados.json", "azure_custo_get_desatualizado.json", "azure_custo_get_indisponivel_com_valor.json",
                "azure_custo_get_indisponivel_apos_sem_dados.json", "azure_custo_get_sem_leitura_origem_tela.json",
                "azure_custo_get_configuracao_invalida_tela.json", "azure_custo_get_configuracao_invalida_servidor.json"]


@pytest.mark.parametrize("nome", FIXTURES_GET)
def test_fixture_de_resposta_do_get_segue_o_contrato(nome):
    dados = _fixture(nome)
    assert list(dados) == CHAVES_GET
    assert dados["provedor"] == "azure" and dados["nao_alocado"] is True
    assert dados["origem"] in ("tela", "servidor", None)
    # sem origem (nao_configurado) a função de configuração não diz de onde viria; com `configurado` há origem
    assert (dados["origem"] is None) == (dados["status"] == "nao_configurado")
    # apelido: sempre texto de 1 a 60 caracteres (padrão "Azure"); tenant_final: 4 caracteres só com origem "tela", senão null
    assert isinstance(dados["apelido"], str) and 1 <= len(dados["apelido"]) <= 60
    assert (dados["tenant_final"] is not None) == (dados["origem"] == "tela")
    if dados["tenant_final"] is not None:
        assert len(dados["tenant_final"]) == 4
    if dados["origem"] != "tela":
        assert dados["apelido"] == "Azure"


def test_fixture_nao_configurado_tem_custo_null_e_nunca_zero():
    d = _fixture("azure_custo_get_nao_configurado.json")
    assert d["configurado"] is False and d["status"] == "nao_configurado"
    assert d["custo_mes_total"] is None and d["moeda"] is None and d["atualizado_em"] is None


def test_fixture_desatualizado_nao_mostra_custo_do_mes_anterior():
    d = _fixture("azure_custo_get_desatualizado.json")
    assert d["status"] == "desatualizado" and d["custo_mes_total"] is None and d["mes_referencia"] == "2026-10"


def test_fixture_indisponivel_mantem_o_ultimo_valor_e_o_atualizado_em():
    d = _fixture("azure_custo_get_indisponivel_com_valor.json")
    assert d["status"] == "indisponivel" and d["custo_mes_total"] == 123.45 and d["atualizado_em"]


def test_fixture_de_cooldown_do_post_traz_origem_cooldown_e_proxima_leitura_so_do_cooldown():
    """Sem cache de 4 h: a resposta de cooldown é 200 com `origem: "cooldown"` (nunca "cache") e próxima leitura = tentativa + 60 s."""
    d = _fixture("azure_custo_sincronizar_cooldown_com_valor.json")
    assert list(d) == CHAVES_POST and d["origem"] == "cooldown" and d["origem_credencial"] in ("tela", "servidor")
    assert d["proxima_leitura_em"] - d["atualizado_em"] == _parametros()["cooldown_ms"]
    assert d["custo_mes_total"] == 123.45 and d["moeda"] == "USD"


def test_nenhuma_fixture_do_post_usa_a_origem_cache_do_contrato_antigo():
    for arquivo in sorted(FIXTURES.glob("azure_custo_sincronizar_*.json")):
        d = json.loads(_ler(arquivo))
        assert list(d) == CHAVES_POST, arquivo.name
        assert d["origem"] in ("azure", "cooldown", None), arquivo.name
        assert d["origem_credencial"] in ("tela", "servidor", None), arquivo.name
    assert not (FIXTURES / "azure_custo_sincronizar_cache.json").exists()
    assert not (FIXTURES / "azure_custo_sincronizar_sem_dados_cache.json").exists()


def test_nenhuma_fixture_traz_credencial_ou_id_de_assinatura():
    for arquivo in sorted(FIXTURES.glob("azure_*.json")):
        texto = _ler(arquivo).lower()
        for proibido in ("client_secret", "tenant_id", "tenantid", "subscriptionid", "refresh_token"):
            assert proibido not in texto, f"{arquivo.name}: {proibido}"


# ---------------------------------------------------------------------------
# Cooldown de 60 s (espelho do gate do POST e da próxima leitura do estado)
# ---------------------------------------------------------------------------

AGORA = 1_790_000_000_000


def test_gate_cooldown_depois_de_qualquer_desfecho_nao_chama_o_azure():
    for status in ("ok", "sem_dados", "sem_permissao", "indisponivel", "resposta_incompleta"):
        linha = {"tem_valor": status == "ok", "status": status, "tentativa_em": AGORA - 59_999}
        assert decidir_gate(linha, AGORA) == "cooldown", status
    assert decidir_gate({"tem_valor": False, "tentativa_em": AGORA - 60_000}, AGORA) == "consulta"
    assert decidir_gate(None, AGORA) == "consulta"


def test_gate_sem_cache_valor_recente_nao_impede_a_leitura_depois_do_cooldown():
    p = _parametros()
    linha = {"tem_valor": True, "atualizado_em": AGORA - 3_600_000, "tentativa_em": AGORA - 10_000}
    assert decidir_gate(linha, AGORA) == "cooldown"
    assert proxima_leitura(linha, AGORA) == linha["tentativa_em"] + p["cooldown_ms"]  # 60 s, e não 4 h
    assert decidir_gate(linha, AGORA + 50_000) == "consulta"
    # valor lido há 1 s, mas a tentativa foi há mais de 60 s (ex.: mês/linha antiga): lê de novo
    assert decidir_gate({"tem_valor": True, "atualizado_em": AGORA - 1_000, "tentativa_em": AGORA - 90_000}, AGORA) == "consulta"


def test_gate_bloqueio_do_429_vem_antes_do_cooldown_e_proxima_leitura_pega_o_maior():
    linha = {"tem_valor": False, "tentativa_em": AGORA - 1_000, "bloqueado_ate": AGORA + 300_000}
    assert decidir_gate(linha, AGORA) == "limite"
    assert proxima_leitura(linha, AGORA) == AGORA + 300_000
    curto = {"tem_valor": False, "tentativa_em": AGORA - 1_000, "bloqueado_ate": AGORA + 5_000}
    assert proxima_leitura(curto, AGORA) == curto["tentativa_em"] + 60_000  # cooldown maior que o bloqueio curto
    assert proxima_leitura({"tem_valor": False, "tentativa_em": AGORA - 120_000}, AGORA) is None


def test_fixture_de_cooldown_do_post_traz_estado_guardado_sem_leitura_bem_sucedida():
    # falha sem leitura bem-sucedida (sem_permissao): sem atualizado_em, só o cooldown de 60 s
    d = _fixture("azure_custo_sincronizar_cooldown.json")
    assert list(d) == CHAVES_POST and d["origem"] == "cooldown"
    assert d["status"] == "sem_permissao" and d["custo_mes_total"] is None and d["moeda"] is None and d["atualizado_em"] is None
    assert d["proxima_leitura_em"] is not None and d["proxima_leitura_em"] > 0


def test_fixture_do_429_do_token_tem_cabecalhos_para_o_mesmo_calculo():
    assert segundos_do_429(_fixture("azure_429_cabecalhos.json")["token_e_consulta_mesmo_calculo"]) == 45


# ---------------------------------------------------------------------------
# sem_dados (HTTP 200 com rows vazia) NÃO é erro: leitura bem-sucedida com hora, sem custo
# ---------------------------------------------------------------------------

MES = "2026-11"
LINHA_VAZIA = {"mes_referencia": MES, "custo_mes_total": None, "moeda": "", "atualizado_em": 0, "tem_valor": False,
               "status": "sem_leitura", "erro_resumo": "", "tentativa_em": 0, "bloqueado_ate": 0}


def test_sem_dados_grava_atualizado_em_e_configurado_com_custo_e_moeda_null():
    t0 = 1_790_000_000_000
    linha = aplicar_desfecho(LINHA_VAZIA, "sem_dados", t0)
    assert linha["atualizado_em"] == t0 and linha["tem_valor"] is False and linha["status"] == "sem_dados"
    r = resposta_do_get(linha, MES, t0 + 30_000)
    assert r == _fixture("azure_custo_get_sem_dados.json")
    assert r["proxima_leitura_em"] == t0 + 60_000  # só o cooldown
    assert r["configurado"] is True and r["custo_mes_total"] is None and r["moeda"] is None
    assert r["atualizado_em"] == t0 and r["erro_resumo"] is None  # sem mensagem de erro: a tela mostra "Conectado ao Azure"


def test_sem_dados_do_mesmo_mes_tambem_nao_tem_cache_de_4h_so_cooldown():
    t0 = 1_790_000_000_000
    linha = aplicar_desfecho(LINHA_VAZIA, "sem_dados", t0)
    assert decidir_gate(linha, t0 + 10_000) == "cooldown"
    assert decidir_gate(linha, t0 + 59_999) == "cooldown"
    assert decidir_gate(linha, t0 + 60_000) == "consulta"  # sem_dados NÃO segura mais por 4 h
    assert proxima_leitura(linha, t0 + 30_000) == t0 + 60_000
    assert proxima_leitura(linha, t0 + 3_600_000) is None


def test_ok_tambem_devolve_atualizado_em_e_proxima_leitura():
    t0 = 1_790_000_000_000
    linha = aplicar_desfecho(LINHA_VAZIA, "ok", t0, 123.45, "USD")
    assert resposta_do_get(linha, MES, t0 + 30_000) == _fixture("azure_custo_get_ok.json")
    assert resposta_do_get(linha, MES, t0 + 30_000, "tela", {"apelido": "Azure produção", "tenant_final": "0000"}) == _fixture("azure_custo_get_ok_origem_tela.json")
    assert resposta_do_get(linha, MES, t0 + 30_000, "tela", {"apelido": "", "tenant_final": "0000"}) == _fixture("azure_custo_get_ok_origem_tela_sem_apelido.json")
    assert resposta_do_get(linha, MES, t0 + 60_000)["proxima_leitura_em"] is None  # cooldown vencido: pode sincronizar


def test_sem_dados_depois_de_valor_descarta_o_valor_e_nunca_vira_zero():
    t0 = 1_790_000_000_000
    com_valor = aplicar_desfecho(LINHA_VAZIA, "ok", t0, 123.45, "USD")
    vazio = aplicar_desfecho(com_valor, "sem_dados", t0 + 5 * 3_600_000)
    r = resposta_do_get(vazio, MES, t0 + 5 * 3_600_000 + 1000)
    assert r["status"] == "sem_dados" and r["custo_mes_total"] is None and r["moeda"] is None
    assert r["atualizado_em"] == t0 + 5 * 3_600_000


def test_sem_dados_do_mes_anterior_continua_desatualizado_sem_hora_de_mes_antigo():
    t0 = 1_787_000_000_000
    linha = aplicar_desfecho({**LINHA_VAZIA, "mes_referencia": "2026-10"}, "sem_dados", t0)
    r = resposta_do_get(linha, MES, t0 + 40 * 86_400_000)
    assert r == _fixture("azure_custo_get_desatualizado.json")
    assert r["atualizado_em"] is None and r["custo_mes_total"] is None and r["mes_referencia"] == "2026-10"


def test_falhas_mantem_cooldown_de_60s_e_zeram_a_leitura_bem_sucedida():
    t0 = 1_790_000_000_000
    for desfecho in ("sem_permissao", "resposta_incompleta"):
        linha = aplicar_desfecho(LINHA_VAZIA, desfecho, t0)
        assert linha["atualizado_em"] == 0 and linha["tem_valor"] is False
        assert decidir_gate(linha, t0 + 59_999) == "cooldown" and decidir_gate(linha, t0 + 60_000) == "consulta", desfecho
    # a falha depois de uma leitura bem-sucedida de sem_dados zera o marcador (o GET não mostra hora de leitura)
    depois = aplicar_desfecho(aplicar_desfecho(LINHA_VAZIA, "sem_dados", t0), "sem_permissao", t0 + 5 * 3_600_000)
    assert depois["atualizado_em"] == 0
    assert resposta_do_get(depois, MES, t0 + 5 * 3_600_000 + 1)["atualizado_em"] is None


def test_indisponivel_mantem_a_ultima_leitura_bem_sucedida_com_ou_sem_valor():
    t0 = 1_790_000_000_000
    apos_sem_dados = aplicar_desfecho(aplicar_desfecho(LINHA_VAZIA, "sem_dados", t0), "indisponivel", t0 + 5 * 3_600_000)
    r = resposta_do_get(apos_sem_dados, MES, t0 + 5 * 3_600_000 + 1)
    assert r["status"] == "indisponivel" and r["custo_mes_total"] is None and r["atualizado_em"] == t0
    assert r["proxima_leitura_em"] == t0 + 5 * 3_600_000 + 60_000
    com_valor = aplicar_desfecho(aplicar_desfecho(LINHA_VAZIA, "ok", t0, 123.45, "USD"), "indisponivel", t0 + 5 * 3_600_000)
    r = resposta_do_get(com_valor, MES, t0 + 5 * 3_600_000 + 1)
    assert r["custo_mes_total"] == 123.45 and r["moeda"] == "USD" and r["atualizado_em"] == t0


def test_fixtures_de_sem_dados_do_post_trazem_origem_e_a_hora_da_leitura():
    for nome, origem in (("azure_custo_sincronizar_sem_dados.json", "azure"), ("azure_custo_sincronizar_sem_dados_cooldown.json", "cooldown")):
        d = _fixture(nome)
        assert list(d) == CHAVES_POST and d["origem"] == origem
        assert d["status"] == "sem_dados" and d["configurado"] is True
        assert d["custo_mes_total"] is None and d["moeda"] is None and d["erro_resumo"] is None
        assert d["atualizado_em"] and d["proxima_leitura_em"] - d["atualizado_em"] == _parametros()["cooldown_ms"]


def test_fixture_indisponivel_apos_sem_dados_mantem_a_hora_e_nao_tem_custo():
    d = _fixture("azure_custo_get_indisponivel_apos_sem_dados.json")
    assert d["status"] == "indisponivel" and d["custo_mes_total"] is None and d["moeda"] is None and d["atualizado_em"]


def test_fixtures_do_429_trazem_o_caso_real_dos_cabecalhos():
    reais = _fixture("azure_429_cabecalhos.json")["real_clienttype_retry_after"]
    assert "x-ms-ratelimit-microsoft.costmanagement-clienttype-retry-after: 7" in reais
    assert any("qpu-remaining" in h for h in reais)  # não contém retry-after: não entra no cálculo
    assert segundos_do_429(reais) == 7

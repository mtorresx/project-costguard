"""Alerta de orçamento por e-mail ao DevOps: verificações estáticas, sem rede.

Leem os `.xs` locais como TEXTO (padrão de `test_xano_estatico.py`) e conferem,
com expressões regulares ANCORADAS (condição + tipo de erro + mensagem, ordem
relativa e blocos `if`/`finally`), as regras de segurança do contrato. Um teste
só passa se o trecho exato esperado existir; afrouxar uma `precondition`, trocar
o `error_type`, inverter uma condição ou mover um efeito de lugar o faz falhar.

Também há um ESPELHO em Python da validação do e-mail, do escape do nome e do
mascaramento. Os parâmetros do espelho (regex do e-mail, limite de 254, uso de
`trim`/`to_lower`, trocas do escape, limite de 120, máscara `***@`) são EXTRAÍDOS
do próprio `.xs`, então o teste quebra se o texto do Xano mudar.

O que estes testes NÃO provam:
  - nada sobre o comportamento do Xano PUBLICADO: filtros (`trim`, `to_lower`,
    `round`, `floor`, `substr`, `replace`), o `$` do regex, `precondition` dentro
    de `conditional`, `db.edit` com "" e `api.request` não foram executados;
  - o espelho em Python usa `strip()/lower()/replace` do Python, que podem diferir
    do Xano (conjunto de espaços do `trim`, caixa de letras não ASCII, `substr`
    em Unicode): ele prova a LÓGICA descrita no texto, não a execução no Xano;
  - nada sobre o Resend (aceite, idempotência, limites) nem sobre rede.
Nenhum teste chama o Resend, o Xano ou qualquer rede; e-mails e nomes são
fictícios (`@exemplo.com`).
"""

import re
from pathlib import Path

import pytest

XANO = Path(__file__).resolve().parent.parent / "xano"
APP = XANO / "api" / "app"
FUNCOES = XANO / "function" / "costguard"

NOTIFICAR = APP / "notificar_devops_projeto_POST.xs"
NOTIFICAR_RECURSOS = APP / "notificar_recursos_sem_equipe_projeto_POST.xs"
NORMALIZAR = FUNCOES / "normalizar_email_devops.xs"
TABELA = XANO / "table" / "projetos.xs"
CRIAR = APP / "criar_projeto_POST.xs"
EDITAR = APP / "editar_projeto_PATCH.xs"
LISTAR = APP / "listar_projetos_GET.xs"
DETALHE = APP / "detalhe_projeto_GET.xs"


def _ler(caminho: Path) -> str:
    return caminho.read_text(encoding="utf-8")


def _codigo(caminho: Path) -> str:
    """Texto sem linhas de comentário."""
    return "\n".join(l for l in _ler(caminho).splitlines() if not l.strip().startswith("//"))


def _bloco(texto: str, abertura: str) -> str:
    """Conteúdo (sem as chaves externas) do bloco que começa em `abertura` (termina em `{`)."""
    inicio = texto.index(abertura) + len(abertura)
    abre = abertura[-1]
    fecha = {"{": "}", "[": "]"}[abre]
    nivel, i = 1, inicio
    while nivel:
        if texto[i] == abre:
            nivel += 1
        elif texto[i] == fecha:
            nivel -= 1
        i += 1
    return texto[inicio:i - 1]


def _bloco_re(texto: str, padrao: str) -> str:
    """Conteúdo do bloco `{...}` que abre no fim do trecho casado por `padrao` (que deve terminar na chave de abertura)."""
    m = re.search(padrao, texto)
    assert m, f"trecho não encontrado: {padrao}"
    i, nivel = m.end(), 1
    while nivel:
        if texto[i] == "{":
            nivel += 1
        elif texto[i] == "}":
            nivel -= 1
        i += 1
    return texto[m.end():i - 1]


MSG_INATIVO = "Este projeto está inativo; não é possível notificar o DevOps."
MSG_INATIVO_LITERAL = '"' + MSG_INATIVO + '"'
MSG_TETO = "Limite diário de notificações atingido; tente amanhã."
MSG_TETO_LITERAL = '"' + MSG_TETO + '"'


def _precondicao(codigo: str, condicao: str, tipo: str, mensagem: str | None = None) -> "re.Match[str]":
    """Procura `precondition (<condicao>) { error_type = "<tipo>" error = <mensagem> }` exatamente."""
    padrao = (r"precondition \(" + re.escape(condicao) + r'\) \{\s*error_type = "' + re.escape(tipo) + r'"\s*error = '
              + (re.escape(mensagem) if mensagem is not None else r"[^\n]+") + r"\s*\}")
    m = re.search(padrao, codigo)
    assert m, f"precondition ancorada não encontrada: ({condicao}) {tipo} {mensagem or ''}"
    return m


# ---------------------------------------------------------------------------
# Endpoint: autorização, entrada e destinatário
# ---------------------------------------------------------------------------

def test_endpoint_e_post_do_grupo_app_com_auth_usuarios():
    texto = _codigo(NOTIFICAR)
    assert 'query "projetos/{id}/notificar-devops" verb=POST' in texto
    assert 'api_group = "app"' in texto
    assert 'auth = "usuarios"' in texto


def test_usuario_autenticado_e_ativo_e_exigido_antes_de_qualquer_envio_ou_escrita():
    codigo = _codigo(NOTIFICAR)
    exigencia = _precondicao(
        codigo, '$usuario_logado != null && $usuario_logado.status == "ativo"', "unauthorized", '"Token inválido ou expirado"')
    for efeito in ("db.add travas", "api.request", "db.edit projetos", "function.run", "db.del travas"):
        assert exigencia.start() < codigo.index(efeito), f"a sessão deve ser exigida antes de `{efeito}`"
    # E de novo, com a trava, dentro da seção crítica (sessão relida; desativado no meio vira 401).
    assert re.search(
        r'if \(\$solicitante_atual == null \|\| \$solicitante_atual\.status != "ativo"\) \{\s*'
        r'var\.update \$estado \{ value = "sem_sessao" \}\s*\}\s*'
        r'elseif \(\$proj_atual == null\) \{\s*var\.update \$estado \{ value = "sem_projeto" \}', codigo)
    _precondicao(codigo, "$projeto_alvo != null", "notfound", '"Projeto não encontrado"')


def test_todos_os_perfis_autenticados_podem_notificar_nao_ha_exigencia_de_admin():
    """Decisão: admin E leitura podem usar 'Notificar DevOps'. Nenhum teste de papel no endpoint."""
    codigo = _codigo(NOTIFICAR)
    # O papel só decide o TEXTO da resposta (I1): uma única leitura de `.role`, atribuída a $eh_admin.
    assert re.findall(r"\.role\b", codigo) == [".role"], "só uma leitura de papel é permitida"
    assert re.search(
        r'var\.update \$eh_admin \{ value = \(\$solicitante_atual != null\) \? \(\$solicitante_atual\.role == "admin"\) : false \}', codigo)
    assert codigo.count('"admin"') == 1 and '"leitura"' not in codigo
    assert len(re.findall(r"\$eh_admin", codigo)) == 3, "declaração, atribuição e UM uso (a mensagem)"
    assert not re.search(r"precondition \([^)]*\$eh_admin", codigo), "o papel não pode barrar o envio"
    assert "accessdenied" not in codigo and "Acesso negado" not in codigo, "sem 403 por papel"
    # a autenticação continua obrigatória (token) e usuário inativo/removido não envia
    assert 'auth = "usuarios"' in codigo
    assert '$usuario_logado.status == "ativo"' in codigo and '$solicitante_atual.status != "ativo"' in codigo


def test_so_admin_cria_e_edita_o_email_do_projeto():
    """Notificar é aberto a todos, mas definir/alterar o destinatário segue só admin."""
    for arquivo in (CRIAR, EDITAR):
        codigo = _codigo(arquivo)
        admin = _precondicao(codigo, '$usuario_logado.status == "ativo" && $usuario_logado.role == "admin"',
                             "accessdenied", '"Acesso negado"')
        gravacao = min(codigo.index(p) for p in ("db.add projetos", "db.edit projetos") if p in codigo)
        assert admin.start() < gravacao, arquivo.name


def test_nao_ha_input_de_destinatario():
    codigo = _codigo(NOTIFICAR)
    entrada = _bloco(codigo, "input {")
    campos = re.findall(r"^\s*(?:int|text|email|bool|decimal|object|json)\s+(\w+)", entrada, re.M)
    assert campos == ["id"], f"o único input permitido é `id`, achei {campos}"
    usados = set(re.findall(r"\$input\.(\w+)", codigo))
    assert usados == {"id"}, f"só `$input.id` pode ser lido, achei {sorted(usados)}"


def test_destinatario_vem_somente_do_projeto_gravado():
    codigo = _codigo(NOTIFICAR)
    assert re.search(r"to\s*:\s*\[\$destino\]", codigo), "`to` deve ser a lista de 1 com $destino"
    assert re.search(r"var \$destino \{ value = \$email_atual\.email \}", codigo)
    assert re.search(r"\$email_gravado \{ value = \(\$proj_atual != null\) \? \(\$proj_atual\.email_devops \?\? \"\"\)", codigo)
    # Revalida o valor gravado com a função compartilhada (antes e dentro da trava).
    assert re.search(r'function\.run "costguard/normalizar_email_devops" \{\s*input = \{email: \(\$projeto_alvo\.email_devops \?\? ""\)\}\s*\} as \$email_pre', codigo)
    assert re.search(r'function\.run "costguard/normalizar_email_devops" \{\s*input = \{email: \$email_gravado\}\s*\} as \$email_atual', codigo)
    assert codigo.count('function.run "costguard/normalizar_email_devops"') == 2
    assert "$auth." not in codigo.replace("$auth.id", ""), "só o id do token pode ser usado de $auth"
    assert "$usuario_logado.email" not in codigo and "$solicitante_atual.email" not in codigo, (
        "e-mail de usuário não pode virar destinatário nem entrar no conteúdo")


def test_sem_email_cadastrado_responde_erro_4xx_claro():
    codigo = _codigo(NOTIFICAR)
    pre = _precondicao(codigo, "$email_pre.vazio == false && $email_pre.valido == true", "inputerror",
                       '"Este projeto não tem e-mail do DevOps cadastrado."')
    assert pre.start() < codigo.index("db.add travas") < codigo.index("api.request")
    # na seção crítica, o destino atual também é revalidado
    assert re.search(
        r'if \(\$estado == "" && \(\$email_atual\.vazio == true \|\| \$email_atual\.valido == false\)\) \{\s*'
        r'var\.update \$estado \{ value = "sem_destino" \}', codigo)


# ---------------------------------------------------------------------------
# Configuração do provedor de e-mail: sem chave, nada é enviado
# ---------------------------------------------------------------------------

def test_sem_chave_ou_remetente_nada_e_enviado():
    codigo = _codigo(NOTIFICAR)
    conf = _precondicao(codigo, '$email_chave != "" && $email_from != ""', "standard",
                        '"O envio de e-mail não está configurado no servidor."')
    assert codigo.count("api.request") == 1, "deve haver exatamente UMA chamada ao provedor (sem laço de retentativa)"
    assert conf.start() < codigo.index("api.request"), "a configuração deve ser exigida ANTES da chamada"
    assert conf.start() < codigo.index("db.add travas"), "sem configuração, nem a trava é tomada"
    assert re.search(r'var \$email_chave \{ value = \(\$env\.EMAIL_API_KEY \?\? ""\) \}', codigo)
    assert re.search(r'var \$email_from \{ value = \(\$env\.EMAIL_FROM \?\? ""\) \}', codigo)
    assert set(re.findall(r"\$env\.(\w+)", codigo)) == {"EMAIL_API_KEY", "EMAIL_FROM", "COSTGUARD_APP_URL"}


def test_remetente_vem_da_variavel_email_from_e_nao_e_fixo_no_codigo():
    """O remetente (alertas@...) é configuração do Xano: nada de endereço no código."""
    codigo = _codigo(NOTIFICAR)
    assert re.search(r"from\s*:\s*\$email_from\b", codigo)
    assert not re.search(r"\balertas@|noreply@|no-reply@|@costguard", _ler(NOTIFICAR), re.I)
    assert not re.search(r"[A-Za-z0-9_.+-]+@[A-Za-z0-9-]+\.[A-Za-z]{2,}", _ler(NOTIFICAR)), "nenhum endereço literal no endpoint"


def test_nao_ha_laco_de_retentativa_em_torno_do_envio():
    codigo = _codigo(NOTIFICAR)
    envio = codigo.index("api.request")
    antes, depois = codigo[:envio], codigo[envio:]
    # Só quatro laços no arquivo, todos ANTES do envio: trava, fichas do teto diário, busca no resumo e
    # contagem de recursos sem tag.
    assert len(re.findall(r"\bforeach\b", codigo)) == 4
    assert antes.count("foreach ([1, 2]) {") == 1
    assert antes.count("foreach ([1, 2, 3,") == 1
    assert antes.count("foreach ($resumo.projetos) {") == 1
    assert antes.count("foreach ($recursos_sem_equipe) {") == 1
    assert not re.search(r"\b(foreach|while|for)\b", depois) and "util.sleep" not in codigo


def test_chamada_ao_resend_usa_https_post_json_e_timeout_curto():
    codigo = _codigo(NOTIFICAR)
    req = _bloco(codigo, "api.request {")
    assert 'url = "https://api.resend.com/emails"' in req
    assert 'method = "POST"' in req
    assert "params = $corpo_email" in req
    assert '"Content-Type: application/json"' in req
    assert '"Authorization: Bearer " ~ $email_chave' in req
    timeout = int(re.search(r"timeout = (\d+)", req).group(1))
    assert 0 < timeout <= 15, "timeout curto esperado"
    corpo = _bloco(codigo, "var $corpo_email {\n                      value = {")
    chaves = re.findall(r"^\s*(\w+)\s*:", corpo, re.M)
    assert chaves == ["from", "to", "subject", "html", "text"]
    # exceção (rede/timeout) vale como falha: status 0, que não cai em 2xx
    assert re.search(r"var \$envio_status \{ value = 0 \}", codigo)
    assert re.search(r"catch \{\s*var\.update \$envio_status \{ value = 0 \}\s*\}", codigo)
    assert "($resp_email.response.status ?? 0)" in codigo


def test_erro_do_resend_nao_e_lido_nem_devolvido():
    codigo = _codigo(NOTIFICAR)
    assert "$resp_email.response.result" not in codigo and "$resp_email.response.body" not in codigo
    usos = re.findall(r"\$resp_email\S*", codigo)
    assert sorted(usos) == ["$resp_email", "$resp_email.response.status"], "só o status da resposta pode ser usado"
    for linha in re.findall(r"error = .*", codigo):
        assert "$resp_email" not in linha and "$email_chave" not in linha and "$destino" not in linha


# ---------------------------------------------------------------------------
# Conteúdo: assunto fixo, cabeçalhos estáticos, escape do nome
# ---------------------------------------------------------------------------

def test_assunto_com_projeto_e_faixa_sem_quebras_de_linha_e_cabecalhos_sem_dado_do_usuario():
    """O assunto passou a ser "[CostGuard] Orçamento em alerta: PROJETO (faixa)" (e-mail HTML);
    detalhes extras em tests/test_email_html_devops_estatico.py."""
    codigo = _codigo(NOTIFICAR)
    assert re.search(
        r'var \$assunto \{\s*value = \(\("\[CostGuard\] Orçamento em alerta: " ~ \$nome_limpo ~ " \(" ~ \$faixa_curta ~ "\)"\)'
        r'\|replace:"\\r":""\)\|replace:"\\n":""\s*\}', codigo)
    assert re.search(r"subject\s*:\s*\$assunto", codigo)
    cabecalhos = _bloco(_bloco(codigo, "api.request {"), "headers = [")
    # só duas variáveis entram em cabeçalhos: a chave (Authorization) e a chave de idempotência
    assert re.findall(r"\$\w+", cabecalhos) == ["$email_chave", "$idem_chave"]
    assert cabecalhos.count("~") == 2
    assert not re.search(r"\$(nome|proj|projeto|destino|input|auth|item|resumo|email_atual|email_gravado)", cabecalhos)
    # o assunto só é usado em `subject`
    assert "$assunto" not in re.sub(r"var \$assunto \{.*?\n\s*\}|subject\s*:\s*\$assunto", "", codigo, flags=re.S)


def test_idempotency_key_so_com_id_do_projeto_e_janela_de_5_minutos():
    codigo = _codigo(NOTIFICAR)
    cabecalhos = _bloco(_bloco(codigo, "api.request {"), "headers = [")
    assert '"Idempotency-Key: " ~ $idem_chave' in cabecalhos
    janela = re.search(r"var \$janela_idem \{ value = \(\$agora_ms / (\d+)\)\|floor \}", codigo)
    assert janela and int(janela.group(1)) == 300000, "janela de 5 minutos (300000 ms)"
    chave = re.search(r"var \$idem_chave \{\s*value = (.*?)\n\s*\}", codigo, re.S).group(1)
    assert chave == '"devops-" ~ ($input.id|to_text) ~ "-" ~ (($janela_idem|to_int)|to_text)'
    assert sorted(re.findall(r"\$[\w.]+", chave)) == ["$input.id", "$janela_idem"], "sem nome, e-mail ou outro dado"
    assert codigo.index("var $agora_ms { value = now|to_int }") < codigo.index("$janela_idem") < codigo.index("$idem_chave") < codigo.index("api.request")


def test_nome_do_projeto_e_escapado_no_html_e_limpo_no_texto():
    """A limpeza e o escape agora são as funções costguard/limpar_texto_linha e costguard/escapar_html
    (testadas em tests/test_email_html_devops_estatico.py); aqui só a ligação no endpoint."""
    codigo = _codigo(NOTIFICAR)
    assert re.search(
        r'function\.run "costguard/limpar_texto_linha" \{\s*input = \{texto: \(\$proj_atual\.nome \?\? ""\)\}\s*\} as \$nome_limpo', codigo)
    assert re.search(
        r'function\.run "costguard/escapar_html" \{\s*input = \{texto: \$nome_limpo\}\s*\} as \$nome_html', codigo)
    # autoverificação: com < ou > restante nada é enviado
    assert re.search(r'if \("/\[<>\]/"\|regex_matches:\$escapados_juntos\) \{\s*var\.update \$estado \{ value = "falha_conteudo" \}', codigo)
    assert "var $escapados_juntos { value = $nome_html ~ $enviado_html ~ $mes_html }" in codigo
    # o HTML usa só $nome_html; o texto usa só $nome_limpo
    assert codigo.count("$proj_atual.nome") == 1
    assert "valor_html: $nome_html" in codigo
    assert re.search(r'\$texto ~ "Projeto: " ~ \$nome_limpo ~ "\\n"', codigo)
    assert not re.search(r"valor_html:[^\n]*\$nome_limpo|\$texto[^\n]*\$nome_html", codigo)


def test_conteudo_traz_o_que_o_contrato_pede_e_nada_interno():
    codigo = _codigo(NOTIFICAR)
    for trecho in ("Projeto: ", "Mês de referência: ", "Orçamento: ", "Gasto no mês: ", "Consumo do orçamento: ",
                   "Nível do alerta: ", "Recursos sem equipe: ", "Enviado por: ", "Abrir projeto no CostGuard"):
        assert trecho in codigo, trecho
    assert "Faixa: " not in codigo, "o rótulo agora é 'Nível do alerta'"
    # Mesmas regras do resto do sistema: custo, percentual e nível vêm do resumo, sem recalcular.
    assert 'function.run "costguard/resumo_consumo"' in codigo
    assert "$item_resumo.percentual_usado" in codigo and "$item_resumo.faixa" in codigo
    assert "$item_resumo.custo_mtd" in codigo and "$item_resumo.custo_status" in codigo
    assert "$item_resumo.budget" in codigo
    assert ">= 100" not in codigo and ">= 90" not in codigo and ">= 70" not in codigo, "não duplicar as faixas"
    # Dados internos que não podem entrar no conteúdo/resposta.
    palavras = set(re.findall(r"\w+", codigo.lower()))
    for proibido in ("identificador_conta", "arn", "provedor", "provedores", "username", "aws_access_key_id"):
        assert proibido not in palavras, proibido
    assert not any(p.startswith("aws") for p in palavras)
    # "Enviado por": só o NOME da sessão relida (nunca o e-mail); o usuário da pré-checagem não entra no corpo
    assert "$usuario_logado.nome" not in codigo
    assert codigo.count("$solicitante_atual.nome") == 1


def test_html_so_recebe_nome_escapado_e_valores_nao_livres():
    """Todo texto dinâmico do HTML é o nome escapado ou valor numérico/rótulo fixo/link validado."""
    codigo = _codigo(NOTIFICAR)
    em_html = set()
    for valor in re.findall(r"valor_html: (\$\w+)\}", codigo):
        em_html.add(valor.lstrip("$"))
    assert em_html == {"nome_html", "mes_html", "orcamento_txt", "custo_txt", "pct_txt", "h_selo", "sem_tag_txt", "enviado_html"}
    # o link só entra pela moldura (escapado lá); o conteúdo é montado a partir das linhas
    assert "link: $link_projeto" in codigo
    em_texto = set()
    for linha in re.findall(r"var\.update \$texto \{ value = (.*?) \}\n", codigo):
        em_texto |= set(re.findall(r"\$(\w+)", linha))
    em_texto.discard("texto")
    assert em_texto == {"nome_limpo", "mes_extenso", "orcamento_txt", "custo_txt", "pct_txt", "nivel_rotulo", "sem_tag_txt",
                        "enviado_limpo", "link_projeto"}
    # nenhum campo livre além do nome do projeto e do nome de quem enviou: código, e-mail, ARN etc. ficam de fora
    for proibido in ("proj_atual.codigo", "projeto_alvo.codigo", "destino", "email_atual", "solicitante_atual.email", "rs.arn", "$rs."):
        assert proibido not in "".join(re.findall(r"(?:valor_html|var\.update \$texto).*", codigo)), proibido
    # os textos livres do banco (nome do projeto e do usuário) entram uma única vez cada, pela função de limpeza
    assert codigo.count("$proj_atual.nome") == 1 and codigo.count("$solicitante_atual.nome") == 1


def _parametros_link():
    codigo = _codigo(NOTIFICAR)
    m = re.search(r'regex_matches:\$app_url_host', codigo)
    assert m
    regex = re.search(r'"/(\^\[a-zA-Z0-9\].*?\$)/"\|regex_matches:\$app_url_host', codigo).group(1)
    return re.compile(regex), re.search(r'var \$app_url \{ value = "([^"]+)" \}', codigo).group(1)


def montar_link(env, projeto_id):
    """Espelho da escolha da base do link e da montagem: parâmetros lidos do .xs."""
    regex, padrao = _parametros_link()
    codigo = _codigo(NOTIFICAR)
    maximo = int(re.search(r"\(\$app_url_bruto\|strlen\) <= (\d+)\) \{", codigo).group(1))
    janela = int(re.search(r"\$app_url_bruto\|substr:8:(\d+) \}", codigo).group(1))
    assert maximo == 8 + janela, "o tamanho total máximo deve cobrir exatamente a janela validada pelo substr"
    bruto = (env or "").strip()
    base = padrao
    # O valor INTEIRO vira o href: o texto todo precisa caber na janela validada (M1).
    if 8 < len(bruto) <= maximo and bruto[:8] == "https://" and regex.search(bruto[8:8 + janela]):
        base = bruto
    return f"{base}/projetos/{projeto_id}"


def test_link_do_projeto_vem_de_variavel_de_ambiente_com_padrao_e_validacao():
    codigo = _codigo(NOTIFICAR)
    assert 'var $app_url_bruto { value = (($env.COSTGUARD_APP_URL ?? "")|trim) }' in codigo
    assert 'var $app_url { value = "https://app.costguard.com.br" }' in codigo
    assert 'var $link_projeto { value = $app_url ~ "/projetos/" ~ ($input.id|to_text) }' in codigo
    assert '$app_url_prefixo == "https://"' in codigo, "só https"
    # a validação acontece antes da trava e do envio; o link só usa $app_url validado
    assert codigo.index("var $link_projeto") < codigo.index("db.add travas") < codigo.index("api.request")
    assert codigo.count("var.update $app_url { value = $app_url_bruto }") == 1, "único ponto que troca a base padrão"
    # nunca o link é montado com nome, e-mail ou outro dado do projeto
    link = re.search(r"var \$link_projeto \{ value = (.*?) \}\n", codigo).group(1)
    assert sorted(re.findall(r"\$[\w.]+", link)) == ["$app_url", "$input.id"]
    # só o caminho do app (/projetos/<id>), igual à rota da tela
    assert (APP.parent.parent.parent / "projetoImpacta" / "projetoImpacta.py").read_text(encoding="utf-8").count(
        'route="/projetos/[projeto_id]"') == 1


@pytest.mark.parametrize("env,esperado", [
    (None, "https://app.costguard.com.br/projetos/7"),
    ("", "https://app.costguard.com.br/projetos/7"),
    ("https://painel.exemplo.com", "https://painel.exemplo.com/projetos/7"),
    ("  https://painel.exemplo.com:8443  ", "https://painel.exemplo.com:8443/projetos/7"),
    ("http://painel.exemplo.com", "https://app.costguard.com.br/projetos/7"),                # sem https
    ("https://painel.exemplo.com/", "https://app.costguard.com.br/projetos/7"),              # barra final
    ("https://painel.exemplo.com/x", "https://app.costguard.com.br/projetos/7"),             # com caminho
    ("https://painel.exemplo.com'><script>", "https://app.costguard.com.br/projetos/7"),     # injeção
    ("https://a b.exemplo.com", "https://app.costguard.com.br/projetos/7"),
    ("https://", "https://app.costguard.com.br/projetos/7"),
    ("javascript:alert(1)", "https://app.costguard.com.br/projetos/7"),
    ("https://" + "a" * 200, "https://" + "a" * 200 + "/projetos/7"),                          # 208: no limite
    ("https://" + "a" * 201, "https://app.costguard.com.br/projetos/7"),                      # 209: acima
    ("https://" + "a" * 200 + "'><script>", "https://app.costguard.com.br/projetos/7"),       # lixo depois da janela de 200
    ("https://" + "a" * 200 + "/x", "https://app.costguard.com.br/projetos/7"),               # caminho além da janela
])
def test_espelho_link_base_valida_ou_padrao(env, esperado):
    assert montar_link(env, 7) == esperado


def test_link_exige_tamanho_total_no_xs_e_nao_so_a_janela_do_substr():
    """M1: `substr:8:200` ignora o que passa de 208; o valor inteiro vai ao href, então o total é limitado."""
    codigo = _codigo(NOTIFICAR)
    assert re.search(r"if \(\(\$app_url_bruto\|strlen\) > 8 && \(\$app_url_bruto\|strlen\) <= 208\) \{", codigo)
    # a atribuição da base só acontece dentro desse `if` (o limite de tamanho a protege)
    externo = _bloco_re(codigo, r"if \(\(\$app_url_bruto\|strlen\) > 8 && \(\$app_url_bruto\|strlen\) <= 208\) \{")
    assert "var.update $app_url { value = $app_url_bruto }" in externo
    assert "var.update $app_url {" not in codigo.replace(externo, "")


TXT_ORC_NAO_DEFINIDO = "Orçamento não definido"
TXT_CONSUMO_INDISPONIVEL = "Consumo indisponível (sem custo em USD no mês)"


def problemas_consumo_sem_faixa(codigo: str) -> list[str]:
    """Linha "Consumo do orçamento" sem faixa: orçamento zero/nulo = "Orçamento não definido"; orçamento > 0 = "Consumo indisponível (...)"."""
    faltas = []
    # padrão: orçamento zero ou nulo (budget não é > 0)
    if f'var $pct_txt {{ value = "{TXT_ORC_NAO_DEFINIDO}" }}' not in codigo:
        faltas.append("padrao_orcamento_nao_definido")
    # orçamento POSITIVO sem faixa (sem custo em USD no mês): "Consumo indisponível (sem custo em USD no mês)"
    ajuste = re.search(r'var \$pct_txt \{ value = "' + re.escape(TXT_ORC_NAO_DEFINIDO) + r'" \}\s*conditional \{\s*if \(\$item_resumo\.budget > 0\) \{\s*'
                       r'var\.update \$pct_txt \{ value = "' + re.escape(TXT_CONSUMO_INDISPONIVEL) + r'" \}\s*\}\s*\}\s*var \$pct_largura \{ value = 0 \}', codigo)
    if not ajuste:
        faltas.append("orcamento_positivo_sem_faixa_diz_consumo_indisponivel")
    # o texto novo só existe nesse ajuste; "Orçamento não definido" só no orçamento e no padrão do consumo
    if codigo.count(TXT_CONSUMO_INDISPONIVEL) != 1 or codigo.count(f'"{TXT_ORC_NAO_DEFINIDO}"') != 2:
        faltas.append("textos_do_consumo_sem_duplicidade")
    # a faixa, quando existe, SOBRESCREVE o texto (percentual brasileiro + "%") e vem DEPOIS do ajuste
    sobrescreve = codigo.find('var.update $pct_txt { value = $pct_fmt ~ "%" }')
    if not (0 <= codigo.find(TXT_CONSUMO_INDISPONIVEL) < sobrescreve and re.search(r"if \(\$item_resumo\.faixa != null\) \{\s*var \$pct_decimos", codigo)):
        faltas.append("faixa_sobrescreve_o_texto")
    # texto puro e HTML usam a mesma variável
    if 'var.update $texto { value = $texto ~ "Consumo do orçamento: " ~ $pct_txt ~ "\\n" }' not in codigo or 'rotulo: "Consumo do orçamento", valor_html: $pct_txt' not in codigo:
        faltas.append("html_e_texto_usam_o_mesmo_consumo")
    # o teste é sobre o ORÇAMENTO (budget), nunca sobre o percentual (decimal 0 == null)
    if "percentual_usado != null" in codigo or "percentual_usado == null" in codigo:
        faltas.append("nao_decide_pelo_percentual")
    # sem faixa não há barra nem percentual
    if "var.update $pct_largura" in codigo.replace(_bloco_re(codigo, r"if \(\$item_resumo\.faixa != null\) \{\s*var \$pct_decimos"), ""):
        faltas.append("sem_barra_sem_faixa")
    return faltas


def test_orcamento_positivo_sem_faixa_diz_consumo_indisponivel_e_orcamento_zero_nao_definido():
    assert problemas_consumo_sem_faixa(_codigo(NOTIFICAR)) == []


MUTACOES_CONSUMO_SEM_FAIXA = [
    ("positivo_sem_faixa_continua_nao_definido", f'var.update $pct_txt {{ value = "{TXT_CONSUMO_INDISPONIVEL}" }}',
     f'var.update $pct_txt {{ value = "{TXT_ORC_NAO_DEFINIDO}" }}', "orcamento_positivo_sem_faixa_diz_consumo_indisponivel"),
    ("sem_o_ajuste_do_orcamento_positivo", "if ($item_resumo.budget > 0) {\n                    var.update $pct_txt", "if ($item_resumo.budget < 0) {\n                    var.update $pct_txt",
     "orcamento_positivo_sem_faixa_diz_consumo_indisponivel"),
    ("zero_tambem_vira_consumo_indisponivel", "if ($item_resumo.budget > 0) {\n                    var.update $pct_txt", "if ($item_resumo.budget >= 0) {\n                    var.update $pct_txt",
     "orcamento_positivo_sem_faixa_diz_consumo_indisponivel"),
    ("padrao_trocado", f'var $pct_txt {{ value = "{TXT_ORC_NAO_DEFINIDO}" }}', f'var $pct_txt {{ value = "{TXT_CONSUMO_INDISPONIVEL}" }}', "padrao_orcamento_nao_definido"),
    ("decide_pelo_percentual", "if ($item_resumo.budget > 0) {\n                    var.update $pct_txt", "if ($item_resumo.percentual_usado != null) {\n                    var.update $pct_txt",
     "nao_decide_pelo_percentual"),
    ("texto_duplicado", f'var $sem_tag_txt {{ value =', f'var $dup {{ value = "{TXT_CONSUMO_INDISPONIVEL}" }}\n                var $sem_tag_txt {{ value =', "textos_do_consumo_sem_duplicidade"),
    ("html_usa_outro_texto", 'rotulo: "Consumo do orçamento", valor_html: $pct_txt', 'rotulo: "Consumo do orçamento", valor_html: $orcamento_txt', "html_e_texto_usam_o_mesmo_consumo"),
    ("texto_puro_usa_outro_texto", '"Consumo do orçamento: " ~ $pct_txt', '"Consumo do orçamento: " ~ $orcamento_txt', "html_e_texto_usam_o_mesmo_consumo"),
    ("faixa_nao_sobrescreve", 'var.update $pct_txt { value = $pct_fmt ~ "%" }', 'var.update $pct_largura { value = 0 }', "faixa_sobrescreve_o_texto"),
    ("barra_sem_faixa", "var $pct_largura { value = 0 }\n", "var $pct_largura { value = 0 }\n                var.update $pct_largura { value = 100 }\n", "sem_barra_sem_faixa"),
]


@pytest.mark.parametrize("nome,antigo,novo,regra", MUTACOES_CONSUMO_SEM_FAIXA, ids=[m[0] for m in MUTACOES_CONSUMO_SEM_FAIXA])
def test_mutacao_do_consumo_sem_faixa_e_detectada(nome, antigo, novo, regra):
    codigo = _codigo(NOTIFICAR)
    assert antigo in codigo, nome
    assert regra in problemas_consumo_sem_faixa(codigo.replace(antigo, novo, 1)), nome


def test_percentual_indisponivel_depende_da_faixa_e_nao_do_percentual():
    """Percentual 0 não pode virar "indisponível": no XanoScript decimal 0 == null."""
    codigo = _codigo(NOTIFICAR)
    # padrão (orçamento zero/nulo): "Orçamento não definido"; orçamento positivo sem faixa: "Consumo indisponível (...)"
    # (ver problemas_consumo_sem_faixa); com faixa: percentual brasileiro (1 casa) + "%"
    assert 'var $pct_txt { value = "Orçamento não definido" }' in codigo
    assert problemas_consumo_sem_faixa(codigo) == []
    bloco = _bloco_re(codigo, r"var \$pct_largura \{ value = 0 \}\s*conditional \{\s*if \(\$item_resumo\.faixa != null\) \{")
    assert re.search(r'input = \{escalado: \$pct_decimos, casas: 1\}', bloco)
    assert 'var.update $pct_txt { value = $pct_fmt ~ "%" }' in bloco
    assert "percentual_usado != null" not in codigo and "percentual_usado == null" not in codigo
    for chave, rotulo in (("estourado", "Estourado (100% ou mais do orçamento)"),
                          ("critico", "Crítico (a partir de 90% do orçamento)"),
                          ("atencao", "Atenção (a partir de 70% do orçamento)"),
                          ("normal", "Normal (abaixo de 70% do orçamento)")):
        assert re.search(
            r'\$item_resumo\.faixa == "' + chave + r'"\) \{\s*var\.update \$nivel_rotulo \{ value = "' + re.escape(rotulo) + r'" \}', codigo), chave
    assert 'var $nivel_rotulo { value = "Indisponível (sem custo em USD no período ou orçamento zerado)" }' in codigo
    assert re.search(r'if \(\$item_resumo == null\) \{\s*var\.update \$estado \{ value = "falha_resumo" \}', codigo)


def test_nivel_do_alerta_usa_a_nomenclatura_de_projetos_e_documenta_a_divergencia():
    """Nível = faixa do resumo (70/90/100). Rótulos de /projetos; /inicio e /alertas diferem (Aviso/Excedido)."""
    texto = _ler(NOTIFICAR)
    codigo = _codigo(NOTIFICAR)
    assert "DIVERGÊNCIA CONHECIDA" in texto and "Aviso" in texto and "Excedido" in texto
    rotulos = re.findall(r'var\.update \$nivel_rotulo \{ value = "(\w+)', codigo)
    assert rotulos == ["Estourado", "Crítico", "Atenção", "Normal"], "o e-mail usa a nomenclatura de /projetos"
    # a faixa é a do resumo; o endpoint não recalcula percentual nem compara limites
    assert not re.search(r"\bpct_bruto\b|\$soma\b|/ \$item_resumo\.budget", codigo)
    # `* 100` só existe para converter dólares em centavos (formatação), nunca para calcular o percentual
    for linha in re.findall(r"[^\n]*\* 100[^\n]*", codigo):
        assert re.search(r"\$(orc|custo)_centavos", linha), linha
    # o nível aparece em texto (rótulo completo) e em HTML (selo com a faixa curta)
    assert 'Nível do alerta: " ~ $nivel_rotulo' in codigo
    assert 'rotulo: "Nível do alerta", valor_html: $h_selo' in codigo


def test_custo_do_mes_vem_do_resumo_e_depende_do_status_e_nao_do_valor():
    codigo = _codigo(NOTIFICAR)
    assert 'var $custo_txt { value = "sem custo registrado no mês" }' in codigo
    assert re.search(
        r'if \(\$item_resumo\.custo_status == "ok"\) \{\s*'
        r'var \$custo_centavos \{ value = \(\(\(\$item_resumo\.custo_mtd \?\? 0\) \* 100\)\|round:0\)\|to_int \}\s*'
        r'function\.run "costguard/formatar_numero_br" \{\s*input = \{escalado: \$custo_centavos, casas: 2\}\s*\} as \$custo_fmt\s*'
        r'var\.update \$custo_txt \{ value = "US\$ " ~ \$custo_fmt \}', codigo)
    # moedas mistas e não USD: "indisponível", sem somar nem converter moedas
    assert re.search(r'custo_status == "moedas_mistas"\) \{\s*var\.update \$custo_txt \{ value = "indisponível', codigo)
    assert re.search(r'custo_status == "moeda_incompativel"\) \{\s*var\.update \$custo_txt \{ value = "indisponível', codigo)
    # decimal 0 == null no XanoScript: custo 0 não pode ser lido como ausente
    assert "custo_mtd != null" not in codigo and "custo_mtd == null" not in codigo
    assert "$item_resumo.moeda" not in codigo, "o código da moeda não entra no e-mail"


def test_recursos_sem_tag_conta_ativos_do_projeto_sem_equipe_e_sem_tag_de_equipe():
    """Mesma regra do bloco 'Recursos sem responsável' da tela do projeto; falha vira 'indisponível'."""
    codigo = _codigo(NOTIFICAR)
    consulta = _bloco(codigo, "db.query recursos {")
    assert re.search(
        r"where = \$db\.recursos\.projeto_id == \$input\.id && \$db\.recursos\.ativo == true && "
        r"\(\$db\.recursos\.equipe_id == null \|\| \$db\.recursos\.equipe_id == 0\)", consulta)
    assert 'return = {type: "list"}' in consulta
    # o Xano grava FK nula como 0; a tag em branco conta como sem tag
    laco = _bloco(codigo, "foreach ($recursos_sem_equipe) {")
    assert re.search(r'if \(\(\(\$rs\.codigo_equipe_tag \?\? ""\)\|trim\) == ""\) \{\s*'
                     r"var\.update \$qtd_sem_tag \{ value = \$qtd_sem_tag \+ 1 \}", laco)
    # falha na contagem não bloqueia o alerta e não inventa número
    assert re.search(r"catch \{\s*var\.update \$sem_tag_ok \{ value = false \}\s*\}", codigo)
    assert 'var $sem_tag_txt { value = ($sem_tag_ok == true) ? ($qtd_sem_tag|to_text) : "indisponível" }' in codigo
    # a consulta acontece só depois do limite e antes de montar o conteúdo e enviar
    assert codigo.index("$decorrido_ms < $limite_ms") < codigo.index("db.query recursos") < codigo.index("var $assunto") < codigo.index("api.request")
    assert codigo.count("db.query recursos") == 1


def contar_sem_tag(recursos, projeto_id):
    """Espelho da regra de `where` + laço do .xs (a forma da condição é conferida no teste acima)."""
    total = 0
    for r in recursos:
        if r.get("projeto_id") != projeto_id or r.get("ativo") is not True:
            continue
        if (r.get("equipe_id") in (None, 0)) and (r.get("codigo_equipe_tag") or "").strip() == "":
            total += 1
    return total


def test_espelho_recursos_sem_tag():
    recursos = [
        {"projeto_id": 5, "ativo": True, "equipe_id": None, "codigo_equipe_tag": None},      # conta
        {"projeto_id": 5, "ativo": True, "equipe_id": 0, "codigo_equipe_tag": ""},           # conta (FK nula = 0)
        {"projeto_id": 5, "ativo": True, "equipe_id": 0, "codigo_equipe_tag": "   "},        # conta (tag em branco)
        {"projeto_id": 5, "ativo": True, "equipe_id": 0, "codigo_equipe_tag": "EQP1"},       # equipe não vinculada: não conta
        {"projeto_id": 5, "ativo": True, "equipe_id": 3, "codigo_equipe_tag": "EQP3"},       # com equipe: não conta
        {"projeto_id": 5, "ativo": False, "equipe_id": None, "codigo_equipe_tag": ""},       # inativo: não conta
        {"projeto_id": 6, "ativo": True, "equipe_id": None, "codigo_equipe_tag": ""},        # outro projeto
        {"projeto_id": None, "ativo": True, "equipe_id": None, "codigo_equipe_tag": ""},     # não classificado
    ]
    assert contar_sem_tag(recursos, 5) == 3
    assert contar_sem_tag([], 5) == 0


MENSAGEM_NAO_ADMIN = "Alerta enviado ao DevOps do projeto."


def test_resposta_so_traz_status_e_mensagem_e_so_admin_ve_o_endereco_mascarado():
    """I1: não admin recebe mensagem fixa (nem parte do e-mail); admin, o endereço mascarado."""
    codigo = _codigo(NOTIFICAR)
    resposta = _bloco(codigo, "var $resposta {\n      value = {")
    assert re.findall(r"^\s*(\w+)\s*:", resposta, re.M) == ["status", "mensagem"]
    assert re.search(r'status\s*: "enviado"', resposta) and "mensagem: $mensagem_final" in resposta
    assert "$destino" not in resposta and "$email" not in resposta and "$mascarado" not in resposta
    # padrão (todos os perfis): mensagem fixa, sem nenhuma variável
    assert f'var $mensagem_final {{ value = "{MENSAGEM_NAO_ADMIN}" }}' in codigo
    # o ÚNICO uso de $mascarado fora da atribuição é dentro do ramo de admin
    admin = _bloco_re(codigo, r"if \(\$eh_admin == true\) \{")
    assert re.fullmatch(r'\s*var\.update \$mensagem_final \{ value = "Alerta enviado para " ~ \$mascarado ~ "\." \}\s*', admin)
    resto = codigo.replace(admin, "")
    usos = re.findall(r"[^\n]*\$mascarado[^\n]*", resto)
    assert len(usos) == 2 and all(re.match(r"\s*(var \$mascarado|var\.update \$mascarado) ", u) for u in usos), usos
    assert re.search(
        r'var\.update \$mascarado \{ value = \(\(\$destino\|split:"@"\|first\)\|substr:0:1\) ~ "\*\*\*@" ~ \(\$destino\|split:"@"\|last\) \}',
        codigo)
    assert "Alerta enviado para" not in resto, "o texto com endereço só existe no ramo de admin"
    # o aviso do limite não registrado (mesmo texto para todos) vem DEPOIS e não carrega endereço
    assert codigo.index("if ($eh_admin == true)") < codigo.index("if ($registro_falhou)") < codigo.index("var $resposta")


def test_mascara_e_calculada_antes_do_envio_ao_resend():
    """M3: nenhuma exceção depois de o Resend aceitar pode vir do cálculo da máscara."""
    codigo = _codigo(NOTIFICAR)
    assert codigo.count("var.update $mascarado") == 1, "um único ponto calcula a máscara"
    calculo = codigo.index("var.update $mascarado")
    assert codigo.index("var $janela_idem") < calculo < codigo.index("var $envio_status { value = 0 }") < codigo.index("api.request")
    # dentro do ramo de aceite (depois do envio) não há mais nenhum cálculo de máscara nem split do destino
    aceite = _bloco_re(codigo, r"if \(\$envio_status >= 200 && \$envio_status < 300\) \{")
    assert "$mascarado" not in aceite and "$destino" not in aceite and "split" not in aceite
    depois = codigo[codigo.index("api.request"):]
    assert "split:" not in depois and "$destino" not in depois


def test_limite_nao_registrado_vira_aviso_na_mensagem_de_sucesso():
    codigo = _codigo(NOTIFICAR)
    assert "var $registro_falhou { value = false }" in codigo
    # a falha da gravação do instante (e só ela) liga o aviso, sem virar erro HTTP
    assert re.search(
        r"data = \{devops_ultimo_envio_em: \$instante_envio, devops_ultimo_envio_por: \$solicitante_atual\.id\}\s*\}\s*\}\s*catch \{\s*"
        r"var\.update \$registro_falhou \{ value = true \}", codigo)
    bloco = _bloco_re(codigo, r"if \(\$registro_falhou\) \{")
    assert re.search(r'\$mensagem_final \{\s*value = \$mensagem_final ~ " Aviso: não foi possível registrar o limite de 5 minutos', bloco)
    assert "$registro_falhou" not in re.sub(
        r"var \$registro_falhou \{ value = false \}|var\.update \$registro_falhou \{ value = true \}|if \(\$registro_falhou\) \{", "", codigo)
    assert not re.search(r"precondition \(\$registro_falhou", codigo), "o aviso não pode virar erro"
    # o aviso fica depois da última precondition (sucesso) e antes da resposta
    assert codigo.index('precondition ($estado == "enviado")') < codigo.index("if ($registro_falhou)") < codigo.index("var $resposta")


# ---------------------------------------------------------------------------
# Limite de 1 envio / 5 min, trava e registro só após aceite
# ---------------------------------------------------------------------------

def test_limite_de_5_minutos_responde_429_com_segundos_restantes():
    codigo = _codigo(NOTIFICAR)
    assert "var $limite_ms { value = 300000 }" in codigo
    assert re.search(r"var \$ultimo_envio \{ value = \(\$proj_atual != null\) \? \(\$proj_atual\.devops_ultimo_envio_em \?\? 0\) : 0 \}", codigo)
    assert "var $decorrido_ms { value = $agora_ms - $ultimo_envio }" in codigo
    bloco = _bloco_re(codigo, r'if \(\$estado == "" && \$ultimo_envio > 0 && \$decorrido_ms < \$limite_ms\) \{')
    assert 'var.update $estado { value = "limite" }' in bloco
    # 429 só com o estado "limite"; a mensagem usa o MESMO $segundos_restantes
    _precondicao(codigo, '$estado != "limite"', "toomanyrequests", "$msg_limite")
    msg = re.search(r"var \$msg_limite \{\s*value = (.*?)\n\s*\}", codigo, re.S).group(1)
    assert re.fullmatch(
        r'"Já foi enviado um alerta deste projeto há pouco\. Aguarde " ~ \(\$segundos_restantes\|to_text\) ~ '
        r'" segundos para enviar outro \(limite: 1 envio a cada 5 minutos\)\."', msg)
    assert codigo.index("var $msg_limite") < codigo.index('precondition ($estado != "limite")')
    # o limite é conferido antes de montar o resumo e de chamar o provedor
    assert codigo.index("$decorrido_ms < $limite_ms") < codigo.index('function.run "costguard/resumo_consumo"') < codigo.index("api.request")


def test_segundos_restantes_ficam_entre_1_e_300_sem_depender_de_round():
    codigo = _codigo(NOTIFICAR)
    bloco = _bloco_re(codigo, r'if \(\$estado == "" && \$ultimo_envio > 0 && \$decorrido_ms < \$limite_ms\) \{')
    assert "var $resto_ms { value = ($decorrido_ms < 0) ? $limite_ms : ($limite_ms - $decorrido_ms) }" in bloco
    assert "var.update $segundos_restantes { value = (($resto_ms / 1000)|round:0)|to_int }" in bloco
    assert "+ 999" not in codigo, "o arredondamento para cima por soma foi trocado pelo clamp"
    assert re.search(
        r"if \(\$segundos_restantes < 1\) \{\s*var\.update \$segundos_restantes \{ value = 1 \}\s*\}\s*"
        r"elseif \(\$segundos_restantes > 300\) \{\s*var\.update \$segundos_restantes \{ value = 300 \}\s*\}", bloco)
    # o clamp acontece ANTES de o estado "limite" ser marcado e de a mensagem ser montada
    assert bloco.index("$segundos_restantes > 300") < bloco.index('value = "limite"')
    assert "var $segundos_restantes { value = 0 }" in codigo, "valor inicial neutro (só lido com estado limite)"


def test_trava_por_projeto_com_orfa_e_liberacao_no_finally():
    codigo = _codigo(NOTIFICAR)
    assert 'var $trava_nome { value = "devops_projeto_" ~ ($input.id|to_text) }' in codigo
    assert re.search(r"db\.add travas \{\s*data = \{nome: \$trava_nome, adquirida_em: \$agora_trava\}", codigo)
    assert "foreach ([1, 2]) {" in codigo
    assert "if ($trava_id == null && $trava_ocupada == false) {" in codigo
    assert "var $idade_trava { value = $agora_cmp - $trava_atual.adquirida_em }" in codigo
    assert re.search(r"\$idade_trava > 120000 && \$tentativa == 1\) \{\s*db\.del travas \{\s*field_name = \"id\"\s*field_value = \$trava_atual\.id", codigo)
    assert codigo.count("var.update $trava_ocupada { value = true }") == 2
    fin = _bloco(codigo, "finally {")
    assert re.search(r'db\.del travas \{\s*field_name = "id"\s*field_value = \$trava_id', fin)
    _precondicao(codigo, "$trava_id != null", "toomanyrequests",
                 '"Já existe um envio em andamento para este projeto. Tente novamente em instantes."')
    # a seção crítica (try) contém o limite, o envio e o registro
    sec = codigo[codigo.index("as $solicitante_atual"):codigo.index("finally {")]
    for parte in ("$decorrido_ms < $limite_ms", "api.request", "devops_ultimo_envio_em"):
        assert parte in sec
    # falha inesperada na seção crítica vira o estado de falha (a trava é liberada no finally)
    assert re.search(r"catch \{\s*var\.update \$falha \{ value = true \}\s*\}\s*finally \{", codigo)


def test_instante_so_e_registrado_quando_o_provedor_aceita():
    codigo = _codigo(NOTIFICAR)
    assert codigo.count("devops_ultimo_envio_em:") == 1, "um único ponto grava o instante"
    aceite = _bloco_re(codigo, r"if \(\$envio_status >= 200 && \$envio_status < 300\) \{")
    assert 'var.update $estado { value = "enviado" }' in aceite
    assert "db.edit projetos" in aceite and "devops_ultimo_envio_em: $instante_envio" in aceite
    assert re.search(r'\}\s*else \{\s*var\.update \$estado \{ value = "falha_envio" \}\s*\}', codigo)
    assert "falha_envio" not in aceite and codigo.count('var.update $estado { value = "enviado" }') == 1
    assert codigo.count("db.edit projetos") == 1
    pos_aceite = codigo.index("$envio_status >= 200 && $envio_status < 300")
    assert codigo.index("api.request") < pos_aceite < codigo.index("devops_ultimo_envio_em:") < codigo.index('value = "falha_envio"')
    assert re.search(r"data = \{devops_ultimo_envio_em: \$instante_envio, devops_ultimo_envio_por: \$solicitante_atual\.id\}", codigo)


def test_registro_de_quem_e_quando_na_propria_linha_do_projeto_sem_tabela_nova():
    """Decisão: colunas aditivas em `projetos` (quando + quem), gravadas juntas e só após o aceite do Resend."""
    codigo = _codigo(NOTIFICAR)
    assert codigo.count("devops_ultimo_envio_por:") == 1 and codigo.count("devops_ultimo_envio_em:") == 1
    # quem = usuário da sessão relido com a trava, nunca valor vindo da requisição
    assert "devops_ultimo_envio_por: $solicitante_atual.id" in codigo
    assert not re.search(r"devops_ultimo_envio_por:\s*\$input", codigo)
    aceite = _bloco_re(codigo, r"if \(\$envio_status >= 200 && \$envio_status < 300\) \{")
    assert "devops_ultimo_envio_por" in aceite, "só é gravado quando o provedor aceita"
    # a única escrita nova é em `projetos`; a trava é a única outra tabela escrita
    assert sorted(set(re.findall(r"db\.(?:add|edit|del) (\w+)", codigo))) == ["projetos", "travas"]
    assert set(re.findall(r"db\.add (\w+)", codigo)) == {"travas"}
    tabela = _ler(TABELA)
    assert re.search(r"^\s*int devops_ultimo_envio_por\?\s*$", tabela, re.M)
    assert re.search(r"^\s*int devops_ultimo_envio_em\?\s*$", tabela, re.M)
    # nenhuma tabela nova para o registro
    novas = [p.name for p in (XANO / "table").glob("*.xs") if re.search(r"devops|notific|envio", p.name)]
    assert novas == [], novas
    # `alertas` e `travas` não foram alteradas para guardar o registro
    for outra in ("alertas.xs", "travas.xs"):
        assert "devops" not in _ler(XANO / "table" / outra).lower(), outra


def test_cada_estado_vira_o_erro_http_certo_na_ordem_certa_e_so_enviado_chega_ao_sucesso():
    codigo = _codigo(NOTIFICAR)
    padrao = [
        ("$falha == false", "standard", '"Não foi possível concluir o envio do alerta. Tente novamente em instantes."'),
        ('$estado != "sem_sessao"', "unauthorized", '"Token inválido ou expirado"'),
        ('$estado != "sem_projeto"', "notfound", '"Projeto não encontrado"'),
        ('$estado != "projeto_inativo"', "inputerror", MSG_INATIVO_LITERAL),
        ('$estado != "sem_destino"', "inputerror", '"Este projeto não tem e-mail do DevOps cadastrado."'),
        ('$estado != "limite"', "toomanyrequests", "$msg_limite"),
        ('$estado != "teto_diario"', "toomanyrequests", MSG_TETO_LITERAL),
        ('$estado != "falha_resumo" && $estado != "falha_conteudo"', "standard",
         '"Não foi possível montar o alerta deste projeto. Tente novamente em instantes."'),
        ('$estado != "falha_envio"', "standard", '"Não foi possível enviar o e-mail agora. Tente novamente em instantes."'),
        ('$estado == "enviado"', "standard", '"Não foi possível concluir o envio do alerta. Tente novamente em instantes."'),
    ]
    posicoes = [_precondicao(codigo, *item).start() for item in padrao]
    assert posicoes == sorted(posicoes), "as preconditions de estado devem seguir esta ordem"
    assert posicoes[0] > codigo.index("finally {"), "o estado só é avaliado depois de liberar a trava"
    assert posicoes[-1] < codigo.index("var $resposta"), "a resposta de sucesso vem depois de todas"
    # e todo estado atribuído tem sua precondition (nenhum estado novo escapa para o sucesso)
    atribuidos = set(re.findall(r'var\.update \$estado \{ value = "(\w+)" \}', codigo))
    assert atribuidos == {"sem_sessao", "sem_projeto", "projeto_inativo", "sem_destino", "limite", "teto_diario",
                          "falha_resumo", "falha_conteudo", "falha_envio", "enviado"}


def test_erros_usam_mensagens_genericas_em_portugues():
    codigo = _codigo(NOTIFICAR)
    mensagens = re.findall(r'error = "([^"]+)"', codigo)
    assert "Não foi possível enviar o e-mail agora. Tente novamente em instantes." in mensagens
    assert "O envio de e-mail não está configurado no servidor." in mensagens
    for m in mensagens:
        assert not re.search(r"resend|api[_ ]?key|bearer|re_[A-Za-z0-9]", m, re.I), m


# ---------------------------------------------------------------------------
# Função de validação, tabela e demais endpoints de projeto
# ---------------------------------------------------------------------------

def test_tabela_projetos_so_acrescenta_colunas_opcionais():
    texto = _ler(TABELA)
    assert re.search(r"^\s*text email_devops\? filters=trim\|lower\s*$", texto, re.M)
    assert re.search(r"^\s*int devops_ultimo_envio_em\?\s*$", texto, re.M)
    assert re.search(r"^\s*int devops_ultimo_envio_por\?\s*$", texto, re.M)
    # colunas e índices originais preservados
    for original in ("int id", "text nome filters=trim", "text codigo filters=trim|upper", "decimal budget",
                     "enum status?=ativo", "timestamp criado_em?=now",
                     'type: "btree|unique", field: [{name: "codigo", op: "asc"}]',
                     'guid = "FKsUn2RpttLw4as7xWHWe3ys-GE"'):
        assert original in texto, f"coluna/índice original ausente: {original}"
    # nenhuma das duas novas é obrigatória nem tem índice único
    assert "email_devops" not in re.search(r"index = \[.*?\n  \]", texto, re.S).group(0)


def test_criar_valida_no_servidor_so_com_admin_antes_de_gravar():
    codigo = _codigo(CRIAR)
    admin = _precondicao(codigo, '$usuario_logado.status == "ativo" && $usuario_logado.role == "admin"',
                         "accessdenied", '"Acesso negado"')
    funcao = re.search(r'function\.run "costguard/normalizar_email_devops" \{\s*input = \{email: \$input\.email_devops\}\s*\} as \$email_check', codigo)
    assert funcao, "criar deve normalizar `$input.email_devops` com a função compartilhada"
    pre = _precondicao(codigo, "$email_check.valido == true", "inputerror", '"Informe um e-mail válido para o DevOps."')
    assert admin.start() < funcao.start() < pre.start() < codigo.index("db.add projetos")
    assert "text email_devops? filters=trim" in codigo
    assert re.search(r"email_devops: \$email_check\.email", codigo)
    assert codigo.count("$input.email_devops") == 1
    assert 'email_devops    : (($novo_projeto.email_devops ?? "") == "") ? null : $novo_projeto.email_devops' in codigo


def test_editar_valida_no_servidor_so_com_admin_antes_de_gravar():
    codigo = _codigo(EDITAR)
    admin = _precondicao(codigo, '$usuario_logado.status == "ativo" && $usuario_logado.role == "admin"',
                         "accessdenied", '"Acesso negado"')
    funcao = re.search(r'function\.run "costguard/normalizar_email_devops" \{\s*input = \{email: \$email_enviado_bruto\}\s*\} as \$email_check', codigo)
    assert funcao
    pre = _precondicao(codigo, "$email_check.valido == true", "inputerror", '"Informe um e-mail válido para o DevOps."')
    assert admin.start() < funcao.start() < pre.start() < codigo.index("db.edit projetos")
    assert re.search(r"email_devops: \$email_devops_novo", codigo)
    assert not re.search(r"email_devops\s*:\s*null", codigo), "db.edit ignora null: nunca gravar null"
    assert 'email_devops    : (($projeto_atualizado.email_devops ?? "") == "") ? null : $projeto_atualizado.email_devops' in codigo


def test_editar_so_remove_com_a_flag_explicita_e_nunca_com_espacos():
    codigo = _codigo(EDITAR)
    # entrada sem `filters=trim`: o servidor precisa enxergar os espaços
    assert re.search(r"^\s*text email_devops\?\s*$", codigo, re.M), "email_devops deve ser `text email_devops?` (sem filtro trim)"
    assert "bool remover_email_devops?=false" in codigo
    assert re.search(r'var \$email_devops_novo \{ value = \(\$projeto_alvo\.email_devops \?\? ""\) \}', codigo), "padrão: mantém o atual"
    assert 'var $email_enviado_bruto { value = ($input.email_devops ?? "") }' in codigo
    assert "var $email_enviado_aparado { value = ($email_enviado_bruto|trim) }" in codigo
    # ramo da remoção: exige a flag, recusa e-mail junto, e é o ÚNICO lugar que grava ""
    remocao = _bloco_re(codigo, r"if \(\$input\.remover_email_devops == true\) \{")
    _precondicao(remocao, '$email_enviado_aparado == ""', "inputerror", '"Informe o e-mail do DevOps ou peça a remoção, não os dois."')
    assert 'var.update $email_devops_novo { value = "" }' in remocao
    assert codigo.count('var.update $email_devops_novo { value = "" }') == 1
    # ramo do e-mail enviado: só com texto não vazio; só espaços é erro claro (não remove)
    troca = _bloco_re(codigo, r'elseif \(\$email_enviado_bruto != ""\) \{')
    branco = _precondicao(troca, '$email_enviado_aparado != ""', "inputerror")
    assert "remover_email_devops=true" in branco.group(0)
    assert troca.index("precondition ($email_enviado_aparado") < troca.index("function.run")
    assert "var.update $email_devops_novo { value = $email_check.email }" in troca
    # nenhum outro caminho altera o e-mail
    assert len(re.findall(r"var\.update \$email_devops_novo", codigo)) == 2


def test_listar_so_admin_recebe_o_email_e_nunca_devolve_registro_cru():
    codigo = _codigo(LISTAR)
    sessao = _precondicao(codigo, '$usuario_sessao != null && $usuario_sessao.status == "ativo"', "unauthorized",
                          '"Token inválido ou expirado"')
    assert sessao.start() < codigo.index("db.query projetos"), "sessão ativa antes de ler projetos"
    assert re.search(r'var \$eh_admin \{ value = \(\$usuario_sessao\.role == "admin"\) \}', codigo)
    admin = _bloco_re(codigo, r"if \(\$eh_admin\) \{")
    assert 'email_devops    : (($p.email_devops ?? "") == "") ? null : $p.email_devops' in admin
    fora = re.sub(r'tem_email_devops\s*: \(\(\$\w+\.email_devops \?\? ""\) != ""\)', "", codigo.replace(admin, ""))
    assert not re.search(r"email_devops", fora), "o endereço só pode aparecer dentro do ramo de admin"
    assert re.search(r"var \$item \{\s*value = \{\s*id\s*: \$p\.id\s*nome\s*: \$p\.nome\s*codigo\s*: \$p\.codigo\s*budget\s*: \$p\.budget\s*status\s*: \$p\.status\s*"
                     r'tem_email_devops\s*: \(\(\$p\.email_devops \?\? ""\) != ""\)\s*\}', codigo)
    assert re.search(r"var\.update \$lista_saida \{ value = \$lista_saida\|push:\$item \}", codigo)
    assert re.search(r"response = \$lista_saida\b", codigo) and not re.search(r"response = \$lista_projetos", codigo)
    assert "devops_ultimo_envio" not in codigo


def test_listar_informa_tem_email_devops_a_todos_os_perfis_sem_expor_o_endereco():
    codigo = _codigo(LISTAR)
    booleano = 'tem_email_devops: (($p.email_devops ?? "") != "")'
    assert codigo.count(booleano) == 2, "no item base (todos) e no item de admin"
    admin = _bloco_re(codigo, r"if \(\$eh_admin\) \{")
    base = codigo.replace(admin, "")
    assert booleano in base, "o booleano está FORA do ramo de admin: vale para todos os perfis"
    # fora do ramo de admin só existe o booleano, nunca o texto do endereço
    assert "$p.email_devops" not in re.sub(r'tem_email_devops\s*: \(\(\$p\.email_devops \?\? ""\) != ""\)', "", base)


def test_detalhe_informa_tem_email_devops_a_todos_os_perfis_sem_expor_o_endereco():
    codigo = _codigo(DETALHE)
    booleano = 'tem_email_devops: (($projeto.email_devops ?? "") != "")'
    assert codigo.count(booleano) == 2
    admin = _bloco_re(codigo, r'if \(\$usuario_sessao\.role == "admin"\) \{')
    base = codigo.replace(admin, "")
    assert booleano in base
    assert "$projeto.email_devops" not in re.sub(r'tem_email_devops\s*: \(\(\$projeto\.email_devops \?\? ""\) != ""\)', "", base)


def test_respostas_de_criar_e_editar_tambem_trazem_tem_email_devops():
    assert 'tem_email_devops: (($novo_projeto.email_devops ?? "") != "")' in _codigo(CRIAR)
    assert 'tem_email_devops: (($projeto_atualizado.email_devops ?? "") != "")' in _codigo(EDITAR)


def test_registro_de_envio_nunca_e_devolvido_por_nenhuma_leitura_ou_escrita_de_projeto():
    for arquivo in (LISTAR, DETALHE, CRIAR, EDITAR):
        assert "devops_ultimo_envio" not in _codigo(arquivo), arquivo.name
    # nem o painel nem o resumo de consumo
    for nome in ("painel_projeto_GET.xs", "painel_GET.xs", "projetos_resumo_consumo_mtd_GET.xs"):
        assert "devops" not in _codigo(APP / nome).lower(), nome


def test_envio_e_somente_manual_nenhum_outro_xs_chama_ou_usa_o_envio():
    """Nada no ciclo/sincronização/alertas dispara e-mail: só este endpoint conhece o Resend e o envio."""
    marcadores = ("notificar-devops", "notificar_devops", "api.resend.com", "EMAIL_API_KEY", "EMAIL_FROM",
                  "devops_ultimo_envio", "COSTGUARD_APP_URL")
    donos = {NOTIFICAR, NOTIFICAR_RECURSOS}  # os dois avisos manuais (orçamento e recursos sem equipe)
    for arquivo in XANO.rglob("*.xs"):
        if arquivo in donos:
            continue
        codigo = _codigo(arquivo)
        for marcador in marcadores:
            if arquivo == TABELA and marcador == "devops_ultimo_envio":
                continue  # a coluna existe na tabela e é lida/gravada só pelo endpoint
            assert marcador not in codigo, f"{arquivo.relative_to(XANO)} usa `{marcador}`"
    # ciclo automático do app (Python): só o endpoint de sincronização, nunca o de e-mail
    for py in (XANO.parent / "projetoImpacta").glob("sincronizacao*.py"):
        assert "notificar" not in py.read_text(encoding="utf-8").lower(), py.name
    # nenhum agendamento/tarefa no workspace chama o envio
    assert "notificar" not in _ler(XANO / "workspace" / "miguels_workspace.xs").lower()


def test_detalhe_so_admin_recebe_o_email_e_nunca_devolve_registro_cru():
    codigo = _codigo(DETALHE)
    sessao = _precondicao(codigo, '$usuario_sessao != null && $usuario_sessao.status == "ativo"', "unauthorized",
                          '"Token inválido ou expirado"')
    assert sessao.start() < codigo.index("db.get projetos")
    _precondicao(codigo, "$projeto != null", "notfound", '"Projeto não encontrado"')
    admin = _bloco_re(codigo, r'if \(\$usuario_sessao\.role == "admin"\) \{')
    assert 'email_devops    : (($projeto.email_devops ?? "") == "") ? null : $projeto.email_devops' in admin
    fora = re.sub(r'tem_email_devops\s*: \(\(\$\w+\.email_devops \?\? ""\) != ""\)', "", codigo.replace(admin, ""))
    assert not re.search(r"email_devops", fora), "o endereço só pode aparecer dentro do ramo de admin"
    assert re.search(r"var \$resposta \{\s*value = \{\s*id\s*: \$projeto\.id\s*nome\s*: \$projeto\.nome\s*codigo\s*: \$projeto\.codigo\s*budget\s*: \$projeto\.budget\s*status\s*: \$projeto\.status\s*"
                     r'tem_email_devops\s*: \(\(\$projeto\.email_devops \?\? ""\) != ""\)\s*\}', codigo)
    assert re.search(r"response = \$resposta\b", codigo) and not re.search(r"response = \$projeto\b", codigo)
    assert "devops_ultimo_envio" not in codigo


def test_funcao_de_validacao_regras_basicas():
    codigo = _codigo(NORMALIZAR)
    assert 'var $bruto { value = (($input.email ?? "")|trim)|to_lower }' in codigo
    assert "var $tamanho { value = $bruto|strlen }" in codigo
    assert "var $vazio { value = ($tamanho == 0) }" in codigo
    assert "var $formato_ok { value = false }" in codigo
    # só vira válido se não vazio, dentro de 254 e no formato
    assert re.search(
        r'if \(\$vazio == false && \$tamanho <= 254 && \("/\^.*\$/"\|regex_matches:\$bruto\)\) \{\s*'
        r'var\.update \$formato_ok \{ value = true \}', codigo)
    assert codigo.count("var.update $formato_ok { value = true }") == 1
    # resultado: e-mail devolvido SÓ quando o formato é válido; vazio devolve ""
    resultado = _bloco_re(codigo, r"var \$resultado \{\s*value = \{")
    assert re.search(r"vazio : \$vazio\s*valido: \(\$vazio \|\| \$formato_ok\)\s*email : \(\$formato_ok\) \? \$bruto : \"\"", resultado)


def test_arquivos_novos_sem_segredo_nem_email_real():
    permitido_dominio = "exemplo.com"
    for arquivo in (NOTIFICAR, NORMALIZAR, TABELA, CRIAR, EDITAR, LISTAR, DETALHE):
        texto = _ler(arquivo)
        assert not re.search(r"\bre_[A-Za-z0-9_]{8,}", texto), f"{arquivo.name}: parece chave do Resend"
        for dominio in re.findall(r"[A-Za-z0-9_.+-]+@([A-Za-z0-9.-]+)", texto):
            assert dominio == permitido_dominio, f"{arquivo.name}: e-mail com domínio {dominio}"


# ---------------------------------------------------------------------------
# ESPELHO em Python da lógica do .xs. Parâmetros extraídos do texto Xano.
# Prova a lógica escrita no texto; NÃO prova o comportamento dos filtros do Xano.
# ---------------------------------------------------------------------------

def _regex_email() -> "re.Pattern[str]":
    m = re.search(r'"/(\^\[a-z0-9_%\+-\].*?\$)/"\|regex_matches:\$bruto', _ler(NORMALIZAR))
    assert m, "regex do e-mail não encontrada em normalizar_email_devops.xs"
    return re.compile(m.group(1))


def _parametros_normalizar():
    """(limite de tamanho, usa trim, usa to_lower), lidos do .xs."""
    xs = _codigo(NORMALIZAR)
    limite = int(re.search(r"\$tamanho <= (\d+)", xs).group(1))
    bruto = re.search(r"var \$bruto \{ value = (.*?) \}\n", xs).group(1)
    return limite, "|trim" in bruto, "|to_lower" in bruto


def normalizar(entrada):
    """Espelho de costguard/normalizar_email_devops: devolve (vazio, valido, email)."""
    limite, usa_trim, usa_lower = _parametros_normalizar()
    bruto = entrada or ""
    if usa_trim:
        bruto = bruto.strip()
    if usa_lower:
        bruto = bruto.lower()
    vazio = len(bruto) == 0
    ok = (not vazio) and len(bruto) <= limite and _regex_email().search(bruto) is not None
    return vazio, (vazio or ok), (bruto if ok else "")


def _parametros_nome():
    """(limite de caracteres, usa trim) do nome, lidos de costguard/limpar_texto_linha."""
    linha = re.search(r"var\.update \$limpo \{ value = (.*?) \}\n", _codigo(FUNCOES / "limpar_texto_linha.xs")).group(1)
    return int(re.search(r"substr:0:(\d+)", linha).group(1)), "|trim" in linha


def escapar_nome(nome):
    """Espelho da limpeza/escape do nome: (texto_simples, html), trocas lidas das funções .xs."""
    codigo = _codigo(FUNCOES / "escapar_html.xs")
    m = re.search(r"var \$escapado \{\s*value = (.*?)\n\s*\}", codigo, re.S)
    trocas = [(de, para) for de, para in re.findall(r'\|replace:"((?:[^"\\]|\\.)*)":"((?:[^"\\]|\\.)*)"', m.group(1))]
    trocas = [(de.replace('\\"', '"'), para) for de, para in trocas]
    limite, usa_trim = _parametros_nome()
    limpo = nome
    for ctrl in ("\r", "\n", "\t"):
        limpo = limpo.replace(ctrl, " ")
    if usa_trim:
        limpo = limpo.strip()
    limpo = limpo[:limite]
    html = limpo
    for de, para in trocas:
        html = html.replace(de, para)
    return limpo, html


def mascarar(email):
    """Espelho do mascaramento: tamanho do trecho inicial e literal `***@` lidos do .xs."""
    m = re.search(
        r'var\.update \$mascarado \{ value = \(\(\$destino\|split:"@"\|first\)\|substr:0:(\d+)\) ~ "([^"]*)" ~ '
        r'\(\$destino\|split:"@"\|last\) \}', _codigo(NOTIFICAR))
    assert m, "mascaramento não encontrado no .xs"
    local, dominio = email.split("@")
    return local[:int(m.group(1))] + m.group(2) + dominio


@pytest.mark.parametrize("entrada,esperado", [
    ("devops@exemplo.com", "devops@exemplo.com"),
    ("  DevOps.Time+alerta@Exemplo.COM  ", "devops.time+alerta@exemplo.com"),
    ("a_b%c@sub.exemplo.com.br", "a_b%c@sub.exemplo.com.br"),
    ("a@exemplo.co", "a@exemplo.co"),
])
def test_espelho_aceita_e_normaliza_para_minusculas(entrada, esperado):
    assert normalizar(entrada) == (False, True, esperado)


@pytest.mark.parametrize("entrada", [
    "devops",                                   # sem @
    "devops@exemplo",                           # sem domínio com ponto
    "@exemplo.com",                             # sem caixa
    "a@@exemplo.com",
    "a b@exemplo.com",                          # espaço
    "a@exemplo.com, b@exemplo.com",             # duas caixas (vírgula)
    "a@exemplo.com;b@exemplo.com",              # ponto e vírgula
    "a@exemplo.com\nb@exemplo.com",             # quebra de linha
    "a@exemplo.com\r\nBcc: x@exemplo.com",      # injeção de cabeçalho
    "a\x00@exemplo.com",                        # caractere de controle
    "a@exemplo.com\tb",                         # tabulação
    "<a@exemplo.com>",                          # formato com colchetes
    "Nome <a@exemplo.com>",
    "a'b@exemplo.com",                          # aspas fora da lista fechada
    'a"b@exemplo.com',
    ".a@exemplo.com",                           # ponto no início da caixa
    "a..b@exemplo.com",                         # pontos seguidos
    "a@-exemplo.com",                           # rótulo começando com hífen
    "a@exemplo.c",                              # TLD curto
    "a@exemplo.com.",                           # ponto final
    "a@exemplo.123",                            # TLD numérico
    "a" * 250 + "@exemplo.com",                 # acima de 254
])
def test_espelho_rejeita_formatos_perigosos(entrada):
    vazio, valido, email = normalizar(entrada)
    assert (vazio, valido, email) == (False, False, "")


@pytest.mark.parametrize("entrada", ["", "   ", None, "\n"])
def test_espelho_vazio_significa_sem_destinatario_e_e_valido(entrada):
    assert normalizar(entrada) == (True, True, "")


def test_espelho_limite_de_254_caracteres_na_fronteira():
    dominio = "@exemplo.com"
    no_limite = "a" * (254 - len(dominio)) + dominio
    acima = "a" * (255 - len(dominio)) + dominio
    assert len(no_limite) == 254 and len(acima) == 255
    assert normalizar(no_limite) == (False, True, no_limite)
    assert normalizar(acima) == (False, False, "")


def test_espelho_quebra_de_linha_final_e_removida_pelo_trim_nao_aceita_no_meio():
    assert normalizar("a@exemplo.com\n") == (False, True, "a@exemplo.com")
    assert normalizar("a@exemplo.com\nx")[1] is False


def test_espelho_escape_do_nome_neutraliza_html_e_quebras_de_linha():
    texto, html = escapar_nome('<script>alert(1)</script> & "Projeto"\r\nBcc: x@exemplo.com\tfim')
    assert "\n" not in texto and "\r" not in texto and "\t" not in texto
    assert "<" not in html and ">" not in html
    assert "&lt;script&gt;" in html and "&amp;" in html
    assert "&amp;lt;" not in html, "o & deve ser escapado antes dos demais (sem escape duplo)"
    assert not re.search(r"[<>]", html)
    assert escapar_nome("  Alfa  ")[0] == "Alfa"


def test_espelho_escape_limita_o_tamanho_do_nome():
    texto, html = escapar_nome("x" * 500)
    assert len(texto) == 120 and len(html) == 120


def test_espelho_mascara_nunca_mostra_o_endereco_completo():
    assert mascarar("alerta@exemplo.com") == "a***@exemplo.com"
    assert "alerta" not in mascarar("alerta@exemplo.com")


# ---------------------------------------------------------------------------
# Projeto inativo (400), teto diário global (429 sem segundos) e ordem das checagens
# ---------------------------------------------------------------------------

def _posicoes_db_add_travas(codigo):
    posicoes = [m.start() for m in re.finditer(r"db\.add travas", codigo)]
    assert len(posicoes) == 2, "esperado: 1 db.add da trava do projeto + 1 db.add da ficha do teto diário"
    return posicoes


def test_projeto_inativo_responde_400_antes_de_qualquer_trava_ficha_ou_envio():
    codigo = _codigo(NOTIFICAR)
    inativo = _precondicao(codigo, '$projeto_alvo.status == "ativo"', "inputerror", MSG_INATIVO_LITERAL)
    for efeito in ("function.run", "db.add travas", "api.request", "db.edit projetos", "db.del travas", "now|to_int"):
        assert inativo.start() < codigo.index(efeito), f"o projeto inativo deve ser recusado antes de `{efeito}`"
    # depois de "projeto existe" e ANTES de "tem e-mail"
    existe = _precondicao(codigo, "$projeto_alvo != null", "notfound", '"Projeto não encontrado"')
    sem_email = _precondicao(codigo, "$email_pre.vazio == false && $email_pre.valido == true", "inputerror")
    assert existe.start() < inativo.start() < sem_email.start()
    # a mensagem é exatamente a combinada, em português, sem dado do usuário
    assert MSG_INATIVO == "Este projeto está inativo; não é possível notificar o DevOps."
    # dentro da seção crítica o status é relido com a trava (projeto desativado durante a espera)
    assert re.search(
        r'elseif \(\$proj_atual == null\) \{\s*var\.update \$estado \{ value = "sem_projeto" \}\s*\}\s*'
        r'elseif \(\$proj_atual\.status != "ativo"\) \{\s*var\.update \$estado \{ value = "projeto_inativo" \}\s*\}', codigo)
    _precondicao(codigo, '$estado != "projeto_inativo"', "inputerror", MSG_INATIVO_LITERAL)
    # só estas duas leituras do status do projeto (a de fora e a da seção crítica)
    assert len(re.findall(r"\$(?:projeto_alvo|proj_atual)\.status\b", codigo)) == 2


def test_teto_diario_sao_30_fichas_numeradas_de_1_a_30_na_tabela_travas_ja_existente():
    codigo = _codigo(NOTIFICAR)
    lista = re.search(r"foreach \(\[((?:\d+, )*\d+)\]\) \{\s*each as \$n_ficha \{", codigo)
    assert lista, "laço das fichas do teto diário não encontrado"
    numeros = [int(n) for n in lista.group(1).split(", ")]
    assert numeros == list(range(1, 31)), "o teto diário é de EXATAMENTE 30 fichas, numeradas de 1 a 30"
    assert re.search(
        r'db\.add travas \{\s*data = \{nome: "devops_dia_" ~ \$dia_civil ~ "_" ~ \(\$n_ficha\|to_text\), adquirida_em: \$agora_ms\}\s*\} as \$nova_ficha',
        codigo)
    assert re.search(r"var\.update \$ficha_id \{ value = \$nova_ficha\.id \}", codigo)
    # tabela já existente com índice único em `nome` (a atomicidade vem do banco); nenhuma tabela nova
    travas = _ler(XANO / "table" / "travas.xs")
    assert re.search(r'type: "btree\|unique", field: \[\{name: "nome", op: "asc"\}\]', travas)
    assert "devops" not in travas.lower()
    # constante no código, não configurável: nenhuma variável de ambiente nova nem input
    assert set(re.findall(r"\$env\.(\w+)", codigo)) == {"EMAIL_API_KEY", "EMAIL_FROM", "COSTGUARD_APP_URL"}
    assert re.search(r"\$input\.\w*teto", codigo, re.I) is None
    # tenta a próxima ficha só enquanto nenhuma foi tomada; sem ficha livre vira "teto_diario"
    assert re.search(r"if \(\$ficha_id == null\) \{\s*try_catch \{\s*try \{\s*db\.add travas", codigo)
    assert re.search(r'if \(\$ficha_id == null\) \{\s*var\.update \$estado \{ value = "teto_diario" \}\s*\}', codigo)
    assert codigo.count('value = "teto_diario"') == 1


def _dia_civil_do_xs():
    """(deslocamento em ms, formato, fuso) lidos do .xs."""
    codigo = _codigo(NOTIFICAR)
    desloc = re.search(r"var \$agora_brt_ms \{ value = \$agora_ms - (\d+) \}", codigo)
    assert desloc, "dia civil: `$agora_ms - <deslocamento>` não encontrado"
    fmt = re.search(r'var \$dia_civil \{ value = \$agora_brt_ms\|format_timestamp:"([^"]+)":"([^"]+)" \}', codigo)
    assert fmt, "dia civil: `format_timestamp` não encontrado"
    return int(desloc.group(1)), fmt.group(1), fmt.group(2)


def dia_civil(instante_ms):
    """Espelho do dia civil do .xs: instante menos o deslocamento, formatado no fuso lido do .xs."""
    from datetime import datetime, timezone
    deslocamento, formato, fuso = _dia_civil_do_xs()
    assert formato == "Y-m-d" and fuso == "UTC"
    return datetime.fromtimestamp((instante_ms - deslocamento) / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def _ms(ano, mes, dia, h=0, m=0, s=0, ms=0):
    from datetime import datetime, timezone
    return int(datetime(ano, mes, dia, h, m, s, tzinfo=timezone.utc).timestamp() * 1000) + ms


def test_dia_civil_e_o_de_sao_paulo_utc_menos_3_com_formato_de_data_completo():
    desloc, formato, fuso = _dia_civil_do_xs()
    assert desloc == 3 * 60 * 60 * 1000, "America/Sao_Paulo = UTC-3 (sem horário de verão desde 2019)"
    assert (formato, fuso) == ("Y-m-d", "UTC"), "dia inteiro (não só o mês) e fuso UTC, o único comprovado no repositório"
    # a data é a base do nome da ficha: um dia = 30 nomes novos
    assert "$dia_civil" in _codigo(NOTIFICAR) and "format_timestamp" in _codigo(NOTIFICAR)
    # viradas do dia: 02:59:59.999 UTC ainda é o dia anterior em São Paulo; 03:00 UTC já é o novo dia
    assert dia_civil(_ms(2026, 11, 25, 2, 59, 59, 999)) == "2026-11-24"
    assert dia_civil(_ms(2026, 11, 25, 3, 0, 0)) == "2026-11-25"
    assert dia_civil(_ms(2026, 11, 24, 23, 0, 0)) == "2026-11-24"      # 20h em SP
    assert dia_civil(_ms(2026, 11, 25, 0, 30, 0)) == "2026-11-24"      # 21h30 em SP: ainda dia 24
    assert dia_civil(_ms(2026, 1, 1, 2, 0, 0)) == "2025-12-31"         # virada de ano
    assert dia_civil(_ms(2026, 3, 1, 2, 59, 59, 999)) == "2026-02-28"  # virada de mês


def test_dia_civil_coincide_com_america_sao_paulo_depois_de_2019():
    """O deslocamento fixo só é correto se o Brasil segue sem horário de verão: confere na base de fusos, se houver."""
    from datetime import datetime, timedelta, timezone
    try:
        from zoneinfo import ZoneInfo
        sp = ZoneInfo("America/Sao_Paulo")
    except Exception:  # pragma: no cover - sem base de fusos neste ambiente
        pytest.skip("base de fusos (tzdata) indisponível: equivalência com America/Sao_Paulo NÃO VERIFICADA aqui")
    inicio = datetime(2020, 1, 1, tzinfo=timezone.utc)
    for horas in range(0, 24 * 366 * 6, 7):  # 6 anos, amostras a cada 7 h (verão e inverno)
        instante = inicio + timedelta(hours=horas)
        esperado = instante.astimezone(sp).strftime("%Y-%m-%d")
        assert dia_civil(int(instante.timestamp() * 1000)) == esperado, instante


def test_ficha_so_e_tomada_depois_de_todas_as_recusas_e_antes_do_conteudo_e_do_envio():
    codigo = _codigo(NOTIFICAR)
    trava_projeto, ficha = _posicoes_db_add_travas(codigo)
    sem_sessao = codigo.index('value = "sem_sessao"')
    inativo = codigo.index('value = "projeto_inativo"')
    sem_destino = codigo.index('value = "sem_destino"')
    limite = codigo.index('value = "limite"')
    assert trava_projeto < sem_sessao < inativo < sem_destino < limite < ficha, "a ficha vem depois de TODAS as recusas"
    assert ficha < codigo.index('function.run "costguard/resumo_consumo"') < codigo.index("var $assunto") < codigo.index("api.request")
    # o laço das fichas só roda sem recusa pendente
    assert re.search(r'if \(\$estado == ""\) \{\s*foreach \(\[1, 2, 3,', codigo)
    # dia civil calculado depois do `agora` e antes do laço
    assert codigo.index("var $agora_ms { value = now|to_int }") < codigo.index("var $agora_brt_ms") < codigo.index("var $dia_civil") < ficha


def test_ficha_so_fica_consumida_com_aceite_do_resend_e_e_devolvida_no_finally():
    codigo = _codigo(NOTIFICAR)
    # única atribuição de "aceita": dentro do ramo de aceite do Resend (2xx)
    aceite = _bloco_re(codigo, r"if \(\$envio_status >= 200 && \$envio_status < 300\) \{")
    assert aceite.count("var.update $ficha_aceita { value = true }") == 1
    assert codigo.count("var.update $ficha_aceita { value = true }") == 1
    assert "var $ficha_aceita { value = false }" in codigo, "a ficha nasce NÃO aceita"
    assert len(re.findall(r"\$ficha_aceita", codigo)) == 3, "declaração, atribuição no aceite e a condição do finally"
    # o finally devolve a ficha quando tomada E não aceita (cobre recusa, timeout, falha do alerta e exceção)
    fin = _bloco(codigo, "finally {")
    devolucao = _bloco_re(fin, r"if \(\$ficha_id != null && \$ficha_aceita == false\) \{")
    assert re.search(r'db\.del travas \{\s*field_name = "id"\s*field_value = \$ficha_id\s*\}', devolucao)
    assert codigo.count("field_value = $ficha_id") == 1, "a ficha só é apagada nesse ponto"
    assert 'field_name = "nome"' not in devolucao, "nunca apaga a ficha por nome (poderia apagar a de outro envio)"
    # a devolução vem depois de liberar a trava do projeto e nunca impede liberá-la nem muda a resposta
    assert fin.index("field_value = $trava_id") < fin.index("$ficha_id != null")
    assert re.search(r"catch \{\s*var\.update \$ficha_liberacao_falhou \{ value = true \}\s*\}", devolucao)
    assert "$ficha_liberacao_falhou" not in re.sub(
        r"var \$ficha_liberacao_falhou \{ value = false \}|var\.update \$ficha_liberacao_falhou \{ value = true \}", "", codigo)
    # o envio recusado/falho (falha_envio) NÃO marca a ficha como aceita
    assert re.search(r'\}\s*else \{\s*var\.update \$estado \{ value = "falha_envio" \}\s*\}', codigo)
    assert "ficha_aceita" not in codigo[codigo.index('value = "falha_envio"'):codigo.index("finally {")]


def test_teto_diario_responde_429_com_mensagem_fixa_sem_numero_de_segundos():
    codigo = _codigo(NOTIFICAR)
    pre = _precondicao(codigo, '$estado != "teto_diario"', "toomanyrequests", MSG_TETO_LITERAL)
    bloco = pre.group(0)
    assert MSG_TETO == "Limite diário de notificações atingido; tente amanhã."
    assert not re.search(r"\d", MSG_TETO), "sem número na mensagem"
    linha_erro = re.search(r"error = [^\n]+", bloco).group(0)
    assert "$" not in linha_erro and "~" not in linha_erro, "mensagem literal: sem variável nem concatenação"
    assert "segundos" not in MSG_TETO.lower() and "aguarde" not in MSG_TETO.lower()
    # fica depois do 429 do limite de 5 min e antes dos erros de conteúdo/envio
    limite = _precondicao(codigo, '$estado != "limite"', "toomanyrequests", "$msg_limite")
    falha = _precondicao(codigo, '$estado != "falha_resumo" && $estado != "falha_conteudo"', "standard")
    assert limite.start() < pre.start() < falha.start()
    # os segundos do limite de 5 min continuam só nesse 429
    assert codigo.count("$segundos_restantes|to_text") == 1


def test_helper_do_app_nao_extrai_segundos_do_teto_diario_e_extrai_do_limite_de_5_min():
    from projetoImpacta import api
    assert api.segundos_restantes({"code": "ERROR_CODE_TOO_MANY_REQUESTS", "message": MSG_TETO}) is None
    assert api.segundos_restantes({"message": MSG_TETO}) is None
    # o helper troca o texto de qualquer 429 por um genérico: a tela deste endpoint usa corpo["message"] direto
    assert api.mensagem_erro({"code": "ERROR_CODE_TOO_MANY_REQUESTS", "message": MSG_TETO}) != MSG_TETO
    assert api.mensagem_erro({"message": MSG_TETO}) == MSG_TETO
    assert api.segundos_restantes({"message": "Já foi enviado um alerta deste projeto há pouco. Aguarde 42 segundos "
                                              "para enviar outro (limite: 1 envio a cada 5 minutos)."}) == 42


def test_ordem_das_checagens_do_endpoint():
    """401, 404, 400 inativo, 400 sem e-mail, 500 sem configuração, 429 trava, 429 limite, 429 teto, conteúdo, envio."""
    codigo = _codigo(NOTIFICAR)
    etapas = [
        codigo.index('precondition ($usuario_logado != null && $usuario_logado.status == "ativo")'),
        codigo.index("precondition ($projeto_alvo != null)"),
        codigo.index('precondition ($projeto_alvo.status == "ativo")'),
        codigo.index("precondition ($email_pre.vazio == false && $email_pre.valido == true)"),
        codigo.index('precondition ($email_chave != "" && $email_from != "")'),
        codigo.index("precondition ($trava_id != null)"),
        codigo.index('value = "sem_sessao"'),
        codigo.index('value = "projeto_inativo"'),
        codigo.index('value = "sem_destino"'),
        codigo.index('value = "limite"'),
        _posicoes_db_add_travas(codigo)[1],
        codigo.index('value = "teto_diario"'),
        codigo.index('function.run "costguard/resumo_consumo"'),
        codigo.index("api.request"),
    ]
    assert etapas == sorted(etapas) and len(set(etapas)) == len(etapas)
    # o teto só é tocado se nenhuma recusa anterior marcou o estado
    assert re.search(r'if \(\$estado == ""\) \{\s*foreach \(\[1, 2, 3,', codigo)


# --- espelho do mecanismo de fichas (parâmetros lidos do .xs) ---------------------------------

def _parametros_ficha():
    codigo = _codigo(NOTIFICAR)
    teto = len(re.search(r"foreach \(\[((?:\d+, )*\d+)\]\) \{\s*each as \$n_ficha", codigo).group(1).split(", "))
    m = re.search(r'nome: "([^"]*)" ~ \$dia_civil ~ "([^"]*)" ~ \(\$n_ficha\|to_text\)', codigo)
    assert m, "nome da ficha não encontrado"
    return teto, m.group(1), m.group(2)


class _TabelaTravas:
    """Índice único em `nome`: add devolve False se já existir (a violação vira catch no .xs)."""

    def __init__(self):
        self.nomes = set()

    def add(self, nome):
        if nome in self.nomes:
            return False
        self.nomes.add(nome)
        return True

    def delete(self, nome):
        self.nomes.discard(nome)


def tomar_ficha(tabela, dia):
    teto, prefixo, separador = _parametros_ficha()
    for n in range(1, teto + 1):
        nome = f"{prefixo}{dia}{separador}{n}"
        if tabela.add(nome):
            return nome
    return None


def test_espelho_fichas_nunca_passam_de_30_por_dia_e_virada_do_dia_zera():
    teto, prefixo, separador = _parametros_ficha()
    assert (teto, prefixo, separador) == (30, "devops_dia_", "_")
    tabela = _TabelaTravas()
    tomadas = [tomar_ficha(tabela, "2026-11-24") for _ in range(30)]
    assert None not in tomadas and len(set(tomadas)) == 30
    assert tomadas[0] == "devops_dia_2026-11-24_1" and tomadas[-1] == "devops_dia_2026-11-24_30"
    assert tomar_ficha(tabela, "2026-11-24") is None, "a 31ª tentativa do dia é recusada"
    assert tomar_ficha(tabela, "2026-11-25") == "devops_dia_2026-11-25_1", "novo dia civil, novo teto"
    # devolver uma ficha libera exatamente uma vaga
    tabela.delete("devops_dia_2026-11-24_7")
    assert tomar_ficha(tabela, "2026-11-24") == "devops_dia_2026-11-24_7"
    assert tomar_ficha(tabela, "2026-11-24") is None


def test_espelho_envios_aceitos_nunca_passam_de_30_mesmo_com_falhas_e_envios_simultaneos():
    import random
    rng = random.Random(20261124)
    tabela, aceitos, negados = _TabelaTravas(), 0, 0
    em_voo = []  # fichas tomadas e ainda sem desfecho (projetos enviando ao mesmo tempo)
    for _ in range(400):
        if em_voo and (len(em_voo) >= 3 or rng.random() < 0.5):
            nome = em_voo.pop(rng.randrange(len(em_voo)))
            if rng.random() < 0.35:       # Resend não aceitou: ficha devolvida (finally)
                tabela.delete(nome)
            else:                         # aceito: a ficha fica consumida
                aceitos += 1
        else:
            nome = tomar_ficha(tabela, "2026-11-24")
            if nome is None:
                negados += 1
            else:
                em_voo.append(nome)
        assert len(tabela.nomes) <= 30, "nunca mais de 30 fichas existentes no dia"
    aceitos += len(em_voo)  # desfecho pendente ao fim: conta como aceito (pior caso)
    assert aceitos <= 30 and negados > 0
    assert len(tabela.nomes) == aceitos, "só as fichas dos envios aceitos permanecem consumidas"

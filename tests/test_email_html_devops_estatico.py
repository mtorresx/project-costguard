"""E-mail HTML + texto do DevOps e aviso de "recursos sem equipe": verificações estáticas, sem rede.

Leem os `.xs` locais como TEXTO (mesmo padrão de `test_notificar_devops_estatico.py`) e conferem, com
expressões regulares ANCORADAS, as regras de segurança, de layout e de contrato dos dois e-mails:

  - `xano/api/app/notificar_devops_projeto_POST.xs`  (alerta de orçamento, reescrito em HTML + texto);
  - `xano/api/app/notificar_recursos_sem_equipe_projeto_POST.xs`  (endpoint novo, QUALQUER perfil ativo; só o admin vê o endereço mascarado);
  - funções novas em `xano/function/costguard/`: escapar_html, limpar_texto_linha, formatar_numero_br,
    mes_extenso_pt_br, email_html_layout, email_html_linha.

O escape é verificado por UM verificador por arquivo (`problemas_*`): o teste "sem problemas" exige lista vazia
no código real e os testes de MUTAÇÃO aplicam, EM MEMÓRIA, uma sabotagem (tirar o escape de um campo, trocar a
variável escapada pela crua, apagar uma troca do escape, etc.) e exigem que o MESMO verificador acuse o problema.
Nenhum arquivo é alterado. Há também ESPELHOS em Python (formatação brasileira, mês por extenso, largura da barra,
lista dos 50 + "e mais N", escape) com parâmetros extraídos dos `.xs` quando possível.

O que estes testes NÃO provam:
  - nada sobre o comportamento do Xano PUBLICADO: sintaxe aceita, `replace`, `substr`, `to_int`, `round`, `floor`,
    `format_timestamp` com "America/Sao_Paulo" em timestamp de tabela, `sort = {id: "asc"}`, função devolvendo
    texto simples, `function.run` dentro de `foreach`, tamanho máximo do corpo da requisição;
  - nada sobre o Resend (campos html/text, idempotência, limites) nem sobre a renderização nos clientes de e-mail;
  - os espelhos em Python provam a LÓGICA escrita no texto, não a execução no Xano.
Nenhum teste chama o Resend, o Xano ou qualquer rede; nomes e e-mails são fictícios (`@exemplo.com`).
"""

import re
from decimal import Decimal
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
XANO = RAIZ / "xano"
APP = XANO / "api" / "app"
FUNCOES = XANO / "function" / "costguard"

NOTIFICAR = APP / "notificar_devops_projeto_POST.xs"
RECURSOS = APP / "notificar_recursos_sem_equipe_projeto_POST.xs"
ESCAPAR = FUNCOES / "escapar_html.xs"
LIMPAR = FUNCOES / "limpar_texto_linha.xs"
FORMATAR = FUNCOES / "formatar_numero_br.xs"
MES = FUNCOES / "mes_extenso_pt_br.xs"
LAYOUT = FUNCOES / "email_html_layout.xs"
LINHA = FUNCOES / "email_html_linha.xs"
TABELA = XANO / "table" / "projetos.xs"
CONTRATO = RAIZ / "docs" / "interno" / "CONTRATO_API_DEVOPS.md"

ARQUIVOS_EMAIL = [NOTIFICAR, RECURSOS, ESCAPAR, LIMPAR, FORMATAR, MES, LAYOUT, LINHA]


def _ler(caminho: Path) -> str:
    return caminho.read_text(encoding="utf-8")


def _ler_doc_interno(caminho: Path) -> str:
    """Le um documento de `docs/interno/`. Essa pasta e ignorada pelo Git (nao existe num clone limpo do repositorio
    publico): sem o arquivo, o teste e PULADO, nunca reprovado. Com o arquivo, a verificacao e a mesma de sempre."""
    if not caminho.exists():
        pytest.skip("docs/interno não faz parte do repositório público")
    return _ler(caminho)


def _sem_comentarios(texto: str) -> str:
    return "\n".join(l for l in texto.splitlines() if not l.strip().startswith("//"))


def _codigo(caminho: Path) -> str:
    """Texto sem linhas de comentário."""
    return _sem_comentarios(_ler(caminho))


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


def _bloco(texto: str, abertura: str) -> str:
    """Conteúdo (sem as chaves externas) do bloco que começa em `abertura` (termina em `{` ou `[`)."""
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


def _precondicao(codigo: str, condicao: str, tipo: str, mensagem: str | None = None) -> "re.Match[str]":
    padrao = (r"precondition \(" + re.escape(condicao) + r'\) \{\s*error_type = "' + re.escape(tipo) + r'"\s*error = '
              + (re.escape(mensagem) if mensagem is not None else r"[^\n]+") + r"\s*\}")
    m = re.search(padrao, codigo)
    assert m, f"precondition ancorada não encontrada: ({condicao}) {tipo} {mensagem or ''}"
    return m


def _mutar(codigo: str, antigo: str, novo: str) -> str:
    assert antigo in codigo, f"trecho a mutar não existe: {antigo!r}"
    return codigo.replace(antigo, novo, 1)


def _mutar_re(codigo: str, padrao: str, novo: str) -> str:
    resultado, n = re.subn(padrao, lambda _m: novo, codigo, count=1, flags=re.S)
    assert n == 1, f"trecho a mutar não existe: {padrao!r}"
    return resultado


# ---------------------------------------------------------------------------
# Verificadores de ESCAPE (um por arquivo). Lista vazia = sem problema.
# ---------------------------------------------------------------------------

LIMPEZA = "costguard/limpar_texto_linha"
ESCAPE = "costguard/escapar_html"


def _chamada(codigo: str, funcao: str, entrada: str, saida: str) -> bool:
    return bool(re.search(
        r'function\.run "' + re.escape(funcao) + r'" \{\s*input = \{texto: ' + entrada + r'\}\s*\} as \$' + saida + r"\b", codigo))


def _linhas_html(codigo: str) -> list[str]:
    """Linhas que montam HTML: as que citam `$h_...` ou `valor_html`."""
    return [l for l in codigo.splitlines() if re.search(r"\$h_|valor_html", l)]


def problemas_campos(codigo: str, campos) -> list[str]:
    """Cada campo livre do banco: entra SÓ pela limpeza, é escapado e o HTML usa só a versão escapada."""
    problemas = []
    linhas_html = _linhas_html(codigo)
    for rotulo, fonte, limpo, html in campos:
        if not _chamada(codigo, LIMPEZA, fonte, limpo):
            problemas.append(f"{rotulo}: a fonte não passa por {LIMPEZA}")
        if not _chamada(codigo, ESCAPE, r"\$" + limpo, html):
            problemas.append(f"{rotulo}: sem {ESCAPE} (${limpo} -> ${html})")
        if not any(re.search(r"\$" + html + r"\b", l) for l in linhas_html):
            problemas.append(f"{rotulo}: o HTML não usa ${html}")
        if any(re.search(r"\$" + limpo + r"\b", l) for l in linhas_html):
            problemas.append(f"{rotulo}: o HTML usa a versão NÃO escapada ${limpo}")
    return problemas


def problemas_assunto(codigo: str) -> list[str]:
    m = re.search(r"var \$assunto \{\s*value = (.*?)\n\s*\}", codigo, re.S)
    if not m:
        return ["assunto não encontrado"]
    valor, problemas = m.group(1), []
    for ctrl in (r"\r", r"\n"):
        if '|replace:"' + ctrl + '":""' not in valor:
            problemas.append(f"assunto sem remoção de {ctrl}")
    if "$nome_limpo" not in valor:
        problemas.append("assunto não usa a versão limpa do nome")
    if re.search(r"\$(nome_html|proj_atual|enviado|solicitante|destino)", valor):
        problemas.append("assunto com dado indevido")
    return problemas


def problemas_escapar_html(codigo: str) -> list[str]:
    m = re.search(r"var \$escapado \{\s*value = (.*?)\n\s*\}", codigo, re.S)
    if not m:
        return ["bloco $escapado não encontrado"]
    trocas = [(de.replace('\\"', '"'), para) for de, para in
              re.findall(r'\|replace:"((?:[^"\\]|\\.)*)":"((?:[^"\\]|\\.)*)"', m.group(1))]
    esperado = [("&", "&amp;"), ("<", "&lt;"), (">", "&gt;"), ('"', "&quot;"), ("'", "&#39;")]
    problemas = []
    if trocas != esperado:
        problemas.append(f"trocas do escape: {trocas}")
    if 'var $bruto { value = ($input.texto ?? "") }' not in codigo:
        problemas.append("entrada nula não vira vazia")
    if "response = $escapado" not in codigo:
        problemas.append("resposta não é o texto escapado")
    return problemas


def problemas_limpar(codigo: str) -> list[str]:
    m = re.search(r"var \$limpo \{\s*value = (.*?)\n\s*\}", codigo, re.S)
    problemas = []
    if not m or re.findall(r'\|replace:"([^"]*)":" "', m.group(1)) != ["\\r", "\\n", "\\t"]:
        problemas.append("CR, LF e tabulação não são trocados por espaço")
    elif '($input.texto ?? "")' not in m.group(1):
        problemas.append("entrada nula não vira vazia")
    if "var.update $limpo { value = ($limpo|trim)|substr:0:120 }" not in codigo:
        problemas.append("sem trim e limite de 120")
    return problemas


def problemas_linha(codigo: str) -> list[str]:
    problemas = []
    if not _chamada(codigo, ESCAPE, r'\(\$input\.rotulo \?\? ""\)', "rotulo_html"):
        problemas.append("rótulo sem escape")
    if codigo.count("$input.rotulo") != 1:
        problemas.append("rótulo usado fora do escape")
    if "$rotulo_html" not in codigo:
        problemas.append("a linha não usa o rótulo escapado")
    if '($input.valor_html ?? "")' not in codigo:
        problemas.append("o valor HTML pronto não é usado")
    return problemas


def problemas_layout(codigo: str) -> list[str]:
    problemas = []
    for campo, saida in (("titulo", "titulo_html"), ("link", "link_html")):
        entrada = r'\(\$input\.titulo \?\? ""\)' if campo == "titulo" else r"\$link_limpo"
        if not _chamada(codigo, ESCAPE, entrada, saida):
            problemas.append(f"{campo} sem escape")
        if codigo.count("$input." + campo) != 1:
            problemas.append(f"{campo} usado fora do escape")
        if "$" + saida not in re.sub(r"function\.run[^}]*\} as \$" + saida, "", codigo, flags=re.S):
            problemas.append(f"a moldura não usa ${saida}")
    # Link: aparado e só vira botão se começar com https:// (e tiver algo depois)
    for literal in ('var $link_limpo { value = (($input.link ?? "")|trim) }',
                    "var $link_prefixo { value = $link_limpo|substr:0:8 }",
                    'var $link_ok { value = (($link_limpo|strlen) > 8 && $link_prefixo == "https://") }',
                    'var $botao_html { value = "" }',
                    'var.update $html { value = $html ~ $botao_html ~ "</td></tr>" }'):
        if literal not in codigo:
            problemas.append(f"validação do link ausente: {literal}")
    m = re.search(r"if \(\$link_ok == true\) \{", codigo)
    if not m:
        problemas.append("o botão não depende de $link_ok")
    else:
        botao = _bloco_re(codigo, r"if \(\$link_ok == true\) \{")
        if "$link_html" not in botao or ">Abrir projeto no CostGuard</a>" not in botao:
            problemas.append("o botão não está dentro do teste do link")
        if "<a href" in codigo.replace(botao, ""):
            problemas.append("há âncora fora do teste do link")
    return problemas


def problemas_mes(codigo: str) -> list[str]:
    """mes_extenso_pt_br: fora do padrão AAAA-MM (01 a 12) o resultado é VAZIO, nunca o texto cru."""
    problemas = []
    if 'var $resultado { value = "" }' not in codigo:
        problemas.append("entrada fora do padrão não devolve vazio")
    if codigo.count("var.update $resultado") != 1 or 'var.update $resultado { value = $nome ~ " de " ~ $ano }' not in codigo:
        problemas.append("o resultado só pode ser atualizado dentro do padrão (nome de ano)")
    if '"/^[0-9]{4}-(0[1-9]|1[0-2])$/"|regex_matches:$bruto' not in codigo:
        problemas.append("padrão AAAA-MM ausente")
    if "response = $resultado" not in codigo:
        problemas.append("a resposta não é o resultado")
    return problemas


def _params_formatar(codigo: str) -> dict:
    """Literais numéricos CRÍTICOS de formatar_numero_br, lidos do .xs com regex ancorado (None = não achou)."""
    def lista(variavel):
        m = re.search(r"foreach \(\[((?:\d+, )*\d+)\]\) \{\s*each as \$" + variavel + r"\b", codigo)
        return len(m.group(1).split(", ")) if m else None

    def numero(padrao):
        m = re.search(padrao, codigo)
        return int(m.group(1)) if m else None

    return {
        "zeros": lista("passo"),
        "grupos": lista("grupo"),
        "escala2": numero(r"if \(\$input\.casas == 2\) \{\s*var\.update \$escala \{ value = (\d+) \}"),
        "escala1": numero(r"elseif \(\$input\.casas == 1\) \{\s*var\.update \$escala \{ value = (\d+) \}"),
        "divisor": numero(r"var\.update \$resto_num \{ value = \(\(\(\$resto_num - \$cauda_num\) / (\d+)\)\|round:0\)\|to_int \}"),
    }


# Valores exigidos (contrato da função): zeros à esquerda 2x, 5 grupos de milhares, escala 100 (2 casas) e 10 (1 casa),
# divisor 1000 por grupo. Os demais literais são conferidos como linhas inteiras abaixo.
PARAMS_FORMATAR_ESPERADOS = {"zeros": 2, "grupos": 5, "escala2": 100, "escala1": 10, "divisor": 1000}
LITERAIS_FORMATAR = [
    "var $minimo { value = $input.casas + 1 }",
    "if (($digitos|strlen) < $minimo) {",
    'var.update $digitos { value = "0" ~ $digitos }',
    "var $corte { value = ($digitos|strlen) - $input.casas }",
    "var.update $fracao_txt { value = $digitos|substr:$corte }",
    "var $resto_num { value = ((($absoluto - $fracao_num) / $escala)|round:0)|to_int }",
    "if (($resto_txt|strlen) > 3) {",
    "var $inicio_cauda { value = ($resto_txt|strlen) - 3 }",
    "var $cauda_txt { value = $resto_txt|substr:$inicio_cauda }",
]


def problemas_formatar(codigo: str) -> list[str]:
    problemas = []
    for nome, valor in _params_formatar(codigo).items():
        if valor != PARAMS_FORMATAR_ESPERADOS[nome]:
            problemas.append(f"{nome}: {valor} (esperado {PARAMS_FORMATAR_ESPERADOS[nome]})")
    for literal in LITERAIS_FORMATAR:
        if literal not in codigo:
            problemas.append(f"literal ausente: {literal}")
    return problemas


def problemas_derivados(codigo: str, derivados) -> list[str]:
    """Valores não livres (mês por extenso, data do recurso) também passam por escapar_html antes do HTML."""
    problemas = []
    linhas_html = _linhas_html(codigo)
    for rotulo, cru, html in derivados:
        if not _chamada(codigo, ESCAPE, r"\$" + cru, html):
            problemas.append(f"{rotulo}: sem {ESCAPE} (${cru} -> ${html})")
        if not any(re.search(r"\$" + html + r"\b", l) for l in linhas_html):
            problemas.append(f"{rotulo}: o HTML não usa ${html}")
        if any(re.search(r"\$" + cru + r"\b", l) for l in linhas_html):
            problemas.append(f"{rotulo}: o HTML usa a versão NÃO escapada ${cru}")
        if not re.search(r"var(?:\.update)? \$escapados_juntos \{ value = [^\n]*\$" + html + r"\b", codigo):
            problemas.append(f"{rotulo}: ${html} fora da autoverificação do escape")
    return problemas


DERIVADOS_ORCAMENTO = [("mês de referência", "mes_extenso", "mes_html")]
DERIVADOS_RECURSOS = [("mês de referência", "mes_extenso", "mes_html"), ("data do recurso", "r_data", "r_data_html")]


CAMPOS_ORCAMENTO = [
    ("nome do projeto", r'\(\$proj_atual\.nome \?\? ""\)', "nome_limpo", "nome_html"),
    ("enviado por", r'\(\$solicitante_atual\.nome \?\? ""\)', "enviado_limpo", "enviado_html"),
]

CAMPOS_RECURSOS = [
    ("nome do projeto", r'\(\$proj_atual\.nome \?\? ""\)', "nome_limpo", "nome_html"),
    ("enviado por", r'\(\$solicitante_atual\.nome \?\? ""\)', "enviado_limpo", "enviado_html"),
    ("nome do recurso", r"\$arn_nome", "r_nome", "r_nome_html"),
    ("serviço do recurso", r'\(\$rs\.servico \?\? ""\)', "r_servico", "r_servico_html"),
    ("região do recurso", r'\(\$rs\.regiao \?\? ""\)', "r_regiao", "r_regiao_html"),
]


def test_verificadores_aprovam_o_codigo_real():
    assert problemas_campos(_codigo(NOTIFICAR), CAMPOS_ORCAMENTO) == []
    assert problemas_campos(_codigo(RECURSOS), CAMPOS_RECURSOS) == []
    assert problemas_assunto(_codigo(NOTIFICAR)) == []
    assert problemas_assunto(_codigo(RECURSOS)) == []
    assert problemas_escapar_html(_codigo(ESCAPAR)) == []
    assert problemas_limpar(_codigo(LIMPAR)) == []
    assert problemas_linha(_codigo(LINHA)) == []
    assert problemas_layout(_codigo(LAYOUT)) == []
    assert problemas_derivados(_codigo(NOTIFICAR), DERIVADOS_ORCAMENTO) == []
    assert problemas_derivados(_codigo(RECURSOS), DERIVADOS_RECURSOS) == []
    assert problemas_mes(_codigo(MES)) == []
    assert problemas_formatar(_codigo(FORMATAR)) == []


# ---------------------------------------------------------------------------
# MUTAÇÕES em memória: o verificador TEM de acusar cada sabotagem.
# ---------------------------------------------------------------------------

def _sem_escape(codigo: str, limpo: str, html: str) -> str:
    """Troca a chamada de escape por uma cópia crua: `$html` passa a ser igual a `$limpo`."""
    return _mutar_re(codigo, r'function\.run "costguard/escapar_html" \{\s*input = \{texto: \$' + limpo + r'\}\s*\} as \$' + html + r"\b",
                     f"var ${html} {{ value = ${limpo} }}")


def _html_cru(codigo: str, limpo: str, html: str) -> str:
    """O HTML passa a usar a variável NÃO escapada (o escape existe, mas é ignorado)."""
    linhas = codigo.split("\n")
    for i, l in enumerate(linhas):
        if re.search(r"\$h_|valor_html", l) and re.search(r"\$" + html + r"\b", l):
            linhas[i] = re.sub(r"\$" + html + r"\b", "$" + limpo, l)
    novo = "\n".join(linhas)
    assert novo != codigo, f"nenhuma linha HTML usa ${html}"
    return novo


MUTACOES_CAMPOS = []
for _rotulo, _arq, _campos in (("orcamento", NOTIFICAR, CAMPOS_ORCAMENTO), ("recursos", RECURSOS, CAMPOS_RECURSOS)):
    for _campo in _campos:
        MUTACOES_CAMPOS.append(pytest.param(_arq, _campos, _campo, "sem_escape", id=f"{_rotulo}:{_campo[3]}:remove-escape"))
        MUTACOES_CAMPOS.append(pytest.param(_arq, _campos, _campo, "html_cru", id=f"{_rotulo}:{_campo[3]}:html-usa-cru"))


@pytest.mark.parametrize("arquivo,campos,campo,tipo", MUTACOES_CAMPOS)
def test_mutacao_do_escape_de_cada_campo_do_banco_e_detectada(arquivo, campos, campo, tipo):
    _, _, limpo, html = campo
    codigo = _codigo(arquivo)
    mutado = _sem_escape(codigo, limpo, html) if tipo == "sem_escape" else _html_cru(codigo, limpo, html)
    assert problemas_campos(mutado, campos), f"mutação {tipo} em {html} NÃO foi detectada"


def test_mutacao_a_limpeza_do_campo_e_removida_e_detectada():
    for arquivo, campos in ((NOTIFICAR, CAMPOS_ORCAMENTO), (RECURSOS, CAMPOS_RECURSOS)):
        for rotulo, fonte, limpo, html in campos:
            codigo = _codigo(arquivo)
            mutado = _mutar_re(codigo, r'function\.run "costguard/limpar_texto_linha" \{\s*input = \{texto: ' + fonte + r'\}\s*\} as \$' + limpo + r"\b",
                               f"var ${limpo} {{ value = \"\" }}")
            assert problemas_campos(mutado, campos), f"{arquivo.name}: sem limpeza de {limpo} não foi detectado"


TROCAS_ESCAPE = [("&", "&amp;"), ("<", "&lt;"), (">", "&gt;"), ('\\"', "&quot;"), ("'", "&#39;")]


@pytest.mark.parametrize("de,para", TROCAS_ESCAPE, ids=[p for _, p in TROCAS_ESCAPE])
def test_mutacao_remover_uma_troca_do_escape_html_e_detectada(de, para):
    codigo = _codigo(ESCAPAR)
    mutado = _mutar(codigo, f'|replace:"{de}":"{para}"', "")
    assert problemas_escapar_html(mutado)


def test_mutacao_escapar_o_e_comercial_por_ultimo_e_detectada():
    """Com & no fim, os & dos demais escapes seriam escapados de novo (&amp;lt;)."""
    codigo = _codigo(ESCAPAR)
    sem = _mutar(codigo, '($bruto|replace:"&":"&amp;")|replace:"<":"&lt;"', '$bruto|replace:"<":"&lt;"')
    mutado = _mutar(sem, "|replace:\"'\":\"&#39;\"", "|replace:\"'\":\"&#39;\"|replace:\"&\":\"&amp;\"")
    assert problemas_escapar_html(mutado)


def test_mutacao_entrada_nula_do_escape_e_detectada():
    assert problemas_escapar_html(_mutar(_codigo(ESCAPAR), '($input.texto ?? "")', "$input.texto"))


@pytest.mark.parametrize("ctrl", ["\\r", "\\n", "\\t"])
def test_mutacao_remover_a_troca_de_quebra_de_linha_da_limpeza_e_detectada(ctrl):
    assert problemas_limpar(_mutar(_codigo(LIMPAR), f'|replace:"{ctrl}":" "', ""))


def test_mutacao_limpeza_sem_limite_e_detectada():
    assert problemas_limpar(_mutar(_codigo(LIMPAR), "|substr:0:120", ""))


@pytest.mark.parametrize("arquivo", [NOTIFICAR, RECURSOS], ids=["orcamento", "recursos"])
@pytest.mark.parametrize("ctrl", [r"\r", r"\n"])
def test_mutacao_assunto_com_quebra_de_linha_e_detectada(arquivo, ctrl):
    codigo = _codigo(arquivo)
    assert problemas_assunto(_mutar(codigo, f'|replace:"{ctrl}":""', ""))


@pytest.mark.parametrize("arquivo", [NOTIFICAR, RECURSOS], ids=["orcamento", "recursos"])
def test_mutacao_assunto_com_nome_escapado_e_detectada(arquivo):
    codigo = _codigo(arquivo)
    mutado = _mutar_re(codigo, r'var \$assunto \{\s*value = \(\("\[CostGuard\] [^"]*" ~ \$nome_limpo',
                       'var $assunto { value = (("[CostGuard] x: " ~ $nome_html')
    assert problemas_assunto(mutado)


def test_mutacao_rotulo_da_linha_sem_escape_e_detectada():
    codigo = _codigo(LINHA)
    mutado = _mutar_re(codigo, r'function\.run "costguard/escapar_html" \{.*?\} as \$rotulo_html', 'var $rotulo_html { value = ($input.rotulo ?? "") }')
    assert problemas_linha(mutado)


@pytest.mark.parametrize("campo,saida", [("titulo", "titulo_html"), ("link", "link_html")])
def test_mutacao_titulo_ou_link_da_moldura_sem_escape_e_detectada(campo, saida):
    codigo = _codigo(LAYOUT)
    entrada = r'\(\$input\.titulo \?\? ""\)' if campo == "titulo" else r"\$link_limpo"
    bruto = '($input.titulo ?? "")' if campo == "titulo" else "$link_limpo"
    mutado = _mutar_re(codigo, r'function\.run "costguard/escapar_html" \{\s*input = \{texto: ' + entrada + r'\}\s*\} as \$' + saida,
                       f"var ${saida} {{ value = {bruto} }}")
    assert problemas_layout(mutado), campo


@pytest.mark.parametrize("campo,saida", [("titulo", "titulo_html"), ("link", "link_html")])
def test_mutacao_moldura_usando_a_entrada_crua_no_html_e_detectada(campo, saida):
    codigo = _codigo(LAYOUT)
    mutado = codigo.replace("~ $" + saida + " ~", '~ ($input.' + campo + ' ?? "") ~')
    assert mutado != codigo
    assert problemas_layout(mutado), campo


def botao_renderizado(link):
    """Espelho da decisão da moldura: o botão só existe com link https:// (aparado) e algo depois do prefixo."""
    limpo = (link or "").strip()
    return len(limpo) > 8 and limpo[:8] == "https://"


@pytest.mark.parametrize("link,esperado", [
    ("https://app.costguard.com.br/projetos/7", True), ("  https://app.exemplo.com/projetos/7  ", True),
    ("https://a", True), ("https://", False), ("", False), (None, False), ("   ", False),
    ("http://app.exemplo.com/projetos/7", False), ("javascript:alert(1)", False), ("data:text/html;base64,AAAA", False),
    ("HTTPS://app.exemplo.com", False), ("//app.exemplo.com/x", False), ("ftp://app.exemplo.com", False),
])
def test_espelho_botao_so_com_link_https(link, esperado):
    assert botao_renderizado(link) is esperado


def test_moldura_valida_o_link_https_e_so_entao_monta_o_botao():
    codigo = _codigo(LAYOUT)
    assert problemas_layout(codigo) == []
    botao = _bloco_re(codigo, r"if \(\$link_ok == true\) \{")
    assert botao.count("<a href='") == 1 and "$link_html" in botao
    assert "<a href" not in codigo.replace(botao, "")
    # sem link válido o corpo fecha igual, sem botão e sem erro (nenhuma precondition/throw na função)
    assert not re.search(r"precondition|throw|error_type", codigo)


@pytest.mark.parametrize("antigo,novo", [
    ("if ($link_ok == true) {", "if (true) {"),
    ('$link_prefixo == "https://"', '$link_prefixo == "http://"'),
    ("($link_limpo|strlen) > 8", "($link_limpo|strlen) > 0"),
    ('(($input.link ?? "")|trim)', '($input.link ?? "")'),
    ("var $link_prefixo { value = $link_limpo|substr:0:8 }", "var $link_prefixo { value = $link_limpo|substr:0:7 }"),
])
def test_mutacao_da_validacao_do_link_da_moldura_e_detectada(antigo, novo):
    assert problemas_layout(_mutar(_codigo(LAYOUT), antigo, novo)), (antigo, novo)


def test_mutacao_botao_fora_do_teste_do_link_e_detectada():
    codigo = _codigo(LAYOUT)
    mutado = _mutar(codigo, "var.update $html { value = $html ~ $botao_html ~ \"</td></tr>\" }",
                    "var.update $html { value = $html ~ \"<a href='\" ~ $link_html ~ \"'>x</a></td></tr>\" }")
    assert problemas_layout(mutado)


def test_limpar_texto_linha_mantem_so_cr_lf_tab_sem_inventar_sintaxe_e_documenta_o_risco():
    """Item aceito: sem precedente de escape unicode/classe de regex em .xs do repositório, a limpeza NÃO foi ampliada."""
    codigo = _codigo(LIMPAR)
    assert problemas_limpar(codigo) == []
    assert not re.search(r"\\u[0-9a-fA-F]{4}|\\x[0-9a-fA-F]{2}|\\v|\\f|\\0|regex_", codigo)
    comentario = _ler(LIMPAR)
    for trecho in ("RISCO ACEITO", "NÃO VERIFICADO", "U+2028", "U+202A", "U+2066", "U+0085", "JSON"):
        assert trecho in comentario, trecho


# ---------------------------------------------------------------------------
# Escape: espelho em Python (trocas lidas do .xs) e regras gerais
# ---------------------------------------------------------------------------

def _trocas_escape():
    m = re.search(r"var \$escapado \{\s*value = (.*?)\n\s*\}", _codigo(ESCAPAR), re.S)
    return [(de.replace('\\"', '"'), para) for de, para in
            re.findall(r'\|replace:"((?:[^"\\]|\\.)*)":"((?:[^"\\]|\\.)*)"', m.group(1))]


def escapar_html(texto):
    texto = texto or ""
    for de, para in _trocas_escape():
        texto = texto.replace(de, para)
    return texto


@pytest.mark.parametrize("entrada,esperado", [
    ("Projeto Alfa", "Projeto Alfa"),
    ("<script>alert(1)</script>", "&lt;script&gt;alert(1)&lt;/script&gt;"),
    ("A & B", "A &amp; B"),
    ("&lt;", "&amp;lt;"),                                  # sem escape duplo ao contrário: o & vem primeiro
    ('x" onmouseover="alert(1)', "x&quot; onmouseover=&quot;alert(1)"),
    ("x' onload='alert(1)", "x&#39; onload=&#39;alert(1)"),
    ("<img src=x onerror=alert(1)>", "&lt;img src=x onerror=alert(1)&gt;"),
    (None, ""),
    ("", ""),
])
def test_espelho_escape_html(entrada, esperado):
    assert escapar_html(entrada) == esperado


def test_funcao_escapar_html_existe_e_devolve_texto():
    codigo = _codigo(ESCAPAR)
    assert 'function "costguard/escapar_html" {' in codigo
    assert re.search(r"input \{\s*text texto\?\s*\}", codigo)
    assert not re.search(r"\|(trim|substr|to_lower|to_upper)", codigo), "o escape não altera nada além das 5 trocas"


def test_todo_texto_do_banco_dos_dois_endpoints_chega_ao_html_so_pelas_funcoes():
    """Fontes de texto livre: só entram por `limpar_texto_linha`; nenhuma outra leitura do banco vai ao corpo."""
    for arquivo, campos in ((NOTIFICAR, CAMPOS_ORCAMENTO), (RECURSOS, CAMPOS_RECURSOS)):
        codigo = _codigo(arquivo)
        assert codigo.count("$proj_atual.nome") == 1 and codigo.count("$solicitante_atual.nome") == 1, arquivo.name
        for _, fonte, limpo, html in campos:
            assert _chamada(codigo, LIMPEZA, fonte, limpo) and _chamada(codigo, ESCAPE, r"\$" + limpo, html)
    codigo = _codigo(RECURSOS)
    assert codigo.count("$rs.servico") == 1 and codigo.count("$rs.regiao") == 1 and codigo.count("$rs.arn") == 1
    assert codigo.count("$rs.criado_em") == 1, "a data entra só como número formatado (format_timestamp)"
    # nenhum outro campo do recurso (nem o ARN inteiro) vai ao e-mail
    assert set(re.findall(r"\$rs\.(\w+)", codigo)) == {"codigo_equipe_tag", "arn", "servico", "regiao", "criado_em"}


def test_html_do_recurso_e_o_texto_puro_usam_cada_um_a_sua_versao():
    codigo = _codigo(RECURSOS)
    html = re.search(r"var\.update \$h_linhas \{\s*value = (.*?)\n\s*\}", codigo, re.S).group(1)
    assert sorted(set(re.findall(r"\$(\w+)", html))) == ["h_linhas", "r_data_html", "r_nome_html", "r_regiao_html", "r_servico_html", "r_td"]
    texto = re.search(r"var\.update \$t_linhas \{ value = (.*?) \}\n", codigo).group(1)
    assert sorted(set(re.findall(r"\$(\w+)", texto))) == ["r_data", "r_nome", "r_regiao", "r_servico", "t_linhas"]
    # o texto puro nunca recebe entidades HTML
    for l in codigo.splitlines():
        if re.search(r"var(?:\.update)? \$(texto|t_linhas)\b", l):
            assert "&" not in l.replace("&&", ""), l
            assert "<" not in l, l


def test_texto_puro_dos_dois_emails_nao_usa_html_nem_escape():
    for arquivo in (NOTIFICAR, RECURSOS):
        codigo = _codigo(arquivo)
        linhas = [l for l in codigo.splitlines() if re.search(r"var(?:\.update)? \$texto\b", l)]
        assert len(linhas) >= 6, arquivo.name
        for l in linhas:
            assert not re.search(r"\$(h_\w+|\w+_html)\b", l), l
            assert "<" not in l and "&nbsp;" not in l, l
        assert "text   : $texto" in codigo


# ---------------------------------------------------------------------------
# HTML: layout em tabelas, sem recursos perigosos
# ---------------------------------------------------------------------------

PROIBIDOS_HTML = [r"<script", r"<img", r"<svg", r"url\(", r"@import", r"javascript:", r"<style", r"<iframe", r"<link",
                  r"<form", r"<object", r"<embed", r"<video", r"<audio", r"\bon[a-z]+\s*=", r"\bsrc\s*=", r"expression\(",
                  r"https?://"]


@pytest.mark.parametrize("arquivo", ARQUIVOS_EMAIL, ids=[a.name for a in ARQUIVOS_EMAIL])
def test_nenhum_recurso_perigoso_ou_externo_no_html(arquivo):
    codigo = _codigo(arquivo).lower()
    for proibido in PROIBIDOS_HTML:
        if proibido == r"https?://" and arquivo in (NOTIFICAR, RECURSOS, LAYOUT):
            continue  # endpoints: URL do Resend e padrão do link do app; moldura: só o prefixo "https://" (conferidos abaixo)
        assert not re.search(proibido, codigo), f"{arquivo.name}: `{proibido}`"


def test_moldura_so_cita_o_prefixo_https_e_nenhuma_url():
    assert set(re.findall(r"https?://[^\s\"')]*", _codigo(LAYOUT))) == {"https://"}
    assert "http://" not in _codigo(LAYOUT)


def test_urls_dos_endpoints_so_o_resend_e_o_link_padrao_do_app():
    for arquivo in (NOTIFICAR, RECURSOS):
        urls = set(re.findall(r"https?://[^\s\"')]*", _codigo(arquivo)))
        assert urls == {"https://api.resend.com/emails", "https://app.costguard.com.br", "https://"}, (arquivo.name, urls)


def test_moldura_tem_largura_maxima_600_cabecalho_escuro_acento_e_rodape():
    codigo = _codigo(LAYOUT)
    assert "width='600'" in codigo and "max-width:600px" in codigo
    assert re.search(r"max-width:600px", codigo) and "width:100%" in codigo
    assert "#14b8a6" in codigo
    assert re.search(r"background-color:#0f172a[^']*font-size:22px[^']*color:#ffffff;'>Cost<span style='color:#14b8a6;'>Guard</span>", codigo), \
        "cabeçalho escuro com 'CostGuard' em TEXTO e o acento"
    assert "Alerta manual enviado pelo CostGuard" in codigo
    assert ">Abrir projeto no CostGuard</a>" in codigo
    # só tabelas e CSS inline; atributos entre aspas simples (strings do XanoScript são de aspas duplas)
    assert codigo.count("<table") == codigo.count("</table>") == 3
    assert "<div" not in codigo and "<style" not in codigo
    assert "role='presentation'" in codigo
    # o corpo é claro (fundo branco do cartão) e o botão usa o acento
    assert "background-color:#ffffff" in codigo and "bgcolor='#14b8a6'" in codigo
    # estrutura fechada
    assert codigo.count("<html") == 1 and codigo.count("</html>") == 1 and codigo.count("<body") == 1 and codigo.count("</body>") == 1


def test_botao_usa_exatamente_o_link_do_projeto_do_email_atual():
    for arquivo in (NOTIFICAR, RECURSOS):
        codigo = _codigo(arquivo)
        assert "link: $link_projeto" in codigo, arquivo.name
        assert 'var $link_projeto { value = $app_url ~ "/projetos/" ~ ($input.id|to_text) }' in codigo
    assert "<a href='\" ~ $link_html ~ \"'" in _codigo(LAYOUT)
    # a lógica da base do link (COSTGUARD_APP_URL validada, 208, padrão) é IDÊNTICA nos dois endpoints
    def trecho(arquivo):
        c = _codigo(arquivo)
        return c[c.index("var $app_url_bruto"):c.index("var $link_projeto")]
    assert trecho(NOTIFICAR) == trecho(RECURSOS)
    assert 'var $app_url { value = "https://app.costguard.com.br" }' in trecho(NOTIFICAR)
    assert "<= 208" in trecho(NOTIFICAR)


def test_o_email_do_usuario_nunca_entra_no_corpo():
    for arquivo in (NOTIFICAR, RECURSOS):
        codigo = _codigo(arquivo)
        assert "$usuario_logado.email" not in codigo and "$solicitante_atual.email" not in codigo
        assert not re.search(r"\.email\b", codigo.replace("$email_pre.email", "").replace("$email_atual.email", "")), arquivo.name
        # o destino só aparece em `to`, no cálculo da máscara e na validação; nunca em linha de conteúdo
        for l in _linhas_html(codigo) + [x for x in codigo.splitlines() if re.search(r"var(?:\.update)? \$(texto|t_linhas)\b", x)]:
            assert "$destino" not in l and "$email" not in l and "$mascarado" not in l, l
        assert re.search(r"to\s*:\s*\[\$destino\]", codigo)
        # do usuário da sessão só se lê o nome (corpo), id, status e papel
        assert set(re.findall(r"\$solicitante_atual\.(\w+)", codigo)) <= {"nome", "id", "status", "role"}, arquivo.name


def test_dados_internos_nao_entram_nos_emails():
    for arquivo in (NOTIFICAR, RECURSOS):
        palavras = set(re.findall(r"\w+", _codigo(arquivo).lower()))
        for proibido in ("identificador_conta", "provedor_id", "username", "aws_access_key_id", "senha_hash"):
            assert proibido not in palavras, (arquivo.name, proibido)


# ---------------------------------------------------------------------------
# Assunto
# ---------------------------------------------------------------------------

def test_assuntos_tem_o_formato_pedido_e_nao_recebem_quebras_de_linha():
    cod = _codigo(NOTIFICAR)
    assert re.search(r'"\[CostGuard\] Orçamento em alerta: " ~ \$nome_limpo ~ " \(" ~ \$faixa_curta ~ "\)"', cod)
    rec = _codigo(RECURSOS)
    assert re.search(r'"\[CostGuard\] Recursos sem equipe: " ~ \$nome_limpo ~ " \(" ~ \(\$quantidade\|to_text\) ~ "\)"', rec)
    for codigo in (cod, rec):
        assert re.search(r"subject\s*:\s*\$assunto", codigo)
        assert problemas_assunto(codigo) == []
        # \r e \n são removidos do assunto INTEIRO (e o nome já vem sem CR/LF/tabulação da função de limpeza)
        valor = re.search(r"var \$assunto \{\s*value = (.*?)\n\s*\}", codigo, re.S).group(1)
        assert valor.endswith('|replace:"\\r":"")|replace:"\\n":""')


def assunto(modelo, nome, sufixo):
    limpo = nome
    for ctrl in ("\r", "\n", "\t"):
        limpo = limpo.replace(ctrl, " ")
    limpo = limpo.strip()[:120]
    return (modelo + limpo + f" ({sufixo})").replace("\r", "").replace("\n", "")


def test_espelho_assunto_nunca_tem_cr_lf_mesmo_com_nome_malicioso():
    nome = "Alfa\r\nBcc: x@exemplo.com\nX-Teste: 1"
    a = assunto("[CostGuard] Orçamento em alerta: ", nome, "Crítico")
    assert "\r" not in a and "\n" not in a
    assert a.startswith("[CostGuard] Orçamento em alerta: Alfa")
    assert a.endswith("(Crítico)")
    b = assunto("[CostGuard] Recursos sem equipe: ", nome, "7")
    assert "\r" not in b and "\n" not in b and b.endswith("(7)")


# ---------------------------------------------------------------------------
# Formatação brasileira (espelho do algoritmo de formatar_numero_br)
# ---------------------------------------------------------------------------

def formatar_br(escalado: int, casas: int, params: dict | None = None) -> str:
    """Espelho passo a passo de costguard/formatar_numero_br (mesmas variáveis e a mesma ordem).

    Os literais críticos (nº de zeros à esquerda, nº de grupos, escalas e divisor) vêm do .xs (`_params_formatar`),
    não de cópia manual; o resto da lógica é conferido por `problemas_formatar`."""
    p = params or _params_formatar(_codigo(FORMATAR))
    negativo = escalado < 0
    absoluto = (0 - escalado) if negativo else escalado
    digitos = str(absoluto)
    minimo = casas + 1
    for _ in range(p["zeros"]):
        if len(digitos) < minimo:
            digitos = "0" + digitos
    corte = len(digitos) - casas
    fracao_txt, fracao_num, escala = "", 0, 1
    if casas == 2:
        escala, fracao_txt = p["escala2"], digitos[corte:]
        fracao_num = int(fracao_txt)
    elif casas == 1:
        escala, fracao_txt = p["escala1"], digitos[corte:]
        fracao_num = int(fracao_txt)
    resto_num = (absoluto - fracao_num) // escala
    resto_txt = str(resto_num)
    agrupado = ""
    for _ in range(p["grupos"]):
        if len(resto_txt) > 3:
            inicio = len(resto_txt) - 3
            cauda_txt = resto_txt[inicio:]
            cauda_num = int(cauda_txt)
            agrupado = "." + cauda_txt + agrupado
            resto_num = (resto_num - cauda_num) // p["divisor"]
            resto_txt = str(resto_num)
    saida = ("-" if negativo else "") + resto_txt + agrupado
    if casas in (1, 2):
        saida += "," + fracao_txt
    return saida


def referencia_br(valor: Decimal, casas: int) -> str:
    """Formatação brasileira por outro caminho (separadores trocados), para comparar."""
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "#").replace(".", ",").replace("#", ".")


@pytest.mark.parametrize("escalado,casas,esperado", [
    (500000, 2, "5.000,00"),
    (0, 2, "0,00"),
    (5, 2, "0,05"),
    (99, 2, "0,99"),
    (100, 2, "1,00"),
    (123456789, 2, "1.234.567,89"),
    (100000000, 2, "1.000.000,00"),
    (-340, 2, "-3,40"),
    (-123456, 2, "-1.234,56"),
    (125, 1, "12,5"),
    (0, 1, "0,0"),
    (5, 1, "0,5"),
    (1000, 1, "100,0"),
    (1123, 1, "112,3"),
    (-25, 1, "-2,5"),
])
def test_formatacao_brasileira_exemplos(escalado, casas, esperado):
    assert formatar_br(escalado, casas) == esperado


def test_formatacao_brasileira_confere_com_referencia_independente():
    import random
    rng = random.Random(20261124)
    for _ in range(3000):
        casas = rng.choice([1, 2])
        escalado = rng.randint(-10**14, 10**14) if rng.random() < 0.3 else rng.randint(-10**7, 10**7)
        assert formatar_br(escalado, casas) == referencia_br(Decimal(escalado) / (10 ** casas), casas), (escalado, casas)


def test_espelho_formatar_le_os_literais_criticos_do_xs_e_eles_sao_os_esperados():
    assert _params_formatar(_codigo(FORMATAR)) == PARAMS_FORMATAR_ESPERADOS
    assert problemas_formatar(_codigo(FORMATAR)) == []


# (id, trecho do .xs, substituto, a mutação muda o resultado do espelho?)
MUTACOES_FORMATAR = [
    ("divisor-1000-vira-100", "/ 1000)|round:0)", "/ 100)|round:0)", True),
    ("divisor-1000-vira-10000", "/ 1000)|round:0)", "/ 10000)|round:0)", True),
    ("zeros-2-viram-1", "foreach ([1, 2]) {", "foreach ([1]) {", False),  # equivalente no resultado (corte = 0); só o literal pega
    ("zeros-2-viram-3", "foreach ([1, 2]) {", "foreach ([1, 2, 3]) {", False),
    ("grupos-5-viram-4", "foreach ([1, 2, 3, 4, 5]) {", "foreach ([1, 2, 3, 4]) {", True),
    ("escala-100-vira-10", "var.update $escala { value = 100 }", "var.update $escala { value = 10 }", True),
    ("escala-10-vira-100", "var.update $escala { value = 10 }", "var.update $escala { value = 100 }", True),
    ("minimo-casas-mais-1-vira-casas", "var $minimo { value = $input.casas + 1 }", "var $minimo { value = $input.casas }", False),
    ("limite-do-grupo-3-vira-4", "if (($resto_txt|strlen) > 3) {", "if (($resto_txt|strlen) > 4) {", False),
    ("cauda-de-3-vira-2", "var $inicio_cauda { value = ($resto_txt|strlen) - 3 }", "var $inicio_cauda { value = ($resto_txt|strlen) - 2 }", False),
]


@pytest.mark.parametrize("trecho,novo,muda", [pytest.param(a, b, c, id=i) for i, a, b, c in MUTACOES_FORMATAR])
def test_mutacao_dos_literais_criticos_de_formatar_numero_br_e_detectada_pelo_xs_real(trecho, novo, muda):
    mutado = _mutar(_codigo(FORMATAR), trecho, novo)
    assert problemas_formatar(mutado), f"mutação {novo!r} NÃO foi detectada"
    if muda:
        # além do literal, o espelho alimentado pelo .xs mutado erra algum valor conhecido
        params = _params_formatar(mutado)
        casos = [(123456789, 2), (100000000, 2), (1234567, 1), (5, 2), (1000, 1), (-123456, 2), (10**17, 2)]
        assert any(formatar_br(e, c, params) != referencia_br(Decimal(e) / (10 ** c), c) for e, c in casos)


def test_funcao_de_formatacao_usa_os_separadores_brasileiros_e_nao_depende_de_locale():
    codigo = _codigo(FORMATAR)
    assert 'var.update $agrupado { value = "." ~ $cauda_txt ~ $agrupado }' in codigo, "ponto nos milhares"
    assert 'var.update $saida { value = $saida ~ "," ~ $fracao_txt }' in codigo, "vírgula nos decimais"
    assert re.search(r"foreach \(\[1, 2, 3, 4, 5\]\)", codigo), "até 5 grupos de milhares"
    assert re.search(r"input \{\s*int escalado\s*int casas\s*\}", codigo)
    assert not re.search(r"locale|number_format|\|floor|\|mod\b| % ", codigo, re.I)
    assert "var $absoluto { value = ($negativo == true) ? (0 - $input.escalado) : $input.escalado }" in codigo
    assert 'var $sinal { value = ($negativo == true) ? "-" : "" }' in codigo


def test_emails_usam_a_funcao_para_dinheiro_com_2_casas_e_percentual_com_1():
    cod = _codigo(NOTIFICAR)
    assert re.search(r"input = \{escalado: \$orc_centavos, casas: 2\}", cod)
    assert re.search(r"input = \{escalado: \$custo_centavos, casas: 2\}", cod)
    assert re.search(r"input = \{escalado: \$pct_decimos, casas: 1\}", cod)
    assert 'var.update $orcamento_txt { value = "US$ " ~ $orc_fmt }' in cod
    assert 'var.update $custo_txt { value = "US$ " ~ $custo_fmt }' in cod
    assert 'var.update $pct_txt { value = $pct_fmt ~ "%" }' in cod
    # nada é formatado com to_text direto (que usaria ponto decimal e sem milhares)
    assert not re.search(r"\|round:[12]\)\|to_text", cod)
    assert "$budget_txt" not in cod


# ---------------------------------------------------------------------------
# Mês por extenso (espelho do mapa de 12 nomes)
# ---------------------------------------------------------------------------

NOMES_MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
               "novembro", "dezembro"]


def _mapa_meses():
    codigo = _codigo(MES)
    return re.findall(r'\$numero == (\d+)\) \{\s*var\.update \$nome \{ value = "([^"]+)" \}', codigo)


def mes_extenso(mes):
    bruto = (mes or "").strip()
    if not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", bruto):
        return ""  # fora do padrão: vazio, nunca o texto cru
    ano, numero = bruto.split("-")
    mapa = {int(n): nome for n, nome in _mapa_meses()}
    return f"{mapa[int(numero)]} de {ano}"


def test_mapa_de_meses_tem_os_12_nomes_em_ptbr_sem_depender_de_locale():
    mapa = _mapa_meses()
    assert [int(n) for n, _ in mapa] == list(range(1, 13))
    assert [nome for _, nome in mapa] == NOMES_MESES
    codigo = _codigo(MES)
    assert not re.search(r"format_timestamp|locale|strftime", codigo, re.I)
    assert 'var.update $resultado { value = $nome ~ " de " ~ $ano }' in codigo


@pytest.mark.parametrize("entrada,esperado", [
    ("2026-11", "novembro de 2026"), ("2026-01", "janeiro de 2026"), ("2027-03", "março de 2027"),
    ("2026-12", "dezembro de 2026"), (" 2026-09 ", "setembro de 2026"),
    ("2026-13", ""), ("2026-00", ""), ("novembro", ""), ("<b>x</b>", ""), ("2026-11x", ""), ("20261-1", ""), ("", ""), (None, ""),
])
def test_espelho_mes_extenso(entrada, esperado):
    assert mes_extenso(entrada) == esperado


def test_mes_extenso_fora_do_padrao_devolve_vazio_e_nunca_o_texto_cru():
    codigo = _codigo(MES)
    assert problemas_mes(codigo) == []
    assert 'var $resultado { value = "" }' in codigo and "var $resultado { value = $bruto }" not in codigo


def test_mutacao_mes_extenso_devolvendo_o_texto_cru_e_detectada():
    mutado = _mutar(_codigo(MES), 'var $resultado { value = "" }', "var $resultado { value = $bruto }")
    assert problemas_mes(mutado)
    assert problemas_mes(_mutar(_codigo(MES), 'var.update $resultado { value = $nome ~ " de " ~ $ano }',
                                'var.update $resultado { value = $bruto }'))


@pytest.mark.parametrize("arquivo,derivados", [(NOTIFICAR, DERIVADOS_ORCAMENTO), (RECURSOS, DERIVADOS_RECURSOS)], ids=["orcamento", "recursos"])
def test_mes_e_data_do_recurso_tambem_passam_por_escapar_html_antes_do_html(arquivo, derivados):
    codigo = _codigo(arquivo)
    assert problemas_derivados(codigo, derivados) == []
    # o texto puro continua com a versão sem escape (sem entidades HTML)
    assert re.search(r'"Mês de referência: " ~ \$mes_extenso\b', codigo)
    if arquivo == RECURSOS:
        assert re.search(r'\$t_linhas \{ value = \$t_linhas ~ [^\n]*\$r_data ~ "\\n" \}', codigo)


def _mutacoes_derivados():
    casos = []
    for rotulo, arquivo, derivados in (("orcamento", NOTIFICAR, DERIVADOS_ORCAMENTO), ("recursos", RECURSOS, DERIVADOS_RECURSOS)):
        for derivado in derivados:
            for tipo in ("sem_escape", "html_cru"):
                casos.append(pytest.param(arquivo, derivados, derivado, tipo, id=f"{rotulo}:{derivado[2]}:{tipo}"))
    return casos


@pytest.mark.parametrize("arquivo,derivados,derivado,tipo", _mutacoes_derivados())
def test_mutacao_do_escape_do_mes_e_da_data_e_detectada(arquivo, derivados, derivado, tipo):
    _, cru, html = derivado
    codigo = _codigo(arquivo)
    mutado = _sem_escape(codigo, cru, html) if tipo == "sem_escape" else _html_cru(codigo, cru, html)
    assert problemas_derivados(mutado, derivados), f"{tipo} em {html} NÃO foi detectada"


def test_mes_do_orcamento_vem_do_resumo_e_o_dos_recursos_do_dia_civil():
    assert 'function.run "costguard/mes_extenso_pt_br" {' in _codigo(NOTIFICAR)
    assert "input = {mes: $mes_ref}" in _codigo(NOTIFICAR) and "var $mes_ref { value = $resumo.mes }" in _codigo(NOTIFICAR)
    rec = _codigo(RECURSOS)
    assert "var $mes_ref { value = $dia_civil|substr:0:7 }" in rec and "input = {mes: $mes_ref}" in rec


# ---------------------------------------------------------------------------
# Orçamento definido x não definido; barra de consumo; selo da faixa
# ---------------------------------------------------------------------------

def test_sem_faixa_nao_calcula_percentual_nem_barra_e_orcamento_zero_diz_nao_definido():
    cod = _codigo(NOTIFICAR)
    assert 'var $orcamento_txt { value = "Orçamento não definido" }' in cod
    assert 'var $pct_txt { value = "Orçamento não definido" }' in cod
    assert "var $pct_largura { value = 0 }" in cod
    # orçamento só é formatado com orçamento > 0
    assert re.search(r"if \(\$item_resumo\.budget > 0\) \{\s*var \$orc_centavos", cod)
    # percentual, formatação do percentual e largura só dentro de `faixa != null`
    calculo = _bloco_re(cod, r"var \$pct_largura \{ value = 0 \}\s*conditional \{\s*if \(\$item_resumo\.faixa != null\) \{")
    assert "$pct_decimos" in calculo and "formatar_numero_br" in calculo and "var.update $pct_largura" in calculo
    fora = cod.replace(calculo, "")
    assert "percentual_usado" not in fora, "o percentual só é lido dentro do ramo com faixa"
    assert "var.update $pct_largura" not in fora
    # a barra só é montada dentro de `faixa != null`; sem faixa, a linha da barra fica vazia
    assert cod.count('var $h_barra_linha { value = "" }') == 1
    barra = _bloco_re(cod, r'var \$h_barra_linha \{ value = "" \}\s*conditional \{\s*if \(\$item_resumo\.faixa != null\) \{')
    assert "var.update $h_barra_linha" in barra
    assert "var.update $h_barra_linha" not in cod.replace(barra, "")
    assert "$h_barra_linha" in cod[cod.index("var $h_conteudo"):]
    # o teste usa a faixa (texto), nunca o percentual (decimal 0 == null no XanoScript)
    assert "percentual_usado != null" not in cod and "percentual_usado == null" not in cod


def largura_barra(percentual):
    """Espelho do cálculo da largura da barra (inteiro limitado a 0..100)."""
    pct_decimos = int(round((percentual or 0) * 10))
    largura = int(round(percentual or 0))
    if largura < 1 and pct_decimos > 0:
        largura = 1
    elif largura < 0:
        largura = 0
    elif largura > 100:
        largura = 100
    return largura


@pytest.mark.parametrize("pct,esperado", [(0, 0), (0.04, 0), (0.3, 1), (12.5, 12), (69.9, 70), (99.6, 100), (100, 100), (250.7, 100), (-5, 0)])
def test_espelho_largura_da_barra_fica_entre_0_e_100(pct, esperado):
    assert largura_barra(pct) == esperado
    assert 0 <= largura_barra(pct) <= 100


def test_barra_e_tabela_com_celulas_de_largura_em_percentual_limitadas():
    cod = _codigo(NOTIFICAR)
    assert re.search(
        r"if \(\$pct_largura < 1 && \$pct_decimos > 0\) \{\s*var\.update \$pct_largura \{ value = 1 \}\s*\}\s*"
        r"elseif \(\$pct_largura < 0\) \{\s*var\.update \$pct_largura \{ value = 0 \}\s*\}\s*"
        r"elseif \(\$pct_largura > 100\) \{\s*var\.update \$pct_largura \{ value = 100 \}", cod)
    assert "var $barra_resto { value = 100 - $pct_largura }" in cod
    assert re.search(r'"<td width=\'" ~ \(\$pct_largura\|to_text\) ~ "%\' bgcolor=\'" ~ \$cor_faixa ~ "\' style=\'width:" ~ \(\$pct_largura\|to_text\) ~ "%;', cod)
    assert re.search(r'"<td width=\'" ~ \(\$barra_resto\|to_text\) ~ "%\' bgcolor=\'#e5e7eb\'', cod)
    assert "if ($pct_largura > 0) {" in cod and "if ($barra_resto > 0) {" in cod, "célula de largura 0% não é emitida"
    assert "<img" not in cod and "url(" not in cod


FAIXAS = [("estourado", "Estourado", "vermelho"), ("critico", "Crítico", "vermelho"), ("atencao", "Atenção", "amarelo"),
          ("normal", "Normal", "verde")]


def matiz(cor: str) -> str:
    r, g, b = (int(cor[i:i + 2], 16) for i in (1, 3, 5))
    if g > r and g > b:
        return "verde"
    if r > g and abs(g - b) <= 30:
        return "vermelho"
    if r >= g > b:
        return "amarelo"
    return "cinza"


@pytest.mark.parametrize("faixa,curta,cor", FAIXAS)
def test_selo_da_faixa_colorido_mapeia_as_faixas_existentes(faixa, curta, cor):
    cod = _codigo(NOTIFICAR)
    m = re.search(
        r'\$item_resumo\.faixa == "' + faixa + r'"\) \{\s*var\.update \$nivel_rotulo \{ value = "[^"]+" \}\s*'
        r'var\.update \$faixa_curta \{ value = "' + curta + r'" \}\s*'
        r'var\.update \$cor_faixa \{ value = "(#[0-9a-f]{6})" \}\s*'
        r'var\.update \$fundo_faixa \{ value = "(#[0-9a-f]{6})" \}', cod)
    assert m, faixa
    assert matiz(m.group(1)) == cor and matiz(m.group(2)) == cor, (faixa, m.groups())


def test_selo_sem_faixa_e_cinza_e_as_quatro_faixas_do_resumo_sao_as_unicas():
    cod = _codigo(NOTIFICAR)
    assert 'var $faixa_curta { value = "Indisponível" }' in cod
    assert 'var $cor_faixa { value = "#6b7280" }' in cod and 'var $fundo_faixa { value = "#f3f4f6" }' in cod
    faixas_xs = re.findall(r'\$item_resumo\.faixa == "(\w+)"', cod)
    assert faixas_xs == [f for f, _, _ in FAIXAS]
    # as faixas existem em costguard/resumo_consumo com os mesmos nomes
    resumo = _codigo(FUNCOES / "resumo_consumo.xs")
    for faixa, _, _ in FAIXAS:
        assert f'value = "{faixa}"' in resumo
    assert 'var.update $faixa { value = "estourado" }' in resumo


def test_selo_e_barra_usam_so_cores_fixas_do_codigo():
    cod = _codigo(NOTIFICAR)
    selo = re.search(r"var \$h_selo \{\s*value = (.*?)\n\s*\}", cod, re.S).group(1)
    assert sorted(set(re.findall(r"\$(\w+)", selo))) == ["cor_faixa", "faixa_curta", "fundo_faixa"]
    cores = re.findall(r'value = "(#[0-9a-f]{6})"', cod)
    assert cores and all(re.fullmatch(r"#[0-9a-f]{6}", c) for c in cores)


def test_quantidade_de_recursos_sem_equipe_continua_sendo_a_mesma_regra_do_orcamento():
    cod = _codigo(NOTIFICAR)
    assert 'rotulo: "Recursos sem equipe", valor_html: $sem_tag_txt' in cod
    assert 'var $sem_tag_txt { value = ($sem_tag_ok == true) ? ($qtd_sem_tag|to_text) : "indisponível" }' in cod


# ---------------------------------------------------------------------------
# Endpoint novo: rota, autorização, ordem, erros
# ---------------------------------------------------------------------------

def test_endpoint_novo_e_post_do_grupo_app_no_caminho_pedido_com_auth_usuarios():
    codigo = _codigo(RECURSOS)
    assert 'query "projetos/{id}/notificar-recursos-sem-equipe" verb=POST' in codigo
    # o mesmo prefixo de rota do endpoint de orçamento (grupo app, `projetos/{id}/...`)
    assert 'query "projetos/{id}/notificar-devops" verb=POST' in _codigo(NOTIFICAR)
    assert 'api_group = "app"' in codigo and 'auth = "usuarios"' in codigo
    assert RECURSOS.name == "notificar_recursos_sem_equipe_projeto_POST.xs"


def test_endpoint_novo_nao_tem_input_de_destinatario_nem_outros_campos():
    codigo = _codigo(RECURSOS)
    entrada = _bloco(codigo, "input {")
    assert re.findall(r"^\s*(?:int|text|email|bool|decimal|object|json)\s+(\w+)", entrada, re.M) == ["id"]
    assert set(re.findall(r"\$input\.(\w+)", codigo)) == {"id"}
    assert re.search(r"to\s*:\s*\[\$destino\]", codigo)
    assert re.search(r"var \$destino \{ value = \$email_atual\.email \}", codigo)
    assert codigo.count('function.run "costguard/normalizar_email_devops"') == 2


def _precondicao_ou_none(codigo: str, condicao: str, tipo: str, mensagem: str):
    padrao = (r"precondition \(" + re.escape(condicao) + r'\) \{\s*error_type = "' + re.escape(tipo) + r'"\s*error = ' + re.escape(mensagem) + r"\s*\}")
    return re.search(padrao, codigo)


def _bloco_re_ou_vazio(texto: str, padrao: str) -> str:
    try:
        return _bloco_re(texto, padrao)
    except AssertionError:
        return ""


def problemas_autorizacao_recursos(codigo: str) -> list[str]:
    """QUALQUER perfil autenticado e ATIVO pode notificar (como /notificar-devops); o papel só muda o texto da resposta."""
    faltas = []
    sessao = _precondicao_ou_none(codigo, '$usuario_logado != null && $usuario_logado.status == "ativo"', "unauthorized", '"Token inválido ou expirado"')
    existe = _precondicao_ou_none(codigo, "$projeto_alvo != null", "notfound", '"Projeto não encontrado"')
    if not (sessao and existe and sessao.start() < existe.start()):
        faltas.append("401_depois_404")
    if re.search(r"accessdenied|Acesso negado|\"negado\"|role != \"admin\"|role == \"admin\"\) \{\s*error", codigo):
        faltas.append("sem_403_por_papel")
    if codigo.count(".role") != 1 or not re.search(r'var\.update \$eh_admin \{ value = \(\$solicitante_atual != null\) \? \(\$solicitante_atual\.role == "admin"\) : false \}', codigo):
        faltas.append("papel_so_decide_o_texto_da_resposta")
    # a releitura com a trava só derruba sessão inativa (401), nunca papel
    if not re.search(r'if \(\$solicitante_atual == null \|\| \$solicitante_atual\.status != "ativo"\) \{\s*var\.update \$estado \{ value = "sem_sessao" \}\s*\}\s*elseif \(\$proj_atual == null\)', codigo):
        faltas.append("releitura_so_status_ativo")
    # `destinatario_mascarado` e o endereço mascarado SÓ no admin
    if codigo.count("destinatario_mascarado") != 1:
        faltas.append("destinatario_mascarado_so_na_resposta_do_admin")
    admin = _bloco_re_ou_vazio(codigo, r"if \(\$eh_admin == true\) \{\s*var\.update \$resposta \{")
    if "destinatario_mascarado: $mascarado" not in admin:
        faltas.append("destinatario_mascarado_so_na_resposta_do_admin")
    base = _bloco(codigo, "var $resposta {\n      value = {")
    if re.findall(r"^\s*(\w+)\s*:", base, re.M) != ["status", "mensagem", "enviado", "quantidade"] or "$mascarado" in base:
        faltas.append("resposta_base_sem_endereco")
    final = codigo[codigo.index("var $mensagem_final"):]
    if 'var $mensagem_final { value = "Aviso de recursos sem equipe enviado ao DevOps do projeto." }' not in codigo:
        faltas.append("mensagem_fixa_para_nao_admin")
    if not re.search(r'if \(\$eh_admin == true\) \{\s*var\.update \$mensagem_final \{ value = "Aviso de recursos sem equipe enviado para " ~ \$mascarado ~ "\." \}', codigo):
        faltas.append("mascarado_so_na_mensagem_do_admin")
    if "$destino" in final or len(re.findall(r"\$mascarado", final)) != 2:
        faltas.append("endereco_so_mascarado_e_so_no_admin")
    return faltas


def test_endpoint_novo_aceita_qualquer_perfil_ativo_sem_403_e_so_o_admin_ve_o_endereco_mascarado():
    codigo = _codigo(RECURSOS)
    assert problemas_autorizacao_recursos(codigo) == []
    sessao = _precondicao(codigo, '$usuario_logado != null && $usuario_logado.status == "ativo"', "unauthorized", '"Token inválido ou expirado"')
    existe = _precondicao(codigo, "$projeto_alvo != null", "notfound", '"Projeto não encontrado"')
    assert sessao.start() < existe.start()
    # nenhuma escrita, trava, ficha nem envio antes da checagem de sessão ativa
    for efeito in ("db.add travas", "api.request", "db.edit projetos", "function.run", "db.del travas", "db.query recursos"):
        assert sessao.start() < codigo.index(efeito), efeito
    # a mesma autorização do endpoint de orçamento (qualquer perfil ativo)
    assert _precondicao(_codigo(NOTIFICAR), '$usuario_logado != null && $usuario_logado.status == "ativo"', "unauthorized", '"Token inválido ou expirado"').group(0) == sessao.group(0)
    assert "accessdenied" not in _codigo(NOTIFICAR)


MUTACOES_AUTORIZACAO_RECURSOS = [
    ("volta_o_admin_only", '    precondition ($projeto_alvo != null) {',
     '    precondition ($usuario_logado.status == "ativo" && $usuario_logado.role == "admin") {\n      error_type = "accessdenied"\n      error = "Acesso negado"\n    }\n\n    precondition ($projeto_alvo != null) {', "sem_403_por_papel"),
    ("volta_o_negado_na_releitura", 'elseif ($proj_atual == null) {', 'elseif ($solicitante_atual.role != "admin") {\n            var.update $estado { value = "negado" }\n          }\n          elseif ($proj_atual == null) {', "sem_403_por_papel"),
    ("sessao_inativa_sem_401", 'precondition ($usuario_logado != null && $usuario_logado.status == "ativo") {\n      error_type = "unauthorized"',
     'precondition ($usuario_logado != null && $usuario_logado.status == "ativo") {\n      error_type = "standard"', "401_depois_404"),
    ("sem_checagem_de_sessao", 'precondition ($usuario_logado != null && $usuario_logado.status == "ativo") {', 'precondition ($usuario_logado != null) {', "401_depois_404"),
    ("papel_restringe_o_envio", 'var.update $eh_admin { value = ($solicitante_atual != null) ? ($solicitante_atual.role == "admin") : false }',
     'var.update $eh_admin { value = true }', "papel_so_decide_o_texto_da_resposta"),
    ("mascarado_para_todos_na_resposta", "quantidade: $quantidade\n      }\n    }\n\n    conditional {", "quantidade: $quantidade\n        destinatario_mascarado: $mascarado\n      }\n    }\n\n    conditional {",
     "resposta_base_sem_endereco"),
    ("mascarado_na_mensagem_de_todos", 'var $mensagem_final { value = "Aviso de recursos sem equipe enviado ao DevOps do projeto." }',
     'var $mensagem_final { value = "Aviso de recursos sem equipe enviado para " ~ $mascarado ~ "." }', "mensagem_fixa_para_nao_admin"),
    ("mensagem_fixa_com_dominio", 'var $mensagem_final { value = "Aviso de recursos sem equipe enviado ao DevOps do projeto." }',
     'var $mensagem_final { value = "Aviso de recursos sem equipe enviado ao DevOps de " ~ ($destino|split:"@"|last) ~ "." }', "mensagem_fixa_para_nao_admin"),
    ("admin_sem_mascarado", 'var.update $mensagem_final { value = "Aviso de recursos sem equipe enviado para " ~ $mascarado ~ "." }',
     'var.update $mensagem_final { value = "Aviso de recursos sem equipe enviado para " ~ $destino ~ "." }', "mascarado_so_na_mensagem_do_admin"),
    ("endereco_inteiro_na_mensagem", 'var.update $mensagem_final { value = "Aviso de recursos sem equipe enviado para " ~ $mascarado ~ "." }',
     'var.update $mensagem_final { value = "Aviso de recursos sem equipe enviado para " ~ $mascarado ~ " (" ~ $destino ~ ")." }', "endereco_so_mascarado_e_so_no_admin"),
    ("resposta_do_admin_sem_mascarado", "destinatario_mascarado: $mascarado", "destinatario_mascarado: null", "destinatario_mascarado_so_na_resposta_do_admin"),
    ("resposta_de_todos_com_mascarado_por_condicao_errada", "if ($eh_admin == true) {\n        var.update $resposta {", "if ($eh_admin == false) {\n        var.update $resposta {",
     "destinatario_mascarado_so_na_resposta_do_admin"),
]


@pytest.mark.parametrize("nome,antigo,novo,regra", MUTACOES_AUTORIZACAO_RECURSOS, ids=[m[0] for m in MUTACOES_AUTORIZACAO_RECURSOS])
def test_mutacao_da_autorizacao_do_aviso_de_recursos_e_detectada(nome, antigo, novo, regra):
    codigo = _codigo(RECURSOS)
    assert antigo in codigo, nome
    assert regra in problemas_autorizacao_recursos(codigo.replace(antigo, novo, 1)), nome


def test_endpoint_novo_mesmas_mensagens_dos_erros_do_endpoint_de_orcamento():
    novo, antigo = _codigo(RECURSOS), _codigo(NOTIFICAR)
    mensagens_novo = set(re.findall(r'error = "([^"]+)"', novo))
    mensagens_antigo = set(re.findall(r'error = "([^"]+)"', antigo))
    # tudo que o novo diz já existe no antigo (copiado), exceto o 400 de zero recursos: NÃO há mais 403 ("Acesso negado")
    assert mensagens_novo - mensagens_antigo == {"Nenhum recurso sem equipe neste projeto no mês."}
    assert "Acesso negado" not in mensagens_novo
    # e o inverso: o novo reaproveita todas as do antigo (a de "montar o alerta" também vale para a falha do conteúdo)
    assert mensagens_antigo - mensagens_novo == set()
    msg_limite = r'"Já foi enviado um alerta deste projeto há pouco\. Aguarde " ~ \(\$segundos_restantes\|to_text\) ~ " segundos para enviar outro \(limite: 1 envio a cada 5 minutos\)\."'
    assert re.search(r"var \$msg_limite \{\s*value = " + msg_limite, novo)
    assert re.search(r"var \$msg_limite \{\s*value = " + msg_limite, antigo)
    _precondicao(novo, '$estado != "limite"', "toomanyrequests", "$msg_limite")
    _precondicao(novo, '$estado != "teto_diario"', "toomanyrequests", '"Limite diário de notificações atingido; tente amanhã."')
    _precondicao(novo, "$trava_id != null", "toomanyrequests", '"Já existe um envio em andamento para este projeto. Tente novamente em instantes."')
    _precondicao(novo, '$email_chave != "" && $email_from != ""', "standard", '"O envio de e-mail não está configurado no servidor."')
    _precondicao(novo, '$projeto_alvo.status == "ativo"', "inputerror", '"Este projeto está inativo; não é possível notificar o DevOps."')
    _precondicao(novo, "$email_pre.vazio == false && $email_pre.valido == true", "inputerror", '"Este projeto não tem e-mail do DevOps cadastrado."')
    _precondicao(novo, '$estado != "falha_envio"', "standard", '"Não foi possível enviar o e-mail agora. Tente novamente em instantes."')
    _precondicao(novo, '$estado != "falha_conteudo"', "standard", '"Não foi possível montar o alerta deste projeto. Tente novamente em instantes."')
    _precondicao(novo, '$estado == "enviado"', "standard", '"Não foi possível concluir o envio do alerta. Tente novamente em instantes."')
    _precondicao(novo, "$falha == false", "standard", '"Não foi possível concluir o envio do alerta. Tente novamente em instantes."')
    # sem texto de provedor/segredo nas mensagens
    for m in mensagens_novo:
        assert not re.search(r"resend|api[_ ]?key|bearer|re_[A-Za-z0-9]", m, re.I), m


def test_ordem_das_checagens_do_endpoint_novo():
    """401, 404, 400 inativo, 400 sem e-mail, 500 sem config, 429 trava, 429 limite, 400 zero, 429 teto, conteúdo, envio (sem 403)."""
    codigo = _codigo(RECURSOS)
    fichas = [m.start() for m in re.finditer(r"db\.add travas", codigo)]
    assert len(fichas) == 2, "1 trava do projeto + 1 ficha do teto"
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
        codigo.index("db.query recursos"),
        codigo.index('value = "sem_recursos"'),
        fichas[1],
        codigo.index('value = "teto_diario"'),
        codigo.index('value = "falha_conteudo"'),
        codigo.index("api.request"),
    ]
    assert etapas == sorted(etapas) and len(set(etapas)) == len(etapas)
    assert fichas[0] < codigo.index('value = "sem_sessao"'), "a trava do projeto vem antes das releituras"
    # as respostas de estado seguem a mesma ordem, depois do finally
    padrao = [
        ("$falha == false", "standard"), ('$estado != "sem_sessao"', "unauthorized"),
        ('$estado != "sem_projeto"', "notfound"), ('$estado != "projeto_inativo"', "inputerror"),
        ('$estado != "sem_destino"', "inputerror"), ('$estado != "limite"', "toomanyrequests"),
        ('$estado != "sem_recursos"', "inputerror"), ('$estado != "teto_diario"', "toomanyrequests"),
        ('$estado != "falha_conteudo"', "standard"), ('$estado != "falha_envio"', "standard"), ('$estado == "enviado"', "standard"),
    ]
    posicoes = [_precondicao(codigo, c, t).start() for c, t in padrao]
    assert posicoes == sorted(posicoes) and posicoes[0] > codigo.index("finally {")
    atribuidos = set(re.findall(r'var\.update \$estado \{ value = "(\w+)" \}', codigo))
    assert atribuidos == {"sem_sessao", "sem_projeto", "projeto_inativo", "sem_destino", "limite", "sem_recursos",
                          "teto_diario", "falha_conteudo", "falha_envio", "enviado"}
    # o teto só é tocado se nenhuma recusa anterior marcou o estado
    assert re.search(r'if \(\$estado == ""\) \{\s*foreach \(\[1, 2, 3,', codigo)


def test_zero_recursos_responde_400_sem_enviar_sem_ficha_e_sem_consumir_o_limite():
    codigo = _codigo(RECURSOS)
    _precondicao(codigo, '$estado != "sem_recursos"', "inputerror", '"Nenhum recurso sem equipe neste projeto no mês."')
    assert codigo.count('value = "sem_recursos"') == 1
    assert re.search(r'if \(\$quantidade == 0\) \{\s*var\.update \$estado \{ value = "sem_recursos" \}\s*\}', codigo)
    ficha = [m.start() for m in re.finditer(r"db\.add travas", codigo)][1]
    assert codigo.index("db.query recursos") < codigo.index('value = "sem_recursos"') < ficha < codigo.index("api.request")
    # a consulta e a recusa acontecem depois do limite de 5 min e só sem recusa pendente
    assert codigo.index('value = "limite"') < codigo.index("db.query recursos")
    assert re.search(r'if \(\$estado == ""\) \{\s*db\.query recursos', codigo)
    # o que consome limite e ficha só existe depois do aceite / só depois da checagem de zero
    assert codigo.count("db.edit projetos") == 1 and codigo.index("db.edit projetos") > codigo.index("api.request")
    assert codigo.index('var.update $ficha_id') > codigo.index('value = "sem_recursos"')


# ---------------------------------------------------------------------------
# Limite de 5 min PRÓPRIO, teto diário COMPARTILHADO, trava, idempotência, registro
# ---------------------------------------------------------------------------

def test_limite_de_5_minutos_proprio_em_colunas_novas_e_independente_do_de_orcamento():
    novo, antigo = _codigo(RECURSOS), _codigo(NOTIFICAR)
    assert "devops_ultimo_envio" not in novo, "o limite do orçamento não pode ser lido nem gravado pelo aviso de recursos"
    assert "devops_recursos" not in antigo, "e vice-versa"
    assert "var $limite_ms { value = 300000 }" in novo
    assert re.search(r"var \$ultimo_envio \{ value = \(\$proj_atual != null\) \? \(\$proj_atual\.devops_recursos_ultimo_envio_em \?\? 0\) : 0 \}", novo)
    assert "var $decorrido_ms { value = $agora_ms - $ultimo_envio }" in novo
    bloco = _bloco_re(novo, r'if \(\$estado == "" && \$ultimo_envio > 0 && \$decorrido_ms < \$limite_ms\) \{')
    assert 'var.update $estado { value = "limite" }' in bloco
    assert "var $resto_ms { value = ($decorrido_ms < 0) ? $limite_ms : ($limite_ms - $decorrido_ms) }" in bloco
    assert re.search(r"if \(\$segundos_restantes < 1\) \{\s*var\.update \$segundos_restantes \{ value = 1 \}\s*\}\s*"
                     r"elseif \(\$segundos_restantes > 300\) \{\s*var\.update \$segundos_restantes \{ value = 300 \}", bloco)
    # colunas anuláveis e aditivas na tabela
    tabela = _ler(TABELA)
    assert re.search(r"^\s*int devops_recursos_ultimo_envio_em\?\s*$", tabela, re.M)
    assert re.search(r"^\s*int devops_recursos_ultimo_envio_por\?\s*$", tabela, re.M)
    assert "devops_recursos" not in re.search(r"index = \[.*?\n  \]", tabela, re.S).group(0)
    assert re.search(r"^\s*int devops_ultimo_envio_em\?\s*$", tabela, re.M), "as colunas antigas continuam"


def test_registro_do_limite_so_apos_2xx_do_resend():
    codigo = _codigo(RECURSOS)
    assert codigo.count("devops_recursos_ultimo_envio_em:") == 1 and codigo.count("devops_recursos_ultimo_envio_por:") == 1
    aceite = _bloco_re(codigo, r"if \(\$envio_status >= 200 && \$envio_status < 300\) \{")
    assert "db.edit projetos" in aceite and "devops_recursos_ultimo_envio_em: $instante_envio" in aceite
    assert "devops_recursos_ultimo_envio_por: $solicitante_atual.id" in aceite
    assert 'var.update $estado { value = "enviado" }' in aceite and "var.update $ficha_aceita { value = true }" in aceite
    assert re.search(r'\}\s*else \{\s*var\.update \$estado \{ value = "falha_envio" \}\s*\}', codigo)
    assert codigo.count("db.edit projetos") == 1
    assert codigo.index("api.request") < codigo.index("$envio_status >= 200 && $envio_status < 300") < codigo.index("devops_recursos_ultimo_envio_em:")
    # só estas duas tabelas são escritas; nada de db.edit em recursos/custos
    assert sorted(set(re.findall(r"db\.(?:add|edit|del) (\w+)", codigo))) == ["projetos", "travas"]
    assert set(re.findall(r"db\.add (\w+)", codigo)) == {"travas"}
    assert set(re.findall(r"db\.(?:query|get) (\w+)", codigo)) == {"usuarios", "projetos", "recursos", "travas"}
    # falha ao gravar o instante vira aviso na mensagem de sucesso (mesmo texto do endpoint de orçamento)
    assert re.search(r"catch \{\s*var\.update \$registro_falhou \{ value = true \}", codigo)
    aviso = " Aviso: não foi possível registrar o limite de 5 minutos; um novo envio pode ser aceito agora."
    assert aviso in codigo and aviso in _codigo(NOTIFICAR)


def _parte_do_teto(arquivo):
    codigo = _codigo(arquivo)
    ini = codigo.index("foreach ([1, 2, 3,")
    return codigo[ini:codigo.index('value = "teto_diario"')]


def test_teto_diario_e_o_mesmo_30_fichas_devops_dia_da_tabela_travas():
    novo, antigo = _codigo(RECURSOS), _codigo(NOTIFICAR)
    lista = re.search(r"foreach \(\[((?:\d+, )*\d+)\]\) \{\s*each as \$n_ficha", novo)
    assert [int(n) for n in lista.group(1).split(", ")] == list(range(1, 31))
    ficha = r'db\.add travas \{\s*data = \{nome: "devops_dia_" ~ \$dia_civil ~ "_" ~ \(\$n_ficha\|to_text\), adquirida_em: \$agora_ms\}\s*\} as \$nova_ficha'
    assert re.search(ficha, novo) and re.search(ficha, antigo)
    assert _parte_do_teto(RECURSOS) == _parte_do_teto(NOTIFICAR), "o mecanismo das fichas é IDÊNTICO nos dois endpoints"
    for codigo in (novo, antigo):
        assert "var $agora_brt_ms { value = $agora_ms - 10800000 }" in codigo
        assert 'var $dia_civil { value = $agora_brt_ms|format_timestamp:"Y-m-d":"UTC" }' in codigo
    # nenhuma tabela nova nem prefixo de ficha próprio
    assert "devops_dia_rec" not in novo and "devops_rec_dia" not in novo
    assert not [p for p in (XANO / "table").glob("*.xs") if re.search(r"devops|notific|envio|ficha", p.name)]


def test_ficha_so_fica_consumida_com_aceite_e_e_devolvida_no_finally():
    codigo = _codigo(RECURSOS)
    assert codigo.count("var.update $ficha_aceita { value = true }") == 1
    assert "var $ficha_aceita { value = false }" in codigo
    fin = _bloco(codigo, "finally {")
    devolucao = _bloco_re(fin, r"if \(\$ficha_id != null && \$ficha_aceita == false\) \{")
    assert re.search(r'db\.del travas \{\s*field_name = "id"\s*field_value = \$ficha_id\s*\}', devolucao)
    assert fin.index("field_value = $trava_id") < fin.index("$ficha_id != null")
    assert codigo.count("field_value = $ficha_id") == 1
    assert re.search(r"catch \{\s*var\.update \$ficha_liberacao_falhou \{ value = true \}", devolucao)
    ficha = [m.start() for m in re.finditer(r"db\.add travas", codigo)][1]
    assert codigo.index('value = "limite"') < codigo.index('value = "sem_recursos"') < ficha < codigo.index("var $assunto") < codigo.index("api.request")
    assert "ficha_aceita" not in codigo[codigo.index('value = "falha_envio"'):codigo.index("finally {")]


def test_trava_do_projeto_e_propria_deste_aviso_e_liberada_no_finally():
    novo, antigo = _codigo(RECURSOS), _codigo(NOTIFICAR)
    assert 'var $trava_nome { value = "devops_rec_projeto_" ~ ($input.id|to_text) }' in novo
    assert 'var $trava_nome { value = "devops_projeto_" ~ ($input.id|to_text) }' in antigo
    assert re.search(r"db\.add travas \{\s*data = \{nome: \$trava_nome, adquirida_em: \$agora_trava\}", novo)
    assert "$idade_trava > 120000 && $tentativa == 1" in novo
    assert re.search(r'db\.del travas \{\s*field_name = "id"\s*field_value = \$trava_id', _bloco(novo, "finally {"))
    assert re.search(r"catch \{\s*var\.update \$falha \{ value = true \}\s*\}\s*finally \{", novo)


def test_idempotency_key_propria_com_id_do_projeto_e_janela_de_5_minutos():
    novo, antigo = _codigo(RECURSOS), _codigo(NOTIFICAR)
    cab = _bloco(_bloco(novo, "api.request {"), "headers = [")
    assert '"Idempotency-Key: " ~ $idem_chave' in cab
    assert re.findall(r"\$\w+", cab) == ["$email_chave", "$idem_chave"]
    chave = re.search(r"var \$idem_chave \{\s*value = (.*?)\n\s*\}", novo, re.S).group(1)
    assert chave == '"devops-rec-" ~ ($input.id|to_text) ~ "-" ~ (($janela_idem|to_int)|to_text)'
    chave_antiga = re.search(r"var \$idem_chave \{\s*value = (.*?)\n\s*\}", antigo, re.S).group(1)
    assert chave != chave_antiga and chave_antiga.startswith('"devops-" ~')
    assert re.search(r"var \$janela_idem \{ value = \(\$agora_ms / 300000\)\|floor \}", novo)
    assert sorted(re.findall(r"\$[\w.]+", chave)) == ["$input.id", "$janela_idem"], "sem nome nem e-mail"


def test_chamada_ao_resend_igual_a_do_orcamento_html_e_text_uma_unica_vez():
    novo, antigo = _codigo(RECURSOS), _codigo(NOTIFICAR)
    assert novo.count("api.request") == 1 and antigo.count("api.request") == 1
    req = _bloco(novo, "api.request {")
    assert 'url = "https://api.resend.com/emails"' in req and 'method = "POST"' in req and "params = $corpo_email" in req
    assert int(re.search(r"timeout = (\d+)", req).group(1)) == 10
    for codigo in (novo, antigo):
        corpo = _bloco(codigo, "var $corpo_email {\n" + re.search(r"( *)value = \{", codigo[codigo.index("var $corpo_email"):]).group(0).split("value")[0] + "value = {")
        assert re.findall(r"^\s*(\w+)\s*:", corpo, re.M) == ["from", "to", "subject", "html", "text"]
        assert re.search(r"from\s*:\s*\$email_from\b", codigo) and re.search(r"html\s*:\s*\$html\b", codigo) and re.search(r"text\s*:\s*\$texto\b", codigo)
    assert "$resp_email.response.body" not in novo and "$resp_email.response.result" not in novo
    assert sorted(re.findall(r"\$resp_email\S*", novo)) == ["$resp_email", "$resp_email.response.status"]
    assert not re.search(r"\b(while|for)\b|util\.sleep", novo[novo.index("api.request"):])
    assert len(re.findall(r"\bforeach\b", novo)) == 3, "trava, linhas dos recursos e fichas do teto"


def test_mascara_calculada_antes_do_envio_igual_a_do_orcamento():
    novo, antigo = _codigo(RECURSOS), _codigo(NOTIFICAR)
    mascara = r'var\.update \$mascarado \{ value = \(\(\$destino\|split:"@"\|first\)\|substr:0:1\) ~ "\*\*\*@" ~ \(\$destino\|split:"@"\|last\) \}'
    assert re.search(mascara, novo) and re.search(mascara, antigo)
    assert novo.count("var.update $mascarado") == 1
    assert novo.index("var $janela_idem") < novo.index("var.update $mascarado") < novo.index("var $envio_status { value = 0 }") < novo.index("api.request")
    aceite = _bloco_re(novo, r"if \(\$envio_status >= 200 && \$envio_status < 300\) \{")
    assert "$mascarado" not in aceite and "$destino" not in aceite and "split" not in aceite


# ---------------------------------------------------------------------------
# Lista de recursos: critério, ordenação, máximo de 50 + "e mais N", quantidade total
# ---------------------------------------------------------------------------

def test_consulta_de_recursos_do_projeto_ativos_sem_equipe_e_sem_tag_com_ordenacao_deterministica():
    codigo = _codigo(RECURSOS)
    consulta = _bloco(codigo, "db.query recursos {")
    assert re.search(
        r"where = \$db\.recursos\.projeto_id == \$input\.id && \$db\.recursos\.ativo == true && "
        r"\(\$db\.recursos\.equipe_id == null \|\| \$db\.recursos\.equipe_id == 0\)", consulta)
    assert 'sort = {id: "asc"}' in consulta and 'return = {type: "list"}' in consulta
    assert codigo.count("db.query recursos") == 1
    # a MESMA condição da contagem do e-mail de orçamento
    onde = lambda c: re.search(r"where = (\$db\.recursos[^\n]+)", c).group(1)
    assert onde(codigo) == onde(_codigo(NOTIFICAR))
    assert re.search(r'if \(\(\(\$rs\.codigo_equipe_tag \?\? ""\)\|trim\) == ""\) \{', codigo)
    # sem custo por recurso: nenhuma tabela/coluna de custo é lida
    assert not re.search(r"custo", codigo, re.I)


def test_nome_do_recurso_e_o_ultimo_trecho_do_arn_e_o_arn_inteiro_nao_vai_ao_email():
    codigo = _codigo(RECURSOS)
    assert 'var $arn_parte { value = ((($arn_bruto|split:"/")|last) ?? "") }' in codigo
    assert 'var $arn_nome { value = ((($arn_parte|split:":")|last) ?? "") }' in codigo
    assert codigo.count("$arn_bruto") == 2 and codigo.count("$rs.arn") == 1
    assert "$arn_bruto" not in "".join(l for l in codigo.splitlines() if re.search(r"\$h_|valor_html|\$t_linhas|\$texto", l))
    assert '"(sem identificador)"' in codigo
    assert 'var.update $r_data { value = $criado_ms|format_timestamp:"d/m/Y":"America/Sao_Paulo" }' in codigo
    assert "var $criado_ms { value = (($rs.criado_em ?? 0)|to_int) }" in codigo


def nome_do_arn(arn):
    parte = (arn or "").split("/")[-1]
    return parte.split(":")[-1]


@pytest.mark.parametrize("arn,esperado", [
    ("arn:aws:s3:::bucket-fict-0001", "bucket-fict-0001"),
    ("arn:aws:ec2:us-west-2:000000000000:instance/i-0abc123", "i-0abc123"),
    ("arn:aws:iam::000000000000:role/caminho/papel-x", "papel-x"),
    ("arn:aws:lambda:us-east-1:000000000000:function:minha-funcao", "minha-funcao"),
    ("", ""), (None, ""),
])
def test_espelho_nome_derivado_do_arn_nao_expoe_a_conta(arn, esperado):
    assert nome_do_arn(arn) == esperado
    assert "000000000000" not in nome_do_arn(arn)


def montar_lista(recursos, projeto_id, maximo):
    """Espelho da consulta + laço: ordenação por id, filtros, total e as primeiras `maximo` linhas."""
    candidatos = sorted(
        (r for r in recursos if r["projeto_id"] == projeto_id and r["ativo"] is True and r["equipe_id"] in (None, 0)),
        key=lambda r: r["id"])
    quantidade, linhas = 0, []
    for r in candidatos:
        if (r.get("codigo_equipe_tag") or "").strip() == "":
            quantidade += 1
            if quantidade <= maximo:
                linhas.append(r["id"])
    return quantidade, linhas, quantidade - maximo


def _maximo_do_xs():
    codigo = _codigo(RECURSOS)
    maximo = int(re.search(r"var \$maximo_linhas \{ value = (\d+) \}", codigo).group(1))
    assert "if ($quantidade <= $maximo_linhas) {" in codigo
    return maximo


def _recursos_fict(n, projeto=5, **extra):
    return [{"id": i, "projeto_id": projeto, "ativo": True, "equipe_id": None, "codigo_equipe_tag": None, **extra}
            for i in range(n, 0, -1)]  # ids em ordem decrescente: a ordenação precisa reordenar


def test_espelho_maximo_de_50_linhas_e_e_mais_n_com_quantidade_total():
    maximo = _maximo_do_xs()
    assert maximo == 50
    quantidade, linhas, mais = montar_lista(_recursos_fict(50), 5, maximo)
    assert (quantidade, len(linhas), mais) == (50, 50, 0)
    quantidade, linhas, mais = montar_lista(_recursos_fict(51), 5, maximo)
    assert (quantidade, len(linhas), mais) == (51, 50, 1)
    quantidade, linhas, mais = montar_lista(_recursos_fict(173), 5, maximo)
    assert quantidade == 173 and len(linhas) == 50 and mais == 123
    assert linhas == list(range(1, 51)), "ordem determinística por id crescente"
    assert montar_lista([], 5, maximo) == (0, [], -50)


def test_espelho_so_conta_ativos_do_projeto_sem_equipe_e_sem_tag():
    recursos = [
        {"id": 1, "projeto_id": 5, "ativo": True, "equipe_id": None, "codigo_equipe_tag": None},      # conta
        {"id": 2, "projeto_id": 5, "ativo": True, "equipe_id": 0, "codigo_equipe_tag": "  "},         # conta
        {"id": 3, "projeto_id": 5, "ativo": True, "equipe_id": 0, "codigo_equipe_tag": "EQP1"},        # tag sem equipe: não conta
        {"id": 4, "projeto_id": 5, "ativo": True, "equipe_id": 7, "codigo_equipe_tag": ""},            # com equipe: não conta
        {"id": 5, "projeto_id": 5, "ativo": False, "equipe_id": None, "codigo_equipe_tag": ""},       # inativo
        {"id": 6, "projeto_id": 9, "ativo": True, "equipe_id": None, "codigo_equipe_tag": ""},        # outro projeto
        {"id": 7, "projeto_id": None, "ativo": True, "equipe_id": None, "codigo_equipe_tag": ""},     # não classificado
    ]
    quantidade, linhas, _ = montar_lista(recursos, 5, 50)
    assert (quantidade, linhas) == (2, [1, 2])


def test_xs_conta_o_total_fora_do_limite_e_so_monta_linhas_dentro_dele():
    codigo = _codigo(RECURSOS)
    laco = _bloco_re(codigo, r"foreach \(\$recursos_sem_equipe\) \{")
    incremento = "var.update $quantidade { value = $quantidade + 1 }"
    limite = "if ($quantidade <= $maximo_linhas) {"
    assert laco.count(incremento) == 1 and laco.count(limite) == 1
    assert laco.index(incremento) < laco.index(limite), "o total é contado ANTES e FORA do limite de 50"
    dentro = _bloco_re(laco, r"if \(\$quantidade <= \$maximo_linhas\) \{")
    for parte in ("function.run", "var.update $h_linhas", "var.update $t_linhas"):
        assert parte in dentro and parte not in laco.replace(dentro, ""), parte
    # "e mais N": só quando passa de 50, em HTML e em texto, e a resposta traz o TOTAL
    assert "var $mais { value = $quantidade - $maximo_linhas }" in codigo
    assert codigo.count("if ($mais > 0) {") == 2
    assert 'var.update $texto { value = $texto ~ "e mais " ~ ($mais|to_text) ~ " recursos\\n" }' in codigo
    assert "e mais \" ~ ($mais|to_text) ~ \" recursos</p>" in codigo
    assert re.search(r"quantidade\s*: \$quantidade\b", codigo)
    assert "$maximo_linhas" in codigo and "var $maximo_linhas { value = 50 }" in codigo


def test_resposta_200_tem_os_campos_pedidos_mais_status_e_mensagem_do_endpoint_atual():
    codigo = _codigo(RECURSOS)
    resposta = _bloco(codigo, "var $resposta {\n      value = {")
    # todos os perfis: status, mensagem, enviado e quantidade (SEM o endereço mascarado)
    assert re.findall(r"^\s*(\w+)\s*:", resposta, re.M) == ["status", "mensagem", "enviado", "quantidade"]
    assert re.search(r'enviado\s*: true', resposta) and "$mascarado" not in resposta
    assert "$destino" not in resposta and "$email" not in resposta
    # admin: a mesma resposta + destinatario_mascarado
    admin = _bloco_re(codigo, r"if \(\$eh_admin == true\) \{\s*var\.update \$resposta \{")
    assert re.findall(r"^\s*(\w+)\s*:", _bloco(admin, "value = {"), re.M) == ["status", "mensagem", "enviado", "destinatario_mascarado", "quantidade"]
    assert "destinatario_mascarado: $mascarado" in admin
    assert 'var $mensagem_final { value = "Aviso de recursos sem equipe enviado ao DevOps do projeto." }' in codigo
    assert 'var.update $mensagem_final { value = "Aviso de recursos sem equipe enviado para " ~ $mascarado ~ "." }' in codigo
    # o endpoint de orçamento devolve só status e mensagem (o "aviso" é texto da mensagem)
    antigo = _codigo(NOTIFICAR)
    assert re.findall(r"^\s*(\w+)\s*:", _bloco(antigo, "var $resposta {\n      value = {"), re.M) == ["status", "mensagem"]
    assert codigo.index('precondition ($estado == "enviado")') < codigo.index("if ($registro_falhou)") < codigo.index("var $resposta")


def test_mascara_do_destinatario_so_na_resposta_do_admin_endereco_inteiro_nunca():
    codigo = _codigo(RECURSOS)
    usos = re.findall(r"[^\n]*\$mascarado[^\n]*", codigo)
    assert len(usos) == 4, usos  # declaração, cálculo, mensagem do admin e campo da resposta do admin
    assert "$destino" not in codigo[codigo.index("var $mensagem_final"):]
    # os dois últimos usos (mensagem e campo) só existem dentro de `if ($eh_admin == true)`
    final = codigo[codigo.index("var $mensagem_final"):]
    for bloco in re.findall(r"if \(\$eh_admin == true\) \{", final):
        assert bloco
    assert final.count("$eh_admin == true") == 2
    for uso in re.findall(r"[^\n]*\$mascarado[^\n]*", final):
        pos = final.index(uso)
        assert any(m.start() < pos for m in re.finditer(r"if \(\$eh_admin == true\) \{", final[:pos])), uso


# ---------------------------------------------------------------------------
# O novo endpoint não toca no Azure nem em segredos
# ---------------------------------------------------------------------------

def test_novo_endpoint_nao_chama_azure_nem_variaveis_azure_nem_o_resumo():
    codigo = _codigo(RECURSOS)
    assert not re.search(r"azure|AZURE_|management\.azure|login\.microsoftonline|provedor_externo_leitura", codigo, re.I)
    assert "costguard/resumo_consumo" not in codigo, "este aviso lê só `recursos`"
    for arquivo in ARQUIVOS_EMAIL:
        assert not re.search(r"azure", _codigo(arquivo), re.I), arquivo.name


def test_novo_endpoint_e_funcoes_sem_segredo_nem_email_real():
    for arquivo in ARQUIVOS_EMAIL:
        texto = _ler(arquivo)
        assert not re.search(r"\bre_[A-Za-z0-9_]{8,}", texto), arquivo.name
        assert not re.search(r"eyJ[A-Za-z0-9_-]{10,}", texto), arquivo.name
        for dominio in re.findall(r"[A-Za-z0-9_.+-]+@([A-Za-z0-9.-]+)", texto):
            assert dominio == "exemplo.com", f"{arquivo.name}: e-mail com domínio {dominio}"
    for arquivo in (NOTIFICAR, RECURSOS):
        codigo = _codigo(arquivo)
        assert set(re.findall(r"\$env\.(\w+)", codigo)) == {"EMAIL_API_KEY", "EMAIL_FROM", "COSTGUARD_APP_URL"}
        assert re.search(r'var \$email_chave \{ value = \(\$env\.EMAIL_API_KEY \?\? ""\) \}', codigo)
        assert re.search(r'var \$email_from \{ value = \(\$env\.EMAIL_FROM \?\? ""\) \}', codigo) or "EMAIL_FROM" in codigo
        assert not re.search(r"\balertas@|noreply@|no-reply@|@costguard", _ler(arquivo), re.I)
        assert "$email_chave" not in "".join(re.findall(r"error = .*", codigo))
    # as funções novas não leem variável de ambiente
    for arquivo in (ESCAPAR, LIMPAR, FORMATAR, MES, LAYOUT, LINHA):
        assert "$env" not in _codigo(arquivo), arquivo.name


def test_funcoes_novas_tem_input_tipado_e_nenhuma_escreve_no_banco_nem_chama_rede():
    for arquivo in (ESCAPAR, LIMPAR, FORMATAR, MES, LAYOUT, LINHA):
        codigo = _codigo(arquivo)
        assert re.match(r'function "costguard/\w+" \{\s*input \{', codigo), arquivo.name
        assert not re.search(r"db\.(add|edit|del|query|get)|api\.request", codigo), arquivo.name
    assert [p.stem for p in sorted(FUNCOES.glob("*.xs")) if p in (ESCAPAR, LIMPAR, FORMATAR, MES, LAYOUT, LINHA)] == sorted(
        ["escapar_html", "limpar_texto_linha", "formatar_numero_br", "mes_extenso_pt_br", "email_html_layout", "email_html_linha"])


def test_envio_continua_somente_manual_e_so_os_dois_endpoints_conhecem_o_resend():
    donos = {NOTIFICAR, RECURSOS}
    for arquivo in XANO.rglob("*.xs"):
        if arquivo in donos:
            continue
        codigo = _codigo(arquivo)
        for marcador in ("notificar-recursos-sem-equipe", "notificar_recursos", "api.resend.com", "EMAIL_API_KEY", "EMAIL_FROM",
                         "devops_recursos_ultimo_envio", "COSTGUARD_APP_URL"):
            if arquivo == TABELA and marcador == "devops_recursos_ultimo_envio":
                continue
            assert marcador not in codigo, f"{arquivo.relative_to(XANO)} usa `{marcador}`"
    assert "notificar" not in _ler(XANO / "workspace" / "miguels_workspace.xs").lower()
    for py in (RAIZ / "projetoImpacta").glob("sincronizacao*.py"):
        assert "recursos-sem-equipe" not in py.read_text(encoding="utf-8").lower(), py.name


def test_leituras_de_projeto_nunca_devolvem_o_registro_do_aviso_de_recursos():
    for nome in ("listar_projetos_GET.xs", "detalhe_projeto_GET.xs", "criar_projeto_POST.xs", "editar_projeto_PATCH.xs",
                 "painel_projeto_GET.xs", "painel_GET.xs", "projetos_resumo_consumo_mtd_GET.xs"):
        assert "devops_recursos" not in _codigo(APP / nome), nome


# ---------------------------------------------------------------------------
# Contrato documentado
# ---------------------------------------------------------------------------

def test_contrato_documenta_html_novo_endpoint_decisao_admin_e_nao_verificado():
    texto = _ler_doc_interno(CONTRATO)
    for trecho in ("notificar-recursos-sem-equipe", "html", "text", "[CostGuard] Orçamento em alerta", "[CostGuard] Recursos sem equipe",
                   "devops_recursos_ultimo_envio_em", "qualquer perfil", "destinatario_mascarado", "quantidade",
                   "Nenhum recurso sem equipe neste projeto no mês.", "NÃO VERIFICADO", "escapar_html", "Idempotency-Key",
                   "devops-rec-", "e mais N", "Orçamento não definido"):
        assert trecho in texto, f"o contrato não menciona: {trecho}"
    assert texto.index("## 2.1") < texto.index("## 2.2") < texto.index("## 3. Pré-requisitos")


def test_contrato_registra_riscos_aceitos_latencia_nao_verificada_e_decisoes_pendentes():
    texto = _ler_doc_interno(CONTRATO)
    assert "até 150 chamadas" not in texto
    # (b) e (d) deixaram de ser pendências: o teto compartilhado é RISCO ACEITO (decisão do usuário em 24/11/2026) e o texto de (d) foi resolvido
    assert "DECISÃO PENDENTE" not in texto and "admin-only" not in texto and "Acesso negado" not in texto.split("## 2.2")[1].split("## 2.3")[0]
    assert "24/11/2026" in texto and "qualquer perfil" in texto
    riscos = texto.split("## 2.4")[1].split("## 3. Pré-requisitos")[0]
    assert 0 <= riscos.index("RISCO ACEITO") < riscos.index("(b) Teto de 30/dia global e compartilhado")
    for trecho in ("~350 chamadas", "~19 restantes", "latência total é NÃO VERIFICADA", "## 2.4", "RISCO ACEITO",
                   "(a) CPU em repetição", "(b) Teto de 30/dia", "(c) Ficha devolvida", "(d)", "Consumo indisponível (sem custo em USD no mês)",
                   "(e) Arredondamento", "(f) Nome do recurso = último trecho do ARN", "U+2028", "U+202A", "Não há injeção de cabeçalho",
                   "`https://`", "sem o botão", "devolve **vazio**"):
        assert trecho in texto, f"o contrato não menciona: {trecho}"
    # o texto antigo sobre o fuso foi corrigido: o uso de America/Sao_Paulo com format_timestamp já existe no repositório
    assert "(**NÃO VERIFICADO** se aceitaria `America/Sao_Paulo`)" not in texto and "não usado de propósito" not in texto


def test_fuso_america_sao_paulo_com_format_timestamp_ja_e_usado_no_repositorio():
    """Parte do teste de riscos que NAO depende do documento interno: roda mesmo sem docs/interno."""
    for arquivo in ("resumo_consumo.xs", "avaliar_alertas.xs"):
        assert re.search(r'format_timestamp:[^\n]*"America/Sao_Paulo"', _codigo(FUNCOES / arquivo)), arquivo


def test_comentarios_do_dia_civil_dos_endpoints_nao_dizem_mais_que_o_fuso_nunca_foi_usado():
    for arquivo in (NOTIFICAR, RECURSOS):
        texto = _ler(arquivo)
        assert "só o\n        // fuso \"UTC\" é de uso comprovado" not in texto
        assert "NÃO VERIFICADO se\n        // `format_timestamp` aceitaria" not in texto
        assert "JÁ é usado em" in texto and "costguard/avaliar_alertas" in texto

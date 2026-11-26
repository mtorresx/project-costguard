"""Custo por recurso (coluna `recursos.custo_mensal`): verificações estáticas e de contrato.

Leem o TEXTO dos .xs de `xano/` e as respostas gravadas em `tests/fixtures/xano/`. Não provam o
comportamento do Xano publicado (isso exige publicar e testar contra o Xano).

Garantias cobertas:
1. A coluna é aditiva, anulável, sem padrão, e nenhuma coluna existente muda.
2. A sincronização de inventário nunca lê, grava, zera nem apaga `custo_mensal`
   (cada `db.edit`/`db.add`/`db.del` em `recursos` lista campos explícitos).
3. `recursos_projeto` devolve `custo_mensal` como está (número ou null), sem soma e sem 0 forçado.
4. As respostas gravadas respeitam o contrato (número ou null, nunca string).
As funções `violacoes_*` são usadas também sobre textos mutados, para provar que o teste detecta
as regressões.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
XANO = RAIZ / "xano"
FIXTURES = Path(__file__).parent / "fixtures" / "xano"

TABELA = XANO / "table" / "recursos.xs"
SINCRONIZAR = XANO / "function" / "costguard" / "sincronizar_inventario.xs"
RECURSOS_PROJETO = XANO / "function" / "costguard" / "recursos_projeto.xs"

# Declarações da tabela `recursos` ANTES da coluna nova (sem comentários; linhas normalizadas).
BASELINE_TABELA = """
table recursos {
auth = false
schema {
int id
int provedor_id {
table = "provedores"
}
text arn
text regiao filters=trim
text servico filters=trim
int projeto_id? {
table = "projetos"
}
int equipe_id? {
table = "equipes"
}
text codigo_projeto_tag?
text codigo_equipe_tag?
text sync_id?
timestamp ultima_vista_em? {
visibility = "private"
}
bool ativo?=true
timestamp criado_em?=now {
visibility = "private"
}
timestamp atualizado_em?=now {
visibility = "private"
}
}
index = [
{type: "primary", field: [{name: "id"}]}
{type: "btree|unique", field: [{name: "provedor_id", op: "asc"}, {name: "arn", op: "asc"}]}
{type: "btree", field: [{name: "projeto_id", op: "asc"}]}
{type: "btree", field: [{name: "equipe_id", op: "asc"}]}
]
guid = "bcONi1wyFos3CfA2wG2lFZnR-DE"
}
""".strip().splitlines()

# Campos que a sincronização controla em cada escrita de `recursos` (nenhum é custo_mensal).
CAMPOS_EDIT_ATUALIZACAO = {
    "regiao", "servico", "projeto_id", "equipe_id", "codigo_projeto_tag", "codigo_equipe_tag",
    "sync_id", "ultima_vista_em", "ativo", "atualizado_em",
}
CAMPOS_EDIT_DESATIVACAO = {"ativo", "atualizado_em"}
CAMPOS_ADD = {
    "provedor_id", "arn", "regiao", "servico", "projeto_id", "equipe_id", "codigo_projeto_tag",
    "codigo_equipe_tag", "sync_id", "ultima_vista_em", "ativo",
}

ORDEM_CAMPOS_RESPOSTA = [
    "id", "provedor_id", "arn", "regiao", "servico", "projeto_id", "equipe_id",
    "codigo_projeto_tag", "codigo_equipe_tag", "sem_responsavel", "ativo", "descoberto_em",
    "custo_mensal",
]


# ----------------------------------------------------------------------------------------------
# Utilidades de texto
# ----------------------------------------------------------------------------------------------

def _ler(caminho: Path) -> str:
    return caminho.read_text(encoding="utf-8")


def _sem_comentarios(texto: str) -> str:
    return "\n".join(l for l in texto.splitlines() if not l.strip().startswith("//"))


def _bloco(texto: str, inicio: int) -> str:
    """Texto de `{ ... }` a partir da primeira `{` depois de `inicio` (chaves balanceadas)."""
    abre = texto.index("{", inicio)
    nivel = 0
    for i in range(abre, len(texto)):
        if texto[i] == "{":
            nivel += 1
        elif texto[i] == "}":
            nivel -= 1
            if nivel == 0:
                return texto[abre:i + 1]
    raise AssertionError("bloco sem fechamento")


def _escritas_recursos(texto: str) -> list[tuple[str, str]]:
    """[(operação, texto do bloco)] de todo `db.<op> recursos {` com op diferente de query/get."""
    achados = []
    limpo = _sem_comentarios(texto)
    for m in re.finditer(r"\bdb\.(\w+)\s+recursos\b", limpo):
        op = m.group(1)
        if op in ("query", "get", "has"):
            continue
        achados.append((op, _bloco(limpo, m.end())))
    return achados


def _campos_data(bloco: str) -> set[str] | None:
    """Chaves do objeto literal `data = { ... }`; None se `data` não for um objeto literal."""
    m = re.search(r"\bdata\s*=\s*\{", bloco)
    if not m:
        return None
    interno = _bloco(bloco, m.end() - 1)
    return set(re.findall(r"(?m)^\s*(\w+)\s*:", interno[1:-1]))


# ----------------------------------------------------------------------------------------------
# Regras: tabela
# ----------------------------------------------------------------------------------------------

def _linhas_tabela(texto: str) -> list[str]:
    return [l.strip() for l in _sem_comentarios(texto).splitlines() if l.strip()]


def violacoes_tabela(texto: str) -> list[str]:
    v = []
    linhas = _linhas_tabela(texto)
    decl = [l for l in linhas if re.match(r"decimal\s+custo_mensal\b", l)]
    if decl != ["decimal custo_mensal?"]:
        v.append(f"declaração de custo_mensal deve ser exatamente `decimal custo_mensal?`: {decl}")
    if sum("custo_mensal" in l for l in linhas) != 1:
        v.append("custo_mensal deve aparecer uma única vez (sem índice, sem padrão)")
    resto = [l for l in linhas if "custo_mensal" not in l]
    if resto != BASELINE_TABELA:
        v.append("a tabela diverge da versão anterior além da coluna custo_mensal")
    return v


def test_tabela_recursos_tem_coluna_aditiva_anulavel_sem_padrao():
    assert violacoes_tabela(_ler(TABELA)) == []


def test_tabela_documenta_usd_opcional_sem_coleta_automatica():
    comentarios = "\n".join(l for l in _ler(TABELA).splitlines() if l.strip().startswith("//"))
    trecho = comentarios.split("Custo mensal do recurso", 1)[-1].lower()
    assert "usd" in trecho and "opcional" in trecho and "coleta autom" in trecho


def test_tabela_nao_altera_colunas_existentes_em_relacao_ao_head():
    """Compara com `git show HEAD:xano/table/recursos.xs` (somente leitura); pula sem repositório git."""
    try:
        topo = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=RAIZ,
                              capture_output=True, text=True, encoding="utf-8", timeout=30)
        if topo.returncode != 0 or Path(topo.stdout.strip()).resolve() != RAIZ.resolve():
            pytest.skip("sem repositório git")
        r = subprocess.run(["git", "show", "HEAD:xano/table/recursos.xs"], cwd=RAIZ,
                           capture_output=True, text=True, encoding="utf-8", timeout=30)
    except (OSError, subprocess.SubprocessError):
        pytest.skip("sem repositório git")
    if r.returncode != 0:
        pytest.skip("sem repositório git (HEAD:xano/table/recursos.xs indisponível)")
    antes = [l for l in _linhas_tabela(r.stdout) if "custo_mensal" not in l]
    depois = [l for l in _linhas_tabela(_ler(TABELA)) if "custo_mensal" not in l]
    assert antes == depois


@pytest.mark.parametrize("mutacao", [
    lambda t: t.replace("decimal custo_mensal?", "decimal custo_mensal"),
    lambda t: t.replace("decimal custo_mensal?", "decimal custo_mensal?=0"),
    lambda t: t.replace("decimal custo_mensal?", "decimal? custo_mensal"),
    lambda t: t.replace("decimal custo_mensal?", "text custo_mensal?"),
    lambda t: t.replace("text arn\n", "text arn?\n"),
    lambda t: t.replace("    text sync_id?\n", ""),
    lambda t: t.replace("bool ativo?=true", "bool ativo?=false"),
    lambda t: t.replace("]\n  guid", "  {type: \"btree\", field: [{name: \"custo_mensal\"}]}\n  ]\n  guid"),
], ids=["sem-anulavel", "padrao-zero", "sintaxe-trocada", "tipo-text", "coluna-existente-alterada",
        "coluna-existente-removida", "padrao-existente-alterado", "indice-novo"])
def test_mutacoes_da_tabela_sao_detectadas(mutacao):
    original = _ler(TABELA)
    mutado = mutacao(original)
    assert mutado != original
    assert violacoes_tabela(mutado)


# ----------------------------------------------------------------------------------------------
# Regras: sincronização de inventário
# ----------------------------------------------------------------------------------------------

def violacoes_sincronizacao(texto: str) -> list[str]:
    v = []
    limpo = _sem_comentarios(texto)
    if "custo_mensal" in limpo:
        v.append("custo_mensal aparece no código da sincronização")

    escritas = _escritas_recursos(texto)
    ops = [op for op, _ in escritas]
    if ops != ["edit", "add", "edit"]:
        v.append(f"escritas em recursos esperadas [edit, add, edit] (atualização, criação, "
                 f"desativação); encontradas {ops}")
        return v
    esperados = [CAMPOS_EDIT_ATUALIZACAO, CAMPOS_ADD, CAMPOS_EDIT_DESATIVACAO]
    for (op, bloco), esperado in zip(escritas, esperados):
        if "custo_mensal" in bloco:
            v.append(f"bloco db.{op} recursos menciona custo_mensal")
        campos = _campos_data(bloco)
        if campos is None:
            v.append(f"db.{op} recursos sem `data = {{ ... }}` explícito (registro inteiro?)")
        elif campos != esperado:
            v.append(f"db.{op} recursos grava {sorted(campos)}; esperado {sorted(esperado)}")
        if op == "edit" and not re.search(r'field_name\s*=\s*"id"', bloco):
            v.append("db.edit recursos deve localizar o registro por `id`")

    m = re.search(r"var \$igual\s*\{\s*value\s*=(.*?)\n\s*\}", limpo, re.S)
    if not m:
        v.append("comparação `$igual` não encontrada")
    elif "custo_mensal" in m.group(1):
        v.append("`$igual` inclui custo_mensal")

    # Reativação (edit de atualização) grava ativo true; desativação grava ativo false.
    if not re.search(r"\bativo\s*:\s*true\b", escritas[0][1]):
        v.append("a atualização/reativação deve gravar `ativo: true`")
    if not re.search(r"\bativo\s*:\s*false\b", escritas[2][1]):
        v.append("a desativação deve gravar `ativo: false`")
    return v


def test_sincronizacao_nao_toca_custo_mensal():
    assert violacoes_sincronizacao(_ler(SINCRONIZAR)) == []


def test_sincronizacao_auditoria_de_cada_escrita_em_recursos():
    escritas = _escritas_recursos(_ler(SINCRONIZAR))
    assert [op for op, _ in escritas] == ["edit", "add", "edit"]
    assert _campos_data(escritas[0][1]) == CAMPOS_EDIT_ATUALIZACAO
    assert _campos_data(escritas[1][1]) == CAMPOS_ADD
    assert _campos_data(escritas[2][1]) == CAMPOS_EDIT_DESATIVACAO
    # Desativação: só ativo/atualizado_em (não toca ultima_vista_em nem sync_id).
    assert not ({"ultima_vista_em", "sync_id"} & _campos_data(escritas[2][1]))
    # Reativação é o edit de atualização: ativo true + ultima_vista_em + sync_id.
    assert {"ativo", "ultima_vista_em", "sync_id"} <= _campos_data(escritas[0][1])
    # Criação: custo_mensal fica de fora (null).
    assert "custo_mensal" not in _campos_data(escritas[1][1])


def test_nenhum_outro_arquivo_escreve_em_recursos_exceto_exclusao_de_provedor_de_teste():
    escritores = {}
    for arq in XANO.rglob("*.xs"):
        escritas = _escritas_recursos(_ler(arq))
        if escritas:
            escritores[arq.relative_to(XANO).as_posix()] = [op for op, _ in escritas]
    assert escritores == {
        "function/costguard/sincronizar_inventario.xs": ["edit", "add", "edit"],
        "api/app/excluir_provedor_teste_POST.xs": ["del"],
    }


def _editar_bloco(texto: str, n: int, novo_bloco) -> str:
    """Troca o valor de `data = ...` da n-ésima escrita (edit/add) em recursos."""
    m = list(re.finditer(r"db\.(edit|add)\s+recursos\b", texto))[n]
    d = re.compile(r"data\s*=\s*").search(texto, m.end())
    bloco = _bloco(texto, d.end())
    fim = texto.index(bloco, d.end()) + len(bloco)
    return texto[:d.start()] + novo_bloco(bloco) + texto[fim:]


def _com_campo(bloco: str, linha: str) -> str:
    return "data = " + bloco[:-1] + "\n  " + linha + "\n}"


MUTACOES_SINCRONIZACAO = {
    "edit-atualizacao-custo-zero": lambda t: _editar_bloco(t, 0, lambda b: _com_campo(b, "custo_mensal: 0")),
    "edit-atualizacao-custo-null": lambda t: _editar_bloco(t, 0, lambda b: _com_campo(b, "custo_mensal: null")),
    "edit-desativacao-custo-null": lambda t: _editar_bloco(t, 2, lambda b: _com_campo(b, "custo_mensal: null")),
    "add-copia-custo-existente": lambda t: _editar_bloco(t, 1, lambda b: _com_campo(b, "custo_mensal: $existente.custo_mensal")),
    "edit-atualizacao-registro-inteiro": lambda t: _editar_bloco(t, 0, lambda b: "data = $existente"),
    "edit-desativacao-registro-inteiro": lambda t: _editar_bloco(t, 2, lambda b: "data = $o"),
    "add-registro-inteiro": lambda t: _editar_bloco(t, 1, lambda b: "data = $r"),
    "edit-registro-montado-por-set": lambda t: _editar_bloco(
        t, 0, lambda b: 'data = ($existente|set:"ativo":true)'),
    "edit-campo-extra-nao-controlado": lambda t: _editar_bloco(t, 2, lambda b: _com_campo(b, "projeto_id: 0")),
    "igual-inclui-custo": lambda t: t.replace(
        "(($existente.codigo_equipe_tag ?? \"\") == $val_eqp))",
        "(($existente.codigo_equipe_tag ?? \"\") == $val_eqp) && ($existente.custo_mensal == null))"),
    "edit-novo-bloco-add-or-edit": lambda t: t.replace(
        "var.update $recursos_criados { value = $recursos_criados + 1 }",
        "db.add_or_edit recursos {\n field_name = \"arn\"\n field_value = $arn\n data = {ativo: true}\n }\n"
        "var.update $recursos_criados { value = $recursos_criados + 1 }"),
    "edit-novo-bloco-del": lambda t: t.replace(
        "var.update $recursos_desativados { value = $recursos_desativados + 1 }",
        "db.del recursos {\n field_name = \"id\"\n field_value = $o.id\n }\n"
        "var.update $recursos_desativados { value = $recursos_desativados + 1 }"),
    "custo-lido-fora-de-escrita": lambda t: t.replace(
        "var $kr { value = \"k\" ~ ($arn|sha256) }",
        "var $custo_antigo { value = $mapa_rec|get:\"x\":null|get:\"custo_mensal\":null }\n"
        "                        var $kr { value = \"k\" ~ ($arn|sha256) }"),
}


@pytest.mark.parametrize("nome", sorted(MUTACOES_SINCRONIZACAO))
def test_mutacoes_da_sincronizacao_sao_detectadas(nome):
    original = _ler(SINCRONIZAR)
    mutado = MUTACOES_SINCRONIZACAO[nome](original)
    assert mutado != original, "a mutação não alterou o texto (padrão de busca desatualizado)"
    assert violacoes_sincronizacao(mutado), f"mutação `{nome}` não foi detectada"


def test_ha_ao_menos_oito_mutacoes_da_sincronizacao():
    assert len(MUTACOES_SINCRONIZACAO) >= 8


# ----------------------------------------------------------------------------------------------
# Regras: função recursos_projeto
# ----------------------------------------------------------------------------------------------

def _campos_resposta(texto: str) -> list[str] | None:
    limpo = _sem_comentarios(texto)
    m = re.search(r"\|map:\s*\{", limpo)
    if not m:
        return None
    interno = _bloco(limpo, m.end() - 1)[1:-1]
    return re.findall(r"(?m)^\s*(\w+)\s*:", interno)


def violacoes_recursos_projeto(texto: str) -> list[str]:
    v = []
    limpo = _sem_comentarios(texto)
    campos = _campos_resposta(texto)
    if campos != ORDEM_CAMPOS_RESPOSTA:
        v.append(f"campos/ordem da resposta: {campos}")
    if len(re.findall(r"custo_mensal", limpo)) != 2:
        v.append("custo_mensal deve aparecer só como chave e valor da resposta")
    if not re.search(r"(?m)^\s*custo_mensal\s*:\s*\$\$\.custo_mensal\s*$", limpo):
        v.append("custo_mensal deve ser devolvido como `$$.custo_mensal` (sem ?? 0, sem filtro)")
    if re.search(r"\b(sum|reduce|add)\b|\|\s*(sum|add)\b", limpo):
        v.append("a função não deve somar valores")
    # Nenhuma coluna de custo do recurso entra em soma/agregado.
    if re.search(r"custo_mensal[^\n]*(\+|\bsum\b|\?\?|to_int|round|floor|ceil)", limpo):
        v.append("custo_mensal sofre operação (soma/coalescência/arredondamento)")
    return v


def test_recursos_projeto_devolve_custo_mensal_cru_e_no_fim():
    assert violacoes_recursos_projeto(_ler(RECURSOS_PROJETO)) == []


def test_recursos_projeto_mantem_campos_existentes_na_mesma_ordem():
    campos = _campos_resposta(_ler(RECURSOS_PROJETO))
    assert campos[:-1] == ORDEM_CAMPOS_RESPOSTA[:-1]
    assert campos[-1] == "custo_mensal"


def test_recursos_projeto_nao_filtra_nem_agrega_por_custo():
    limpo = _sem_comentarios(_ler(RECURSOS_PROJETO))
    assert re.search(r"where\s*=\s*\$db\.recursos\.projeto_id == \$input\.id\s*\n", limpo)
    assert "custo_mensal" not in re.search(r"db\.query recursos \{.*?\} as \$lista", limpo, re.S).group(0)


MUTACOES_RECURSOS_PROJETO = {
    "zero-forcado": lambda t: t.replace("$$.custo_mensal\n", "($$.custo_mensal ?? 0)\n"),
    "campo-removido": lambda t: t.replace(",\n        custo_mensal     : $$.custo_mensal", ""),
    "ordem-trocada": lambda t: t.replace(
        "descoberto_em    : $$.criado_em,\n        custo_mensal     : $$.custo_mensal",
        "custo_mensal     : $$.custo_mensal,\n        descoberto_em    : $$.criado_em"),
    "valor-diferente": lambda t: t.replace("custo_mensal     : $$.custo_mensal", "custo_mensal     : $$.valor"),
    "soma-no-total": lambda t: t.replace(
        "response = $resposta", "var $total { value = $lista|map:$$.custo_mensal|sum }\n  response = $resposta"),
    "arredondado": lambda t: t.replace("$$.custo_mensal\n", "($$.custo_mensal|round)\n"),
    "campo-existente-removido": lambda t: t.replace("        regiao           : $$.regiao,\n", ""),
    "somado-ao-valor": lambda t: t.replace("$$.custo_mensal\n", "($$.custo_mensal + 0)\n"),
}


@pytest.mark.parametrize("nome", sorted(MUTACOES_RECURSOS_PROJETO))
def test_mutacoes_de_recursos_projeto_sao_detectadas(nome):
    original = _ler(RECURSOS_PROJETO)
    mutado = MUTACOES_RECURSOS_PROJETO[nome](original)
    assert mutado != original, "a mutação não alterou o texto (padrão de busca desatualizado)"
    assert violacoes_recursos_projeto(mutado), f"mutação `{nome}` não foi detectada"


def test_custo_mensal_so_aparece_na_tabela_e_na_funcao_de_recursos_do_projeto():
    usam = {a.relative_to(XANO).as_posix() for a in XANO.rglob("*.xs")
            if "custo_mensal" in _sem_comentarios(_ler(a))}
    assert usam == {"table/recursos.xs", "function/costguard/recursos_projeto.xs"}


def test_recursos_nao_classificados_nao_foi_alterada():
    limpo = _sem_comentarios(_ler(XANO / "function" / "costguard" / "recursos_nao_classificados.xs"))
    assert "custo_mensal" not in limpo


def test_endpoints_da_lista_apenas_chamam_a_funcao():
    for nome in ("listar_recursos_projeto_GET.xs", "painel_projeto_GET.xs"):
        limpo = _sem_comentarios(_ler(XANO / "api" / "app" / nome))
        assert 'function.run "costguard/recursos_projeto"' in limpo
        assert "custo_mensal" not in limpo and "db.query recursos" not in limpo


# ----------------------------------------------------------------------------------------------
# Contrato das respostas gravadas
# ----------------------------------------------------------------------------------------------

def _gravada(nome: str):
    return json.loads((FIXTURES / f"{nome}.json").read_text(encoding="utf-8"))["corpo"]


def violacoes_contrato(recursos) -> list[str]:
    v = []
    if not isinstance(recursos, list) or not recursos:
        return ["lista de recursos vazia ou inválida"]
    for r in recursos:
        rid = r.get("id") if isinstance(r, dict) else r
        if not isinstance(r, dict) or "custo_mensal" not in r:
            v.append(f"recurso {rid}: campo custo_mensal ausente")
            continue
        valor = r["custo_mensal"]
        if valor is not None and (isinstance(valor, bool) or not isinstance(valor, (int, float))):
            v.append(f"recurso {rid}: custo_mensal deve ser número ou null, veio {valor!r}")
        elif valor is not None and valor < 0:
            v.append(f"recurso {rid}: custo_mensal negativo")
        if list(r) != ORDEM_CAMPOS_RESPOSTA:
            v.append(f"recurso {rid}: campos/ordem fora do contrato: {list(r)}")
    return v


def _lista_recursos(nome: str):
    corpo = _gravada(nome)
    return corpo["recursos"] if isinstance(corpo, dict) else corpo


@pytest.mark.parametrize("fixture", ["projeto_recursos", "projeto_painel"])
def test_fixture_cumpre_o_contrato_de_custo_mensal(fixture):
    assert violacoes_contrato(_lista_recursos(fixture)) == []


@pytest.mark.parametrize("fixture", ["projeto_recursos", "projeto_painel"])
def test_fixture_tem_recursos_com_e_sem_custo(fixture):
    valores = [r["custo_mensal"] for r in _lista_recursos(fixture)]
    assert None in valores
    assert sorted(v for v in valores if v is not None) == [2.0, 6.0]


def test_painel_do_projeto_e_lista_de_recursos_trazem_os_mesmos_recursos():
    assert _lista_recursos("projeto_painel") == _lista_recursos("projeto_recursos")


def test_fixtures_usam_conta_ficticia():
    for nome in ("projeto_recursos", "projeto_painel"):
        texto = (FIXTURES / f"{nome}.json").read_text(encoding="utf-8")
        assert "210987654321" in texto


def test_fixture_de_nao_classificados_nao_ganhou_custo_mensal():
    assert "custo_mensal" not in (FIXTURES / "recursos_nao_classificados.json").read_text(encoding="utf-8")
    assert "custo_mensal" not in json.dumps(_gravada("painel")["recursos_nao_classificados"])


def _copia(nome: str) -> list[dict]:
    return json.loads(json.dumps(_lista_recursos(nome)))


@pytest.mark.parametrize("mutacao", [
    lambda rs: rs[0].__setitem__("custo_mensal", "6.0"),
    lambda rs: rs[0].__setitem__("custo_mensal", True),
    lambda rs: rs[0].__setitem__("custo_mensal", -1),
    lambda rs: rs[0].pop("custo_mensal"),
    lambda rs: rs.__setitem__(0, {"custo_mensal": 1.0, **{k: v for k, v in rs[0].items() if k != "custo_mensal"}}),
    lambda rs: rs.__setitem__(0, {k: v for k, v in rs[0].items() if k != "regiao"} | {"custo_mensal": None}),
    lambda rs: rs.clear(),
], ids=["string", "booleano", "negativo", "ausente", "ordem", "campo-existente-removido", "lista-vazia"])
def test_mutacoes_do_contrato_sao_detectadas(mutacao):
    recursos = _copia("projeto_recursos")
    mutacao(recursos)
    assert violacoes_contrato(recursos)

"""Autorização por papel no Xano: admin escreve; leitura lê, mas não escreve (403).

    .venv/Scripts/python -m pytest tests/integracao/test_autorizacao.py --integracao -v

As escritas tentadas com o papel leitura miram só objetos TESTE_ (o provedor do
teste, um projeto TESTE_ que não deve chegar a existir). Se alguma passar por
engano, o projeto criado é desativado no final e o teste falha.
"""

import pytest

from cliente import CONTA_TESTE, PREFIXO, sufixo


@pytest.fixture(scope="module")
def token_leitura(vivo):
    st, corpo = vivo.login("leitura")
    token = corpo.get("token") if isinstance(corpo, dict) else None
    if not token:
        # O login responde HTTP 200 com {status: 401, erro} para qualquer falha (sem enumerar usuários).
        detalhe = (corpo.get("status"), corpo.get("erro")) if isinstance(corpo, dict) else corpo
        pytest.skip(f"login de XANO_E2E_LEITURA_* não devolveu token (HTTP {st}, corpo {detalhe})")
    return token


def test_admin_escreve(vivo, provedor_teste):
    pid = provedor_teste
    novo = f"{PREFIXO}ADMIN_{sufixo()}"
    st, r = vivo.x("PATCH", f"/provedores/{pid}", {"apelido": novo})
    assert st == 200 and r["apelido"] == novo, (st, r)
    st, _ = vivo.x("GET", "/usuarios")
    assert st == 200


def test_leitura_le_mas_nao_escreve(vivo, provedor_teste, token_leitura):
    pid = provedor_teste
    vivo._tokens["leitura"] = token_leitura

    for caminho in ("/painel", "/provedores", "/alertas", "/recursos-nao-classificados", "/sincronizacao/estado"):
        st, _ = vivo.x("GET", caminho, papel="leitura")
        assert st == 200, (caminho, st)

    codigo = f"{PREFIXO}AUTZ_{sufixo()}"
    tentativas = [
        ("POST", "/provedores", {"apelido": f"{PREFIXO}LEITURA", "tipo": "aws", "identificador_conta": CONTA_TESTE,
                                 "aws_access_key_id": "AKIAX", "aws_secret_access_key": "x"}),
        ("PATCH", f"/provedores/{pid}", {"apelido": f"{PREFIXO}INVADIDO"}),
        ("POST", f"/provedores/{pid}/sincronizar-recursos", {}),
        ("POST", f"/provedores/{pid}/testar-conexao", {}),
        ("POST", "/projetos", {"nome": codigo, "codigo": codigo, "budget": 1}),
    ]
    vazou = []
    try:
        for metodo, caminho, corpo in tentativas:
            st, r = vivo.x(metodo, caminho, corpo, papel="leitura")
            if st != 403:
                vazou.append((metodo, caminho, st))
        st, _ = vivo.x("GET", "/usuarios", papel="leitura")
        if st != 403:
            vazou.append(("GET", "/usuarios", st))
        assert vivo.provedor(pid)["apelido"].startswith(PREFIXO) and "INVADIDO" not in vivo.provedor(pid)["apelido"]
    finally:
        st, projetos = vivo.x("GET", "/projetos")
        for p in projetos if st == 200 else []:
            if p["codigo"] == codigo:  # só se a criação passou indevidamente
                vivo.x("POST", f"/projetos/{p['id']}/desativar", {})
                vazou.append(("resíduo", f"projeto {codigo} desativado", p["id"]))
    assert vazou == [], vazou

"""P2-12: provedor inativo continua inativo ao editar a credencial (só com provedor TESTE_).

    .venv/Scripts/python -m pytest tests/integracao/test_provedor_credencial.py --integracao -v
"""


def _status(vivo, pid):
    return vivo.provedor(pid)["status"]


def test_provedor_inativo_continua_inativo(vivo, provedor_teste):
    pid = provedor_teste
    st, _ = vivo.x("POST", f"/provedores/{pid}/desativar", {})
    assert st == 200 and _status(vivo, pid) == "inativo"
    st, r = vivo.x("PATCH", f"/provedores/{pid}", {"aws_secret_access_key": "outro-segredo-ficticio"})
    assert st == 200 and r["status"] == "inativo", (st, r)

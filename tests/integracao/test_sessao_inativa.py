"""P2-10: usuário desativado perde o acesso às leituras (GET -> 401), mesmo com token ainda válido.

    .venv/Scripts/python -m pytest tests/integracao/test_sessao_inativa.py --integracao -v

Cria um usuário de leitura `teste_sess_*`, faz login, desativa e confere os GETs.
Ao final a linha do usuário de teste é removida pela Metadata API (não há endpoint
de exclusão de usuário). A senha é gerada aqui e nunca impressa.
"""

import secrets

from cliente import sufixo

GETS = ["/painel", "/projetos", "/projetos-resumo-consumo-mtd", "/alertas", "/recursos-nao-classificados",
        "/sincronizacao/estado", "/provedores", "/provedores/2", "/projetos/5", "/projetos/5/painel",
        "/projetos/5/recursos", "/projetos/5/equipes", "/projetos/5/custos-equipe"]


def test_usuario_desativado_recebe_401_nas_leituras(vivo):
    marca = sufixo().lower()
    username = f"teste_sess_{marca}"
    senha = secrets.token_urlsafe(18)
    st, u = vivo.x("POST", "/usuarios", {"nome": f"TESTE_SESSAO {marca}", "username": username,
                                         "email": f"{username}@exemplo.com", "role": "leitura", "senha": senha})
    assert st == 200 and u.get("id"), (st, u)
    uid = u["id"]
    try:
        st, r = vivo._enviar("POST", f"{vivo.auth}/login", {"username": username, "password": senha})
        token = (r or {}).get("token")
        assert token, ("login do usuário de teste", st)
        cab = {"Authorization": f"Bearer {token}"}

        antes = {g: vivo._enviar("GET", vivo.app + g, None, cab)[0] for g in GETS}
        assert set(antes.values()) == {200}, antes

        st, _ = vivo.x("POST", f"/usuarios/{uid}/desativar", {})
        assert st == 200, st
        depois = {g: vivo._enviar("GET", vivo.app + g, None, cab)[0] for g in GETS}
        assert set(depois.values()) == {401}, depois
    finally:
        assert vivo.apagar_usuario_teste(uid, username) == 200
        st, lista = vivo.x("GET", "/usuarios")
        assert not [x for x in lista if x["id"] == uid]

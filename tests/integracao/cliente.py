"""Cliente dos testes de integração: Xano real e Metadata API (limpeza de usuários de teste).

Regras (não mudar sem aprovação do usuário):
- só cria provedores e projetos com prefixo TESTE_ e apaga tudo ao final;
- nunca sincroniza, desativa ou apaga o provedor de produção nem qualquer outro que não seja TESTE_;
- credenciais vêm do `.env` (ou do ambiente) e nunca são impressas.
"""

from __future__ import annotations

import os
import random
import shutil
import string
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
from dotenv import dotenv_values

RAIZ = Path(__file__).resolve().parents[2]
# Identificador fictício da conta dos provedores TESTE_ (nunca conecta a nenhuma AWS).
CONTA_TESTE = "000000000000"
PAUSA_XANO = 2.1  # plano Free: 10 requisições a cada 20 s
PREFIXO = "TESTE_"


def env() -> dict[str, str]:
    valores = {k: v for k, v in dotenv_values(RAIZ / ".env").items() if v is not None}
    valores.update({k: v for k, v in os.environ.items() if k.startswith(("XANO_", "COSTGUARD_"))})
    return valores


def sufixo() -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


class Vivo:
    def __init__(self):
        self.env = env()
        faltam = [k for k in ("XANO_BASE_URL", "XANO_APP_BASE_URL", "XANO_E2E_USER", "XANO_E2E_PASS")
                  if not self.env.get(k)]
        if faltam:
            raise RuntimeError("Variáveis ausentes: " + ", ".join(faltam))
        self.auth = self.env["XANO_BASE_URL"].rstrip("/")
        self.app = self.env["XANO_APP_BASE_URL"].rstrip("/")
        self.http = httpx.Client(timeout=180, headers={"User-Agent": "costguard-teste"})
        self._tokens: dict[str, str] = {}
        self._ultima = 0.0

    # --- Xano ---

    def _pausar(self) -> None:
        espera = PAUSA_XANO - (time.monotonic() - self._ultima)
        if espera > 0:
            time.sleep(espera)
        self._ultima = time.monotonic()

    def _enviar(self, metodo: str, url: str, corpo: Any = None, cab: dict | None = None) -> tuple[int, Any]:
        for tentativa in range(4):
            self._pausar()
            r = self.http.request(metodo, url, json=corpo, headers=cab)
            if r.status_code != 429:
                break
            time.sleep(5 * (tentativa + 1))
        try:
            return r.status_code, r.json()
        except ValueError:
            return r.status_code, None

    def login(self, papel: str = "admin") -> tuple[int, Any]:
        """(status, corpo) do login, sem guardar nada além do token."""
        usuario, senha = (("XANO_E2E_USER", "XANO_E2E_PASS") if papel == "admin"
                          else ("XANO_E2E_LEITURA_USER", "XANO_E2E_LEITURA_PASS"))
        return self._enviar("POST", f"{self.auth}/login",
                            {"username": self.env.get(usuario, ""), "password": self.env.get(senha, "")})

    def token(self, papel: str = "admin") -> str:
        if papel not in self._tokens:
            _, corpo = self.login(papel)
            self._tokens[papel] = (corpo or {}).get("token") or "" if isinstance(corpo, dict) else ""
        return self._tokens[papel]

    def x(self, metodo: str, caminho: str, corpo: Any = None, papel: str = "admin") -> tuple[int, Any]:
        return self._enviar(metodo, self.app + caminho, corpo, {"Authorization": f"Bearer {self.token(papel)}"})

    # --- provedor TESTE_ ---

    def criar_provedor_teste(self, rotulo: str) -> int:
        """Cria um provedor TESTE_ com credencial fictícia. Fica "pendente": o teste não conecta à AWS."""
        apelido = f"{PREFIXO}{rotulo}_{sufixo()}"
        st, pv = self.x("POST", "/provedores", {
            "apelido": apelido, "tipo": "aws", "identificador_conta": CONTA_TESTE,
            "aws_access_key_id": "AKIAIOSFODNN7EXAMPLE", "aws_secret_access_key": "segredo-ficticio-de-teste",
            "tag_alocacao_projeto": "PRJ",
        })
        assert st == 200 and pv["apelido"] == apelido, (st, pv)
        return pv["id"]

    def provedor(self, pid: int) -> dict:
        st, lista = self.x("GET", "/provedores")
        assert st == 200
        return next(p for p in lista if p["id"] == pid)

    def apagar_provedor_teste(self, pid: int) -> tuple[int, Any]:
        return self.x("POST", f"/provedores/{pid}/excluir-teste", {})

    # --- Metadata API (credencial do perfil do Xano CLI) ---

    def _instancia(self) -> str:
        """Origem (esquema + host) da instância Xano: XANO_INSTANCIA ou derivada de XANO_BASE_URL.

        Não há valor padrão no código: sem nenhuma das duas variáveis, o teste falha sem imprimir valores.
        """
        explicita = (self.env.get("XANO_INSTANCIA") or "").strip().rstrip("/")
        if explicita:
            return explicita
        partes = urlsplit(self.env.get("XANO_BASE_URL", ""))
        if not partes.scheme or not partes.netloc:
            raise RuntimeError("Instância Xano indefinida: defina XANO_INSTANCIA ou XANO_BASE_URL no .env")
        return f"{partes.scheme}://{partes.netloc}"

    def _meta(self, tabela: str) -> tuple[str, dict]:
        cli = shutil.which("xano")
        if not cli:
            raise RuntimeError("Xano CLI não encontrado")
        token = subprocess.run([cli, "profile", "token"], capture_output=True, text=True, check=True).stdout.strip()
        instancia = self._instancia()
        workspace = (self.env.get("XANO_WORKSPACE") or "").strip()
        if not workspace:
            raise RuntimeError("Workspace Xano indefinido: defina XANO_WORKSPACE no .env")
        base = f"{instancia}/api:meta/workspace/{workspace}"
        cab = {"Authorization": f"Bearer {token}"}
        tabelas = self.http.get(f"{base}/table", headers=cab, params={"per_page": 200}).json()
        tid = next(t["id"] for t in tabelas["items"] if t["name"] == tabela)
        return f"{base}/table/{tid}/content", cab

    def apagar_usuario_teste(self, usuario_id: int, username: str) -> int:
        """Remove a linha de um usuário criado pelo teste (não há endpoint de exclusão de usuário)."""
        assert username.startswith("teste_"), username
        url, cab = self._meta("usuarios")
        linha = self.http.get(f"{url}/{usuario_id}", headers=cab).json()
        assert linha.get("username") == username, "a linha não é o usuário de teste"
        return self.http.delete(f"{url}/{usuario_id}", headers=cab).status_code

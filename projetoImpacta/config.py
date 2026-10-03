"""Configuração de runtime do frontend CostGuard.

A URL base do backend Xano é lida de variável de ambiente para não versionar
configuração de ambiente no código-fonte. Nenhum segredo é armazenado aqui:
o token de autenticação é um dado de runtime do usuário, não um segredo de build.
"""

import os

# URL base do grupo de APIs de autenticação do Xano (ex.: a base do api_group "auth").
# Definir via variável de ambiente XANO_BASE_URL (ver .env.example).
# Sem valor padrão embutido para evitar fixar um endpoint no código versionado.
XANO_BASE_URL: str = os.getenv("XANO_BASE_URL", "").rstrip("/")


def get_xano_base_url() -> str:
    """Retorna a URL base do Xano, validando que foi configurada."""
    if not XANO_BASE_URL:
        raise RuntimeError(
            "XANO_BASE_URL não configurada. Defina a variável de ambiente "
            "XANO_BASE_URL (ver .env.example) com a base do api_group de "
            "autenticação do Xano."
        )
    return XANO_BASE_URL

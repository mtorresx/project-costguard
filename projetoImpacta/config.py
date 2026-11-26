"""Configuração de runtime do frontend CostGuard.

As URLs base do backend Xano são lidas de variáveis de ambiente para não
versionar configuração de ambiente no código-fonte. Nenhum segredo é
armazenado aqui: o token de autenticação é um dado de runtime do usuário.

No Xano, cada api_group tem um `canonical` próprio e, portanto, uma base de URL
distinta. O CostGuard usa dois grupos:
- `auth` (login, me)         -> XANO_BASE_URL
- `app`  (projetos, negócio) -> XANO_APP_BASE_URL
"""

import os

# Base do api_group de autenticação ("auth"): login, me.
XANO_BASE_URL: str = os.getenv("XANO_BASE_URL", "").rstrip("/")

# Base do api_group de negócio ("app"): projetos e demais recursos autenticados.
XANO_APP_BASE_URL: str = os.getenv("XANO_APP_BASE_URL", "").rstrip("/")


# Destino dos links da área do app (login) que levam à landing. Lida na compilação
# do frontend. Em produção a landing e o app ficam em origens diferentes
# (costguard.com.br e app.costguard.com.br), então o valor é a URL absoluta da
# landing e a navegação deve ser de documento. Ausente, vazia ou só com espaços:
# "/" (desenvolvimento local, navegação interna do cliente como sempre foi).
URL_LANDING: str = os.getenv("COSTGUARD_LANDING_URL", "").strip() or "/"


def get_xano_base_url() -> str:
    """Retorna a base do api_group de autenticação, validando que foi configurada."""
    if not XANO_BASE_URL:
        raise RuntimeError(
            "XANO_BASE_URL não configurada. Defina a variável de ambiente "
            "XANO_BASE_URL (ver .env.example) com a base do api_group de "
            "autenticação do Xano."
        )
    return XANO_BASE_URL


def get_xano_app_base_url() -> str:
    """Retorna a base do api_group de negócio ("app"), validando que foi configurada."""
    if not XANO_APP_BASE_URL:
        raise RuntimeError(
            "XANO_APP_BASE_URL não configurada. Defina a variável de ambiente "
            "XANO_APP_BASE_URL (ver .env.example) com a base do api_group 'app' "
            "do Xano (projetos)."
        )
    return XANO_APP_BASE_URL

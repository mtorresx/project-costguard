"""Formatação de valores exibidos no CostGuard."""

from decimal import Decimal
import re


def numero_br(valor: float | Decimal, casas: int = 2) -> str:
    return f"{valor:,.{casas}f}".translate(str.maketrans(",.", ".,"))


def formatar_valor(valor: float, moeda: str) -> str:
    prefixo = "US$" if moeda == "USD" else moeda
    sinal = "-" if valor < 0 else ""
    return f"{sinal}{prefixo} {numero_br(abs(valor))}"


def percentual_br(valor: float) -> str:
    return f"{numero_br(valor, 1)}%"


def mascarar_orcamento(texto: str) -> str:
    digitos = re.sub(r"[^0-9]", "", texto)
    if not digitos:
        return ""
    centavos = digitos.zfill(3)
    sinal = "-" if texto.lstrip().startswith("-") else ""
    return numero_br(Decimal(f"{sinal}{centavos[:-2]}.{centavos[-2:]}"))


def ler_orcamento(texto: str) -> float:
    return float(texto.replace(".", "").replace(",", "."))


def mascarar_conta_aws(conta: str) -> str:
    return f"•••• •••• {conta[-4:]}" if re.fullmatch(r"[0-9]{12}", conta) else "—"

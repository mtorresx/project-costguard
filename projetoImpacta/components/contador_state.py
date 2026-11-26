"""Contador de alertas abertos exibido no shell (topo e menu).

Não faz chamada própria ao backend (limite de requisições do plano Xano): é
atualizado pelas páginas que já leem `GET /alertas` (home e /alertas).
"""

import reflex as rx


class ContadorAlertasState(rx.State):
    carregado: bool = False
    abertos: int = 0
    criticos: int = 0

    def atualizar(self, abertos: int, criticos: int) -> None:
        self.carregado = True
        self.abertos = abertos
        self.criticos = criticos

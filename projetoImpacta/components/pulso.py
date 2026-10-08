"""Ponto pulsante em Python puro: keyframes do emotion via `Var`. Sem arquivo CSS."""

from reflex.components.el import elements
from reflex.utils.imports import ImportVar
from reflex.vars.base import LiteralVar, Var

_PULSO = Var(
    r"keyframes({ '0%, 100%': { opacity: 1, boxShadow: '0 0 0 0 rgba(45, 212, 191, 0.55)' }, "
    r"'50%': { opacity: 0.55, boxShadow: '0 0 0 6px rgba(45, 212, 191, 0)' } })"
).to(str)


class PontoPulsante(elements.Div):
    """`div` com a animação de pulso (opacidade + halo verde-água) em loop."""

    def add_imports(self):
        return {"@emotion/react": [ImportVar(tag="keyframes")]}

    @classmethod
    def create(cls, *children, **props):
        return super().create(
            *children,
            animation=LiteralVar.create(f"{_PULSO} 2s ease-in-out infinite"),
            **props,
        )


ponto_pulsante = PontoPulsante.create

"""Explicit LIFO stack used by the undo subsystem."""

from __future__ import annotations

from typing import Generic, TypeVar

T = TypeVar("T")


class Pila(Generic[T]):
    """Simple own stack; append and pop at the end are O(1) amortized."""

    def __init__(self) -> None:
        self._elementos: list[T] = []

    def apilar(self, elemento: T) -> None:
        self._elementos.append(elemento)

    def desapilar(self) -> T:
        if self.esta_vacia():
            raise IndexError("No se puede desapilar una pila vacia.")
        return self._elementos.pop()

    def cima(self) -> T:
        if self.esta_vacia():
            raise IndexError("La pila esta vacia.")
        return self._elementos[-1]

    def esta_vacia(self) -> bool:
        return not self._elementos

    def __len__(self) -> int:
        return len(self._elementos)

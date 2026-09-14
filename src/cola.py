"""Explicit FIFO queue for pending reports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Iterator, Optional, TypeVar

T = TypeVar("T")


@dataclass
class _NodoCola(Generic[T]):
    valor: T
    siguiente: Optional["_NodoCola[T]"] = None


class Cola(Generic[T]):
    """Linked FIFO queue with O(1) enqueue and dequeue operations."""

    def __init__(self) -> None:
        self._frente: Optional[_NodoCola[T]] = None
        self._final: Optional[_NodoCola[T]] = None
        self._tamano = 0

    def encolar(self, elemento: T) -> None:
        nuevo = _NodoCola(elemento)
        if self._final is None:
            self._frente = nuevo
        else:
            self._final.siguiente = nuevo
        self._final = nuevo
        self._tamano += 1

    def desencolar(self) -> T:
        if self._frente is None:
            raise IndexError("No se puede desencolar una cola vacia.")
        nodo = self._frente
        self._frente = nodo.siguiente
        self._tamano -= 1
        if self._frente is None:
            self._final = None
        return nodo.valor

    def frente(self) -> T:
        if self._frente is None:
            raise IndexError("La cola esta vacia.")
        return self._frente.valor

    def esta_vacia(self) -> bool:
        return self._frente is None

    def __len__(self) -> int:
        return self._tamano

    def __iter__(self) -> Iterator[T]:
        actual = self._frente
        while actual is not None:
            yield actual.valor
            actual = actual.siguiente

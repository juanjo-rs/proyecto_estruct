"""Nodes used by the hand-built binary search trees."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .dominio import Evento


@dataclass
class NodoArbol:
    """A mutable binary-tree node; height is -1 for a missing child."""

    evento: Evento
    izquierda: Optional["NodoArbol"] = None
    derecha: Optional["NodoArbol"] = None
    altura: int = 0

    def es_hoja(self) -> bool:
        return self.izquierda is None and self.derecha is None

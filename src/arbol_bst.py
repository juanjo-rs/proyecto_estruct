"""Unbalanced comparison BST using the same SismoLab key."""

from __future__ import annotations

from typing import Optional

from .dominio import Evento
from .nodo import NodoArbol


class ArbolBST:
    """Reference tree used only to compare against the AVL."""

    def __init__(self) -> None:
        self.raiz: Optional[NodoArbol] = None

    def insertar(self, evento: Evento) -> None:
        if self.raiz is None:
            self.raiz = NodoArbol(evento)
            return
        actual = self.raiz
        while True:
            if evento.clave() < actual.evento.clave():
                if actual.izquierda is None:
                    actual.izquierda = NodoArbol(evento)
                    return
                actual = actual.izquierda
            elif evento.clave() > actual.evento.clave():
                if actual.derecha is None:
                    actual.derecha = NodoArbol(evento)
                    return
                actual = actual.derecha
            else:
                raise ValueError("No se permiten claves repetidas en el BST.")

    def altura(self) -> int:
        def calcular(nodo: Optional[NodoArbol]) -> int:
            if nodo is None:
                return -1
            return 1 + max(calcular(nodo.izquierda), calcular(nodo.derecha))

        return calcular(self.raiz)

    def buscar_clave(self, clave: tuple[int, object, int]) -> tuple[Optional[Evento], int]:
        actual = self.raiz
        examinados = 0
        while actual is not None:
            examinados += 1
            if clave == actual.evento.clave():
                return actual.evento, examinados
            actual = actual.izquierda if clave < actual.evento.clave() else actual.derecha
        return None, examinados

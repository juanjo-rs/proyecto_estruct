"""Unbalanced comparison BST using the same SismoLab key."""

from __future__ import annotations

from typing import Optional,Generator

from .dominio import Evento
from .nodo import NodoArbol

Clave = tuple[int, object, int]


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

    def inorden(self, descendente: bool = False) -> Generator[Evento, None, None]:
        def recorrer(nodo: Optional[NodoArbol]) -> Generator[Evento, None, None]:
            if nodo is not None:
                primero, segundo = (nodo.derecha, nodo.izquierda) if descendente else (nodo.izquierda, nodo.derecha)
                yield from recorrer(primero)
                yield nodo.evento
                yield from recorrer(segundo)

        yield from recorrer(self.raiz)
   

    def altura(self) -> int:
        def calcular(nodo: Optional[NodoArbol]) -> int:
            if nodo is None:
                return -1
            return 1 + max(calcular(nodo.izquierda), calcular(nodo.derecha))

        return calcular(self.raiz)

    def buscar_clave(self, clave: Clave) -> tuple[Optional[Evento], int]:
        actual = self.raiz
        examinados = 0
        while actual is not None:
            examinados += 1
            if clave == actual.evento.clave():
                return actual.evento, examinados
            actual = actual.izquierda if clave < actual.evento.clave() else actual.derecha
        return None, examinados

    def eliminar(self, clave: Clave) -> Evento:
        """Remove exactly the node whose key is supplied."""
        eliminado: list[Evento] = []
        self.raiz = self._eliminar(self.raiz, clave, eliminado)
        if not eliminado:
            raise KeyError(f"No existe la clave {clave}.")
        return eliminado[0]

    def _eliminar(
        # Delete by key using the classic 0/1/2-child BST cases (no rotations)

        self, nodo: Optional[NodoArbol], clave: Clave,eliminado: list[Evento]
    ) -> Optional[NodoArbol]:
        if nodo is None:
            return None
        if clave < nodo.evento.clave():
            nodo.izquierda = self._eliminar(nodo.izquierda, clave, eliminado)
        elif clave > nodo.evento.clave():
            nodo.derecha = self._eliminar(nodo.derecha, clave, eliminado)
        else:
            eliminado.append(nodo.evento)
            if nodo.izquierda is None:
                return nodo.derecha
            if nodo.derecha is None:
                return nodo.izquierda
            sucesor = self._minimo(nodo.derecha)
            nodo.evento = sucesor.evento
            nodo.derecha = self._eliminar_sucesor(nodo.derecha, sucesor.evento.clave())
        return nodo
  
    def _eliminar_sucesor(
        self, nodo: Optional[NodoArbol], clave: Clave
    ) -> Optional[NodoArbol]:
        if nodo is None:
            return None
        if clave < nodo.evento.clave():
            nodo.izquierda = self._eliminar_sucesor(nodo.izquierda, clave)
        elif clave > nodo.evento.clave():
            nodo.derecha = self._eliminar_sucesor(nodo.derecha, clave)
        else:
            return nodo.derecha if nodo.izquierda is None else nodo.izquierda
        return nodo

    @staticmethod
    def _minimo(nodo: NodoArbol) -> NodoArbol:
        while nodo.izquierda is not None:
            nodo = nodo.izquierda
        return nodo

    def cantidad_hojas(self) -> int:
        def contar(nodo: Optional[NodoArbol]) -> int:
            if nodo is None:
                return 0
            if nodo.izquierda is None and nodo.derecha is None:
                return 1
            return contar(nodo.izquierda) + contar(nodo.derecha)

        return contar(self.raiz)

    def profundidad_maxima(self) -> int:
        """Return the maximum depth from root to any leaf node."""
        def calcular_profundidad(nodo: Optional[NodoArbol], profundidad_actual: int) -> int:
            if nodo is None:
                return profundidad_actual - 1
            if nodo.izquierda is None and nodo.derecha is None:
                return profundidad_actual
            return max(
                calcular_profundidad(nodo.izquierda, profundidad_actual + 1),
                calcular_profundidad(nodo.derecha, profundidad_actual + 1),
            )

        return calcular_profundidad(self.raiz, 0) if self.raiz else -1
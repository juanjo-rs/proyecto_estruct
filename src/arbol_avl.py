"""AVL implementation with the exact key order required by SismoLab."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generator, Optional

from .dominio import Evento
from .nodo import NodoArbol

Clave = tuple[int, object, int]


@dataclass
class ResultadoAuditoria:
    orden_correcto: bool
    alturas_correctas: bool
    balanceado: bool
    errores: list[str]


class ArbolAVL:
    """A hand-built AVL; no ordered collection is used for its operations."""

    def __init__(self) -> None:
        self.raiz: Optional[NodoArbol] = None
        self.giros_izquierda = 0
        self.giros_derecha = 0
        self.casos_ll = 0
        self.casos_rr = 0
        self.casos_lr = 0
        self.casos_rl = 0

    @staticmethod
    def _altura(nodo: Optional[NodoArbol]) -> int:
        return -1 if nodo is None else nodo.altura

    @classmethod
    def _actualizar_altura(cls, nodo: NodoArbol) -> None:
        nodo.altura = 1 + max(cls._altura(nodo.izquierda), cls._altura(nodo.derecha))

    @classmethod
    def _factor(cls, nodo: Optional[NodoArbol]) -> int:
        if nodo is None:
            return 0
        return cls._altura(nodo.izquierda) - cls._altura(nodo.derecha)

    def _girar_izquierda(self, raiz: NodoArbol) -> NodoArbol:
        pivote = raiz.derecha
        if pivote is None:
            return raiz
        raiz.derecha = pivote.izquierda
        pivote.izquierda = raiz
        self._actualizar_altura(raiz)
        self._actualizar_altura(pivote)
        self.giros_izquierda += 1
        return pivote

    def _girar_derecha(self, raiz: NodoArbol) -> NodoArbol:
        pivote = raiz.izquierda
        if pivote is None:
            return raiz
        raiz.izquierda = pivote.derecha
        pivote.derecha = raiz
        self._actualizar_altura(raiz)
        self._actualizar_altura(pivote)
        self.giros_derecha += 1
        return pivote

    def _rebalancear(self, nodo: NodoArbol) -> NodoArbol:
        """Rebalance one root, also valid when its imbalance exceeds two."""
        self._actualizar_altura(nodo)
        factor = self._factor(nodo)
        if factor > 1:
            if self._factor(nodo.izquierda) < 0:
                self.casos_lr += 1
                nodo.izquierda = self._girar_izquierda(nodo.izquierda)  # type: ignore[arg-type]
            else:
                self.casos_ll += 1
            return self._girar_derecha(nodo)
        if factor < -1:
            if self._factor(nodo.derecha) > 0:
                self.casos_rl += 1
                nodo.derecha = self._girar_derecha(nodo.derecha)  # type: ignore[arg-type]
            else:
                self.casos_rr += 1
            return self._girar_izquierda(nodo)
        return nodo

    def insertar(self, evento: Evento, balancear: bool = True) -> None:
        """Insert an event by (priority, magnitude, id)."""
        self.raiz = self._insertar(self.raiz, evento, balancear)

    def _insertar(self, nodo: Optional[NodoArbol], evento: Evento, balancear: bool) -> NodoArbol:
        if nodo is None:
            return NodoArbol(evento)
        if evento.clave() < nodo.evento.clave():
            nodo.izquierda = self._insertar(nodo.izquierda, evento, balancear)
        elif evento.clave() > nodo.evento.clave():
            nodo.derecha = self._insertar(nodo.derecha, evento, balancear)
        else:
            raise ValueError("No se permiten claves repetidas en el AVL.")
        self._actualizar_altura(nodo)
        return self._rebalancear(nodo) if balancear else nodo

    def buscar_clave(self, clave: Clave) -> tuple[Optional[Evento], int]:
        """Return event and visited-node count for a key search."""
        actual = self.raiz
        examinados = 0
        while actual is not None:
            examinados += 1
            if clave == actual.evento.clave():
                return actual.evento, examinados
            actual = actual.izquierda if clave < actual.evento.clave() else actual.derecha
        return None, examinados

    def eliminar(self, clave: Clave, balancear: bool = True) -> Evento:
        """Remove exactly the node whose key is supplied."""
        eliminado: list[Evento] = []
        self.raiz = self._eliminar(self.raiz, clave, balancear, eliminado)
        if not eliminado:
            raise KeyError(f"No existe la clave {clave}.")
        return eliminado[0]

    def _eliminar(
        self, nodo: Optional[NodoArbol], clave: Clave, balancear: bool, eliminado: list[Evento]
    ) -> Optional[NodoArbol]:
        if nodo is None:
            return None
        if clave < nodo.evento.clave():
            nodo.izquierda = self._eliminar(nodo.izquierda, clave, balancear, eliminado)
        elif clave > nodo.evento.clave():
            nodo.derecha = self._eliminar(nodo.derecha, clave, balancear, eliminado)
        else:
            eliminado.append(nodo.evento)
            if nodo.izquierda is None:
                return nodo.derecha
            if nodo.derecha is None:
                return nodo.izquierda
            sucesor = self._minimo(nodo.derecha)
            nodo.evento = sucesor.evento
            nodo.derecha = self._eliminar_sucesor(nodo.derecha, sucesor.evento.clave(), balancear)
        self._actualizar_altura(nodo)
        return self._rebalancear(nodo) if balancear else nodo

    def _eliminar_sucesor(
        self, nodo: Optional[NodoArbol], clave: Clave, balancear: bool
    ) -> Optional[NodoArbol]:
        if nodo is None:
            return None
        if clave < nodo.evento.clave():
            nodo.izquierda = self._eliminar_sucesor(nodo.izquierda, clave, balancear)
        elif clave > nodo.evento.clave():
            nodo.derecha = self._eliminar_sucesor(nodo.derecha, clave, balancear)
        else:
            return nodo.derecha if nodo.izquierda is None else nodo.izquierda
        self._actualizar_altura(nodo)
        return self._rebalancear(nodo) if balancear else nodo

    @staticmethod
    def _minimo(nodo: NodoArbol) -> NodoArbol:
        while nodo.izquierda is not None:
            nodo = nodo.izquierda
        return nodo

    def inorden(self, descendente: bool = False) -> Generator[Evento, None, None]:
        def recorrer(nodo: Optional[NodoArbol]) -> Generator[Evento, None, None]:
            if nodo is not None:
                primero, segundo = (nodo.derecha, nodo.izquierda) if descendente else (nodo.izquierda, nodo.derecha)
                yield from recorrer(primero)
                yield nodo.evento
                yield from recorrer(segundo)

        yield from recorrer(self.raiz)

    def preorden(self) -> Generator[Evento, None, None]:
        def recorrer(nodo: Optional[NodoArbol]) -> Generator[Evento, None, None]:
            if nodo is not None:
                yield nodo.evento
                yield from recorrer(nodo.izquierda)
                yield from recorrer(nodo.derecha)

        yield from recorrer(self.raiz)

    def por_niveles(self) -> Generator[Evento, None, None]:
        """Breadth-first traversal using an explicit local list of pending nodes."""
        pendientes: list[NodoArbol] = [] if self.raiz is None else [self.raiz]
        indice = 0
        while indice < len(pendientes):
            nodo = pendientes[indice]
            indice += 1
            yield nodo.evento
            if nodo.izquierda is not None:
                pendientes.append(nodo.izquierda)
            if nodo.derecha is not None:
                pendientes.append(nodo.derecha)

    def cantidad_hojas(self) -> int:
        return sum(1 for evento in self._nodos() if evento.es_hoja())

    def _nodos(self) -> Generator[NodoArbol, None, None]:
        def recorrer(nodo: Optional[NodoArbol]) -> Generator[NodoArbol, None, None]:
            if nodo is not None:
                yield nodo
                yield from recorrer(nodo.izquierda)
                yield from recorrer(nodo.derecha)

        yield from recorrer(self.raiz)

    def recuperar_balance(self) -> int:
        """Repair a stress-mode tree with rotations, never by rebuilding from a list."""
        giros_iniciales = self.giros_izquierda + self.giros_derecha
        limite = max(1, sum(1 for _ in self._nodos()) ** 2)
        for _ in range(limite):
            self.raiz = self._reparar_pasada(self.raiz)
            if self.auditar().balanceado:
                return self.giros_izquierda + self.giros_derecha - giros_iniciales
        raise RuntimeError("La recuperacion no termino dentro del limite de seguridad.")

    def _reparar_pasada(self, nodo: Optional[NodoArbol]) -> Optional[NodoArbol]:
        if nodo is None:
            return None
        nodo.izquierda = self._reparar_pasada(nodo.izquierda)
        nodo.derecha = self._reparar_pasada(nodo.derecha)
        self._actualizar_altura(nodo)
        return self._rebalancear(nodo)

    def auditar(self) -> ResultadoAuditoria:
        """Check global BST order, stored heights, and AVL factors."""
        errores: list[str] = []

        def revisar(nodo: Optional[NodoArbol], minimo: Optional[Clave], maximo: Optional[Clave]) -> int:
            if nodo is None:
                return -1
            clave = nodo.evento.clave()
            if (minimo is not None and clave <= minimo) or (maximo is not None and clave >= maximo):
                errores.append(f"Orden BST invalido en SIS-{nodo.evento.identificador:06d}.")
            izquierda = revisar(nodo.izquierda, minimo, clave)
            derecha = revisar(nodo.derecha, clave, maximo)
            esperada = 1 + max(izquierda, derecha)
            if nodo.altura != esperada:
                errores.append(f"Altura almacenada invalida en SIS-{nodo.evento.identificador:06d}.")
            if abs(izquierda - derecha) > 1:
                errores.append(f"Desbalance AVL en SIS-{nodo.evento.identificador:06d}.")
            return esperada

        revisar(self.raiz, None, None)
        return ResultadoAuditoria(
            orden_correcto=not any(error.startswith("Orden") for error in errores),
            alturas_correctas=not any(error.startswith("Altura") for error in errores),
            balanceado=not any(error.startswith("Desbalance") for error in errores),
            errores=errores,
        )

"""Test for E2: Tree view API and data integrity."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest import TestCase

from interfaz import SEPARACION_X_NODO, SEPARACION_Y_NODO, posiciones_arbol
from src.catalogo import CatalogoSismico
from src.dominio import Evento, VistaNodo, Zona


RELOJ = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)


def evento(identificador: int, magnitud: float = 4.5) -> Evento:
    """Create a minimal Evento object."""
    return Evento(
        identificador=identificador,
        magnitud=magnitud,
        profundidad_hipocentro=30.0,
        x=100.0,
        y=100.0,
        ocurrencia="2026-09-07T10:00:00Z",
        revision=1,
        estaciones={"EST-01"},
    )


class TestVistaArbol(TestCase):
    """Test the immutable tree view API (E2 requirement)."""

    def test_vista_arbol_vacio(self) -> None:
        """Test that empty trees return empty views."""
        zonas = [Zona("Ciudad", 0, 500, 0, 500, True)]
        catalogo = CatalogoSismico(zonas, RELOJ)

        vista_avl, raiz_avl = catalogo.obtener_vista_arbol("avl")
        vista_bst, raiz_bst = catalogo.obtener_vista_arbol("bst")

        self.assertEqual(vista_avl, {})
        self.assertIsNone(raiz_avl)
        self.assertEqual(vista_bst, {})
        self.assertIsNone(raiz_bst)

    def test_vista_arbol_un_nodo(self) -> None:
        """Test that a single node tree returns correct view."""
        zonas = [Zona("Ciudad", 0, 500, 0, 500, True)]
        catalogo = CatalogoSismico(zonas, RELOJ)

        catalogo.crear_evento(evento(10, magnitud=5.0))

        vista_avl, raiz_avl = catalogo.obtener_vista_arbol("avl")
        vista_bst, raiz_bst = catalogo.obtener_vista_arbol("bst")

        # Verify AVL view
        self.assertEqual(raiz_avl, 10)
        self.assertIn(10, vista_avl)
        nodo_avl = vista_avl[10]
        self.assertIsInstance(nodo_avl, VistaNodo)
        self.assertEqual(nodo_avl.id, 10)
        self.assertEqual(nodo_avl.clave, catalogo.indice_activos[10].clave())
        self.assertIsNone(nodo_avl.izquierdo_id)
        self.assertIsNone(nodo_avl.derecho_id)
        self.assertEqual(nodo_avl.altura, 0)
        self.assertIsNotNone(nodo_avl.factor)  # AVL has factor
        self.assertEqual(nodo_avl.factor, 0)

        # Verify BST view
        self.assertEqual(raiz_bst, 10)
        self.assertIn(10, vista_bst)
        nodo_bst = vista_bst[10]
        self.assertIsInstance(nodo_bst, VistaNodo)
        self.assertEqual(nodo_bst.id, 10)
        self.assertEqual(nodo_bst.clave, catalogo.indice_activos[10].clave())
        self.assertIsNone(nodo_bst.izquierdo_id)
        self.assertIsNone(nodo_bst.derecho_id)
        self.assertEqual(nodo_bst.altura, 0)
        self.assertIsNone(nodo_bst.factor)  # BST has no factor

    def test_vista_arbol_multiple_nodos(self) -> None:
        """Test that a multi-node tree returns correct view with structure."""
        zonas = [Zona("Ciudad", 0, 500, 0, 500, True)]
        catalogo = CatalogoSismico(zonas, RELOJ)

        # Create multiple events
        for eid in (30, 20, 10, 40, 50):
            catalogo.crear_evento(evento(eid))

        vista_avl, raiz_avl = catalogo.obtener_vista_arbol("avl")

        # Verify all nodes are present
        self.assertEqual(len(vista_avl), 5)
        for eid in (10, 20, 30, 40, 50):
            self.assertIn(eid, vista_avl)

        # Verify structure (children IDs are correct)
        for nodo_id, nodo_vista in vista_avl.items():
            self.assertIsInstance(nodo_vista, VistaNodo)
            self.assertEqual(nodo_vista.id, nodo_id)
            # Verify that child IDs are either None or valid node IDs
            if nodo_vista.izquierdo_id is not None:
                self.assertIn(nodo_vista.izquierdo_id, vista_avl)
            if nodo_vista.derecho_id is not None:
                self.assertIn(nodo_vista.derecho_id, vista_avl)

    def test_vista_arbol_tipo_invalido(self) -> None:
        """Test that invalid tree type raises ValueError."""
        zonas = [Zona("Ciudad", 0, 500, 0, 500, True)]
        catalogo = CatalogoSismico(zonas, RELOJ)

        with self.assertRaises(ValueError) as context:
            catalogo.obtener_vista_arbol("invalido")
        self.assertIn("avl", str(context.exception).lower())
        self.assertIn("bst", str(context.exception).lower())

    def test_vista_arbol_inmutable(self) -> None:
        """Test that the view is immutable and does not expose NodoArbol."""
        zonas = [Zona("Ciudad", 0, 500, 0, 500, True)]
        catalogo = CatalogoSismico(zonas, RELOJ)

        catalogo.crear_evento(evento(10, magnitud=5.0))

        vista_avl, raiz_avl = catalogo.obtener_vista_arbol("avl")

        # VistaNodo is frozen (immutable)
        nodo = vista_avl[10]
        self.assertTrue(hasattr(nodo, "__dataclass_fields__"))

        # Verify that the view does not contain NodoArbol attributes
        self.assertFalse(hasattr(nodo, "izquierda"))
        self.assertFalse(hasattr(nodo, "derecha"))
        self.assertFalse(hasattr(nodo, "evento"))

        # Verify that modifying the view does not affect the tree
        # (VistaNodo is frozen, so this would raise an error if attempted)
        try:
            nodo.altura = 999
            self.fail("VistaNodo should be immutable (frozen)")
        except (AttributeError, TypeError):
            pass  # Expected for frozen dataclass

    def test_vista_arbol_factor_avl_vs_bst(self) -> None:
        """Test that AVL nodes have factor but BST nodes do not."""
        zonas = [Zona("Ciudad", 0, 500, 0, 500, True)]
        catalogo = CatalogoSismico(zonas, RELOJ)

        catalogo.crear_evento(evento(10, magnitud=5.0))

        vista_avl, _ = catalogo.obtener_vista_arbol("avl")
        vista_bst, _ = catalogo.obtener_vista_arbol("bst")

        # AVL has factor
        self.assertIsNotNone(vista_avl[10].factor)

        # BST has no factor
        self.assertIsNone(vista_bst[10].factor)


def _nodo(identificador: int, izquierdo: int | None, derecho: int | None) -> VistaNodo:
    """A view node used only to check layout, not catalog state."""
    return VistaNodo(
        identificador,
        (1, Decimal("1.0"), identificador),
        izquierdo,
        derecho,
        0,
        None,
    )


class PruebasPosicionesArbol(TestCase):
    def test_cadena_derecha_crece_hacia_abajo(self) -> None:
        """A long right spine keeps a fixed step so the bottom stays reachable by scroll."""
        vista = {
            identificador: _nodo(identificador, None, identificador + 1 if identificador < 12 else None)
            for identificador in range(1, 13)
        }
        posiciones = posiciones_arbol(vista, 1)
        ys = [posiciones[identificador][1] for identificador in range(1, 13)]
        self.assertEqual(ys, sorted(ys))
        self.assertEqual(ys[1] - ys[0], SEPARACION_Y_NODO)
        self.assertGreater(ys[-1] - ys[0], 700)

    def test_nodos_quedan_separados_en_horizontal(self) -> None:
        """Each node owns its own x slot, so a wide balanced tree does not collapse."""
        vista = {
            2: _nodo(2, 1, 3),
            1: _nodo(1, None, None),
            3: _nodo(3, None, 4),
            4: _nodo(4, None, None),
        }
        posiciones = posiciones_arbol(vista, 2)
        xs = sorted(x for x, _y in posiciones.values())
        self.assertEqual(len(xs), len(set(xs)))
        for izquierda, derecha in zip(xs, xs[1:]):
            self.assertGreaterEqual(derecha - izquierda, SEPARACION_X_NODO)

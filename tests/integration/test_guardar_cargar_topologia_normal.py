"""Integration test for D4: Save and load topology in normal mode."""

import json
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from src.catalogo import CatalogoSismico, escribir_json_escenario, leer_json_archivo
from src.dominio import Evento, Zona


RELOJ = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)


def evento(identificador: int, magnitud: float = 4.5, estacion: str = "EST-01") -> Evento:
    """Create a minimal Evento object."""
    return Evento(
        identificador=identificador,
        magnitud=magnitud,
        profundidad_hipocentro=30.0,
        x=100.0,
        y=100.0,
        ocurrencia="2026-09-07T10:00:00Z",
        revision=1,
        estaciones={estacion},
    )


def nodo_avl(eid: int, izquierdo: int | None = None, derecho: int | None = None, altura: int = 0) -> dict:
    """Create an AVL node dict for JSON topology."""
    return {
        "evento": {
            "identificador": eid,
            "magnitud": 4.5,
            "profundidad_hipocentro": 30.0,
            "x": 100.0,
            "y": 100.0,
            "ocurrencia": "2026-09-07T10:00:00Z",
            "revision": 1,
            "estaciones": ["EST-01"],
        },
        "altura": altura,
        "factor": 0,
        "izquierdo": izquierdo,
        "derecho": derecho,
    }


class TestGuardarCargarTopologiaNormal(TestCase):
    """Test saving and loading topology in normal mode (D4 requirement)."""

    def test_guardar_cargar_topologia_normal(self) -> None:
        """
        Save topology in normal mode, create new catalog, load and verify content and topology.
        Demonstrates D4: Carga por topología.
        """
        # Create initial catalog with events in normal mode
        zonas = [Zona("Ciudad", 0, 500, 0, 500, True)]
        catalogo1 = CatalogoSismico(zonas, RELOJ)

        # Add events via insertion to build a balanced tree
        for eid in (30, 20, 10, 40, 50):
            catalogo1.crear_evento(evento(eid))

        # Verify initial state
        self.assertEqual(len(catalogo1.indice_activos), 5)
        self.assertFalse(catalogo1.modo_estres)
        auditoria1 = catalogo1.avl.auditar()
        self.assertTrue(auditoria1.orden_correcto, auditoria1.errores)
        self.assertTrue(auditoria1.balanceado, auditoria1.errores)
        ids_inorden1 = [e.identificador for e in catalogo1.avl.inorden()]
        self.assertEqual(ids_inorden1, [10, 20, 30, 40, 50])

        # Export topology
        datos_exportados = catalogo1.exportar_escenario_completo()

        # Convert to topology format for loading
        datos_carga = {
            "version": 1,
            "tipo_carga": "topologia",
            "reloj": datos_exportados["reloj"],
            "modo": datos_exportados["modo"],
            "zonas": datos_exportados["zonas"],
            "raiz": datos_exportados["avl"]["raiz"],
            "nodos": datos_exportados["avl"]["nodos"],
        }

        # Save to temporary file
        with TemporaryDirectory() as tmpdir:
            ruta = Path(tmpdir) / "topologia_normal.json"
            escribir_json_escenario(datos_carga, str(ruta))

            # Create new catalog
            catalogo2 = CatalogoSismico(zonas, RELOJ)

            # Load topology from file
            datos_leidos = leer_json_archivo(str(ruta))
            # Convert string keys to int for reconstruction
            datos_leidos["nodos"] = {int(k): v for k, v in datos_leidos["nodos"].items()}
            datos_leidos["raiz"] = int(datos_leidos["raiz"]) if datos_leidos["raiz"] is not None else None
            estadisticas = catalogo2.cargar_por_topologia(datos_leidos)

            # Verify statistics
            self.assertIsNotNone(estadisticas)
            # The root ID depends on the AVL structure after insertions
            self.assertIsNotNone(estadisticas["avl"]["raiz_id"])

            # Verify content matches
            self.assertEqual(len(catalogo2.indice_activos), 5)
            self.assertFalse(catalogo2.modo_estres)
            for eid in (10, 20, 30, 40, 50):
                self.assertIn(eid, catalogo2.indice_activos)
                self.assertEqual(catalogo2.indice_activos[eid].magnitud, 4.5)

            # Verify topology matches (order and balance)
            auditoria2 = catalogo2.avl.auditar()
            self.assertTrue(auditoria2.orden_correcto, auditoria2.errores)
            self.assertTrue(auditoria2.balanceado, auditoria2.errores)
            ids_inorden2 = [e.identificador for e in catalogo2.avl.inorden()]
            self.assertEqual(ids_inorden2, [10, 20, 30, 40, 50])

            # Verify BST is also reconstructed correctly
            ids_bst_inorden = [e.identificador for e in catalogo2.bst.inorden()]
            self.assertEqual(ids_bst_inorden, [10, 20, 30, 40, 50])

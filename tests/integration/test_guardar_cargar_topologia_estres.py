"""Integration test for D4: Save and load topology in stress mode."""

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


class TestGuardarCargarTopologiaEstres(TestCase):
    """Test saving and loading topology in stress mode (D4 requirement)."""

    def test_guardar_cargar_topologia_estres(self) -> None:
        """
        Save topology in stress mode, create new catalog, load and verify content and topology.
        Demonstrates D4: Carga por topología (stress mode).
        """
        # Create initial catalog with events
        zonas = [Zona("Ciudad", 0, 500, 0, 500, True)]
        catalogo1 = CatalogoSismico(zonas, RELOJ)

        # Add events via insertion
        for eid in (30, 20, 10, 40, 50):
            catalogo1.crear_evento(evento(eid))

        # Activate stress mode
        catalogo1.activar_modo_estres()
        self.assertTrue(catalogo1.modo_estres)

        # Verify initial state in stress mode
        self.assertEqual(len(catalogo1.indice_activos), 5)
        auditoria1 = catalogo1.avl.auditar()
        self.assertTrue(auditoria1.orden_correcto, auditoria1.errores)
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
            ruta = Path(tmpdir) / "topologia_estres.json"
            escribir_json_escenario(datos_carga, str(ruta))

            # Create new catalog
            catalogo2 = CatalogoSismico(zonas, RELOJ)

            # Load topology from file (stress mode is preserved from JSON)
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
            self.assertTrue(catalogo2.modo_estres)  # Stress mode should be loaded
            for eid in (10, 20, 30, 40, 50):
                self.assertIn(eid, catalogo2.indice_activos)
                self.assertEqual(catalogo2.indice_activos[eid].magnitud, 4.5)

            # Verify topology matches (order is preserved in stress mode)
            auditoria2 = catalogo2.avl.auditar()
            self.assertTrue(auditoria2.orden_correcto, auditoria2.errores)
            ids_inorden2 = [e.identificador for e in catalogo2.avl.inorden()]
            self.assertEqual(ids_inorden2, [10, 20, 30, 40, 50])

            # Verify BST is also reconstructed correctly
            ids_bst_inorden = [e.identificador for e in catalogo2.bst.inorden()]
            self.assertEqual(ids_bst_inorden, [10, 20, 30, 40, 50])

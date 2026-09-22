"""Integration test for D5: Restore version after creating new catalog."""

from datetime import datetime, timezone
from tempfile import TemporaryDirectory
from unittest import TestCase

from src.catalogo import CatalogoSismico
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


class TestRestaurarVersionNuevoCatalogo(TestCase):
    """Test restoring a version after creating a new catalog (D5 requirement)."""

    def test_restaurar_version_nuevo_catalogo(self) -> None:
        """
        Save a version, create a new catalog, restore and verify content and topology.
        Demonstrates D5: Load by Version.
        """
        zonas = [Zona("Ciudad", 0, 500, 0, 500, True)]

        # Create first catalog with events
        catalogo1 = CatalogoSismico(zonas, RELOJ)
        for eid in (30, 20, 10, 40, 50):
            catalogo1.crear_evento(evento(eid))
        catalogo1.parametros["W"] = 4.5
        catalogo1.metricas["correcciones_aceptadas"] = 5

        # Verify initial state
        self.assertEqual(len(catalogo1.indice_activos), 5)
        auditoria1 = catalogo1.avl.auditar()
        self.assertTrue(auditoria1.orden_correcto, auditoria1.errores)
        self.assertTrue(auditoria1.balanceado, auditoria1.errores)
        ids_inorden1 = [e.identificador for e in catalogo1.avl.inorden()]
        self.assertEqual(ids_inorden1, [10, 20, 30, 40, 50])

        # Save version using temporary directory
        with TemporaryDirectory() as tmpdir:
            from pathlib import Path
            import os
            import sys

            # Change to temp directory for version storage
            original_dir = os.getcwd()
            os.chdir(tmpdir)

            try:
                # Save version
                ruta = catalogo1.guardar_version("version_prueba")
                self.assertTrue(Path(ruta).exists())

                # Create new catalog (empty)
                catalogo2 = CatalogoSismico(zonas, RELOJ)
                self.assertEqual(len(catalogo2.indice_activos), 0)
                self.assertIsNone(catalogo2.avl.raiz)

                # Restore version
                catalogo2.restaurar_version("version_prueba")

                # Verify content matches original
                self.assertEqual(len(catalogo2.indice_activos), 5)
                for eid in (10, 20, 30, 40, 50):
                    self.assertIn(eid, catalogo2.indice_activos)
                    self.assertEqual(catalogo2.indice_activos[eid].magnitud, 4.5)

                # Verify parameters and metrics
                self.assertEqual(catalogo2.parametros["W"], 4.5)
                self.assertEqual(catalogo2.metricas["correcciones_aceptadas"], 5)

                # Verify topology matches (order and balance)
                auditoria2 = catalogo2.avl.auditar()
                self.assertTrue(auditoria2.orden_correcto, auditoria2.errores)
                self.assertTrue(auditoria2.balanceado, auditoria2.errores)
                ids_inorden2 = [e.identificador for e in catalogo2.avl.inorden()]
                self.assertEqual(ids_inorden2, [10, 20, 30, 40, 50])

                # Verify BST is also reconstructed correctly
                ids_bst_inorden = [e.identificador for e in catalogo2.bst.inorden()]
                self.assertEqual(ids_bst_inorden, [10, 20, 30, 40, 50])

            finally:
                os.chdir(original_dir)

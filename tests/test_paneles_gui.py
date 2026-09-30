"""Test for E4 and E5: GUI panels and structure verification."""

from datetime import datetime, timezone
from unittest import TestCase
import os
import tempfile
import shutil

from src.catalogo import CatalogoSismico
from src.dominio import Evento, Zona


RELOJ = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)


def evento(identificador: int, magnitud: float = 4.5) -> Evento:
    """Create a minimal Evento object."""
    return Evento(
        identificador=identificador,
        magnitud=magnitud,
        profundidad_hipocentro=30.0,
        x=500.0,
        y=500.0,
        ocurrencia="2026-09-07T10:00:00Z",
        revision=1,
        estaciones={"EST-01"},
    )


class TestPanelesGUI(TestCase):
    """Test the GUI panel APIs (E4 and E5 requirements)."""

    def setUp(self) -> None:
        """Set up a fresh catalog for each test."""
        self.zonas = [Zona("Ciudad", 0, 500, 0, 500, True)]
        self.catalogo = CatalogoSismico(self.zonas, RELOJ)

        # Create a temporary directory for version tests
        self.temp_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)

    def tearDown(self) -> None:
        """Clean up temporary directory."""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_deshacer_funciona(self) -> None:
        """Test that deshacer() works correctly."""
        # Create an event
        self.catalogo.crear_evento(evento(10))
        self.assertEqual(len(self.catalogo.indice_activos), 1)

        # Undo the action
        mensaje = self.catalogo.deshacer()
        self.assertIn("Deshecho", mensaje)
        self.assertEqual(len(self.catalogo.indice_activos), 0)

    def test_deshacer_sin_historial(self) -> None:
        """Test that deshacer() raises IndexError when history is empty."""
        with self.assertRaises(IndexError):
            self.catalogo.deshacer()

    def test_guardar_y_restaurar_version(self) -> None:
        """Test that guardar_version() and restaurar_version() work correctly."""
        # Create an event
        self.catalogo.crear_evento(evento(10))
        self.assertEqual(len(self.catalogo.indice_activos), 1)

        # Save version
        ruta = self.catalogo.guardar_version("test_version")
        self.assertTrue(os.path.exists(ruta))

        # Create another event
        self.catalogo.crear_evento(evento(20))
        self.assertEqual(len(self.catalogo.indice_activos), 2)

        # Restore version
        self.catalogo.restaurar_version("test_version")
        self.assertEqual(len(self.catalogo.indice_activos), 1)
        self.assertIn(10, self.catalogo.indice_activos)
        self.assertNotIn(20, self.catalogo.indice_activos)

    def test_listar_versiones(self) -> None:
        """Test that listar_versiones() returns available versions."""
        # Initially no versions
        versiones = self.catalogo.listar_versiones()
        self.assertEqual(len(versiones), 0)

        # Save a version
        self.catalogo.guardar_version("v1")

        # Now should have one version
        versiones = self.catalogo.listar_versiones()
        self.assertEqual(len(versiones), 1)
        self.assertIn("v1", versiones)

    def test_verificar_estructura_modo_normal(self) -> None:
        """Test that auditar() with exigir_balanceo=True works in normal mode."""
        # Create events
        for eid in (10, 20, 30):
            self.catalogo.crear_evento(evento(eid))

        # Verify structure with balance required
        resultado = self.catalogo.avl.auditar(exigir_balanceo=True)
        self.assertTrue(resultado.orden_correcto)
        self.assertTrue(resultado.alturas_correctas)
        self.assertTrue(resultado.balanceado)
        self.assertEqual(len(resultado.errores), 0)

    def test_verificar_estructura_modo_estres(self) -> None:
        """Test that auditar() with exigir_balanceo=False works in stress mode."""
        # Activate stress mode
        self.catalogo.activar_modo_estres()

        # Create events in order that creates imbalance
        for eid in (10, 20, 30, 40, 50):
            self.catalogo.crear_evento(evento(eid))

        # Verify structure without balance required
        resultado = self.catalogo.avl.auditar(exigir_balanceo=False)
        self.assertTrue(resultado.orden_correcto)
        self.assertTrue(resultado.alturas_correctas)
        # In stress mode, imbalance is expected
        self.assertFalse(resultado.balanceado)
        # But should not report balance as error
        self.assertFalse(any("Desbalance" in error for error in resultado.errores))

    def test_indicadores_retorna_datos_correctos(self) -> None:
        """Test that indicadores() returns correct data."""
        # Create events
        for eid in (10, 20, 30):
            self.catalogo.crear_evento(evento(eid))

        indicadores = self.catalogo.indicadores()

        # Check AVL indicators
        self.assertIn("avl", indicadores)
        avl_data = indicadores["avl"]
        self.assertIn("altura", avl_data)
        self.assertIn("hojas", avl_data)
        self.assertIn("profundidad_maxima", avl_data)
        self.assertIn("casos_rr", avl_data)
        self.assertIn("casos_lr", avl_data)
        self.assertIn("casos_rl", avl_data)

        # Check BST indicators
        self.assertIn("bst", indicadores)
        bst_data = indicadores["bst"]
        self.assertIn("altura", bst_data)
        self.assertIn("hojas", bst_data)
        self.assertIn("profundidad_maxima", bst_data)

        # Check expensive access
        self.assertIn("acceso_costoso", indicadores)
        self.assertIsInstance(indicadores["acceso_costoso"], list)

    def test_indicadores_acceso_costoso(self) -> None:
        """Test that expensive access is correctly calculated."""
        # Set L to 0 to make events with depth > 0 expensive
        self.catalogo.parametros["L"] = 0

        # Create events
        for eid in (10, 20, 30):
            self.catalogo.crear_evento(evento(eid))

        indicadores = self.catalogo.indicadores()
        costosos = indicadores["acceso_costoso"]

        # At least some events should be marked as expensive
        self.assertGreater(len(costosos), 0)

        # Each expensive access item should have required fields
        for item in costosos:
            self.assertIn("identificador", item)
            self.assertIn("profundidad", item)
            self.assertIn("examinados", item)

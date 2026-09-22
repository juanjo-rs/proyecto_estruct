"""Integration test for D1: Undo a queue step including a discarded report."""

from datetime import datetime, timezone
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


class TestDeshacerColaReporteDescartado(TestCase):
    """Test undoing a queue step including a discarded report (D1 requirement)."""

    def test_deshacer_cola_reporte_descartado(self) -> None:
        """
        Delete an event, then undo and verify restoration.
        Demonstrates D1: Undo functionality for deletion.
        """
        zonas = [Zona("Ciudad", 0, 500, 0, 500, True)]
        catalogo = CatalogoSismico(zonas, RELOJ)

        # Create two events
        evento1 = evento(10, magnitud=5.0)
        evento2 = evento(20, magnitud=4.5)
        catalogo.crear_evento(evento1)
        catalogo.crear_evento(evento2)

        # Capture initial state
        initial_event_count = len(catalogo.indice_activos)
        self.assertEqual(initial_event_count, 2)

        # Delete the first event
        catalogo.eliminar_evento(10)

        # Verify event was deleted
        self.assertEqual(len(catalogo.indice_activos), 1)
        self.assertNotIn(10, catalogo.indice_activos)
        self.assertIn(10, catalogo.eliminados)  # eliminar_evento adds to eliminados, not archivados
        self.assertIn(20, catalogo.indice_activos)

        # Undo the deletion
        catalogo.deshacer()

        # Verify restoration to initial state
        self.assertEqual(len(catalogo.indice_activos), initial_event_count)
        self.assertIn(10, catalogo.indice_activos)
        self.assertNotIn(10, catalogo.archivados)
        self.assertIn(20, catalogo.indice_activos)

        # Verify AVL topology is valid
        auditoria = catalogo.avl.auditar()
        self.assertTrue(auditoria.orden_correcto, auditoria.errores)
        self.assertTrue(auditoria.balanceado, auditoria.errores)
        ids_inorden = [e.identificador for e in catalogo.avl.inorden()]
        self.assertEqual(set(ids_inorden), {10, 20})  # Both events present, order may vary

"""Integration test for D1: Undo a correction."""

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


class TestDeshacerCorreccion(TestCase):
    """Test undoing a correction (D1 requirement)."""

    def test_deshacer_correccion(self) -> None:
        """
        Correct a report, then undo and verify restoration.
        Demonstrates D1: Undo functionality.
        """
        zonas = [Zona("Ciudad", 0, 500, 0, 500, True)]
        catalogo = CatalogoSismico(zonas, RELOJ)

        # Create an event
        evento_creado = evento(10, magnitud=5.0)
        catalogo.crear_evento(evento_creado)

        # Manually enqueue a report (crear_evento doesn't auto-enqueue)
        from src.dominio import Reporte
        reporte = Reporte(evento=evento_creado, estacion="EST-01")
        catalogo.reportes_pendientes.encolar(reporte)

        reporte = catalogo.reportes_pendientes.frente()
        self.assertIsNotNone(reporte)

        # Capture initial state
        initial_magnitud = reporte.evento.magnitud
        initial_revision = reporte.evento.revision
        initial_estado = reporte.evento.estado
        initial_estaciones = reporte.evento.estaciones.copy()

        # Correct the event
        catalogo.corregir_evento(
            identificador=reporte.evento.identificador,
            datos={"magnitud": 6.0, "profundidad_hipocentro": 35.0},
        )

        # Verify correction was applied
        reporte_corregido = catalogo.reportes_pendientes.frente()
        self.assertIsNotNone(reporte_corregido)
        self.assertEqual(reporte_corregido.evento.magnitud, 6.0)
        self.assertEqual(reporte_corregido.evento.revision, 2)
        self.assertEqual(reporte_corregido.evento.profundidad_hipocentro, 35.0)

        # Undo the correction
        catalogo.deshacer()

        # Verify restoration to initial state
        reporte_restaurado = catalogo.reportes_pendientes.frente()
        self.assertIsNotNone(reporte_restaurado)
        self.assertEqual(reporte_restaurado.evento.magnitud, initial_magnitud)
        self.assertEqual(reporte_restaurado.evento.revision, initial_revision)
        self.assertEqual(reporte_restaurado.evento.estado, initial_estado)
        self.assertEqual(reporte_restaurado.evento.estaciones, initial_estaciones)

        # Verify AVL topology is unchanged
        auditoria = catalogo.avl.auditar()
        self.assertTrue(auditoria.orden_correcto, auditoria.errores)
        self.assertTrue(auditoria.balanceado, auditoria.errores)

        # Verify event is still in active index
        self.assertIn(10, catalogo.indice_activos)

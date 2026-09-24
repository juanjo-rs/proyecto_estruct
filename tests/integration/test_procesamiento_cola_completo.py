"""Integration test for C5: Queue processing with all decision types."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest import TestCase

from src.catalogo import CatalogoSismico
from src.dominio import Evento, Reporte, Zona


RELOJ = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)


def evento(
    identificador: int,
    magnitud: float = 4.5,
    revision: int = 1,
    estacion: str = "EST-01",
    profundidad_hipocentro: float = 30.0,
) -> Evento:
    """Create a minimal Evento object."""
    return Evento(
        identificador=identificador,
        magnitud=Decimal(str(magnitud)),
        profundidad_hipocentro=Decimal(str(profundidad_hipocentro)),
        x=Decimal("100.0"),
        y=Decimal("100.0"),
        ocurrencia="2026-09-07T10:00:00Z",
        revision=revision,
        estaciones={estacion},
    )


class TestProcesamientoColaCompleto(TestCase):
    """Test queue processing with all decision types (C5 requirement)."""

    def test_alta_nueva(self) -> None:
        """
        Process a report for a new event ID (alta nueva).
        Demonstrates C5: Queue processing - alta nueva decision.
        """
        zonas = [Zona("Ciudad", 0, 500, 0, 500, True)]
        catalogo = CatalogoSismico(zonas, RELOJ)

        # Enqueue a report for a new event (ID not in active events)
        evento_nuevo = evento(100, magnitud=5.0, revision=1)
        reporte = Reporte(evento=evento_nuevo, estacion="EST-01")
        catalogo.encolar_reporte(reporte)

        # Process the report
        resultado = catalogo.procesar_siguiente_reporte()

        # Verify alta nueva decision
        self.assertEqual(resultado, "alta nueva")

        # Verify event was created in active index
        self.assertIn(100, catalogo.indice_activos)
        self.assertEqual(catalogo.indice_activos[100].magnitud, Decimal("5.0"))

        # Verify queue is empty
        self.assertTrue(catalogo.reportes_pendientes.esta_vacia())

    def test_confirmacion_aceptada(self) -> None:
        """
        Process a report with same revision and same data (confirmacion aceptada).
        Demonstrates C5: Queue processing - confirmacion aceptada decision.
        """
        zonas = [Zona("Ciudad", 0, 500, 0, 500, True)]
        catalogo = CatalogoSismico(zonas, RELOJ)

        # Create an active event
        evento_existente = evento(200, magnitud=4.5, revision=1)
        catalogo.crear_evento(evento_existente)

        # Enqueue a report with same revision and same data
        evento_reporte = evento(200, magnitud=4.5, revision=1)
        reporte = Reporte(evento=evento_reporte, estacion="EST-02")
        catalogo.encolar_reporte(reporte)

        # Process the report
        resultado = catalogo.procesar_siguiente_reporte()

        # Verify confirmacion aceptada decision
        self.assertEqual(resultado, "confirmacion aceptada")

        # Verify station was added to the event
        self.assertIn("EST-02", catalogo.indice_activos[200].estaciones)
        self.assertIn("EST-01", catalogo.indice_activos[200].estaciones)

        # Verify queue is empty
        self.assertTrue(catalogo.reportes_pendientes.esta_vacia())

    def test_reporte_antiguo(self) -> None:
        """
        Process a report with lower revision than the active event (reporte antiguo).
        Demonstrates C5: Queue processing - reporte antiguo decision.
        """
        zonas = [Zona("Ciudad", 0, 500, 0, 500, True)]
        catalogo = CatalogoSismico(zonas, RELOJ)

        # Create an active event with revision 2
        evento_existente = evento(300, magnitud=5.0, revision=2)
        catalogo.crear_evento(evento_existente)

        # Enqueue a report with revision 1 (older)
        evento_reporte = evento(300, magnitud=4.5, revision=1)
        reporte = Reporte(evento=evento_reporte, estacion="EST-01")
        catalogo.encolar_reporte(reporte)

        # Process the report
        resultado = catalogo.procesar_siguiente_reporte()

        # Verify reporte antiguo decision
        self.assertEqual(resultado, "descartado: reporte antiguo")

        # Verify event was not modified
        self.assertEqual(catalogo.indice_activos[300].revision, 2)
        self.assertEqual(catalogo.indice_activos[300].magnitud, Decimal("5.0"))

        # Verify metrics updated
        self.assertEqual(catalogo.metricas["reportes_descartados"], 1)

        # Verify queue is empty
        self.assertTrue(catalogo.reportes_pendientes.esta_vacia())

    def test_correccion_cambia_clave(self) -> None:
        """
        Process a report with higher revision that changes the AVL key (correccion que cambia clave).
        Demonstrates C5: Queue processing - correccion aceptada with key change.
        """
        zonas = [Zona("Ciudad", 0, 500, 0, 500, True)]
        catalogo = CatalogoSismico(zonas, RELOJ)

        # Create an active event with low priority (magnitude 3.5 for priority 1)
        evento_existente = evento(400, magnitud=3.5, revision=1)
        catalogo.crear_evento(evento_existente)

        # Capture initial AVL position
        clave_inicial = catalogo.indice_activos[400].clave()
        # Magnitude 3.5 should give priority 1
        self.assertEqual(clave_inicial[0], 1)

        # Enqueue a report with higher revision and higher magnitude (changes priority)
        evento_reporte = evento(400, magnitud=6.5, revision=2)
        reporte = Reporte(evento=evento_reporte, estacion="EST-01")
        catalogo.encolar_reporte(reporte)

        # Process the report
        resultado = catalogo.procesar_siguiente_reporte()

        # Verify correccion aceptada decision
        self.assertEqual(resultado, "correccion aceptada")

        # Verify event was updated
        self.assertEqual(catalogo.indice_activos[400].revision, 2)
        self.assertEqual(catalogo.indice_activos[400].magnitud, Decimal("6.5"))

        # Verify AVL key changed (priority changed from 1 to 3 due to magnitude >= 6.0)
        clave_nueva = catalogo.indice_activos[400].clave()
        self.assertEqual(clave_nueva, (3, Decimal("6.5"), 400))

        # Verify AVL is still balanced after key change
        auditoria = catalogo.avl.auditar()
        self.assertTrue(auditoria.orden_correcto, auditoria.errores)
        self.assertTrue(auditoria.balanceado, auditoria.errores)

        # Verify queue is empty
        self.assertTrue(catalogo.reportes_pendientes.esta_vacia())

    def test_fifo_no_depende_de_prioridad_avl(self) -> None:
        """
        Verify that FIFO queue order is independent of AVL priority.
        Demonstrates C5: FIFO does not depend on AVL priority.
        """
        zonas = [Zona("Ciudad", 0, 500, 0, 500, True)]
        catalogo = CatalogoSismico(zonas, RELOJ)

        # Create events with different priorities
        evento_baja = evento(500, magnitud=4.0, revision=1)  # Low priority
        evento_alta = evento(501, magnitud=6.5, revision=1)  # High priority
        evento_media = evento(502, magnitud=5.0, revision=1)  # Medium priority

        catalogo.crear_evento(evento_baja)
        catalogo.crear_evento(evento_alta)
        catalogo.crear_evento(evento_media)

        # Enqueue reports in specific order (not priority order)
        reporte1 = Reporte(evento=evento_media, estacion="EST-01")  # Medium priority first
        reporte2 = Reporte(evento=evento_baja, estacion="EST-02")  # Low priority second
        reporte3 = Reporte(evento=evento_alta, estacion="EST-03")  # High priority third

        catalogo.encolar_reporte(reporte1)
        catalogo.encolar_reporte(reporte2)
        catalogo.encolar_reporte(reporte3)

        # Verify queue order is FIFO (order of enqueue), not priority order
        ids_en_cola = [r.evento.identificador for r in catalogo.reportes_pendientes]
        self.assertEqual(ids_en_cola, [502, 500, 501])  # Enqueue order, not priority order

        # Process reports and verify they are processed in FIFO order
        resultado1 = catalogo.procesar_siguiente_reporte()
        self.assertEqual(resultado1, "confirmacion aceptada")

        resultado2 = catalogo.procesar_siguiente_reporte()
        self.assertEqual(resultado2, "confirmacion aceptada")

        resultado3 = catalogo.procesar_siguiente_reporte()
        self.assertEqual(resultado3, "confirmacion aceptada")

        # Verify queue is empty
        self.assertTrue(catalogo.reportes_pendientes.esta_vacia())

        # Explanation: FIFO queue is a separate data structure from AVL.
        # Reports are enqueued in chronological order (arrival time).
        # Processing follows arrival order, not AVL priority order.
        # AVL stores active events ordered by priority for efficient queries,
        # but this does not affect queue processing order.

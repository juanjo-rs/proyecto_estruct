"""Test for E3: Map view API and data integrity."""

from datetime import datetime, timezone
from unittest import TestCase

from src.catalogo import CatalogoSismico
from src.dominio import Evento, VistaEventoMapa, VistaZona, Zona


RELOJ = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)


def evento(identificador: int, magnitud: float = 4.5, x: float = 500.0, y: float = 500.0) -> Evento:
    """Create a minimal Evento object."""
    return Evento(
        identificador=identificador,
        magnitud=magnitud,
        profundidad_hipocentro=30.0,
        x=x,
        y=y,
        ocurrencia="2026-09-07T10:00:00Z",
        revision=1,
        estaciones={"EST-01"},
    )


class TestVistaMapa(TestCase):
    """Test the immutable map view API (E3 requirement)."""

    def test_vista_mapa_vacio(self) -> None:
        """Test that empty catalog returns empty views."""
        zonas = [Zona("Ciudad", 0, 500, 0, 500, True)]
        catalogo = CatalogoSismico(zonas, RELOJ)

        vista_zonas, vista_eventos = catalogo.obtener_vista_mapa()

        # Should have one zone
        self.assertEqual(len(vista_zonas), 1)
        self.assertIsInstance(vista_zonas[0], VistaZona)
        self.assertEqual(vista_zonas[0].nombre, "Ciudad")

        # Should have no events
        self.assertEqual(len(vista_eventos), 0)

    def test_vista_zona_datos_correctos(self) -> None:
        """Test that zone view contains correct data."""
        zonas = [Zona("Zona A", 100, 300, 200, 400, True)]
        catalogo = CatalogoSismico(zonas, RELOJ)

        vista_zonas, _ = catalogo.obtener_vista_mapa()

        zona_vista = vista_zonas[0]
        self.assertEqual(zona_vista.nombre, "Zona A")
        self.assertEqual(zona_vista.x_min, 100)
        self.assertEqual(zona_vista.x_max, 300)
        self.assertEqual(zona_vista.y_min, 200)
        self.assertEqual(zona_vista.y_max, 400)
        self.assertTrue(zona_vista.poblada)

    def test_vista_evento_datos_correctos(self) -> None:
        """Test that event view contains correct data."""
        zonas = [Zona("Ciudad", 0, 500, 0, 500, True)]
        catalogo = CatalogoSismico(zonas, RELOJ)

        catalogo.crear_evento(evento(10, magnitud=5.0, x=250.0, y=250.0))

        _, vista_eventos = catalogo.obtener_vista_mapa()

        self.assertEqual(len(vista_eventos), 1)
        evento_vista = vista_eventos[0]
        self.assertIsInstance(evento_vista, VistaEventoMapa)
        self.assertEqual(evento_vista.id, 10)
        self.assertEqual(evento_vista.x, 250.0)
        self.assertEqual(evento_vista.y, 250.0)
        self.assertEqual(evento_vista.prioridad, 3)  # Magnitude 5.0 in populated zone = priority 3
        self.assertEqual(evento_vista.magnitud, 5.0)
        self.assertTrue(evento_vista.en_zona_poblada)
        self.assertEqual(evento_vista.estado, "pendiente")

    def test_vista_evento_acceso_costoso(self) -> None:
        """Test that expensive access is correctly marked."""
        zonas = [Zona("Ciudad", 0, 500, 0, 500, True)]
        catalogo = CatalogoSismico(zonas, RELOJ)

        # Set L to 0 to make events with depth > 0 expensive
        catalogo.parametros["L"] = 0

        # Create events in a way that creates depth in the AVL
        # Insert in order that creates an unbalanced tree
        for eid in (10, 20, 30):
            catalogo.crear_evento(evento(eid, x=100.0 + eid * 10, y=100.0 + eid * 10))

        _, vista_eventos = catalogo.obtener_vista_mapa()

        # At least some events should be marked as expensive access
        # (events with depth > 0)
        costosos = [e for e in vista_eventos if e.acceso_costoso]
        self.assertGreater(len(costosos), 0, "At least one event should be expensive")

    def test_vista_evento_no_acceso_costoso(self) -> None:
        """Test that events with shallow depth are not marked as expensive."""
        zonas = [Zona("Ciudad", 0, 500, 0, 500, True)]
        catalogo = CatalogoSismico(zonas, RELOJ)

        # Set L to a high value to make no events expensive
        catalogo.parametros["L"] = 100

        # Create events
        for eid in (10, 20, 30):
            catalogo.crear_evento(evento(eid))

        _, vista_eventos = catalogo.obtener_vista_mapa()

        # No events should be marked as expensive access
        for evento_vista in vista_eventos:
            self.assertFalse(evento_vista.acceso_costoso, f"Event {evento_vista.id} should not be expensive")

    def test_vista_prioridad_alta(self) -> None:
        """Test that high priority events are correctly marked."""
        zonas = [Zona("Ciudad", 0, 500, 0, 500, True)]
        catalogo = CatalogoSismico(zonas, RELOJ)

        # Create high priority event (magnitude >= 6.0)
        catalogo.crear_evento(evento(10, magnitud=6.5))

        _, vista_eventos = catalogo.obtener_vista_mapa()

        evento_vista = vista_eventos[0]
        self.assertEqual(evento_vista.prioridad, 3)

    def test_vista_prioridad_baja(self) -> None:
        """Test that low priority events are correctly marked."""
        zonas = [Zona("Zona rural", 0, 500, 0, 500, False)]  # Not populated
        catalogo = CatalogoSismico(zonas, RELOJ)

        # Create low priority event (magnitude < 4.5, not in populated zone)
        catalogo.crear_evento(evento(10, magnitud=4.0))

        _, vista_eventos = catalogo.obtener_vista_mapa()

        evento_vista = vista_eventos[0]
        self.assertEqual(evento_vista.prioridad, 1)

    def test_vista_inmutable(self) -> None:
        """Test that the view is immutable and does not expose Evento objects."""
        zonas = [Zona("Ciudad", 0, 500, 0, 500, True)]
        catalogo = CatalogoSismico(zonas, RELOJ)

        catalogo.crear_evento(evento(10, magnitud=5.0))

        vista_zonas, vista_eventos = catalogo.obtener_vista_mapa()

        # VistaZona and VistaEventoMapa are frozen (immutable)
        zona = vista_zonas[0]
        evento_vista = vista_eventos[0]
        self.assertTrue(hasattr(zona, "__dataclass_fields__"))
        self.assertTrue(hasattr(evento_vista, "__dataclass_fields__"))

        # Verify that the view does not contain Evento attributes
        self.assertFalse(hasattr(evento_vista, "estaciones"))
        self.assertFalse(hasattr(evento_vista, "profundidad_hipocentro"))
        self.assertFalse(hasattr(evento_vista, "ocurrencia"))

        # Verify that modifying the view does not affect the catalog
        # (VistaZona and VistaEventoMapa are frozen, so this would raise an error)
        try:
            evento_vista.prioridad = 999
            self.fail("VistaEventoMapa should be immutable (frozen)")
        except (AttributeError, TypeError):
            pass  # Expected for frozen dataclass

    def test_vista_borde_zona_poblada(self) -> None:
        """Test that events on populated zone border are correctly classified."""
        # Create a populated zone
        zonas = [Zona("Ciudad", 0, 500, 0, 500, True)]
        catalogo = CatalogoSismico(zonas, RELOJ)

        # Create event exactly on the border
        catalogo.crear_evento(evento(10, magnitud=5.0, x=500.0, y=250.0))

        _, vista_eventos = catalogo.obtener_vista_mapa()

        evento_vista = vista_eventos[0]
        self.assertTrue(evento_vista.en_zona_poblada)

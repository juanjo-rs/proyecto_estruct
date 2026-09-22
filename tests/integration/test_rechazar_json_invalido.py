"""Integration test for D4: Reject invalid JSON without mutating state."""

import json
from datetime import datetime, timezone
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


class TestRechazarJSONInvalido(TestCase):
    """Test rejecting invalid JSON without mutating state (D4 atomicity requirement)."""

    def test_rechazar_json_invalido_sin_mutar(self) -> None:
        """
        Attempt to load invalid JSON, verify that state does not mutate.
        Demonstrates D4: Atomicity - if validation fails, scenario remains unchanged.
        """
        # Create initial catalog with events
        zonas = [Zona("Ciudad", 0, 500, 0, 500, True)]
        catalogo = CatalogoSismico(zonas, RELOJ)

        # Add events
        for eid in (30, 20, 10, 40, 50):
            catalogo.crear_evento(evento(eid))

        # Capture initial state
        initial_event_count = len(catalogo.indice_activos)
        initial_root_id = catalogo.avl.raiz.evento.identificador if catalogo.avl.raiz else None
        initial_mode = catalogo.modo_estres
        initial_clock = catalogo.reloj
        initial_param_w = catalogo.parametros.get("W")

        # Create invalid JSON (missing required fields)
        json_invalido = {
            "version": 1,
            "tipo_carga": "topologia",
            "modo": "normal",
            "zonas": [],
            "raiz": None,
            "nodos": {},
        }

        # Save to temporary file
        with TemporaryDirectory() as tmpdir:
            from pathlib import Path
            ruta = Path(tmpdir) / "invalido.json"
            escribir_json_escenario(json_invalido, str(ruta))

            # Attempt to load invalid JSON (missing reloj field)
            with self.assertRaises(KeyError) as context:
                datos_leidos = leer_json_archivo(str(ruta))
                catalogo.cargar_por_topologia(datos_leidos)
            self.assertIn("reloj", str(context.exception).lower())

        # Verify state has NOT mutated (atomicity)
        self.assertEqual(len(catalogo.indice_activos), initial_event_count)
        self.assertEqual(
            catalogo.avl.raiz.evento.identificador if catalogo.avl.raiz else None,
            initial_root_id
        )
        self.assertEqual(catalogo.modo_estres, initial_mode)
        self.assertEqual(catalogo.reloj, initial_clock)
        self.assertEqual(catalogo.parametros.get("W"), initial_param_w)

        # Verify AVL topology is unchanged
        auditoria = catalogo.avl.auditar()
        self.assertTrue(auditoria.orden_correcto, auditoria.errores)
        self.assertTrue(auditoria.balanceado, auditoria.errores)
        ids_inorden = [e.identificador for e in catalogo.avl.inorden()]
        self.assertEqual(ids_inorden, [10, 20, 30, 40, 50])

    def test_rechazar_json_version_incorrecta(self) -> None:
        """Test that incorrect JSON version is rejected without mutation."""
        zonas = [Zona("Ciudad", 0, 500, 0, 500, True)]
        catalogo = CatalogoSismico(zonas, RELOJ)

        catalogo.crear_evento(evento(10))
        initial_count = len(catalogo.indice_activos)

        # JSON with unsupported version
        json_invalido = {
            "version": 2,  # Unsupported version
            "tipo_carga": "topologia",
            "reloj": "2026-09-07T12:00:00Z",
            "modo": "normal",
            "zonas": [],
            "raiz": None,
            "nodos": {},
        }

        with TemporaryDirectory() as tmpdir:
            from pathlib import Path
            ruta = Path(tmpdir) / "version_incorrecta.json"
            escribir_json_escenario(json_invalido, str(ruta))

            with self.assertRaises(ValueError) as context:
                datos_leidos = leer_json_archivo(str(ruta))
                catalogo.cargar_por_topologia(datos_leidos)
            self.assertIn("version", str(context.exception).lower())

        # Verify state unchanged
        self.assertEqual(len(catalogo.indice_activos), initial_count)

    def test_rechazar_json_tipo_carga_incorrecto(self) -> None:
        """Test that incorrect tipo_carga is rejected without mutation."""
        zonas = [Zona("Ciudad", 0, 500, 0, 500, True)]
        catalogo = CatalogoSismico(zonas, RELOJ)

        catalogo.crear_evento(evento(10))
        initial_count = len(catalogo.indice_activos)

        # JSON with incorrect tipo_carga
        json_invalido = {
            "version": 1,
            "tipo_carga": "inserciones",  # Wrong type
            "reloj": "2026-09-07T12:00:00Z",
            "modo": "normal",
            "zonas": [],
            "raiz": None,
            "nodos": {},
        }

        with TemporaryDirectory() as tmpdir:
            from pathlib import Path
            ruta = Path(tmpdir) / "tipo_incorrecto.json"
            escribir_json_escenario(json_invalido, str(ruta))

            with self.assertRaises(ValueError) as context:
                datos_leidos = leer_json_archivo(str(ruta))
                catalogo.cargar_por_topologia(datos_leidos)
            self.assertIn("topologia", str(context.exception).lower())

        # Verify state unchanged
        self.assertEqual(len(catalogo.indice_activos), initial_count)

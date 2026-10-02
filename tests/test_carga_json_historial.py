"""JSON dispatch from the window and the archived-event list."""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest import TestCase

from interfaz import aplicar_carga_json, filas_historial_sismico, texto_detalle_evento
from src.catalogo import CatalogoSismico
from src.dominio import Evento, Zona


RELOJ = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def evento(identificador: int) -> Evento:
    """One active event used to prove a rejected load does not replace it."""
    return Evento(
        identificador=identificador,
        magnitud=4.0,
        profundidad_hipocentro=40.0,
        x=100.0,
        y=100.0,
        ocurrencia="2026-09-07T10:00:00Z",
        revision=1,
        estaciones={"EST-01"},
    )


class PruebasCargaJson(TestCase):
    def setUp(self) -> None:
        self.catalogo = CatalogoSismico([Zona("Campo", 0, 1000, 0, 1000, False)], RELOJ)
        self.catalogo.crear_evento(evento(7))

    def test_tipo_desconocido_no_cambia_el_escenario(self) -> None:
        with self.assertRaises(ValueError):
            aplicar_carga_json(self.catalogo, {"version": 1, "tipo_carga": "otro"})
        self.assertIn(7, self.catalogo.indice_activos)

    def test_inserciones_reemplaza_el_escenario(self) -> None:
        datos = json.loads((FIXTURES / "limites_empates.json").read_text(encoding="utf-8"))
        estadisticas = aplicar_carga_json(self.catalogo, datos)
        self.assertNotIn(7, self.catalogo.indice_activos)
        self.assertIsNotNone(estadisticas["avl"]["raiz_id"])
        self.assertIn(1, self.catalogo.indice_activos)

    def test_topologia_reemplaza_el_escenario(self) -> None:
        datos = json.loads((FIXTURES / "topologia_normal.json").read_text(encoding="utf-8"))
        estadisticas = aplicar_carga_json(self.catalogo, datos)
        self.assertNotIn(7, self.catalogo.indice_activos)
        self.assertEqual(estadisticas["avl"]["raiz_id"], 30)
        self.assertIn(30, self.catalogo.indice_activos)

    def test_json_invalido_conserva_el_evento_previo(self) -> None:
        datos = json.loads((FIXTURES / "json_invalido.json").read_text(encoding="utf-8"))
        with self.assertRaises(ValueError):
            aplicar_carga_json(self.catalogo, datos)
        self.assertIn(7, self.catalogo.indice_activos)


class PruebasHistorialSismico(TestCase):
    def test_lista_vacia_y_un_archivado(self) -> None:
        catalogo = CatalogoSismico([Zona("Campo", 0, 1000, 0, 1000, False)], RELOJ)
        self.assertEqual(filas_historial_sismico(catalogo), [])
        archivado = evento(15)
        archivado.prioridad = 1
        archivado.ocurrencia = RELOJ
        catalogo.archivados[15] = archivado
        filas = filas_historial_sismico(catalogo)
        self.assertEqual(len(filas), 1)
        self.assertIn("SIS-000015", filas[0])
        self.assertIn("P1", filas[0])


class PruebasEscenarioTrasCarga(TestCase):
    def test_carga_exitosa_vacia_el_historico_anterior(self) -> None:
        catalogo = CatalogoSismico([Zona("Campo", 0, 1000, 0, 1000, False)], RELOJ)
        guardado = evento(15)
        guardado.ocurrencia = RELOJ
        guardado.prioridad = 1
        catalogo.archivados[15] = guardado
        datos = json.loads((FIXTURES / "limites_empates.json").read_text(encoding="utf-8"))
        aplicar_carga_json(catalogo, datos)
        self.assertEqual(catalogo.archivados, {})
        self.assertIn(1, catalogo.indice_activos)

    def test_carga_fallida_conserva_el_historico(self) -> None:
        catalogo = CatalogoSismico([Zona("Campo", 0, 1000, 0, 1000, False)], RELOJ)
        guardado = evento(15)
        guardado.ocurrencia = RELOJ
        catalogo.archivados[15] = guardado
        with self.assertRaises(ValueError):
            aplicar_carga_json(
                catalogo,
                {
                    "version": 1,
                    "tipo_carga": "inserciones",
                    "reloj": "2026-09-07T14:00:00Z",
                    "modo": "normal",
                    "zonas": [],
                    "eventos": [
                        {
                            "identificador": 100,
                            "magnitud": 4.0,
                            "profundidad_hipocentro": 30.0,
                            "x": 100.0,
                            "y": 100.0,
                            "ocurrencia": "2026-09-07T12:00:00Z",
                            "revision": 1,
                            "estaciones": ["EST-10"],
                        },
                        {
                            "identificador": 100,
                            "magnitud": 5.0,
                            "profundidad_hipocentro": 40.0,
                            "x": 200.0,
                            "y": 200.0,
                            "ocurrencia": "2026-09-07T13:00:00Z",
                            "revision": 1,
                            "estaciones": ["EST-20"],
                        },
                    ],
                },
            )
        self.assertIn(15, catalogo.archivados)

    def test_detalle_de_activo_incluye_posicion_avl(self) -> None:
        catalogo = CatalogoSismico([Zona("Campo", 0, 1000, 0, 1000, False)], RELOJ)
        catalogo.crear_evento(evento(7))
        texto = texto_detalle_evento(catalogo.consultar_detalle(7))
        self.assertIn("SIS-000007: activo", texto)
        self.assertIn("AVL profundidad", texto)
        self.assertIn("factor", texto)
        self.assertIn("candidatos:", texto)

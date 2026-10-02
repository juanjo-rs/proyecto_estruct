"""Zone replacement reclassifies priority and stays undoable."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest import TestCase

from src.catalogo import CatalogoSismico
from src.dominio import Evento, Zona


RELOJ = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)


def evento(identificador: int) -> Evento:
    """Magnitude 5.0 and depth 20 km: priority 3 only inside a populated zone."""
    return Evento(
        identificador=identificador,
        magnitud=5.0,
        profundidad_hipocentro=20.0,
        x=100.0,
        y=100.0,
        ocurrencia="2026-09-07T10:00:00Z",
        revision=1,
        estaciones={"EST-01"},
    )


class PruebasConfigurarZonas(TestCase):
    def setUp(self) -> None:
        self.catalogo = CatalogoSismico(
            [Zona("Campo", 0, 1000, 0, 1000, False)],
            RELOJ,
        )

    def test_zona_poblada_mueve_la_clave_y_se_deshace(self) -> None:
        self.catalogo.crear_evento(evento(10))
        self.assertEqual(self.catalogo.indice_activos[10].prioridad, 2)

        self.catalogo.configurar_zonas([Zona("Ciudad", 0, 200, 0, 200, True)])

        actual = self.catalogo.indice_activos[10]
        self.assertTrue(actual.en_zona_poblada)
        self.assertEqual(actual.prioridad, 3)
        clave_nueva = (3, Decimal("5.0"), 10)
        clave_vieja = (2, Decimal("5.0"), 10)
        self.assertIsNotNone(self.catalogo.avl.buscar_clave(clave_nueva)[0])
        self.assertIsNotNone(self.catalogo.bst.buscar_clave(clave_nueva)[0])
        self.assertIsNone(self.catalogo.avl.buscar_clave(clave_vieja)[0])
        self.assertIsNone(self.catalogo.bst.buscar_clave(clave_vieja)[0])

        self.catalogo.deshacer()
        actual = self.catalogo.indice_activos[10]
        self.assertFalse(actual.en_zona_poblada)
        self.assertEqual(actual.prioridad, 2)
        self.assertEqual(self.catalogo.zonas[0].nombre, "Campo")
        self.assertIsNotNone(self.catalogo.avl.buscar_clave(clave_vieja)[0])
        self.assertIsNone(self.catalogo.avl.buscar_clave(clave_nueva)[0])

    def test_zona_invalida_no_cambia_el_escenario(self) -> None:
        self.catalogo.crear_evento(evento(10))
        with self.assertRaises(ValueError):
            self.catalogo.configurar_zonas([Zona("Mala", 400, 100, 0, 200, True)])
        with self.assertRaises(ValueError):
            self.catalogo.configurar_zonas([])
        self.assertEqual(self.catalogo.zonas[0].nombre, "Campo")
        self.assertEqual(self.catalogo.indice_activos[10].prioridad, 2)
        self.catalogo.deshacer()
        self.assertNotIn(10, self.catalogo.indice_activos)

    def test_zona_fuera_de_la_inicial_no_entra(self) -> None:
        self.catalogo.configurar_zonas([Zona("Marco", 0, 400, 0, 400, False)])
        with self.assertRaises(ValueError) as contexto:
            self.catalogo.configurar_zonas(
                [
                    Zona("Marco", 0, 400, 0, 400, False),
                    Zona("Afuera", 500, 600, 0, 100, True),
                ]
            )
        self.assertIn("zona inicial", str(contexto.exception).lower())
        self.assertEqual(len(self.catalogo.zonas), 1)
        self.assertEqual(self.catalogo.zonas[0].x_max, Decimal("400"))

    def test_editar_la_inicial_a_poblada_reclasifica(self) -> None:
        self.catalogo.crear_evento(evento(10))
        self.catalogo.configurar_zonas([Zona("Campo", 0, 1000, 0, 1000, True)])
        actual = self.catalogo.indice_activos[10]
        self.assertTrue(actual.en_zona_poblada)
        self.assertEqual(actual.prioridad, 3)

    def test_encoger_la_inicial_rechaza_si_otra_queda_fuera(self) -> None:
        self.catalogo.configurar_zonas(
            [
                Zona("Marco", 0, 1000, 0, 1000, False),
                Zona("Ciudad", 100, 200, 100, 200, True),
            ]
        )
        with self.assertRaises(ValueError):
            self.catalogo.configurar_zonas(
                [
                    Zona("Marco", 0, 50, 0, 50, False),
                    Zona("Ciudad", 100, 200, 100, 200, True),
                ]
            )
        self.assertEqual(self.catalogo.zonas[0].x_max, Decimal("1000"))
        self.assertEqual(self.catalogo.zonas[1].nombre, "Ciudad")

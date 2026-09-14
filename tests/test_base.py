from datetime import datetime, timezone
from unittest import TestCase

from src.arbol_avl import ArbolAVL
from src.catalogo import CatalogoSismico
from src.dominio import EstadoAtencion, Evento, Reporte, Zona


RELOJ = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)


def evento(identificador: int, magnitud: float = 4.5, revision: int = 1, estacion: str = "EST-01") -> Evento:
    return Evento(
        identificador=identificador,
        magnitud=magnitud,
        profundidad_hipocentro=30.0,
        x=100.0,
        y=100.0,
        ocurrencia="2026-09-07T10:00:00Z",
        revision=revision,
        estaciones={estacion},
    )


class PruebasBase(TestCase):
    def setUp(self) -> None:
        self.zonas = [Zona("Ciudad", 0, 500, 0, 500, True)]
        self.catalogo = CatalogoSismico(self.zonas, RELOJ)

    def test_prioridad_alta_en_limites(self) -> None:
        self.catalogo.crear_evento(evento(10))
        actual = self.catalogo.indice_activos[10]
        self.assertEqual(actual.prioridad, 3)
        self.assertEqual(actual.clave()[0], 3)

    def test_avl_conserva_orden_y_balance(self) -> None:
        for identificador in (30, 20, 10, 40, 50):
            actual = evento(identificador)
            self.catalogo._normalizar_y_clasificar(actual)
            self.catalogo.avl.insertar(actual)
        auditoria = self.catalogo.avl.auditar()
        self.assertTrue(auditoria.orden_correcto, auditoria.errores)
        self.assertTrue(auditoria.balanceado, auditoria.errores)
        self.assertEqual([e.identificador for e in self.catalogo.avl.inorden()], [10, 20, 30, 40, 50])

    def test_recuperacion_repara_arbol_de_modo_estres(self) -> None:
        arbol = ArbolAVL()
        for identificador in range(1, 8):
            actual = evento(identificador)
            self.catalogo._normalizar_y_clasificar(actual)
            arbol.insertar(actual, balancear=False)
        self.assertFalse(arbol.auditar().balanceado)
        arbol.recuperar_balance()
        self.assertTrue(arbol.auditar().balanceado)

    def test_confirmacion_no_duplica_evento(self) -> None:
        self.catalogo.crear_evento(evento(10))
        self.catalogo.encolar_reporte(Reporte(evento(10, estacion="EST-02"), "EST-02"))
        self.assertEqual(self.catalogo.procesar_siguiente_reporte(), "confirmacion aceptada")
        actual = self.catalogo.indice_activos[10]
        self.assertEqual(actual.estaciones, {"EST-01", "EST-02"})
        self.assertEqual(len(list(self.catalogo.avl.inorden())), 1)

    def test_correccion_vuelve_pendiente_y_cambia_clave(self) -> None:
        self.catalogo.crear_evento(evento(10, magnitud=4.8))
        self.catalogo.marcar_revisado(10)
        corregido = self.catalogo.corregir_evento(
            10, {"magnitud": 6.2, "profundidad_hipocentro": 15.0}
        )
        self.assertEqual(corregido.prioridad, 3)
        self.assertEqual(corregido.estado, EstadoAtencion.PENDIENTE)
        encontrado, _ = self.catalogo.avl.buscar_clave(corregido.clave())
        self.assertIs(encontrado, corregido)

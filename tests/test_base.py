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

    def test_deshacer_correccion_restaura_datos_y_estaciones(self) -> None:
        self.catalogo.crear_evento(evento(10, magnitud=4.8))
        self.catalogo.marcar_revisado(10)
        self.catalogo.corregir_evento(10, {"magnitud": 6.2, "profundidad_hipocentro": 15.0})
        self.catalogo.indice_activos[10].estaciones.add("EST-02")

        self.assertEqual(self.catalogo.deshacer(), "Deshecho: Corregir SIS-000010")
        restaurado = self.catalogo.indice_activos[10]
        self.assertEqual(str(restaurado.magnitud), "4.8")
        self.assertEqual(restaurado.revision, 1)
        self.assertEqual(restaurado.estaciones, {"EST-01"})
        self.assertEqual(restaurado.estado, EstadoAtencion.REVISADO)

    def test_deshacer_eliminacion_restaura_evento_y_arbol(self) -> None:
        self.catalogo.crear_evento(evento(10))
        self.catalogo.eliminar_evento(10)

        self.catalogo.deshacer()
        estado, restaurado = self.catalogo.consultar(10)
        self.assertEqual(estado, "activo")
        self.assertIsNotNone(restaurado)
        self.assertEqual(self.catalogo.eliminados, set())
        encontrado, _ = self.catalogo.avl.buscar_clave(restaurado.clave())
        self.assertIs(encontrado, restaurado)

    def test_deshacer_reporte_descartado_devuelve_reporte_al_frente(self) -> None:
        self.catalogo.crear_evento(evento(10, revision=2))
        reporte = Reporte(evento(10, revision=1), "EST-02")
        self.catalogo.encolar_reporte(reporte)
        self.assertEqual(self.catalogo.procesar_siguiente_reporte(), "descartado: reporte antiguo")
        self.assertEqual(len(self.catalogo.reportes_pendientes), 0)
        self.assertEqual(self.catalogo.metricas["reportes_descartados"], 1)

        self.catalogo.deshacer()
        self.assertEqual(len(self.catalogo.reportes_pendientes), 1)
        restaurado = self.catalogo.reportes_pendientes.frente()
        self.assertIsNot(restaurado, reporte)
        self.assertEqual(restaurado.estacion, "EST-02")
        self.assertEqual(restaurado.evento.revision, 1)
        self.assertEqual(str(restaurado.evento.magnitud), "4.5")
        self.assertEqual(self.catalogo.metricas["reportes_descartados"], 0)

    def test_deshacer_sin_historial_informa_error(self) -> None:
        with self.assertRaisesRegex(IndexError, "No hay acciones para deshacer"):
            self.catalogo.deshacer()

    def test_correccion_invalida_no_crea_instantanea(self) -> None:
        self.catalogo.crear_evento(evento(10))
        cantidad_antes = len(self.catalogo.historial)

        with self.assertRaises(ValueError):
            self.catalogo.corregir_evento(10, {"magnitud": 20.0})

        self.assertEqual(len(self.catalogo.historial), cantidad_antes)
        self.assertEqual(str(self.catalogo.indice_activos[10].magnitud), "4.5")

    def test_activar_estres_y_desactivar_recuperar(self) -> None:
        self.assertTrue(self.catalogo.activar_modo_estres())
        for i in range(1,8):
            self.catalogo.crear_evento(evento(i))
        self.assertTrue(self.catalogo.modo_estres)
        self.assertFalse(self.catalogo.avl.auditar().balanceado)
        giros = self.catalogo.desactivar_modo_estres()
        self.assertGreaterEqual(giros,1)
        self.assertFalse(self.catalogo.modo_estres)
        self.assertTrue(self.catalogo.avl.auditar().balanceado)

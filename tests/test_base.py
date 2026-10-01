import json
from datetime import datetime, timezone
from decimal import Decimal
from unittest import TestCase
from typing import assert_type

from src.arbol_avl import ArbolAVL
from src.catalogo import CatalogoSismico
from src.dominio import EstadoAtencion, Evento, Reporte, Zona


RELOJ = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)


def evento(
    identificador: int,
    magnitud: float = 4.5,
    revision: int = 1,
    estacion: str = "EST-01",
    profundidad_hipocentro: float = 30.0,
    x: float = 100.0,
    y: float = 100.0,
    ocurrencia: str = "2026-09-07T10:00:00Z",
) -> Evento:
    return Evento(
        identificador=identificador,
        magnitud=magnitud,
        profundidad_hipocentro=profundidad_hipocentro,
        x=x,
        y=y,
        ocurrencia=ocurrencia,
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

    def test_indicadores_de_giro_se_restauran_al_deshacer(self) -> None:
        for identificador in (10, 20, 30):
            self.catalogo.crear_evento(evento(identificador))
        antes = self.catalogo.indicadores()
        self.assertEqual(antes["avl"]["casos_rr"], 1)
        self.assertEqual(antes["avl"]["hojas"], 2)
        self.assertGreater(antes["bst"]["altura"], antes["avl"]["altura"])
        self.catalogo.deshacer()
        despues = self.catalogo.indicadores()
        self.assertEqual(despues["avl"]["casos_rr"], 0)
        self.assertEqual(despues["avl"]["hojas"], 1)
        self.assertEqual(self.catalogo.consultar(30)[0], "desconocido")

    def test_acceso_costoso_si_profundidad_supera_L(self) -> None:
        self.catalogo.parametros["L"] = 0
        for identificador in (10, 20, 30):
            self.catalogo.crear_evento(evento(identificador))
        costosos = self.catalogo.indicadores()["acceso_costoso"]
        self.assertEqual(sorted(item["identificador"] for item in costosos), [10, 30])
        self.assertTrue(all(item["profundidad"] > 0 for item in costosos))
        self.assertTrue(all(item["examinados"] >= 1 for item in costosos))
        self.catalogo.parametros["L"] = 1
        self.assertEqual(self.catalogo.indicadores()["acceso_costoso"], [])    

    def test_correccion_invalida_no_crea_instantanea(self) -> None:
        self.catalogo.crear_evento(evento(10))
        cantidad_antes = len(self.catalogo.historial)

        with self.assertRaises(ValueError):
            self.catalogo.corregir_evento(10, {"magnitud": 20.0})

        self.assertEqual(len(self.catalogo.historial), cantidad_antes)
        self.assertEqual(str(self.catalogo.indice_activos[10].magnitud), "4.5")

    def test_activar_estres_y_desactivar_recuperar(self) -> None:
        self.assertTrue(self.catalogo.activar_modo_estres())
        for i in range(1, 8):
            self.catalogo.crear_evento(evento(i))
        self.assertTrue(self.catalogo.modo_estres)
        self.assertFalse(self.catalogo.avl.auditar().balanceado)
        giros = self.catalogo.desactivar_modo_estres()
        self.assertGreaterEqual(giros, 1)
        self.assertFalse(self.catalogo.modo_estres)
        self.assertTrue(self.catalogo.avl.auditar().balanceado)

    def test_recuperacion_estres_conserva_orden_y_pausa_cola(self) -> None:
        self.assertTrue(self.catalogo.activar_modo_estres())
        for identificador in range(1, 16):
            self.catalogo.crear_evento(evento(identificador))

        en_estres = self.catalogo.avl.auditar(exigir_balanceo=False)
        self.assertTrue(en_estres.orden_correcto, en_estres.errores)
        self.assertTrue(en_estres.alturas_correctas, en_estres.errores)
        self.assertFalse(en_estres.balanceado)
        self.assertFalse(any(error.startswith("Desbalance") for error in en_estres.errores))

        orden_antes = [item.identificador for item in self.catalogo.avl.inorden()]
        self.catalogo.encolar_reporte(Reporte(evento(1, estacion="EST-02"), "EST-02"))
        self.catalogo.cola_pausada = True
        with self.assertRaisesRegex(RuntimeError, "pausada"):
            self.catalogo.procesar_siguiente_reporte()
        self.assertEqual(len(self.catalogo.reportes_pendientes), 1)
        self.catalogo.cola_pausada = False

        giros = self.catalogo.recuperar_balance()
        self.assertGreaterEqual(giros, 1)
        self.assertEqual(
            [item.identificador for item in self.catalogo.avl.inorden()],
            orden_antes,
        )
        self.assertTrue(self.catalogo.avl.auditar().balanceado)
        self.assertFalse(self.catalogo.modo_estres)
        self.assertFalse(self.catalogo.cola_pausada)

    def test_listar_ramas_archivables_no_muta_y_elige_subarbol_completo(self) -> None:
        self.catalogo.parametros["T"] = 60
        for identificador in (10, 20, 30):
            self.catalogo.crear_evento(evento(identificador, magnitud=4.0))
        ids_antes = [item.identificador for item in self.catalogo.avl.inorden()]
        candidatas = self.catalogo.listar_ramas_archivables()
        self.assertGreaterEqual(len(candidatas), 1)
        self.assertEqual(len(candidatas[0].identificadores), 3)
        self.assertEqual(set(candidatas[0].identificadores), set(ids_antes))
        self.assertEqual([item.identificador for item in self.catalogo.avl.inorden()], ids_antes)
        self.assertEqual(self.catalogo.archivados, {})

    def test_listar_ramas_rechaza_subarbol_con_prioridad_alta(self) -> None:
        self.catalogo.parametros["T"] = 60
        self.catalogo.crear_evento(evento(10, magnitud=4.0))
        self.catalogo.crear_evento(evento(20, magnitud=6.5))
        candidatas = self.catalogo.listar_ramas_archivables()
        self.assertTrue(all(20 not in rama.identificadores for rama in candidatas))

    def test_archivar_sin_rama_elegible_informa_error(self) -> None:
        self.catalogo.parametros["T"] = 60
        self.catalogo.crear_evento(evento(10, magnitud=6.5))
        with self.assertRaisesRegex(ValueError, "No hay rama elegible"):
            self.catalogo.archivar_rama()
        self.assertEqual(list(self.catalogo.indice_activos), [10])
        self.assertEqual(self.catalogo.archivados, {})

    def test_archivar_rama_completa(self) -> None:
        self.catalogo.parametros["T"] = 60
        for identificador in (10, 20, 30):
            self.catalogo.crear_evento(evento(identificador, magnitud=4.0))
        ids_antes = [item.identificador for item in self.catalogo.avl.inorden()]
        rama = self.catalogo.archivar_rama()
        self.assertEqual(set(rama.identificadores), set(ids_antes))
        self.assertEqual(list(self.catalogo.avl.inorden()), [])
        self.assertEqual(list(self.catalogo.bst.inorden()), [])
        self.assertEqual(self.catalogo.indice_activos, {})
        self.assertEqual(set(self.catalogo.archivados), set(ids_antes))
        self.assertEqual(self.catalogo.eliminados, set())

    def test_rama_invalida_por_descendiente(self) -> None:
        self.catalogo.parametros["T"] = 60
        self.catalogo.activar_modo_estres()
        self.catalogo.crear_evento(evento(10, magnitud=4.0))
        self.catalogo.crear_evento(evento(20, magnitud=4.0))
        self.catalogo.crear_evento(evento(30, magnitud=6.5))
        self.catalogo.crear_evento(evento(5, magnitud=4.0))
        rama = self.catalogo.archivar_rama()
        self.assertEqual(rama.id_raiz, 5)
        self.assertEqual(self.catalogo.consultar(5)[0], "archivado")
        self.assertEqual(self.catalogo.consultar(10)[0], "activo")
        self.assertEqual(self.catalogo.consultar(30)[0], "activo")
        self.assertNotIn(5, self.catalogo.eliminados)

    def test_desempate_id_raiz_mayor(self) -> None:
        self.catalogo.parametros["T"] = 60
        self.catalogo.crear_evento(evento(10, magnitud=4.0, ocurrencia="2026-09-07T09:00:00Z"))
        self.catalogo.crear_evento(evento(20, magnitud=4.0, ocurrencia="2026-09-07T11:50:00Z"))
        self.catalogo.crear_evento(evento(30, magnitud=4.0, ocurrencia="2026-09-07T09:00:00Z"))
        rama = self.catalogo.archivar_rama()
        self.assertEqual(rama.id_raiz, 30)
        self.assertEqual(self.catalogo.consultar(30)[0], "archivado")
        self.assertEqual(self.catalogo.consultar(10)[0], "activo")
        self.assertEqual(self.catalogo.consultar(20)[0], "activo")
        self.assertEqual(
            [item.identificador for item in self.catalogo.avl.inorden()],
            [item.identificador for item in self.catalogo.bst.inorden()],
        )
        
    def test_desempate_raiz_mas_profunda(self) -> None:
        self.catalogo.parametros["T"] = 60
        self.catalogo.activar_modo_estres()
        self.catalogo.crear_evento(evento(10, magnitud=4.0))
        self.catalogo.crear_evento(evento(20, magnitud=4.0))
        self.catalogo.crear_evento(evento(30, magnitud=6.5))
        self.catalogo.crear_evento(evento(5, magnitud=4.0))
        self.catalogo.crear_evento(evento(15, magnitud=4.0))
        ganadora = self.catalogo.listar_ramas_archivables()[0]
        self.assertEqual(len(ganadora.identificadores), 1)
        self.assertEqual(ganadora.id_raiz, 15)
        self.assertEqual(ganadora.profundidad, 2)
        self.catalogo.archivar_rama()
        self.assertEqual(self.catalogo.consultar(15)[0], "archivado")
        self.assertEqual(self.catalogo.consultar(5)[0], "activo")
        self.assertEqual(self.catalogo.consultar(10)[0], "activo")   

    def  test_sincronizacion_arboles_avl_y_bst(self) -> None:
        for identificador in (10,20,30):
            self.catalogo.crear_evento(evento(identificador))
        self.assertEqual([x.identificador for x in self.catalogo.avl.inorden()],
                        [y.identificador for y in self.catalogo.bst.inorden()])
        self.catalogo.corregir_evento(10, {"magnitud": 6.2, "profundidad_hipocentro": 15.0})
        self.assertEqual([x.identificador for x in self.catalogo.avl.inorden()],
                        [y.identificador for y in self.catalogo.bst.inorden()])
        self.catalogo.eliminar_evento(20)
        self.assertEqual([x.identificador for x in self.catalogo.avl.inorden()],
                        [y.identificador for y in self.catalogo.bst.inorden()])

    def test_casos_balanceo_RR(self) -> None:
        for identificador in (10,20,30):
            self.catalogo.crear_evento(evento(identificador))
        en_orden = self.catalogo.avl.auditar(exigir_balanceo= True)
        self.assertTrue(en_orden.balanceado)
        self.assertTrue(en_orden.orden_correcto)     
        self.assertEqual(self.catalogo.avl.casos_rr,1)
        self.assertEqual(self.catalogo.avl.casos_lr,0)
        self.assertEqual(self.catalogo.avl.casos_rl,0)
        self.assertEqual(self.catalogo.avl.casos_ll,0)

    def test_casos_balanceo_LL(self) -> None:
        for identificador in (30,20,10):
            self.catalogo.crear_evento(evento(identificador))
        en_orden = self.catalogo.avl.auditar(exigir_balanceo= True)    
        self.assertTrue(en_orden.orden_correcto)    
        self.assertTrue(en_orden.balanceado) 
        self.assertEqual(self.catalogo.avl.casos_rr,0)
        self.assertEqual(self.catalogo.avl.casos_lr,0)
        self.assertEqual(self.catalogo.avl.casos_rl,0)
        self.assertEqual(self.catalogo.avl.casos_ll,1)

    def test_casos_balanceo_RL(self) -> None:
        for identificador in (20,30,25):
            self.catalogo.crear_evento(evento(identificador))
        en_orden = self.catalogo.avl.auditar(exigir_balanceo= True)    
        self.assertTrue(en_orden.orden_correcto)
        self.assertTrue(en_orden.balanceado)
        self.assertEqual(self.catalogo.avl.casos_rr,0)
        self.assertEqual(self.catalogo.avl.casos_lr,0)
        self.assertEqual(self.catalogo.avl.casos_rl,1)
        self.assertEqual(self.catalogo.avl.casos_ll,0)

    def test_casos_balanceo_LR(self) -> None:
        for identificador in (30,20,25):
            self.catalogo.crear_evento(evento(identificador))
        en_orden = self.catalogo.avl.auditar(exigir_balanceo= True)    
        self.assertTrue(en_orden.orden_correcto)     
        self.assertTrue(en_orden.balanceado)
        self.assertEqual(self.catalogo.avl.casos_rr,0)
        self.assertEqual(self.catalogo.avl.casos_lr,1)
        self.assertEqual(self.catalogo.avl.casos_rl,0)
        self.assertEqual(self.catalogo.avl.casos_ll,0)

    def test_factor_nodo_desbalance(self) -> None:
        self.catalogo.activar_modo_estres()
        for identificador in(1,2,3,4,5,6,7,8,9,10,11,12):
            self.catalogo.crear_evento(evento(identificador))
        en_orden = self.catalogo.avl.auditar(exigir_balanceo= False)
        self.assertTrue(en_orden.orden_correcto)
        self.assertFalse(en_orden.balanceado)
        self.assertTrue(abs(self.catalogo.avl._factor(self.catalogo.avl.raiz))>2)
        self.catalogo.avl.recuperar_balance()
        arbol = self.catalogo.avl.auditar(exigir_balanceo=True)
        self.assertTrue(arbol.orden_correcto)
        self.assertTrue(arbol.balanceado)

    def test_exportar_escenario_completo_contiene_todos_los_elementos(self) -> None:
        # Create a non-trivial topology with different priorities
        self.catalogo.crear_evento(evento(10, magnitud=4.0, estacion="EST-01"))  # Low priority
        self.catalogo.crear_evento(evento(20, magnitud=5.0, estacion="EST-02"))  # Medium priority
        self.catalogo.crear_evento(evento(30, magnitud=6.5, estacion="EST-03"))  # High priority (>= 6.0)
        self.catalogo.crear_evento(evento(40, magnitud=4.8, profundidad_hipocentro=25.0, estacion="EST-04"))  # High priority (shallow + populated zone)

        # Enqueue a report - normalize the event first
        evento_reporte = evento(50, magnitud=5.5, estacion="EST-05")
        self.catalogo._normalizar_y_clasificar(evento_reporte)
        self.catalogo.encolar_reporte(Reporte(evento_reporte, "EST-05"))

        # Change parameters
        self.catalogo.parametros = {"W": 100, "R": 50, "L": 200, "T": 30}

        # Export the scenario
        datos = self.catalogo.exportar_escenario_completo()

        # Verify all required fields are present
        self.assertEqual(datos["version"], 1)
        self.assertEqual(datos["tipo_guardado"], "escenario_completo")
        self.assertIn("reloj", datos)
        self.assertIn("modo", datos)
        self.assertIn("cola_pausada", datos)
        self.assertIn("parametros", datos)
        self.assertIn("zonas", datos)
        self.assertIn("estaciones", datos)
        self.assertIn("avl", datos)
        self.assertIn("eventos_activos", datos)
        self.assertIn("eventos_historicos", datos)
        self.assertIn("ids_eliminados", datos)
        self.assertIn("cola_fifo", datos)
        self.assertIn("historial", datos)
        self.assertIn("metricas", datos)
        self.assertIn("estado_atencion", datos)
        self.assertIn("asociaciones", datos)

        # Verify AVL topology structure
        self.assertIn("raiz", datos["avl"])
        self.assertIn("nodos", datos["avl"])
        self.assertEqual(len(datos["avl"]["nodos"]), 4)  # 4 active events

        # Verify each node has required structural links
        for nodo_id, nodo_data in datos["avl"]["nodos"].items():
            self.assertIn("evento", nodo_data)
            self.assertIn("altura", nodo_data)
            self.assertIn("factor", nodo_data)
            self.assertIn("izquierdo", nodo_data)
            self.assertIn("derecho", nodo_data)

        # Verify events are in active index
        self.assertEqual(len(datos["eventos_activos"]), 4)
        for eid in [10, 20, 30, 40]:
            self.assertIn(eid, datos["eventos_activos"])

        # Verify queue has one report
        self.assertEqual(len(datos["cola_fifo"]), 1)

        # Verify parameters are exported
        self.assertEqual(datos["parametros"]["W"], 100)
        self.assertEqual(datos["parametros"]["R"], 50)
        self.assertEqual(datos["parametros"]["L"], 200)
        self.assertEqual(datos["parametros"]["T"], 30)

        # Verify stations are collected
        self.assertIn("EST-01", datos["estaciones"])
        self.assertIn("EST-02", datos["estaciones"])
        self.assertIn("EST-03", datos["estaciones"])
        self.assertIn("EST-04", datos["estaciones"])
        self.assertIn("EST-05", datos["estaciones"])

        # Verify JSON can be serialized by json.dumps
        json_str = json.dumps(datos)
        self.assertIsInstance(json_str, str)
        self.assertGreater(len(json_str), 0)

        # Verify round-trip: deserialize and check structure
        datos_cargados = json.loads(json_str)
        self.assertEqual(datos_cargados["version"], 1)
        self.assertEqual(len(datos_cargados["avl"]["nodos"]), 4)

    def test_cargar_por_inserciones_orden_ascendente(self) -> None:
        # Create a valid JSON for insertion mode
        datos = {
            "version": 1,
            "tipo_carga": "inserciones",
            "reloj": "2026-09-07T14:00:00Z",
            "modo": "normal",
            "zonas": [
                {
                    "nombre": "Ciudad",
                    "x_min": 0.0,
                    "x_max": 500.0,
                    "y_min": 0.0,
                    "y_max": 500.0,
                    "poblada": True,
                }
            ],
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
                    "identificador": 200,
                    "magnitud": 5.0,
                    "profundidad_hipocentro": 40.0,
                    "x": 200.0,
                    "y": 200.0,
                    "ocurrencia": "2026-09-07T13:00:00Z",
                    "revision": 1,
                    "estaciones": ["EST-20"],
                },
                {
                    "identificador": 300,
                    "magnitud": 6.0,
                    "profundidad_hipocentro": 50.0,
                    "x": 300.0,
                    "y": 300.0,
                    "ocurrencia": "2026-09-07T13:30:00Z",
                    "revision": 1,
                    "estaciones": ["EST-30"],
                },
            ],
        }

        # Load and verify statistics
        estadisticas = self.catalogo.cargar_por_inserciones(datos)
        self.assertIn("avl", estadisticas)
        self.assertIn("bst", estadisticas)
        self.assertEqual(len(self.catalogo.indice_activos), 3)
        self.assertIn(100, self.catalogo.indice_activos)
        self.assertIn(200, self.catalogo.indice_activos)
        self.assertIn(300, self.catalogo.indice_activos)

        # Verify AVL is balanced
        auditoria = self.catalogo.avl.auditar()
        self.assertTrue(auditoria.balanceado)

        # Verify keys are in ascending order
        claves_avl = [e.clave() for e in self.catalogo.avl.inorden()]
        self.assertEqual(claves_avl, sorted(claves_avl))

    def test_cargar_por_inserciones_id_duplicado_falla_atomicamente(self) -> None:
        # Create initial event
        self.catalogo.crear_evento(evento(10))

        # Try to load with duplicate ID in the same load
        datos = {
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
                    "identificador": 100,  # Duplicate ID
                    "magnitud": 5.0,
                    "profundidad_hipocentro": 40.0,
                    "x": 200.0,
                    "y": 200.0,
                    "ocurrencia": "2026-09-07T13:00:00Z",
                    "revision": 1,
                    "estaciones": ["EST-20"],
                },
            ],
        }

        # Should fail without modifying the scenario
        with self.assertRaises(ValueError) as context:
            self.catalogo.cargar_por_inserciones(datos)
        self.assertIn("duplicado", str(context.exception).lower())

        # Verify original scenario is unchanged
        self.assertEqual(len(self.catalogo.indice_activos), 1)
        self.assertIn(10, self.catalogo.indice_activos)
        self.assertNotIn(100, self.catalogo.indice_activos)

    def test_cargar_por_inserciones_id_existente_falla_atomicamente(self) -> None:
        # Create initial event
        self.catalogo.crear_evento(evento(10))

        # Try to load with ID that already exists in active events
        datos = {
            "version": 1,
            "tipo_carga": "inserciones",
            "reloj": "2026-09-07T14:00:00Z",
            "modo": "normal",
            "zonas": [],
            "eventos": [
                {
                    "identificador": 10,  # Already exists
                    "magnitud": 5.0,
                    "profundidad_hipocentro": 40.0,
                    "x": 200.0,
                    "y": 200.0,
                    "ocurrencia": "2026-09-07T13:00:00Z",
                    "revision": 1,
                    "estaciones": ["EST-20"],
                },
            ],
        }

        # Should fail without modifying the scenario
        with self.assertRaises(ValueError) as context:
            self.catalogo.cargar_por_inserciones(datos)
        self.assertIn("ya existe", str(context.exception).lower())

        # Verify original scenario is unchanged
        self.assertEqual(len(self.catalogo.indice_activos), 1)
        self.assertIn(10, self.catalogo.indice_activos)

    def test_cargar_por_inserciones_formato_invalido_falla(self) -> None:
        # Invalid version
        datos = {
            "version": 2,
            "tipo_carga": "inserciones",
            "reloj": "2026-09-07T14:00:00Z",
            "modo": "normal",
            "zonas": [],
            "eventos": [],
        }

        with self.assertRaises(ValueError):
            self.catalogo.cargar_por_inserciones(datos)

        # Invalid tipo_carga
        datos = {
            "version": 1,
            "tipo_carga": "topologia",
            "reloj": "2026-09-07T14:00:00Z",
            "modo": "normal",
            "zonas": [],
            "eventos": [],
        }

        with self.assertRaises(ValueError):
            self.catalogo.cargar_por_inserciones(datos)

    def test_cargar_por_topologia_valida_normal(self) -> None:
        # Create a valid balanced topology
        datos = {
            "version": 1,
            "tipo_carga": "topologia",
            "reloj": "2026-09-07T14:00:00Z",
            "modo": "normal",
            "zonas": [
                {
                    "nombre": "Ciudad",
                    "x_min": 0.0,
                    "x_max": 500.0,
                    "y_min": 0.0,
                    "y_max": 500.0,
                    "poblada": True,
                }
            ],
            "raiz": 20,
            "nodos": {
                10: {
                    "evento": {
                        "identificador": 10,
                        "magnitud": 4.0,
                        "profundidad_hipocentro": 50.0,
                        "x": 100.0,
                        "y": 100.0,
                        "ocurrencia": "2026-09-07T10:00:00Z",
                        "revision": 1,
                        "estaciones": ["EST-01"],
                    },
                    "altura": 0,
                    "izquierdo": None,
                    "derecho": None,
                },
                20: {
                    "evento": {
                        "identificador": 20,
                        "magnitud": 5.0,
                        "profundidad_hipocentro": 50.0,
                        "x": 200.0,
                        "y": 200.0,
                        "ocurrencia": "2026-09-07T11:00:00Z",
                        "revision": 1,
                        "estaciones": ["EST-02"],
                    },
                    "altura": 1,
                    "izquierdo": 10,
                    "derecho": None,
                },
            },
        }

        estadisticas = self.catalogo.cargar_por_topologia(datos)
        self.assertEqual(len(self.catalogo.indice_activos), 2)
        self.assertIn(10, self.catalogo.indice_activos)
        self.assertIn(20, self.catalogo.indice_activos)
        self.assertTrue(self.catalogo.avl.auditar().balanceado)

    def test_cargar_por_topologia_valida_estres(self) -> None:
        # Create an unbalanced topology (only allowed in stress mode)
        datos = {
            "version": 1,
            "tipo_carga": "topologia",
            "reloj": "2026-09-07T14:00:00Z",
            "modo": "estres",
            "zonas": [],
            "raiz": 30,
            "nodos": {
                10: {
                    "evento": {
                        "identificador": 10,
                        "magnitud": 4.0,
                        "profundidad_hipocentro": 50.0,
                        "x": 100.0,
                        "y": 100.0,
                        "ocurrencia": "2026-09-07T10:00:00Z",
                        "revision": 1,
                        "estaciones": ["EST-01"],
                    },
                    "altura": 0,
                    "izquierdo": None,
                    "derecho": None,
                },
                20: {
                    "evento": {
                        "identificador": 20,
                        "magnitud": 4.5,
                        "profundidad_hipocentro": 50.0,
                        "x": 150.0,
                        "y": 150.0,
                        "ocurrencia": "2026-09-07T10:30:00Z",
                        "revision": 1,
                        "estaciones": ["EST-02"],
                    },
                    "altura": 1,
                    "izquierdo": 10,
                    "derecho": None,
                },
                30: {
                    "evento": {
                        "identificador": 30,
                        "magnitud": 5.0,
                        "profundidad_hipocentro": 50.0,
                        "x": 200.0,
                        "y": 200.0,
                        "ocurrencia": "2026-09-07T11:00:00Z",
                        "revision": 1,
                        "estaciones": ["EST-03"],
                    },
                    "altura": 2,
                    "izquierdo": 20,
                    "derecho": None,
                },
            },
        }

        estadisticas = self.catalogo.cargar_por_topologia(datos)
        self.assertEqual(len(self.catalogo.indice_activos), 3)
        self.assertTrue(self.catalogo.modo_estres)
        # AVL should be unbalanced in stress mode
        self.assertFalse(self.catalogo.avl.auditar().balanceado)

    def test_cargar_por_topologia_referencia_rota_falla_atomicamente(self) -> None:
        # Create initial event
        self.catalogo.crear_evento(evento(10))

        # Try to load with broken reference
        datos = {
            "version": 1,
            "tipo_carga": "topologia",
            "reloj": "2026-09-07T14:00:00Z",
            "modo": "normal",
            "zonas": [],
            "raiz": 20,
            "nodos": {
                20: {
                    "evento": {
                        "identificador": 20,
                        "magnitud": 5.0,
                        "profundidad_hipocentro": 50.0,
                        "x": 200.0,
                        "y": 200.0,
                        "ocurrencia": "2026-09-07T11:00:00Z",
                        "revision": 1,
                        "estaciones": ["EST-02"],
                    },
                    "altura": 1,
                    "izquierdo": 999,  # Non-existent reference
                    "derecho": None,
                },
            },
        }

        with self.assertRaises(ValueError) as context:
            self.catalogo.cargar_por_topologia(datos)
        self.assertIn("inexistente", str(context.exception).lower())

        # Verify original scenario is unchanged
        self.assertEqual(len(self.catalogo.indice_activos), 1)
        self.assertIn(10, self.catalogo.indice_activos)
        self.assertNotIn(20, self.catalogo.indice_activos)

    def test_cargar_por_topologia_ciclo_falla_atomicamente(self) -> None:
        # Create initial event
        self.catalogo.crear_evento(evento(10))

        # Try to load with a cycle (100 -> 200 -> 100)
        datos = {
            "version": 1,
            "tipo_carga": "topologia",
            "reloj": "2026-09-07T14:00:00Z",
            "modo": "normal",
            "zonas": [],
            "raiz": 100,
            "nodos": {
                100: {
                    "evento": {
                        "identificador": 100,
                        "magnitud": 4.0,
                        "profundidad_hipocentro": 50.0,
                        "x": 100.0,
                        "y": 100.0,
                        "ocurrencia": "2026-09-07T10:00:00Z",
                        "revision": 1,
                        "estaciones": ["EST-01"],
                    },
                    "altura": 1,
                    "izquierdo": None,
                    "derecho": 200,
                },
                200: {
                    "evento": {
                        "identificador": 200,
                        "magnitud": 5.0,
                        "profundidad_hipocentro": 50.0,
                        "x": 200.0,
                        "y": 200.0,
                        "ocurrencia": "2026-09-07T11:00:00Z",
                        "revision": 1,
                        "estaciones": ["EST-02"],
                    },
                    "altura": 0,
                    "izquierdo": None,
                    "derecho": 100,  # Cycle back to 100
                },
            },
        }

        with self.assertRaises(ValueError) as context:
            self.catalogo.cargar_por_topologia(datos)
        self.assertIn("ciclo", str(context.exception).lower())

        # Verify original scenario is unchanged
        self.assertEqual(len(self.catalogo.indice_activos), 1)
        self.assertIn(10, self.catalogo.indice_activos)

    def test_cargar_por_topologia_orden_global_invalido_falla_atomicamente(self) -> None:
        # Create initial event
        self.catalogo.crear_evento(evento(10))

        # Try to load with invalid global BST order (right child has smaller key)
        # Parent: (2, 5.0, 300) - medium priority
        # Right child: (1, 4.0, 100) - lower priority, violates BST order
        datos = {
            "version": 1,
            "tipo_carga": "topologia",
            "reloj": "2026-09-07T14:00:00Z",
            "modo": "normal",
            "zonas": [],
            "raiz": 300,
            "nodos": {
                100: {
                    "evento": {
                        "identificador": 100,
                        "magnitud": 4.0,  # Low priority (1, 4.0, 100)
                        "profundidad_hipocentro": 50.0,
                        "x": 100.0,
                        "y": 100.0,
                        "ocurrencia": "2026-09-07T10:00:00Z",
                        "revision": 1,
                        "estaciones": ["EST-01"],
                    },
                    "altura": 0,
                    "izquierdo": None,
                    "derecho": None,
                },
                300: {
                    "evento": {
                        "identificador": 300,
                        "magnitud": 5.0,  # Medium priority (2, 5.0, 300)
                        "profundidad_hipocentro": 50.0,
                        "x": 200.0,
                        "y": 200.0,
                        "ocurrencia": "2026-09-07T11:00:00Z",
                        "revision": 1,
                        "estaciones": ["EST-02"],
                    },
                    "altura": 1,
                    "izquierdo": None,
                    "derecho": 100,  # Invalid: right child has smaller key
                },
            },
        }

        with self.assertRaises(ValueError) as context:
            self.catalogo.cargar_por_topologia(datos)
        self.assertIn("orden", str(context.exception).lower())

        # Verify original scenario is unchanged
        self.assertEqual(len(self.catalogo.indice_activos), 1)
        self.assertIn(10, self.catalogo.indice_activos)

    def test_cargar_por_topologia_altura_incorrecta_falla_atomicamente(self) -> None:
        # Create initial event
        self.catalogo.crear_evento(evento(10))

        # Try to load with incorrect height
        datos = {
            "version": 1,
            "tipo_carga": "topologia",
            "reloj": "2026-09-07T14:00:00Z",
            "modo": "normal",
            "zonas": [],
            "raiz": 200,
            "nodos": {
                100: {
                    "evento": {
                        "identificador": 100,
                        "magnitud": 4.0,
                        "profundidad_hipocentro": 50.0,
                        "x": 100.0,
                        "y": 100.0,
                        "ocurrencia": "2026-09-07T10:00:00Z",
                        "revision": 1,
                        "estaciones": ["EST-01"],
                    },
                    "altura": 0,
                    "izquierdo": None,
                    "derecho": None,
                },
                200: {
                    "evento": {
                        "identificador": 200,
                        "magnitud": 5.0,
                        "profundidad_hipocentro": 50.0,
                        "x": 200.0,
                        "y": 200.0,
                        "ocurrencia": "2026-09-07T11:00:00Z",
                        "revision": 1,
                        "estaciones": ["EST-02"],
                    },
                    "altura": 5,  # Incorrect: should be 1
                    "izquierdo": 100,
                    "derecho": None,
                },
            },
        }

        with self.assertRaises(ValueError) as context:
            self.catalogo.cargar_por_topologia(datos)
        self.assertIn("altura", str(context.exception).lower())

        # Verify original scenario is unchanged
        self.assertEqual(len(self.catalogo.indice_activos), 1)
        self.assertIn(10, self.catalogo.indice_activos)

    def tearDown(self) -> None:
        """Clean up version files created during tests."""
        import shutil
        from pathlib import Path

        versiones_dir = Path("versiones")
        if versiones_dir.exists():
            for archivo in versiones_dir.glob("*.json"):
                if archivo.name != ".gitkeep":
                    archivo.unlink()

    def test_guardar_y_restaurar_version(self) -> None:
        # Create initial events
        self.catalogo.crear_evento(evento(10))
        self.catalogo.crear_evento(evento(20))
        self.catalogo.parametros["W"] = 4.5
        self.catalogo.metricas["correcciones_aceptadas"] = 5

        # Save version
        ruta = self.catalogo.guardar_version("test_guardar_restaurar")
        self.assertIn("versiones/test_guardar_restaurar.json", ruta.replace("\\", "/"))

        # Modify catalog
        self.catalogo.crear_evento(evento(30))
        self.catalogo.parametros["W"] = 6.0
        self.catalogo.metricas["correcciones_aceptadas"] = 10

        # Verify catalog has changed
        self.assertEqual(len(self.catalogo.indice_activos), 3)
        self.assertEqual(self.catalogo.parametros["W"], 6.0)
        self.assertEqual(self.catalogo.metricas["correcciones_aceptadas"], 10)

        # Restore version
        self.catalogo.restaurar_version("test_guardar_restaurar")

        # Verify catalog is restored
        self.assertEqual(len(self.catalogo.indice_activos), 2)
        self.assertIn(10, self.catalogo.indice_activos)
        self.assertIn(20, self.catalogo.indice_activos)
        self.assertNotIn(30, self.catalogo.indice_activos)
        self.assertEqual(self.catalogo.parametros["W"], 4.5)
        self.assertEqual(self.catalogo.metricas["correcciones_aceptadas"], 5)

    def test_sobrescribir_version_falla(self) -> None:
        # Save a version
        self.catalogo.guardar_version("test_sobrescribir")

        # Try to save with the same name
        with self.assertRaises(ValueError) as context:
            self.catalogo.guardar_version("test_sobrescribir")
        self.assertIn("ya existe", str(context.exception).lower())

    def test_restaurar_version_toma_instantanea(self) -> None:
        # Create initial event
        self.catalogo.crear_evento(evento(10))

        # Save version
        self.catalogo.guardar_version("test_instantanea")

        # Modify catalog
        self.catalogo.crear_evento(evento(20))

        # Restore version (should take snapshot before restoring)
        self.catalogo.restaurar_version("test_instantanea")

        # Verify only one event after restore
        self.assertEqual(len(self.catalogo.indice_activos), 1)

        # Undo the restore (should return to state with 2 events)
        self.catalogo.deshacer()
        self.assertEqual(len(self.catalogo.indice_activos), 2)
        self.assertIn(10, self.catalogo.indice_activos)
        self.assertIn(20, self.catalogo.indice_activos)

    def test_listar_versiones(self) -> None:
        # Initially no versions (except .gitkeep which is filtered)
        versiones = self.catalogo.listar_versiones()
        self.assertEqual(len(versiones), 0)

        # Save some versions
        self.catalogo.guardar_version("version_list_1")
        self.catalogo.guardar_version("version_list_2")
        self.catalogo.guardar_version("version_list_3")

        # List versions
        versiones = self.catalogo.listar_versiones()
        self.assertEqual(len(versiones), 3)
        self.assertIn("version_list_1", versiones)
        self.assertIn("version_list_2", versiones)
        self.assertIn("version_list_3", versiones)

    def test_restaurar_version_inexistente_falla(self) -> None:
        with self.assertRaises(ValueError) as context:
            self.catalogo.restaurar_version("version_inexistente")
        self.assertIn("no existe", str(context.exception).lower())

    # ------------------------------------------------------------------
    # C1 - scenario: initial W/R/L/T, cambiar_parametro, station registry.
    # ------------------------------------------------------------------

    def test_parametros_iniciales_del_escenario(self) -> None:
        self.assertEqual(self.catalogo.parametros["W"], Decimal("48"))
        self.assertEqual(self.catalogo.parametros["R"], Decimal("40"))
        self.assertEqual(self.catalogo.parametros["L"], 3)
        self.assertEqual(self.catalogo.parametros["T"], Decimal("4320"))

    def test_cambiar_parametro_valido_es_una_sola_accion_deshacible(self) -> None:
        cantidad_antes = len(self.catalogo.historial)
        self.catalogo.cambiar_parametro("W", 100)
        self.assertEqual(self.catalogo.parametros["W"], Decimal("100"))
        self.assertEqual(len(self.catalogo.historial), cantidad_antes + 1)
        self.assertEqual(self.catalogo.deshacer(), "Deshecho: Cambiar parametro W")
        self.assertEqual(self.catalogo.parametros["W"], Decimal("48"))

    def test_cambiar_parametro_invalido_no_muta_ni_registra_instantanea(self) -> None:
        cantidad_antes = len(self.catalogo.historial)
        for nombre, valor in (("W", 0), ("R", -1), ("T", 0), ("L", -1), ("L", 2.5), ("Z", 5)):
            with self.assertRaises(ValueError):
                self.catalogo.cambiar_parametro(nombre, valor)
        self.assertEqual(len(self.catalogo.historial), cantidad_antes)
        self.assertEqual(self.catalogo.parametros["W"], Decimal("48"))

    def test_estaciones_sin_configurar_es_permisivo(self) -> None:
        # Default registry is empty: no station membership is enforced (risk 1
        # in docs/ANALISIS_REQUISITOS_C1_C6_SAMUEL.md, to not break existing callers).
        self.catalogo.crear_evento(evento(10, estacion="EST-CUALQUIERA"))
        self.assertIn(10, self.catalogo.indice_activos)

    def test_estacion_no_configurada_se_rechaza_cuando_hay_registro(self) -> None:
        catalogo = CatalogoSismico(self.zonas, RELOJ, estaciones=["EST-01", "EST-02"])
        with self.assertRaises(ValueError):
            catalogo.crear_evento(evento(10, estacion="EST-FANTASMA"))
        self.assertEqual(catalogo.indice_activos, {})
        catalogo.crear_evento(evento(10, estacion="EST-01"))
        self.assertIn(10, catalogo.indice_activos)

    def test_configurar_estaciones_rechaza_vacias_y_duplicadas(self) -> None:
        with self.assertRaises(ValueError):
            self.catalogo.configurar_estaciones(["EST-01", ""])
        with self.assertRaises(ValueError):
            self.catalogo.configurar_estaciones(["EST-01", "EST-01"])
        self.catalogo.configurar_estaciones(["EST-01", "EST-02"])
        self.assertEqual(self.catalogo.estaciones, frozenset({"EST-01", "EST-02"}))

    def test_deshacer_restaura_el_registro_de_estaciones(self) -> None:
        self.catalogo.configurar_estaciones(["EST-01"])
        self.catalogo.configurar_estaciones(["EST-02", "EST-03"])
        self.catalogo.deshacer()
        self.assertEqual(self.catalogo.estaciones, frozenset({"EST-01"}))    

    # ------------------------------------------------------------------
    # C2 - associations (PDF section 7, policy A2).
    # ------------------------------------------------------------------

    def test_candidato_valido_se_asocia_como_referencia(self) -> None:
        self.catalogo.crear_evento(evento(1, magnitud=6.5, x=100.0, y=100.0, ocurrencia="2026-09-07T09:00:00Z"))
        self.catalogo.crear_evento(evento(2, magnitud=5.0, x=105.0, y=100.0, ocurrencia="2026-09-07T10:00:00Z"))
        self.assertEqual(self.catalogo.asociaciones[2].candidatos, (1,))
        self.assertEqual(self.catalogo.asociaciones[2].referencia_elegida, 1)
        self.assertEqual(self.catalogo.asociaciones[1].candidatos, ())

    def test_no_candidato_por_igual_magnitud(self) -> None:
        # Same magnitude (not strictly greater) must not qualify, even if earlier.
        self.catalogo.crear_evento(evento(1, magnitud=5.0, ocurrencia="2026-09-07T09:00:00Z"))
        self.catalogo.crear_evento(evento(2, magnitud=5.0, ocurrencia="2026-09-07T10:00:00Z"))
        self.assertEqual(self.catalogo.asociaciones[2].candidatos, ())

    def test_no_candidato_fuera_de_distancia_r(self) -> None:
        # Farther than R km must not qualify even with higher magnitude and earlier time.
        self.catalogo.crear_evento(evento(3, magnitud=6.0, x=900.0, y=900.0, ocurrencia="2026-09-07T08:00:00Z"))
        self.catalogo.crear_evento(evento(4, magnitud=4.0, x=100.0, y=100.0, ocurrencia="2026-09-07T11:00:00Z"))
        self.assertEqual(self.catalogo.asociaciones[4].candidatos, ())

    def test_limite_w_y_r_son_inclusivos(self) -> None:
        # Exactly R km apart (40 km) and exactly W hours apart (48h) must still qualify.
        self.catalogo.crear_evento(evento(1, magnitud=6.0, x=0.0, y=0.0, ocurrencia="2026-09-05T12:00:00Z"))
        self.catalogo.crear_evento(evento(2, magnitud=4.0, x=40.0, y=0.0, ocurrencia="2026-09-07T12:00:00Z"))
        self.assertEqual(self.catalogo.asociaciones[2].referencia_elegida, 1)

    def test_politica_a2_desempate_magnitud_luego_tiempo_luego_id(self) -> None:
        self.catalogo.crear_evento(evento(10, magnitud=5.2, ocurrencia="2026-09-07T11:00:00Z"))  # A1: closest, ties A3 on magnitude
        self.catalogo.crear_evento(evento(20, magnitud=5.0, ocurrencia="2026-09-07T11:50:00Z"))  # A2: loses on magnitude
        self.catalogo.crear_evento(evento(30, magnitud=5.2, ocurrencia="2026-09-07T10:00:00Z"))  # A3: ties A1 on magnitude, farther in time
        self.catalogo.crear_evento(evento(99, magnitud=4.0, ocurrencia="2026-09-07T12:00:00Z"))
        self.assertEqual(self.catalogo.asociaciones[99].referencia_elegida, 10)

    def test_eliminado_no_es_candidato_pero_archivado_si(self) -> None:
        self.catalogo.parametros["T"] = 60
        self.catalogo.crear_evento(evento(1, magnitud=4.0, ocurrencia="2026-09-07T09:00:00Z"))
        self.catalogo.archivar_rama()
        self.catalogo.crear_evento(evento(2, magnitud=6.0, x=0.0, y=0.0, ocurrencia="2026-09-07T08:00:00Z"))
        self.catalogo.crear_evento(evento(3, magnitud=4.0, x=0.0, y=0.0, ocurrencia="2026-09-07T10:00:00Z"))
        self.assertEqual(self.catalogo.asociaciones[3].referencia_elegida, 2)
        self.catalogo.eliminar_evento(2)
        self.assertNotIn(2, self.catalogo.asociaciones[3].candidatos)

    def test_rotacion_avl_no_cambia_asociaciones(self) -> None:
        self.catalogo.crear_evento(evento(1, magnitud=6.5, x=100.0, y=100.0, ocurrencia="2026-09-07T09:00:00Z"))
        self.catalogo.crear_evento(evento(2, magnitud=5.0, x=105.0, y=100.0, ocurrencia="2026-09-07T10:00:00Z"))
        antes = self.catalogo.asociaciones[2].referencia_elegida
        # Force rotations with unrelated low-priority, far-away events.
        for identificador, magnitud in ((3, 1.0), (4, 1.0), (5, 1.0)):
            self.catalogo.crear_evento(evento(identificador, magnitud=magnitud, x=900.0, y=900.0, ocurrencia="2026-09-07T08:00:00Z"))
        self.assertGreaterEqual(self.catalogo.avl.giros_izquierda + self.catalogo.avl.giros_derecha, 1)
        self.assertEqual(self.catalogo.asociaciones[2].referencia_elegida, antes)

    def test_cambiar_w_o_r_recalcula_y_deshacer_restaura(self) -> None:
        self.catalogo.crear_evento(evento(1, magnitud=6.5, x=100.0, y=100.0, ocurrencia="2026-09-07T09:00:00Z"))
        self.catalogo.crear_evento(evento(2, magnitud=5.0, x=105.0, y=100.0, ocurrencia="2026-09-07T10:00:00Z"))
        self.catalogo.cambiar_parametro("R", 1)
        self.assertEqual(self.catalogo.asociaciones[2].candidatos, ())
        self.catalogo.deshacer()
        self.assertEqual(self.catalogo.asociaciones[2].referencia_elegida, 1)

    def test_correccion_recalcula_asociaciones_afectadas(self) -> None:
        self.catalogo.crear_evento(evento(1, magnitud=6.5, x=100.0, y=100.0, ocurrencia="2026-09-07T09:00:00Z"))
        self.catalogo.crear_evento(evento(2, magnitud=5.0, x=105.0, y=100.0, ocurrencia="2026-09-07T10:00:00Z"))
        self.assertEqual(self.catalogo.asociaciones[2].referencia_elegida, 1)
        # Moving event 1 far away removes it as a candidate for event 2.
        self.catalogo.corregir_evento(1, {"x": Decimal("900.0"), "y": Decimal("900.0")})
        self.assertEqual(self.catalogo.asociaciones[2].candidatos, ())

    # ------------------------------------------------------------------
    # C3 - queries (PDF section 11): every query reports nodes examined.
    # ------------------------------------------------------------------

    def test_consultar_top_k_pendientes_orden_descendente_y_salta_revisados(self) -> None:
        for identificador in (30, 20, 10, 40, 50):
            self.catalogo.crear_evento(evento(identificador, magnitud=4.0))
        self.catalogo.marcar_revisado(20)
        resultado = self.catalogo.consultar_top_k_pendientes(2)
        self.assertEqual([e.identificador for e in resultado.resultados], [50, 40])
        self.assertGreaterEqual(resultado.nodos_examinados, 2)

    def test_consultar_top_k_pendientes_rechaza_k_invalido(self) -> None:
        for k in (0, -1, 2.5):
            with self.assertRaises(ValueError):
                self.catalogo.consultar_top_k_pendientes(k)

    def test_consultar_por_magnitud_intervalo_inclusivo(self) -> None:
        for identificador, magnitud in ((1, 4.5), (2, 6.0), (3, 6.1), (4, 4.4)):
            self.catalogo.crear_evento(evento(identificador, magnitud=magnitud))
        resultado = self.catalogo.consultar_por_magnitud(4.5, 6.0)
        self.assertEqual(sorted(e.identificador for e in resultado.resultados), [1, 2])
        self.assertEqual(resultado.nodos_examinados, 4)

    def test_consultar_por_profundidad_y_fecha_limites_inclusivos(self) -> None:
        self.catalogo.crear_evento(evento(1, profundidad_hipocentro=30.0, ocurrencia="2026-09-07T10:00:00Z"))
        self.catalogo.crear_evento(evento(2, profundidad_hipocentro=31.0, ocurrencia="2026-09-07T10:00:00Z"))
        resultado = self.catalogo.consultar_por_profundidad_y_fecha(
            30.0, "2026-09-07T10:00:00Z", "2026-09-07T10:00:00Z"
        )
        self.assertEqual([e.identificador for e in resultado.resultados], [1])
        with self.assertRaises(ValueError):
            self.catalogo.consultar_por_profundidad_y_fecha(30.0, "2026-09-07T11:00:00Z", "2026-09-07T10:00:00Z")

    def test_consultar_asociaciones_no_usa_el_avl(self) -> None:
        self.catalogo.crear_evento(evento(1, magnitud=6.5, x=100.0, y=100.0, ocurrencia="2026-09-07T09:00:00Z"))
        self.catalogo.crear_evento(evento(2, magnitud=5.0, x=105.0, y=100.0, ocurrencia="2026-09-07T10:00:00Z"))
        resultado = self.catalogo.consultar_asociaciones(2)
        self.assertEqual(resultado.nodos_examinados, 0)
        datos = resultado.resultados[0]
        self.assertEqual(datos["referencia_elegida"]["identificador"], 1)
        self.assertEqual([c["identificador"] for c in datos["candidatos"]], [1])

        resultado_inverso = self.catalogo.consultar_asociaciones(1)
        self.assertEqual(
            [r["identificador"] for r in resultado_inverso.resultados[0]["referenciado_por"]], [2]
        )

    def test_consultar_asociaciones_id_eliminado_no_participa(self) -> None:
        self.catalogo.crear_evento(evento(1))
        self.catalogo.eliminar_evento(1)
        resultado = self.catalogo.consultar_asociaciones(1)
        self.assertEqual(resultado.nodos_examinados, 0)
        self.assertIn("mensaje", resultado.resultados[0])

    def test_consultar_acceso_costoso_reporta_profundidad_y_busqueda(self) -> None:
        self.catalogo.parametros["L"] = 0
        for identificador in (10, 20, 30):
            self.catalogo.crear_evento(evento(identificador))
        resultado = self.catalogo.consultar_acceso_costoso()
        self.assertEqual(sorted(r["identificador"] for r in resultado.resultados), [10, 30])
        self.assertTrue(all(r["profundidad_nodo"] > 0 for r in resultado.resultados))
        self.assertTrue(all(r["nodos_visitados_busqueda"] >= 1 for r in resultado.resultados))

    # ------------------------------------------------------------------
    # C4 - remaining section 6/9 gaps: full per-event lookup, archive metrics.
    # ------------------------------------------------------------------

    def test_consultar_detalle_evento_activo_incluye_posicion_avl_y_asociaciones(self) -> None:
        for identificador in (30, 20, 10, 40, 50):
            self.catalogo.crear_evento(evento(identificador, magnitud=4.0))
        detalle = self.catalogo.consultar_detalle(20)
        for campo in ("profundidad_nodo", "altura_nodo", "factor_balance", "acceso_costoso", "asociaciones", "clave"):
            self.assertIn(campo, detalle)
        self.assertEqual(detalle["estado"], "activo")

    def test_consultar_detalle_desconocido_y_eliminado(self) -> None:
        self.assertEqual(self.catalogo.consultar_detalle(99999)["estado"], "desconocido")
        self.catalogo.crear_evento(evento(1))
        self.catalogo.eliminar_evento(1)
        detalle = self.catalogo.consultar_detalle(1)
        self.assertEqual(detalle["estado"], "eliminado")
        self.assertIn("mensaje", detalle)
        self.assertEqual(detalle["magnitud"], Decimal("4.5"))
        self.assertNotIn("profundidad_nodo", detalle)
        self.catalogo.deshacer()
        self.assertNotIn(1, self.catalogo.cuerpos_eliminados)
        self.assertEqual(self.catalogo.consultar(1)[0], "activo")

    def test_version_restaura_estaciones_y_cuerpo_eliminado(self) -> None:
        from pathlib import Path

        self.catalogo.configurar_estaciones(["EST-01"])
        self.catalogo.crear_evento(evento(8, magnitud=4.0))
        self.catalogo.eliminar_evento(8)
        try:
            self.catalogo.guardar_version("test_registro_eliminados")
            self.catalogo.configurar_estaciones(["EST-09"])
            self.catalogo.restaurar_version("test_registro_eliminados")
            self.assertEqual(self.catalogo.estaciones, frozenset({"EST-01"}))
            estado, cuerpo = self.catalogo.consultar(8)
            self.assertEqual(estado, "eliminado")
            self.assertIsNotNone(cuerpo)
            self.assertEqual(cuerpo.magnitud, Decimal("4.0"))
        finally:
            Path("versiones/test_registro_eliminados.json").unlink(missing_ok=True)

    def test_archivar_rama_incrementa_metricas_c4(self) -> None:
        self.catalogo.parametros["T"] = 60
        for identificador in (10, 20, 30):
            self.catalogo.crear_evento(evento(identificador, magnitud=4.0))
        self.catalogo.archivar_rama()
        self.assertEqual(self.catalogo.metricas["archivos_masivos"], 1)
        self.assertEqual(self.catalogo.metricas["eventos_archivados"], 3)

    # ------------------------------------------------------------------
    # C5 - queue: conflict and archived-reactivation, explicit unit coverage
    # (the full alta/confirmacion/antiguo/correccion flow already has a
    # fixture-driven demo in tests/fixtures/rafagas_fifo.json and the Tk queue
    # window in interfaz.py).
    # ------------------------------------------------------------------

    def test_reporte_conflicto_misma_revision_datos_distintos(self) -> None:
        self.catalogo.crear_evento(evento(10, magnitud=4.5))
        self.catalogo.encolar_reporte(Reporte(evento(10, magnitud=5.0, estacion="EST-02"), "EST-02"))
        self.assertEqual(self.catalogo.procesar_siguiente_reporte(), "conflicto: misma revision con datos distintos")
        self.assertEqual(str(self.catalogo.indice_activos[10].magnitud), "4.5")
        self.assertEqual(self.catalogo.metricas["conflictos"], 1)

    def test_reporte_con_revision_mayor_reactiva_evento_archivado(self) -> None:
        self.catalogo.parametros["T"] = 60
        self.catalogo.crear_evento(evento(10, magnitud=4.0))
        self.catalogo.archivar_rama()
        self.assertEqual(self.catalogo.consultar(10)[0], "archivado")
        reporte = Reporte(evento(10, magnitud=4.2, revision=2, estacion="EST-02"), "EST-02")
        self.catalogo.encolar_reporte(reporte)
        self.assertEqual(self.catalogo.procesar_siguiente_reporte(), "reactivado desde historico")
        self.assertEqual(self.catalogo.consultar(10)[0], "activo")
        self.assertEqual(str(self.catalogo.indice_activos[10].magnitud), "4.2")

    def test_reporte_antiguo_no_reactiva_evento_archivado(self) -> None:
        self.catalogo.parametros["T"] = 60
        self.catalogo.crear_evento(evento(10, magnitud=4.0, revision=2))
        self.catalogo.archivar_rama()
        reporte = Reporte(evento(10, magnitud=4.9, revision=1, estacion="EST-02"), "EST-02")
        self.catalogo.encolar_reporte(reporte)
        self.assertEqual(
            self.catalogo.procesar_siguiente_reporte(), "descartado: reporte archivado no es una revision mayor"
        )
        self.assertEqual(self.catalogo.consultar(10)[0], "archivado")

    # ------------------------------------------------------------------
    # C6 - mandatory minimal cases 1-3 (PDF section 16).
    # ------------------------------------------------------------------

    def test_caso16_1_limites_de_prioridad_y_zona(self) -> None:
        self.catalogo.crear_evento(evento(1, magnitud=4.5, profundidad_hipocentro=30.0, x=100, y=100))
        self.assertEqual(self.catalogo.indice_activos[1].prioridad, 3)  # M=4.5, H=30.0, zona poblada
        self.catalogo.crear_evento(evento(2, magnitud=4.5, profundidad_hipocentro=30.0, x=900, y=900))
        self.assertEqual(self.catalogo.indice_activos[2].prioridad, 2)  # same M/H, outside the zone
        self.catalogo.crear_evento(evento(3, magnitud=6.0, profundidad_hipocentro=700.0, x=900, y=900))
        self.assertEqual(self.catalogo.indice_activos[3].prioridad, 3)  # M=6.0 alone is enough
        self.catalogo.crear_evento(evento(4, magnitud=5.0, profundidad_hipocentro=30.0, x=500, y=100))  # on the zone border
        self.assertTrue(self.catalogo.indice_activos[4].en_zona_poblada)
        # Tie on priority and magnitude: id breaks the tie in the AVL order.
        self.catalogo.crear_evento(evento(5, magnitud=4.5, profundidad_hipocentro=30.0, x=100, y=100))
        claves = [e.clave() for e in self.catalogo.avl.inorden()]
        self.assertEqual(claves, sorted(claves))

    def test_caso16_2_correccion_y_reporte_antiguo_no_revierte(self) -> None:
        self.catalogo.crear_evento(evento(1, magnitud=4.8, profundidad_hipocentro=70.0, revision=1))
        self.assertEqual(self.catalogo.indice_activos[1].prioridad, 2)
        self.catalogo.corregir_evento(1, {"magnitud": 6.2, "profundidad_hipocentro": 15.0})
        self.assertEqual(self.catalogo.indice_activos[1].prioridad, 3)
        self.catalogo.encolar_reporte(
            Reporte(evento(1, magnitud=6.2, profundidad_hipocentro=15.0, revision=1, estacion="EST-02"), "EST-02")
        )
        self.assertEqual(self.catalogo.procesar_siguiente_reporte(), "descartado: reporte antiguo")
        self.assertEqual(str(self.catalogo.indice_activos[1].magnitud), "6.2")
        self.assertEqual(sum(1 for e in self.catalogo.avl.inorden() if e.identificador == 1), 1)

    def test_caso16_3_reporte_tardio_cambia_candidatos(self) -> None:
        self.catalogo.crear_evento(evento(1, magnitud=5.6, x=100, y=100, ocurrencia="2026-09-07T10:00:00Z"))
        self.catalogo.crear_evento(evento(2, magnitud=4.2, x=100, y=100, ocurrencia="2026-09-07T10:20:00Z"))
        # Before the late report: event 1 (bigger, earlier) is already event 2's reference.
        self.assertEqual(self.catalogo.asociaciones[1].candidatos, ())
        self.assertEqual(self.catalogo.asociaciones[2].referencia_elegida, 1)
        # Late report: a bigger quake that actually happened even earlier arrives last,
        # and must displace event 1 as the chosen reference for both.
        self.catalogo.crear_evento(evento(3, magnitud=6.1, x=100, y=100, ocurrencia="2026-09-07T09:55:00Z"))
        self.assertEqual(self.catalogo.asociaciones[1].referencia_elegida, 3)
        self.assertEqual(self.catalogo.asociaciones[2].referencia_elegida, 3)
        self.assertIn(3, self.catalogo.asociaciones[2].candidatos)

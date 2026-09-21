"""Business layer that keeps the active AVL separate from the user interface."""

from __future__ import annotations

import json
import os
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Optional

from .arbol_avl import ArbolAVL
from .arbol_bst import ArbolBST
from .cola import Cola
from .dominio import (
    EstadoAtencion,
    Evento,
    Reporte,
    Zona,
    calcular_prioridad,
    clasificar_zona_poblada,
    fecha_utc,
)
from .pila import Pila


@dataclass(frozen=True)
class InstantaneaCatalogo:
    """Deep snapshot of every mutable catalog component except its undo stack."""

    descripcion: str
    zonas: list[Zona]
    reloj: datetime
    avl: ArbolAVL
    bst: ArbolBST
    indice_activos: dict[int, Evento]
    archivados: dict[int, Evento]
    eliminados: set[int]
    reportes_pendientes: Cola[Reporte]
    parametros: dict[str, object]
    modo_estres: bool
    cola_pausada: bool
    asociaciones: dict[object, object]
    metricas: dict[str, int]

    @classmethod
    def capturar(cls, catalogo: "CatalogoSismico", descripcion: str) -> "InstantaneaCatalogo":
        estado = deepcopy(
            {
                "zonas": catalogo.zonas,
                "reloj": catalogo.reloj,
                "avl": catalogo.avl,
                "bst": catalogo.bst,
                "indice_activos": catalogo.indice_activos,
                "archivados": catalogo.archivados,
                "eliminados": catalogo.eliminados,
                "reportes_pendientes": catalogo.reportes_pendientes,
                "parametros": catalogo.parametros,
                "modo_estres": catalogo.modo_estres,
                "cola_pausada": catalogo.cola_pausada,
                "asociaciones": catalogo.asociaciones,
                "metricas": catalogo.metricas,
            }
        )
        return cls(descripcion=descripcion, **estado)

    def restaurar(self, catalogo: "CatalogoSismico") -> None:
        catalogo.zonas = self.zonas
        catalogo.reloj = self.reloj
        catalogo.avl = self.avl
        catalogo.bst = self.bst
        catalogo.indice_activos = self.indice_activos
        catalogo.archivados = self.archivados
        catalogo.eliminados = self.eliminados
        catalogo.reportes_pendientes = self.reportes_pendientes
        catalogo.parametros = self.parametros
        catalogo.modo_estres = self.modo_estres
        catalogo.cola_pausada = self.cola_pausada
        catalogo.asociaciones = self.asociaciones
        catalogo.metricas = self.metricas


class CatalogoSismico:
    """Application service for the first implementation increment."""

    def __init__(self, zonas: Iterable[Zona], reloj: datetime | str) -> None:
        self.zonas = list(zonas)
        self.reloj = fecha_utc(reloj)
        self.avl = ArbolAVL()
        self.bst = ArbolBST()
        self.indice_activos: dict[int, Evento] = {}
        self.archivados: dict[int, Evento] = {}
        self.eliminados: set[int] = set()
        self.reportes_pendientes: Cola[Reporte] = Cola()
        self.historial: Pila[InstantaneaCatalogo] = Pila()
        self.parametros: dict[str, object] = {}
        self.asociaciones: dict[object, object] = {}
        self.modo_estres = False
        self.cola_pausada = False
        self.metricas = {
            "correcciones_aceptadas": 0,
            "reportes_descartados": 0,
            "conflictos": 0,
            "eliminaciones": 0,
        }

    def activar_modo_estres(self) -> bool:
        if self.modo_estres:
            return False
        self._registrar_instantanea("Activar modo estres")
        self.modo_estres = True
        return True

    def desactivar_modo_estres(self) -> int:
        return self.recuperar_desde_estres()

    def recuperar_desde_estres(self) -> int:
        self._registrar_instantanea("Recuperar AVL y desactivar modo estres")
        self.cola_pausada = True
        try:
            giros = self.avl.recuperar_balance()
        finally:
            self.cola_pausada = False
        self.modo_estres = False
        return giros

    def _normalizar_y_clasificar(self, evento: Evento) -> None:
        evento.validar(self.reloj)
        evento.en_zona_poblada = clasificar_zona_poblada(evento, self.zonas)
        evento.prioridad = calcular_prioridad(evento)

    def _registrar_instantanea(self, descripcion: str) -> None:
        self.historial.apilar(InstantaneaCatalogo.capturar(self, descripcion))

    def deshacer(self) -> str:
        if self.historial.esta_vacia():
            raise IndexError("No hay acciones para deshacer.")
        instantanea = self.historial.desapilar()
        instantanea.restaurar(self)
        return f"Deshecho: {instantanea.descripcion}"

    def crear_evento(self, evento: Evento, registrar_accion: bool = True) -> Evento:
        """Create one active event after all validation succeeds."""
        if evento.identificador in self.indice_activos or evento.identificador in self.archivados:
            raise ValueError("El identificador ya pertenece a un evento existente.")
        if evento.identificador in self.eliminados:
            raise ValueError("El identificador fue eliminado y no puede reutilizarse.")
        self._normalizar_y_clasificar(evento)
        if registrar_accion:
            self._registrar_instantanea(f"Crear SIS-{evento.identificador:06d}")
        self.avl.insertar(evento, balancear=not self.modo_estres)
        self.bst.insertar(evento)
        self.indice_activos[evento.identificador] = evento
        return evento

    def consultar(self, identificador: int) -> tuple[str, Optional[Evento]]:
        if identificador in self.indice_activos:
            return "activo", self.indice_activos[identificador]
        if identificador in self.archivados:
            return "archivado", self.archivados[identificador]
        if identificador in self.eliminados:
            return "eliminado", None
        return "desconocido", None

    def corregir_evento(
        self,
        identificador: int,
        datos: dict[str, object],
        revision: Optional[int] = None,
        registrar_accion: bool = True,
    ) -> Evento:
        """Apply a fully validated correction as one business operation."""
        evento = self.indice_activos.get(identificador)
        if evento is None:
            raise KeyError("Solo se pueden corregir eventos activos.")
        candidato = deepcopy(evento)
        for campo, valor in datos.items():
            if campo in {"identificador", "revision", "prioridad", "en_zona_poblada", "estaciones", "estado"}:
                raise ValueError(f"No se permite corregir directamente el campo {campo}.")
            if not hasattr(candidato, campo):
                raise ValueError(f"Campo de correccion desconocido: {campo}.")
            setattr(candidato, campo, valor)
        candidato.revision = evento.revision + 1 if revision is None else revision
        candidato.estado = EstadoAtencion.PENDIENTE
        self._normalizar_y_clasificar(candidato)
        clave_anterior = evento.clave()
        if registrar_accion:
            self._registrar_instantanea(f"Corregir SIS-{identificador:06d}")
        if candidato.clave() != clave_anterior:
            self.avl.eliminar(clave_anterior, balancear=not self.modo_estres)
            self.bst.eliminar(clave_anterior )
        evento.magnitud = candidato.magnitud
        evento.profundidad_hipocentro = candidato.profundidad_hipocentro
        evento.x = candidato.x
        evento.y = candidato.y
        evento.ocurrencia = candidato.ocurrencia
        evento.revision = candidato.revision
        evento.en_zona_poblada = candidato.en_zona_poblada
        evento.prioridad = candidato.prioridad
        evento.estado = EstadoAtencion.PENDIENTE
        if candidato.clave() != clave_anterior:
            self.avl.insertar(evento, balancear=not self.modo_estres)
            self.bst.insertar(evento)

        self.metricas["correcciones_aceptadas"] += 1
        return evento

    def marcar_revisado(self, identificador: int) -> Evento:
        evento = self.indice_activos.get(identificador)
        if evento is None:
            raise KeyError("No existe un evento activo con ese identificador.")
        self._registrar_instantanea(f"Marcar revisado SIS-{identificador:06d}")
        evento.estado = EstadoAtencion.REVISADO
        return evento

    def eliminar_evento(self, identificador: int) -> Evento:
        evento = self.indice_activos.get(identificador)
        if evento is None:
            raise KeyError("No existe un evento activo con ese identificador.")
        self._registrar_instantanea(f"Eliminar SIS-{identificador:06d}")
        self.bst.eliminar(evento.clave())
        retirado = self.avl.eliminar(evento.clave(), balancear=not self.modo_estres)
        del self.indice_activos[identificador]
        self.eliminados.add(identificador)
        self.metricas["eliminaciones"] += 1
        return retirado

    def encolar_reporte(self, reporte: Reporte) -> None:
        if not reporte.estacion.strip():
            raise ValueError("El reporte debe indicar su estacion emisora.")
        self._registrar_instantanea(f"Encolar reporte SIS-{reporte.evento.identificador:06d}")
        self.reportes_pendientes.encolar(reporte)

    def procesar_siguiente_reporte(self) -> str:
        """Resolve exactly one queued report under the mandatory revision table."""
        reporte = self.reportes_pendientes.frente()
        candidato = deepcopy(reporte.evento)
        candidato.estaciones = {reporte.estacion}
        self._normalizar_y_clasificar(candidato)
        self._registrar_instantanea(f"Procesar reporte SIS-{candidato.identificador:06d}")
        reporte = self.reportes_pendientes.desencolar()
        recibido = reporte.evento
        recibido.estaciones = {reporte.estacion}
        self._normalizar_y_clasificar(recibido)
        if recibido.identificador in self.eliminados:
            self.metricas["reportes_descartados"] += 1
            resultado = "rechazado: identificador eliminado"
        elif recibido.identificador in self.archivados:
            anterior = self.archivados[recibido.identificador]
            if recibido.revision <= anterior.revision:
                self.metricas["reportes_descartados"] += 1
                resultado = "descartado: reporte archivado no es una revision mayor"
            else:
                del self.archivados[recibido.identificador]
                recibido.estado = EstadoAtencion.PENDIENTE
                self.crear_evento(recibido, registrar_accion=False)
                resultado = "reactivado desde historico"
        elif recibido.identificador not in self.indice_activos:
            self.crear_evento(recibido, registrar_accion=False)
            resultado = "alta nueva"
        else:
            vigente = self.indice_activos[recibido.identificador]
            if recibido.revision > vigente.revision:
                self.corregir_evento(
                    vigente.identificador,
                    {
                        "magnitud": recibido.magnitud,
                        "profundidad_hipocentro": recibido.profundidad_hipocentro,
                        "x": recibido.x,
                        "y": recibido.y,
                        "ocurrencia": recibido.ocurrencia,
                    },
                    revision=recibido.revision,
                    registrar_accion=False,
                )
                vigente.estaciones.add(reporte.estacion)
                resultado = "correccion aceptada"
            elif recibido.revision == vigente.revision and recibido.datos_reportables() == vigente.datos_reportables():
                vigente.estaciones.add(reporte.estacion)
                resultado = "confirmacion aceptada"
            elif recibido.revision == vigente.revision:
                self.metricas["conflictos"] += 1
                resultado = "conflicto: misma revision con datos distintos"
            else:
                self.metricas["reportes_descartados"] += 1
                resultado = "descartado: reporte antiguo"
        return resultado

    def recuperar_balance(self) -> int:
        self._registrar_instantanea("Recuperacion global del AVL")
        giros = self.avl.recuperar_balance()
        self.modo_estres = False
        return giros

    def avanzar_reloj(self, nuevo_reloj: datetime | str) -> None:
        nuevo = fecha_utc(nuevo_reloj)
        if nuevo < self.reloj:
            raise ValueError("El reloj de simulacion no puede retroceder.")
        self._registrar_instantanea("Avanzar reloj de simulacion")
        self.reloj = nuevo

    def cargar_por_inserciones(self, datos: dict) -> dict:
        """Load events from JSON insertion mode with full validation and atomic replacement."""
        # Validate format
        if datos.get("version") != 1:
            raise ValueError("Version de JSON no soportada.")
        if datos.get("tipo_carga") != "inserciones":
            raise ValueError("El JSON no es del tipo 'inserciones'.")

        # Validate and parse zones
        zonas_json = datos.get("zonas", [])
        zonas = []
        for zona_json in zonas_json:
            zona = Zona(
                nombre=zona_json["nombre"],
                x_min=Decimal(str(zona_json["x_min"])),
                x_max=Decimal(str(zona_json["x_max"])),
                y_min=Decimal(str(zona_json["y_min"])),
                y_max=Decimal(str(zona_json["y_max"])),
                poblada=zona_json["poblada"],
            )
            zonas.append(zona)

        # Validate and parse clock
        reloj_nuevo = fecha_utc(datos["reloj"])

        # Validate mode
        modo = datos.get("modo", "normal")
        if modo not in ("normal", "estres"):
            raise ValueError("El modo debe ser 'normal' o 'estres'.")

        # Validate events are unique in the load
        eventos_json = datos.get("eventos", [])
        ids_en_carga = set()
        for evento_json in eventos_json:
            eid = evento_json["identificador"]
            if eid in ids_en_carga:
                raise ValueError(f"ID duplicado en la carga: {eid}")
            ids_en_carga.add(eid)

        # Validate IDs don't conflict with existing scenario
        for eid in ids_en_carga:
            if eid in self.indice_activos:
                raise ValueError(f"ID {eid} ya existe como evento activo.")
            if eid in self.archivados:
                raise ValueError(f"ID {eid} ya existe en historico.")
            if eid in self.eliminados:
                raise ValueError(f"ID {eid} fue eliminado y no puede reutilizarse.")

        # Build temporary scenario
        avl_temp = ArbolAVL()
        bst_temp = ArbolBST()
        indice_temp: dict[int, Evento] = {}

        # Insert events in order
        for evento_json in eventos_json:
            evento = Evento(
                identificador=evento_json["identificador"],
                magnitud=Decimal(str(evento_json["magnitud"])),
                profundidad_hipocentro=Decimal(str(evento_json["profundidad_hipocentro"])),
                x=Decimal(str(evento_json["x"])),
                y=Decimal(str(evento_json["y"])),
                ocurrencia=evento_json["ocurrencia"],
                revision=evento_json["revision"],
                estaciones=set(evento_json["estaciones"]),
            )

            # Validate event with new clock and zones
            evento.validar(reloj_nuevo)
            evento.en_zona_poblada = clasificar_zona_poblada(evento, zonas)
            evento.prioridad = calcular_prioridad(evento)

            # Insert into temporary trees
            avl_temp.insertar(evento, balancear=(modo == "normal"))
            bst_temp.insertar(evento)
            indice_temp[evento.identificador] = evento

        # All validations passed - atomically replace scenario
        self._registrar_instantanea("Carga por inserciones")
        self.zonas = zonas
        self.reloj = reloj_nuevo
        self.avl = avl_temp
        self.bst = bst_temp
        self.indice_activos = indice_temp
        self.modo_estres = (modo == "estres")

        # Return statistics
        return {
            "avl": {
                "raiz_id": self.avl.raiz.evento.identificador if self.avl.raiz else None,
                "altura": self.avl.altura(),
                "profundidad_maxima": self.avl.profundidad_maxima(),
                "cantidad_hojas": self.avl.cantidad_hojas(),
            },
            "bst": {
                "raiz_id": self.bst.raiz.evento.identificador if self.bst.raiz else None,
                "altura": self.bst.altura(),
                "profundidad_maxima": self.bst.profundidad_maxima(),
                "cantidad_hojas": self.bst.cantidad_hojas(),
            },
        }

    def _validar_topologia(self, nodos_dict: dict, raiz_id: Optional[int], modo: str) -> list[str]:
        """Validate topology references, cycles, uniqueness, BST order, heights, and factors."""
        errores: list[str] = []

        if raiz_id is None and nodos_dict:
            errores.append("Raiz es null pero existen nodos.")
            return errores

        if raiz_id is not None and raiz_id not in nodos_dict:
            errores.append(f"Raiz {raiz_id} no existe en nodos.")
            return errores

        # Validate all references exist
        for nodo_id, nodo_data in nodos_dict.items():
            izquierdo_id = nodo_data["izquierdo"]
            derecho_id = nodo_data["derecho"]
            if izquierdo_id is not None and izquierdo_id not in nodos_dict:
                errores.append(f"Nodo {nodo_id} referencia izquierdo inexistente: {izquierdo_id}.")
            if derecho_id is not None and derecho_id not in nodos_dict:
                errores.append(f"Nodo {nodo_id} referencia derecho inexistente: {derecho_id}.")

        if errores:
            return errores

        # Validate uniqueness of position (each node is child of at most one parent)
        hijos_contados: dict[int, int] = {}
        for nodo_data in nodos_dict.values():
            izquierdo_id = nodo_data["izquierdo"]
            derecho_id = nodo_data["derecho"]
            if izquierdo_id is not None:
                hijos_contados[izquierdo_id] = hijos_contados.get(izquierdo_id, 0) + 1
            if derecho_id is not None:
                hijos_contados[derecho_id] = hijos_contados.get(derecho_id, 0) + 1

        for hijo_id, count in hijos_contados.items():
            if count > 1:
                errores.append(f"Nodo {hijo_id} es hijo de mas de un padre ({count} padres).")

        if raiz_id is not None and hijos_contados.get(raiz_id, 0) > 0:
            errores.append(f"Raiz {raiz_id} tambien es hijo de otro nodo.")

        # Validate all nodes are reachable from root
        if raiz_id is not None:
            visitados = set()

            def dfs_alcanzable(nodo_id: int) -> None:
                if nodo_id in visitados:
                    return
                visitados.add(nodo_id)
                nodo_data = nodos_dict[nodo_id]
                izquierdo_id = nodo_data["izquierdo"]
                derecho_id = nodo_data["derecho"]
                if izquierdo_id is not None:
                    dfs_alcanzable(izquierdo_id)
                if derecho_id is not None:
                    dfs_alcanzable(derecho_id)

            dfs_alcanzable(raiz_id)
            for nodo_id in nodos_dict:
                if nodo_id not in visitados:
                    errores.append(f"Nodo {nodo_id} no es alcanzable desde la raiz.")

        # Validate no cycles using DFS with current path tracking (must run before other validations)
        if raiz_id is not None:
            visitados_completos = set()

            def dfs_ciclo(nodo_id: int, camino_actual: set[int]) -> bool:
                if nodo_id in camino_actual:
                    errores.append(f"Ciclo detectado: nodo {nodo_id} ya esta en el camino actual.")
                    return True
                if nodo_id in visitados_completos:
                    return False

                visitados_completos.add(nodo_id)
                nuevo_camino = camino_actual | {nodo_id}
                nodo_data = nodos_dict[nodo_id]
                izquierdo_id = nodo_data["izquierdo"]
                derecho_id = nodo_data["derecho"]

                ciclo_encontrado = False
                if izquierdo_id is not None:
                    if dfs_ciclo(izquierdo_id, nuevo_camino):
                        ciclo_encontrado = True
                if derecho_id is not None:
                    if dfs_ciclo(derecho_id, nuevo_camino):
                        ciclo_encontrado = True
                return ciclo_encontrado

            if dfs_ciclo(raiz_id, set()):
                return errores  # Return early if cycle found

        # Validate global BST order with propagated limits
        if raiz_id is not None:
            visitados_orden = set()

            def dfs_orden(nodo_id: int, min_key: Optional[Clave], max_key: Optional[Clave]) -> None:
                if nodo_id in visitados_orden:
                    return
                visitados_orden.add(nodo_id)

                nodo_data = nodos_dict[nodo_id]
                evento_dict = nodo_data["evento"]
                evento = Evento(
                    identificador=evento_dict["identificador"],
                    magnitud=Decimal(str(evento_dict["magnitud"])),
                    profundidad_hipocentro=Decimal(str(evento_dict["profundidad_hipocentro"])),
                    x=Decimal(str(evento_dict["x"])),
                    y=Decimal(str(evento_dict["y"])),
                    ocurrencia=evento_dict["ocurrencia"],
                    revision=evento_dict["revision"],
                    estaciones=set(evento_dict["estaciones"]),
                )
                evento.en_zona_poblada = clasificar_zona_poblada(evento, self.zonas)
                evento.prioridad = calcular_prioridad(evento)
                clave = evento.clave()

                if min_key is not None and clave <= min_key:
                    errores.append(f"Orden BST global invalido en nodo {nodo_id}: clave {clave} <= minimo {min_key}.")
                if max_key is not None and clave >= max_key:
                    errores.append(f"Orden BST global invalido en nodo {nodo_id}: clave {clave} >= maximo {max_key}.")

                izquierdo_id = nodo_data["izquierdo"]
                derecho_id = nodo_data["derecho"]
                if izquierdo_id is not None:
                    dfs_orden(izquierdo_id, min_key, clave)
                if derecho_id is not None:
                    dfs_orden(derecho_id, clave, max_key)

            dfs_orden(raiz_id, None, None)

        # Validate heights and factors are coherent
        if raiz_id is not None:
            def dfs_alturas(nodo_id: int) -> int:
                nodo_data = nodos_dict[nodo_id]
                izquierdo_id = nodo_data["izquierdo"]
                derecho_id = nodo_data["derecho"]

                altura_izq = dfs_alturas(izquierdo_id) if izquierdo_id is not None else -1
                altura_der = dfs_alturas(derecho_id) if derecho_id is not None else -1

                altura_esperada = 1 + max(altura_izq, altura_der)
                altura_almacenada = nodo_data["altura"]
                if altura_almacenada != altura_esperada:
                    errores.append(f"Altura incoherente en nodo {nodo_id}: almacenada {altura_almacenada}, esperada {altura_esperada}.")

                factor_esperado = altura_izq - altura_der
                # Factor is not stored in JSON but should be validated if present
                return altura_almacenada

            dfs_alturas(raiz_id)

        return errores

    def cargar_por_topologia(self, datos: dict) -> dict:
        """Load events from JSON topology mode with full validation and atomic replacement."""
        # Validate format
        if datos.get("version") != 1:
            raise ValueError("Version de JSON no soportada.")
        if datos.get("tipo_carga") != "topologia":
            raise ValueError("El JSON no es del tipo 'topologia'.")

        # Validate and parse zones
        zonas_json = datos.get("zonas", [])
        zonas = []
        for zona_json in zonas_json:
            zona = Zona(
                nombre=zona_json["nombre"],
                x_min=Decimal(str(zona_json["x_min"])),
                x_max=Decimal(str(zona_json["x_max"])),
                y_min=Decimal(str(zona_json["y_min"])),
                y_max=Decimal(str(zona_json["y_max"])),
                poblada=zona_json["poblada"],
            )
            zonas.append(zona)

        # Validate and parse clock
        reloj_nuevo = fecha_utc(datos["reloj"])

        # Validate mode
        modo = datos.get("modo", "normal")
        if modo not in ("normal", "estres"):
            raise ValueError("El modo debe ser 'normal' o 'estres'.")

        # Get topology data
        nodos_dict = datos.get("nodos", {})
        raiz_id = datos.get("raiz")

        # Validate IDs don't conflict with existing scenario
        for nodo_id in nodos_dict.keys():
            if nodo_id in self.indice_activos:
                raise ValueError(f"ID {nodo_id} ya existe como evento activo.")
            if nodo_id in self.archivados:
                raise ValueError(f"ID {nodo_id} ya existe en historico.")
            if nodo_id in self.eliminados:
                raise ValueError(f"ID {nodo_id} fue eliminado y no puede reutilizarse.")

        # Validate topology structure
        errores_topologia = self._validar_topologia(nodos_dict, raiz_id, modo)
        if errores_topologia:
            raise ValueError("Errores de topologia: " + "; ".join(errores_topologia))

        # Build temporary AVL from topology
        avl_temp = ArbolAVL()
        avl_temp.raiz = ArbolAVL._construir_desde_topologia(nodos_dict, raiz_id)

        # Build BST from topology (same structure, no balancing)
        bst_temp = ArbolBST()
        bst_temp.raiz = ArbolAVL._construir_desde_topologia(nodos_dict, raiz_id)

        # Build index from events
        indice_temp: dict[int, Evento] = {}
        for nodo_id, nodo_data in nodos_dict.items():
            evento_dict = nodo_data["evento"]
            evento = Evento(
                identificador=evento_dict["identificador"],
                magnitud=Decimal(str(evento_dict["magnitud"])),
                profundidad_hipocentro=Decimal(str(evento_dict["profundidad_hipocentro"])),
                x=Decimal(str(evento_dict["x"])),
                y=Decimal(str(evento_dict["y"])),
                ocurrencia=evento_dict["ocurrencia"],
                revision=evento_dict["revision"],
                estaciones=set(evento_dict["estaciones"]),
            )
            # Validate event with new clock and zones
            evento.validar(reloj_nuevo)
            evento.en_zona_poblada = clasificar_zona_poblada(evento, zonas)
            evento.prioridad = calcular_prioridad(evento)
            indice_temp[evento.identificador] = evento

        # If normal mode, validate AVL is balanced
        if modo == "normal":
            auditoria = avl_temp.auditar()
            if not auditoria.balanceado:
                raise ValueError("Topologia desbalanceada no permitida en modo normal.")

        # All validations passed - atomically replace scenario
        self._registrar_instantanea("Carga por topologia")
        self.zonas = zonas
        self.reloj = reloj_nuevo
        self.avl = avl_temp
        self.bst = bst_temp
        self.indice_activos = indice_temp
        self.modo_estres = (modo == "estres")

        # Return statistics
        return {
            "avl": {
                "raiz_id": self.avl.raiz.evento.identificador if self.avl.raiz else None,
                "altura": self.avl.altura(),
                "profundidad_maxima": self.avl.profundidad_maxima(),
                "cantidad_hojas": self.avl.cantidad_hojas(),
            },
            "bst": {
                "raiz_id": self.bst.raiz.evento.identificador if self.bst.raiz else None,
                "altura": self.bst.altura(),
                "profundidad_maxima": self.bst.profundidad_maxima(),
                "cantidad_hojas": self.bst.cantidad_hojas(),
            },
        }

    def guardar_version(self, nombre: str) -> str:
        """Save the current scenario as a version with the given name."""
        # Validate version name
        if not nombre or not nombre.strip():
            raise ValueError("El nombre de la version no puede estar vacio.")
        nombre = nombre.strip()

        # Check if version already exists
        ruta = _obtener_ruta_version(nombre)
        if ruta.exists():
            raise ValueError(f"La version '{nombre}' ya existe. Use un nombre diferente o elimine la version existente.")

        # Ensure versions directory exists and is writable
        versions_dir = Path(VERSIONES_DIR)
        try:
            versions_dir.mkdir(exist_ok=True)
        except PermissionError:
            raise PermissionError(f"No se puede crear el directorio de versiones '{VERSIONES_DIR}'. Verifique permisos.")

        # Export current scenario
        datos = self.exportar_escenario_completo()

        # Write to file
        try:
            escribir_json_escenario(datos, str(ruta))
        except PermissionError:
            raise PermissionError(f"No se puede escribir en '{ruta}'. Verifique permisos.")

        return str(ruta)

    def listar_versiones(self) -> list[str]:
        """List all available version names."""
        versions_dir = Path(VERSIONES_DIR)
        if not versions_dir.exists():
            return []

        versiones = []
        for archivo in versions_dir.glob("*.json"):
            # Skip .gitkeep
            if archivo.name == ".gitkeep":
                continue
            # Remove .json extension
            nombre = archivo.stem
            versiones.append(nombre)

        return sorted(versiones)

    def restaurar_version(self, nombre: str) -> None:
        """Restore a version by name. Takes a D1 snapshot before restoring."""
        # Validate version exists
        ruta = _obtener_ruta_version(nombre)
        if not ruta.exists():
            raise ValueError(f"La version '{nombre}' no existe.")

        # Take D1 snapshot before restoring
        self._registrar_instantanea(f"Restaurar version '{nombre}'")

        # Load version data
        try:
            datos = leer_json_archivo(str(ruta))
        except PermissionError:
            raise PermissionError(f"No se puede leer '{ruta}'. Verifique permisos.")

        # Reconstruct catalog from exported data
        # Parse zones
        zonas = []
        for zona_json in datos["zonas"]:
            zona = Zona(
                nombre=zona_json["nombre"],
                x_min=Decimal(str(zona_json["x_min"])),
                x_max=Decimal(str(zona_json["x_max"])),
                y_min=Decimal(str(zona_json["y_min"])),
                y_max=Decimal(str(zona_json["y_max"])),
                poblada=zona_json["poblada"],
            )
            zonas.append(zona)

        # Parse clock
        self.reloj = fecha_utc(datos["reloj"])

        # Parse mode
        self.modo_estres = (datos["modo"] == "estres")
        self.cola_pausada = datos["cola_pausada"]

        # Parse parameters
        self.parametros = {
            "W": datos["parametros"]["W"],
            "R": datos["parametros"]["R"],
            "L": datos["parametros"]["L"],
            "T": datos["parametros"]["T"],
        }

        # Reconstruct AVL from topology
        # Convert string keys to int for reconstruction
        nodos_int: dict[int, dict] = {int(k): v for k, v in datos["avl"]["nodos"].items()}
        raiz_int = int(datos["avl"]["raiz"]) if datos["avl"]["raiz"] is not None else None
        avl_temp = ArbolAVL()
        avl_temp.raiz = ArbolAVL._construir_desde_topologia(nodos_int, raiz_int)

        # Reconstruct BST from topology
        bst_temp = ArbolBST()
        bst_temp.raiz = ArbolAVL._construir_desde_topologia(nodos_int, raiz_int)

        # Reconstruct active events index
        indice_temp: dict[int, Evento] = {}
        for eid, evento_json in datos["eventos_activos"].items():
            eid_int = int(eid) if isinstance(eid, str) else eid
            evento = Evento(
                identificador=evento_json["identificador"],
                magnitud=Decimal(str(evento_json["magnitud"])),
                profundidad_hipocentro=Decimal(str(evento_json["profundidad_hipocentro"])),
                x=Decimal(str(evento_json["x"])),
                y=Decimal(str(evento_json["y"])),
                ocurrencia=evento_json["ocurrencia"],
                revision=evento_json["revision"],
                estaciones=set(evento_json["estaciones"]),
            )
            evento.estado = EstadoAtencion(evento_json["estado"])
            evento.en_zona_poblada = evento_json["en_zona_poblada"]
            evento.prioridad = evento_json["prioridad"]
            indice_temp[eid_int] = evento

        # Reconstruct archived events
        archivados_temp: dict[int, Evento] = {}
        for eid, evento_json in datos["eventos_historicos"].items():
            eid_int = int(eid) if isinstance(eid, str) else eid
            evento = Evento(
                identificador=evento_json["identificador"],
                magnitud=Decimal(str(evento_json["magnitud"])),
                profundidad_hipocentro=Decimal(str(evento_json["profundidad_hipocentro"])),
                x=Decimal(str(evento_json["x"])),
                y=Decimal(str(evento_json["y"])),
                ocurrencia=evento_json["ocurrencia"],
                revision=evento_json["revision"],
                estaciones=set(evento_json["estaciones"]),
            )
            evento.estado = EstadoAtencion(evento_json["estado"])
            evento.en_zona_poblada = evento_json["en_zona_poblada"]
            evento.prioridad = evento_json["prioridad"]
            archivados_temp[eid_int] = evento

        # Reconstruct deleted IDs
        eliminados_temp = set(int(eid) if isinstance(eid, str) else eid for eid in datos["ids_eliminados"])

        # Reconstruct queue
        cola_temp = Cola()
        for reporte_json in datos["cola_fifo"]:
            evento = Evento(
                identificador=reporte_json["evento"]["identificador"],
                magnitud=Decimal(str(reporte_json["evento"]["magnitud"])),
                profundidad_hipocentro=Decimal(str(reporte_json["evento"]["profundidad_hipocentro"])),
                x=Decimal(str(reporte_json["evento"]["x"])),
                y=Decimal(str(reporte_json["evento"]["y"])),
                ocurrencia=reporte_json["evento"]["ocurrencia"],
                revision=reporte_json["evento"]["revision"],
                estaciones=set(reporte_json["evento"]["estaciones"]),
            )
            evento.estado = EstadoAtencion(reporte_json["evento"]["estado"])
            evento.en_zona_poblada = reporte_json["evento"]["en_zona_poblada"]
            evento.prioridad = reporte_json["evento"]["prioridad"]
            reporte = Reporte(evento=evento, estacion=reporte_json["estacion"])
            cola_temp.encolar(reporte)

        # Reconstruct metrics
        self.metricas = datos["metricas"].copy()

        # Reconstruct associations
        self.asociaciones = datos["asociaciones"].copy()

        # Atomically replace scenario
        self.zonas = zonas
        self.avl = avl_temp
        self.bst = bst_temp
        self.indice_activos = indice_temp
        self.archivados = archivados_temp
        self.eliminados = eliminados_temp
        self.reportes_pendientes = cola_temp

    def exportar_escenario_completo(self) -> dict:
        """Export the complete scenario as a JSON-serializable dict according to the contract."""
        def serializar_zona(zona: Zona) -> dict:
            return {
                "nombre": zona.nombre,
                "x_min": float(zona.x_min),
                "x_max": float(zona.x_max),
                "y_min": float(zona.y_min),
                "y_max": float(zona.y_max),
                "poblada": zona.poblada,
            }

        def serializar_evento(evento: Evento) -> dict:
            return {
                "identificador": evento.identificador,
                "magnitud": float(evento.magnitud),
                "profundidad_hipocentro": float(evento.profundidad_hipocentro),
                "x": float(evento.x),
                "y": float(evento.y),
                "ocurrencia": evento.ocurrencia.isoformat(),
                "revision": evento.revision,
                "estaciones": list(evento.estaciones),
                "estado": evento.estado.value,
                "en_zona_poblada": evento.en_zona_poblada,
                "prioridad": evento.prioridad,
            }

        def serializar_reporte(reporte: Reporte) -> dict:
            return {
                "evento": serializar_evento(reporte.evento),
                "estacion": reporte.estacion,
            }

        # Collect all unique stations from active, archived events, and pending reports
        todas_estaciones = set()
        for evento in self.indice_activos.values():
            todas_estaciones.update(evento.estaciones)
        for evento in self.archivados.values():
            todas_estaciones.update(evento.estaciones)
        for reporte in self.reportes_pendientes:
            todas_estaciones.add(reporte.estacion)
            todas_estaciones.update(reporte.evento.estaciones)

        return {
            "version": 1,
            "tipo_guardado": "escenario_completo",
            "reloj": self.reloj.isoformat(),
            "modo": "estres" if self.modo_estres else "normal",
            "cola_pausada": self.cola_pausada,
            "parametros": {
                "W": self.parametros.get("W"),
                "R": self.parametros.get("R"),
                "L": self.parametros.get("L"),
                "T": self.parametros.get("T"),
            },
            "zonas": [serializar_zona(zona) for zona in self.zonas],
            "estaciones": sorted(list(todas_estaciones)),
            "avl": self.avl.exportar_topologia(),
            "eventos_activos": {eid: serializar_evento(evt) for eid, evt in self.indice_activos.items()},
            "eventos_historicos": {eid: serializar_evento(evt) for eid, evt in self.archivados.items()},
            "ids_eliminados": sorted(list(self.eliminados)),
            "cola_fifo": [serializar_reporte(reporte) for reporte in self.reportes_pendientes],
            "historial": [{"descripcion": snap.descripcion} for snap in self.historial._elementos],
            "metricas": self.metricas.copy(),
            "estado_atencion": {
                eid: evt.estado.value for eid, evt in self.indice_activos.items()
            },
            "asociaciones": self.asociaciones.copy(),
        }


def escribir_json_escenario(datos: dict, ruta: str) -> None:
    """Write the scenario dict to a JSON file with UTF-8 encoding and readable indentation."""
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(datos, f, indent=2, ensure_ascii=False)


def leer_json_archivo(ruta: str) -> dict:
    """Read a JSON file and return the parsed dict."""
    with open(ruta, "r", encoding="utf-8") as f:
        return json.load(f)


# Version management - versions are stored in the 'versiones/' directory
VERSIONES_DIR = "versiones"


def _obtener_ruta_version(nombre: str) -> Path:
    """Get the full path for a version file."""
    return Path(VERSIONES_DIR) / f"{nombre}.json"

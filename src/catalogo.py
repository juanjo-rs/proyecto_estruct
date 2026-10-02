"""Business layer that keeps the active AVL separate from the user interface."""

from __future__ import annotations

import json
import os
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable, Optional

Clave = tuple[int, object, int]

from .arbol_avl import ArbolAVL
from .arbol_bst import ArbolBST
from .cola import Cola
from .dominio import (
    Asociacion,
    EstadoAtencion,
    Evento,
    Reporte,
    ResultadoConsulta,
    VistaEventoMapa,
    VistaNodo,
    VistaZona,
    Zona,
    calcular_prioridad,
    clasificar_zona_poblada,
    decimal_un_lugar,
    es_candidato,
    fecha_utc,
)
from .pila import Pila
from .nodo import NodoArbol


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
    cuerpos_eliminados: dict[int, Evento]
    reportes_pendientes: Cola[Reporte]
    parametros: dict[str, object]
    modo_estres: bool
    cola_pausada: bool
    asociaciones: dict[object, object]
    estaciones: frozenset[str]
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
                "cuerpos_eliminados": catalogo.cuerpos_eliminados,
                "reportes_pendientes": catalogo.reportes_pendientes,
                "parametros": catalogo.parametros,
                "modo_estres": catalogo.modo_estres,
                "cola_pausada": catalogo.cola_pausada,
                "asociaciones": catalogo.asociaciones,
                "estaciones": catalogo.estaciones,
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
        catalogo.cuerpos_eliminados = self.cuerpos_eliminados
        catalogo.reportes_pendientes = self.reportes_pendientes
        catalogo.parametros = self.parametros
        catalogo.modo_estres = self.modo_estres
        catalogo.cola_pausada = self.cola_pausada
        catalogo.asociaciones = self.asociaciones
        catalogo.estaciones = self.estaciones
        catalogo.metricas = self.metricas

@dataclass(frozen=True)
class RamaArchivable:
    """Eligible subtree: root id, depth from the AVL root, and frozen member ids."""

    id_raiz: int
    profundidad: int
    identificadores: tuple[int, ...]



class CatalogoSismico:
    """Application service for the first implementation increment."""

    def __init__(
        self,
        zonas: Iterable[Zona],
        reloj: datetime | str,
        estaciones: Iterable[str] = (),
    ) -> None:
        self.zonas = list(zonas)
        self.reloj = fecha_utc(reloj)
        self.avl = ArbolAVL()
        self.bst = ArbolBST()
        self.indice_activos: dict[int, Evento] = {}
        self.archivados: dict[int, Evento] = {}
        self.eliminados: set[int] = set()
        self.cuerpos_eliminados: dict[int, Evento] = {}
        self.reportes_pendientes: Cola[Reporte] = Cola()
        self.historial: Pila[InstantaneaCatalogo] = Pila()
        # C1: W/R/L/T start at the mandatory initial values (PDF section 3/6/9/10),
        # not empty. Kept as a plain mutable dict on purpose: internal reconstruction
        # paths (cargar_por_*, restaurar_version) and existing tests still assign it
        # directly; cambiar_parametro() is the validated, undoable, association-aware
        # entry point meant for the GUI and for any new report/business flow.
        self.parametros: dict[str, object] = {
            "W": Decimal("48"),
            "R": Decimal("40"),
            "L": 3,
            "T": Decimal("4320"),  # minutes; matches archivar_rama's minute-based math
        }
        # C2: forward map only (B's candidates and chosen reference, by id).
        # The inverse ("who references A") is derived on demand in _referenciados_por
        # instead of being kept as a second live structure, per PDF section 12: the
        # team may persist associations or rebuild them from the deterministic policy.
        self.asociaciones: dict[int, Asociacion] = {}
        # C1: immutable station registry. Empty means "not configured" (permissive):
        # no station-membership check is enforced, so existing call sites and tests
        # that never configured stations keep working unchanged.
        self.estaciones: frozenset[str] = self._validar_estaciones(estaciones)
        self.modo_estres = False
        self.cola_pausada = False
        self.metricas = {
            "correcciones_aceptadas": 0,
            "reportes_descartados": 0,
            "conflictos": 0,
            "eliminaciones": 0,
            "archivos_masivos": 0,
            "eventos_archivados": 0,
        }

    @staticmethod
    def _validar_estaciones(estaciones: Iterable[str]) -> frozenset[str]:
        """Validate station codes: non-empty text, no duplicates (TUTORIA C1 step 2)."""
        codigos = [codigo.strip() for codigo in estaciones]
        if any(not codigo for codigo in codigos):
            raise ValueError("Los codigos de estacion no pueden ser vacios.")
        if len(codigos) != len(set(codigos)):
            raise ValueError("No se puede repetir un codigo de estacion.")
        return frozenset(codigos)

    def configurar_estaciones(self, estaciones: Iterable[str]) -> None:
        """Replace the station registry as one undoable action.

        Stations stay fixed while the scenario runs, but undo and version
        restore must bring the previous registry back with the rest of the scenario.
        """
        codigos = self._validar_estaciones(estaciones)
        self._registrar_instantanea("Configurar estaciones")
        self.estaciones = codigos

    def configurar_zonas(self, zonas: Iterable[Zona]) -> None:
        """Replace the zone list as one undoable action and reclassify events.

        Validation finishes before the snapshot, so a bad zone leaves the
        scenario untouched. An active event whose priority changes is removed
        from both trees with the old key and inserted with the new one.
        """
        nuevas = [self._validar_zona(zona) for zona in zonas]
        if not nuevas:
            raise ValueError("Debe existir al menos una zona.")
        nombres = [zona.nombre for zona in nuevas]
        if len(nombres) != len(set(nombres)):
            raise ValueError("No se puede repetir el nombre de una zona.")
        marco = nuevas[0]
        for zona in nuevas[1:]:
            if (
                zona.x_min < marco.x_min
                or zona.x_max > marco.x_max
                or zona.y_min < marco.y_min
                or zona.y_max > marco.y_max
            ):
                raise ValueError(
                    f"La zona {zona.nombre} no puede salir de la zona inicial ({marco.nombre})."
                )
        self._registrar_instantanea("Configurar zonas")
        self.zonas = nuevas
        self._reclasificar_por_zonas()

    def _validar_zona(self, zona: Zona) -> Zona:
        """Return a zone with coordinates checked against the 0–1000 map."""
        if not isinstance(zona.nombre, str) or not zona.nombre.strip():
            raise ValueError("La zona necesita un nombre.")
        if not isinstance(zona.poblada, bool):
            raise ValueError("Indica si la zona esta poblada con si o no.")
        x_min = decimal_un_lugar(zona.x_min, "0.0", "1000.0", "La coordenada x minima")
        x_max = decimal_un_lugar(zona.x_max, "0.0", "1000.0", "La coordenada x maxima")
        y_min = decimal_un_lugar(zona.y_min, "0.0", "1000.0", "La coordenada y minima")
        y_max = decimal_un_lugar(zona.y_max, "0.0", "1000.0", "La coordenada y maxima")
        if x_min >= x_max or y_min >= y_max:
            raise ValueError("La zona debe tener ancho y alto positivos.")
        return Zona(zona.nombre.strip(), x_min, x_max, y_min, y_max, zona.poblada)

    def _reclasificar_por_zonas(self) -> None:
        """Recompute populated-zone and priority after the zone list changes."""
        por_mover: list[tuple[Evento, bool, int]] = []
        for evento in list(self.indice_activos.values()):
            en_zona = clasificar_zona_poblada(evento, self.zonas)
            marca_anterior = evento.en_zona_poblada
            evento.en_zona_poblada = en_zona
            nueva_prioridad = calcular_prioridad(evento)
            if nueva_prioridad == evento.prioridad:
                continue
            evento.en_zona_poblada = marca_anterior
            por_mover.append((evento, en_zona, nueva_prioridad))
        for evento, _en_zona, _prioridad in por_mover:
            clave = evento.clave()
            self.avl.eliminar(clave, balancear=not self.modo_estres)
            self.bst.eliminar(clave)
        for evento, en_zona, nueva_prioridad in por_mover:
            evento.en_zona_poblada = en_zona
            evento.prioridad = nueva_prioridad
            self.avl.insertar(evento, balancear=not self.modo_estres)
            self.bst.insertar(evento)
        for evento in self.archivados.values():
            evento.en_zona_poblada = clasificar_zona_poblada(evento, self.zonas)
            evento.prioridad = calcular_prioridad(evento)

    def cambiar_parametro(self, nombre: str, valor: object) -> object:
        """Validate, apply, and (for W/R) recompute associations as ONE undoable
        action (C1 / PDF sections 6-7-9-10). Order follows TUTORIA C1 step 3:
        validate fully first, take exactly one snapshot, then mutate.
        """
        if nombre not in ("W", "R", "L", "T"):
            raise ValueError(f"Parametro desconocido: {nombre}.")
        if nombre == "L":
            if not isinstance(valor, int) or isinstance(valor, bool) or valor < 0:
                raise ValueError("L debe ser un entero mayor o igual a 0.")
            nuevo: object = valor
        else:
            try:
                decimal_valor = Decimal(str(valor))
            except (InvalidOperation, ValueError) as error:
                raise ValueError(f"{nombre} debe ser un numero decimal valido.") from error
            if not decimal_valor.is_finite() or decimal_valor <= 0:
                raise ValueError(f"{nombre} debe ser un numero positivo.")
            nuevo = decimal_valor
        self._registrar_instantanea(f"Cambiar parametro {nombre}")
        self.parametros[nombre] = nuevo
        if nombre in ("W", "R"):
            # Only W/R redefine what a candidate is; L and T have no effect on
            # associations (L only affects the expensive-access mark, T only
            # affects future archive eligibility) per TUTORIA C1 step 3 table.
            self.recalcular_asociaciones()
        return nuevo

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
        # C1: only enforced once a station registry was configured (permissive by
        # default); a single choke point covers crear_evento, corregir_evento and
        # procesar_siguiente_reporte, which all route through this method.
        if self.estaciones and not evento.estaciones <= self.estaciones:
            desconocidas = sorted(evento.estaciones - self.estaciones)
            raise ValueError(f"Estacion(es) no configurada(s) en el escenario: {desconocidas}.")
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

    def indicadores(self) -> dict[str, object]:
        """Read structural counters from the live trees without mutating them."""
        limite = self.parametros.get("L")
        limite_valido = isinstance(limite, int) and not isinstance(limite, bool) and limite >= 0
        costosos: list[dict[str, int]] = []
        if limite_valido:
            for nodo, profundidad in self.avl.nodos_con_profundidad():
                if nodo.evento.prioridad == 3 and profundidad > limite:
                    _, examinados = self.avl.buscar_clave(nodo.evento.clave())
                    costosos.append(
                        {
                            "identificador": nodo.evento.identificador,
                            "profundidad": profundidad,
                            "examinados": examinados,
                        }
                    )
        return {
            "avl": {
                "giros_izquierda": self.avl.giros_izquierda,
                "giros_derecha": self.avl.giros_derecha,
                "casos_ll": self.avl.casos_ll,
                "casos_rr": self.avl.casos_rr,
                "casos_lr": self.avl.casos_lr,
                "casos_rl": self.avl.casos_rl,
                "altura": self.avl.altura(),
                "hojas": self.avl.cantidad_hojas(),
                "profundidad_maxima": self.avl.profundidad_maxima(),
            },
            "bst": {
                "altura": self.bst.altura(),
                "hojas": self.bst.cantidad_hojas(),
                "profundidad_maxima": self.bst.profundidad_maxima(),
            },
            "L": limite if limite_valido else None,
            "acceso_costoso": costosos,
        }


    def recalcular_asociaciones(self) -> None:
        """Rebuild every association from scratch (C2 / PDF section 7).

        O(n^2): each active-or-archived event is compared against every other
        one. Correct and simple for this project's scale (GUIA_IMPLEMENTACION
        section 6, decision 2); callers never take their own snapshot here, so
        this must only be invoked from inside an action that already registered
        exactly one instantanea (crear_evento, corregir_evento, eliminar_evento,
        cambiar_parametro for W/R) or right after an atomic scenario load.

        Never call this for a rotation, a plain archive, or a change of L/T/reloj:
        none of those redefine what a candidate is (PDF section 7, TUTORIA 3.7).
        """
        eventos = list(self.indice_activos.values()) + list(self.archivados.values())
        w_horas = Decimal(str(self.parametros.get("W", 0)))
        r_km = Decimal(str(self.parametros.get("R", 0)))
        nuevas: dict[int, Asociacion] = {}
        for b in eventos:
            candidatos = [a for a in eventos if es_candidato(a, b, w_horas, r_km)]
            # Deterministic policy A2: greater magnitude first, then closer in time
            # to B, then smaller id. Never depends on arrival order or AVL shape.
            candidatos.sort(key=lambda a: (-a.magnitud, b.ocurrencia - a.ocurrencia, a.identificador))
            referencia = candidatos[0].identificador if candidatos else None
            nuevas[b.identificador] = Asociacion(
                candidatos=tuple(a.identificador for a in candidatos),
                referencia_elegida=referencia,
            )
        self.asociaciones = nuevas

    def _referenciados_por(self, identificador: int) -> tuple[int, ...]:
        """Events that chose `identificador` as their reference. Derived on demand
        (O(n) scan) instead of kept as a second live structure, per PDF section 12."""
        return tuple(
            sorted(
                eid
                for eid, asociacion in self.asociaciones.items()
                if asociacion.referencia_elegida == identificador
            )
        )

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
        # C2: a new event may be a candidate for others or have candidates itself.
        self.recalcular_asociaciones()
        return evento

    def consultar(self, identificador: int) -> tuple[str, Optional[Evento]]:
        if identificador in self.indice_activos:
            return "activo", self.indice_activos[identificador]
        if identificador in self.archivados:
            return "archivado", self.archivados[identificador]
        if identificador in self.eliminados:
            return "eliminado", self.cuerpos_eliminados.get(identificador)
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
        # C2: unconditional, even when the key did not change — x/y/ocurrencia can
        # move the W/R candidacy window without touching priority or magnitude.
        self.recalcular_asociaciones()
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
        self.cuerpos_eliminados[identificador] = deepcopy(evento)
        self.metricas["eliminaciones"] += 1
        # C2: drop associations that used this id as a candidate/reference.
        self.recalcular_asociaciones()
        return retirado

    def _evento_cumple_archivo(self, evento: Evento, umbral_t: float) -> bool:
        """True when one event is low priority and strictly older than T minutes."""
        antiguedad = (self.reloj - evento.ocurrencia).total_seconds() / 60.0
        return evento.prioridad == 1 and antiguedad > umbral_t

    def _recorrer_ramas(
        self,
        nodo: Optional[NodoArbol],
        profundidad: int,
        umbral_t: float,
        candidatas: list[RamaArchivable],
    ) -> list[Evento]:
        """Walk one subtree: always visit children, then decide if THIS branch is eligible."""
        if nodo is None:
            return []
        miembros = (
            [nodo.evento]
            + self._recorrer_ramas(nodo.izquierda, profundidad + 1, umbral_t, candidatas)
            + self._recorrer_ramas(nodo.derecha, profundidad + 1, umbral_t, candidatas)
        )
        if all(self._evento_cumple_archivo(evento, umbral_t) for evento in miembros):
            candidatas.append(
                RamaArchivable(
                    id_raiz=nodo.evento.identificador,
                    profundidad=profundidad,
                    identificadores=tuple(evento.identificador for evento in miembros),
                )
            )
        return miembros

    def listar_ramas_archivables(self) -> list[RamaArchivable]:
        """List eligible subtrees without mutating the catalog. Winner sorts first."""
        if self.parametros.get("T") is None:
            raise ValueError("El parametro T no esta definido.")
        umbral_t = float(self.parametros["T"])
        candidatas: list[RamaArchivable] = []
        self._recorrer_ramas(self.avl.raiz, 0, umbral_t, candidatas)
        candidatas.sort(
            key=lambda rama: (-len(rama.identificadores), -rama.profundidad, -rama.id_raiz)
        )
        return candidatas

    def archivar_rama(self) -> RamaArchivable:
        """Archive the winning eligible subtree using its frozen ID set."""
        candidatas = self.listar_ramas_archivables()
        if not candidatas:
            raise ValueError("No hay rama elegible para archivar.")
        ganadora = candidatas[0]
        ids_fijos = list(ganadora.identificadores)
        self._registrar_instantanea(f"Archivar rama SIS-{ganadora.id_raiz:06d}")
        for identificador in ids_fijos:
            evento = self.indice_activos[identificador]
            clave = evento.clave()
            self.bst.eliminar(clave)
            self.avl.eliminar(clave, balancear=not self.modo_estres)
            del self.indice_activos[identificador]
            self.archivados[identificador] = evento
        # C4: a simple archive does not change associations (PDF section 7), only
        # its own counters (archived events stay valid candidates/references).
        self.metricas["archivos_masivos"] += 1
        self.metricas["eventos_archivados"] += len(ids_fijos)
        return ganadora


    def encolar_reporte(self, reporte: Reporte) -> None:
        if not reporte.estacion.strip():
            raise ValueError("El reporte debe indicar su estacion emisora.")
        self._registrar_instantanea(f"Encolar reporte SIS-{reporte.evento.identificador:06d}")
        self.reportes_pendientes.encolar(reporte)

    def procesar_siguiente_reporte(self) -> str:
        """Resolve exactly one queued report under the mandatory revision table."""
        if self.cola_pausada:
            raise RuntimeError("La cola esta pausada durante la recuperacion.")
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
        """Repair via the same path as leaving stress, so the queue stays paused."""
        return self.recuperar_desde_estres()

    def avanzar_reloj(self, nuevo_reloj: datetime | str) -> None:
        nuevo = fecha_utc(nuevo_reloj)
        if nuevo < self.reloj:
            raise ValueError("El reloj de simulacion no puede retroceder.")
        self._registrar_instantanea("Avanzar reloj de simulacion")
        self.reloj = nuevo

    # ------------------------------------------------------------------
    # C3: queries over the active AVL (PDF section 11). Every method here is
    # read-only (never rotates, never mutates `self.avl`) and returns a
    # ResultadoConsulta reporting exactly how many AVL nodes it visited.
    # ------------------------------------------------------------------

    def consultar_top_k_pendientes(self, k: int) -> ResultadoConsulta:
        """First k active PENDIENTE events in descending key order.

        Reverse-inorder traversal (right, node, left) with an explicit stack so
        it stops the instant k results are collected; a reviewed event is still
        visited and counted, just not collected. Best case O(h + k), worst case
        O(n) when most nodes are reviewed or there are fewer than k pending.
        """
        if not isinstance(k, int) or isinstance(k, bool) or k <= 0:
            raise ValueError("k debe ser un entero positivo.")
        resultados: list[Evento] = []
        examinados = 0
        pila: list[NodoArbol] = []
        actual = self.avl.raiz
        while (actual is not None or pila) and len(resultados) < k:
            while actual is not None:
                pila.append(actual)
                actual = actual.derecha
            actual = pila.pop()
            examinados += 1
            if actual.evento.estado == EstadoAtencion.PENDIENTE:
                resultados.append(actual.evento)
            actual = actual.izquierda
        return ResultadoConsulta(
            resultados=resultados,
            nodos_examinados=examinados,
            descripcion_costo="O(h + k) mejor caso; O(n) peor caso (revisados en el camino).",
        )

    def _recorrer_avl_completo(self) -> list[NodoArbol]:
        """Full traversal helper for queries that cannot prune by K (TUTORIA 4.3/4.4):
        magnitude is not the first key component, so no subtree can be discarded
        from magnitude alone, and depth/date are not part of K at all."""
        nodos: list[NodoArbol] = []

        def recorrer(nodo: Optional[NodoArbol]) -> None:
            if nodo is None:
                return
            nodos.append(nodo)
            recorrer(nodo.izquierda)
            recorrer(nodo.derecha)

        recorrer(self.avl.raiz)
        return nodos

    def consultar_por_magnitud(self, min_magnitud: object, max_magnitud: object) -> ResultadoConsulta:
        """Active events with min_magnitud <= M <= max_magnitud (both inclusive).

        Full traversal: magnitude is K's second component, so a node's priority
        alone cannot justify discarding a whole subtree. O(n), n nodes examined.
        """
        minimo = decimal_un_lugar(min_magnitud, "-2.0", "10.0", "La magnitud minima")
        maximo = decimal_un_lugar(max_magnitud, "-2.0", "10.0", "La magnitud maxima")
        if minimo > maximo:
            raise ValueError("La magnitud minima no puede ser mayor que la maxima.")
        nodos = self._recorrer_avl_completo()
        resultados = [n.evento for n in nodos if minimo <= n.evento.magnitud <= maximo]
        return ResultadoConsulta(
            resultados=resultados,
            nodos_examinados=len(nodos),
            descripcion_costo="O(n): magnitud no es el primer componente de K, no se puede podar por prioridad.",
        )

    def consultar_por_profundidad_y_fecha(
        self, limite_h: object, fecha_inicio: datetime | str, fecha_fin: datetime | str
    ) -> ResultadoConsulta:
        """Active events with hypocenter depth H <= limite_h and ocurrencia inside
        [fecha_inicio, fecha_fin] (both inclusive). H and the date are not part of
        K, so no subtree can be discarded: O(n), n nodes examined."""
        limite = decimal_un_lugar(limite_h, "0.0", "700.0", "El limite de profundidad")
        inicio = fecha_utc(fecha_inicio)
        fin = fecha_utc(fecha_fin)
        if inicio > fin:
            raise ValueError("La fecha de inicio no puede ser posterior a la fecha de fin.")
        nodos = self._recorrer_avl_completo()
        resultados = [
            n.evento
            for n in nodos
            if n.evento.profundidad_hipocentro <= limite and inicio <= n.evento.ocurrencia <= fin
        ]
        return ResultadoConsulta(
            resultados=resultados,
            nodos_examinados=len(nodos),
            descripcion_costo="O(n): profundidad y fecha no son parte de K, no se puede podar.",
        )

    def consultar_asociaciones(self, identificador: int) -> ResultadoConsulta:
        """Candidates, chosen reference, and reverse references for one event
        (C2 data read through C3's query contract). Resolved entirely through
        id-indexed structures, never through the AVL: nodos_examinados is 0.
        """
        estado, _ = self.consultar(identificador)
        if estado == "desconocido":
            raise KeyError(f"No existe el identificador {identificador}.")
        if estado == "eliminado":
            return ResultadoConsulta(
                resultados=[{"identificador": identificador, "mensaje": "Eliminado: no participa en asociaciones."}],
                nodos_examinados=0,
                descripcion_costo="O(1): resuelto por indice, no requiere el AVL.",
            )

        def estado_de(eid: int) -> str:
            return self.consultar(eid)[0]

        asociacion = self.asociaciones.get(identificador, Asociacion(candidatos=(), referencia_elegida=None))
        referenciado_por = self._referenciados_por(identificador)
        resultado = {
            "identificador": identificador,
            "estado": estado,
            "candidatos": [{"identificador": c, "estado": estado_de(c)} for c in asociacion.candidatos],
            "referencia_elegida": (
                {"identificador": asociacion.referencia_elegida, "estado": estado_de(asociacion.referencia_elegida)}
                if asociacion.referencia_elegida is not None
                else None
            ),
            "referenciado_por": [{"identificador": r, "estado": estado_de(r)} for r in referenciado_por],
        }
        return ResultadoConsulta(
            resultados=[resultado],
            nodos_examinados=0,
            descripcion_costo="O(c + r): c candidatos mostrados y r referencias inversas, via indices por id.",
        )

    def consultar_acceso_costoso(self) -> ResultadoConsulta:
        """Active, priority-3 events whose AVL depth is strictly greater than L,
        each with node depth, L, and the simulated key-search cost (TUTORIA 4.6).

        Full traversal (O(n)) plus one buscar_clave per match (O(m log n) for m
        matches): the expensive-access mark is not part of K, so it cannot be
        found by pruning. Mirrors indicadores()['acceso_costoso'] but returns the
        richer, self-contained shape this specific C3 query must report.
        """
        limite = self.parametros.get("L")
        if not (isinstance(limite, int) and not isinstance(limite, bool) and limite >= 0):
            raise ValueError("El parametro L no esta definido o es invalido.")
        resultados: list[dict[str, int]] = []
        examinados = 0
        for nodo, profundidad in self.avl.nodos_con_profundidad():
            examinados += 1
            if nodo.evento.prioridad == 3 and profundidad > limite:
                _, visitas = self.avl.buscar_clave(nodo.evento.clave())
                examinados += visitas
                resultados.append(
                    {
                        "identificador": nodo.evento.identificador,
                        "profundidad_nodo": profundidad,
                        "limite": limite,
                        "nodos_visitados_busqueda": visitas,
                    }
                )
        return ResultadoConsulta(
            resultados=resultados,
            nodos_examinados=examinados,
            descripcion_costo="O(n) recorrido completo + O(m log n) busquedas por clave de m resultados.",
        )

    # ------------------------------------------------------------------
    # C4: remaining PDF section 6/9 gaps (full per-event lookup; the expensive
    # access mark and archived-reactivation already exist in crear_evento's and
    # procesar_siguiente_reporte's flows, see docs/ANALISIS_REQUISITOS_C1_C6_SAMUEL.md).
    # ------------------------------------------------------------------

    def _posicion_en_avl(self, clave: Clave) -> tuple[int, int, int]:
        """Read-only walk to one key's node depth, stored height, and balance
        factor. Never rotates; raises if the key is not in the active AVL."""
        nodo = self.avl.raiz
        profundidad = 0
        while nodo is not None:
            if clave == nodo.evento.clave():
                return profundidad, nodo.altura, ArbolAVL._factor(nodo)
            nodo = nodo.izquierda if clave < nodo.evento.clave() else nodo.derecha
            profundidad += 1
        raise KeyError("La clave no esta en el AVL activo.")

    def consultar_detalle(self, identificador: int) -> dict:
        """Full per-event lookup required by PDF section 6 ('Consulta de un
        evento'): status, vigente data, AVL position (depth/height/factor) for
        active events, expensive-access mark, and associations. Read-only: never
        registers an instantanea and never mutates the AVL.
        """
        estado, evento = self.consultar(identificador)
        detalle: dict[str, object] = {"identificador": identificador, "estado": estado}
        if estado == "desconocido":
            return detalle
        if estado == "eliminado":
            detalle["mensaje"] = "Identificador eliminado: no puede reactivarse ni sigue en el AVL."
            if evento is not None:
                detalle.update(
                    {
                        "magnitud": evento.magnitud,
                        "profundidad_hipocentro": evento.profundidad_hipocentro,
                        "x": evento.x,
                        "y": evento.y,
                        "ocurrencia": evento.ocurrencia,
                        "revision": evento.revision,
                        "estaciones": sorted(evento.estaciones),
                        "en_zona_poblada": evento.en_zona_poblada,
                        "prioridad": evento.prioridad,
                        "clave": evento.clave(),
                        "estado_atencion": evento.estado.value,
                    }
                )
            return detalle

        assert evento is not None
        detalle.update(
            {
                "magnitud": evento.magnitud,
                "profundidad_hipocentro": evento.profundidad_hipocentro,
                "x": evento.x,
                "y": evento.y,
                "ocurrencia": evento.ocurrencia,
                "revision": evento.revision,
                "estaciones": sorted(evento.estaciones),
                "en_zona_poblada": evento.en_zona_poblada,
                "prioridad": evento.prioridad,
                "clave": evento.clave(),
                "estado_atencion": evento.estado.value,
            }
        )
        if estado == "activo":
            profundidad_nodo, altura, factor = self._posicion_en_avl(evento.clave())
            limite = self.parametros.get("L")
            limite_valido = isinstance(limite, int) and not isinstance(limite, bool) and limite >= 0
            detalle.update(
                {
                    "profundidad_nodo": profundidad_nodo,
                    "altura_nodo": altura,
                    "factor_balance": factor,
                    "acceso_costoso": bool(
                        limite_valido and evento.prioridad == 3 and profundidad_nodo > limite
                    ),
                }
            )
        detalle["asociaciones"] = self.consultar_asociaciones(identificador).resultados[0]
        return detalle

    def obtener_vista_arbol(self, tipo: str) -> tuple[dict[int, VistaNodo], Optional[int]]:
        """
        Get an immutable view of the AVL or BST tree for GUI rendering.

        Args:
            tipo: "avl" or "bst"

        Returns:
            (dict of id -> VistaNodo, root_id or None)

        Raises:
            ValueError: If tipo is not "avl" or "bst"
        """
        if tipo not in ("avl", "bst"):
            raise ValueError("Tipo debe ser 'avl' o 'bst'.")

        arbol = self.avl if tipo == "avl" else self.bst
        vista: dict[int, VistaNodo] = {}

        def recorrer(nodo: Optional[NodoArbol]) -> Optional[int]:
            if nodo is None:
                return None

            nodo_id = nodo.evento.identificador
            izquierdo_id = recorrer(nodo.izquierda)
            derecho_id = recorrer(nodo.derecha)

            # Calculate balance factor for AVL, None for BST
            factor = None
            if tipo == "avl":
                from .arbol_avl import ArbolAVL
                factor = ArbolAVL._factor(nodo)

            vista[nodo_id] = VistaNodo(
                id=nodo_id,
                clave=nodo.evento.clave(),
                izquierdo_id=izquierdo_id,
                derecho_id=derecho_id,
                altura=nodo.altura,
                factor=factor,
            )

            return nodo_id

        raiz_id = recorrer(arbol.raiz)
        return vista, raiz_id

    def obtener_vista_mapa(self) -> tuple[list[VistaZona], list[VistaEventoMapa]]:
        """
        Get an immutable view of zones and active events for map rendering.

        Returns:
            (list of VistaZona, list of VistaEventoMapa)
        """
        # Create zone views
        vista_zonas = [
            VistaZona(
                nombre=zona.nombre,
                x_min=zona.x_min,
                x_max=zona.x_max,
                y_min=zona.y_min,
                y_max=zona.y_max,
                poblada=zona.poblada,
            )
            for zona in self.zonas
        ]

        # Get expensive access IDs from indicators
        indicadores = self.indicadores()
        costosos_ids = {item["identificador"] for item in indicadores["acceso_costoso"]}

        # Create event views
        vista_eventos = [
            VistaEventoMapa(
                id=evento.identificador,
                x=evento.x,
                y=evento.y,
                prioridad=evento.prioridad,
                magnitud=evento.magnitud,
                en_zona_poblada=evento.en_zona_poblada,
                estado=evento.estado.value,
                acceso_costoso=evento.identificador in costosos_ids,
            )
            for evento in self.indice_activos.values()
        ]

        return vista_zonas, vista_eventos

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
        # C2: this load schema carries no "asociaciones" field (CONTRATO section 2),
        # so associations must be computed fresh for the freshly-loaded scenario.
        self.recalcular_asociaciones()

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
        # C2: the topology load schema also carries no "asociaciones" field.
        self.recalcular_asociaciones()

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

        # Reconstruct deleted IDs and the saved body of each deleted event.
        eliminados_temp = set(int(eid) if isinstance(eid, str) else eid for eid in datos["ids_eliminados"])
        cuerpos_temp: dict[int, Evento] = {}
        for eid, evento_json in datos.get("eventos_eliminados", {}).items():
            eid_int = int(eid) if isinstance(eid, str) else eid
            cuerpo = Evento(
                identificador=evento_json["identificador"],
                magnitud=Decimal(str(evento_json["magnitud"])),
                profundidad_hipocentro=Decimal(str(evento_json["profundidad_hipocentro"])),
                x=Decimal(str(evento_json["x"])),
                y=Decimal(str(evento_json["y"])),
                ocurrencia=evento_json["ocurrencia"],
                revision=evento_json["revision"],
                estaciones=set(evento_json["estaciones"]),
            )
            cuerpo.estado = EstadoAtencion(evento_json["estado"])
            cuerpo.en_zona_poblada = evento_json["en_zona_poblada"]
            cuerpo.prioridad = evento_json["prioridad"]
            cuerpos_temp[eid_int] = cuerpo

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

        # Reconstruct associations (C2): rebuild Asociacion objects from the
        # plain {candidatos, referencia_elegida} shape exportar_escenario_completo wrote.
        self.asociaciones = {
            int(eid): Asociacion(
                candidatos=tuple(dato["candidatos"]),
                referencia_elegida=dato["referencia_elegida"],
            )
            for eid, dato in datos["asociaciones"].items()
        }

        # Atomically replace scenario
        self.zonas = zonas
        self.avl = avl_temp
        self.bst = bst_temp
        self.indice_activos = indice_temp
        self.archivados = archivados_temp
        self.eliminados = eliminados_temp
        self.cuerpos_eliminados = cuerpos_temp
        if "registro_estaciones" in datos:
            self.estaciones = self._validar_estaciones(datos["registro_estaciones"])
        else:
            self.estaciones = frozenset()
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

        def serializar_parametro(valor: object) -> Optional[float]:
            """W/R/T are Decimal once set via cambiar_parametro or the C1 defaults;
            json.dump cannot serialize Decimal directly, so convert here same as
            every other physical quantity in this method. L stays an int/None."""
            return float(valor) if valor is not None else None

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
                "W": serializar_parametro(self.parametros.get("W")),
                "R": serializar_parametro(self.parametros.get("R")),
                "L": self.parametros.get("L"),
                "T": serializar_parametro(self.parametros.get("T")),
            },
            "zonas": [serializar_zona(zona) for zona in self.zonas],
            "estaciones": sorted(list(todas_estaciones)),
            "registro_estaciones": sorted(self.estaciones),
            "avl": self.avl.exportar_topologia(),
            "eventos_activos": {eid: serializar_evento(evt) for eid, evt in self.indice_activos.items()},
            "eventos_historicos": {eid: serializar_evento(evt) for eid, evt in self.archivados.items()},
            "ids_eliminados": sorted(list(self.eliminados)),
            "eventos_eliminados": {
                eid: serializar_evento(evt) for eid, evt in self.cuerpos_eliminados.items()
            },
            "cola_fifo": [serializar_reporte(reporte) for reporte in self.reportes_pendientes],
            "historial": [{"descripcion": snap.descripcion} for snap in self.historial._elementos],
            "metricas": self.metricas.copy(),
            "estado_atencion": {
                eid: evt.estado.value for eid, evt in self.indice_activos.items()
            },
            # C2: Asociacion is a dataclass, not JSON-native; serialize it to the
            # plain {candidatos, referencia_elegida} shape restaurar_version expects.
            "asociaciones": {
                str(eid): {
                    "candidatos": list(asociacion.candidatos),
                    "referencia_elegida": asociacion.referencia_elegida,
                }
                for eid, asociacion in self.asociaciones.items()
            },
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

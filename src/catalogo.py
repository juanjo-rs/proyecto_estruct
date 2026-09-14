"""Business layer that keeps the active AVL separate from the user interface."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Optional

from .arbol_avl import ArbolAVL
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
class AccionPendienteDeInstantanea:
    """Temporary action record; phase 5 will add a complete pre-operation snapshot."""

    descripcion: str


class CatalogoSismico:
    """Application service for the first implementation increment."""

    def __init__(self, zonas: Iterable[Zona], reloj: datetime | str) -> None:
        self.zonas = list(zonas)
        self.reloj = fecha_utc(reloj)
        self.avl = ArbolAVL()
        self.indice_activos: dict[int, Evento] = {}
        self.archivados: dict[int, Evento] = {}
        self.eliminados: set[int] = set()
        self.reportes_pendientes: Cola[Reporte] = Cola()
        self.historial: Pila[AccionPendienteDeInstantanea] = Pila()
        self.modo_estres = False
        self.metricas = {
            "correcciones_aceptadas": 0,
            "reportes_descartados": 0,
            "conflictos": 0,
            "eliminaciones": 0,
        }

    def _normalizar_y_clasificar(self, evento: Evento) -> None:
        evento.validar(self.reloj)
        evento.en_zona_poblada = clasificar_zona_poblada(evento, self.zonas)
        evento.prioridad = calcular_prioridad(evento)

    def _registrar_accion(self, descripcion: str) -> None:
        self.historial.apilar(AccionPendienteDeInstantanea(descripcion))

    def crear_evento(self, evento: Evento, registrar_accion: bool = True) -> Evento:
        """Create one active event after all validation succeeds."""
        if evento.identificador in self.indice_activos or evento.identificador in self.archivados:
            raise ValueError("El identificador ya pertenece a un evento existente.")
        if evento.identificador in self.eliminados:
            raise ValueError("El identificador fue eliminado y no puede reutilizarse.")
        self._normalizar_y_clasificar(evento)
        self.avl.insertar(evento, balancear=not self.modo_estres)
        self.indice_activos[evento.identificador] = evento
        if registrar_accion:
            self._registrar_accion(f"Crear SIS-{evento.identificador:06d}")
        return evento

    def consultar(self, identificador: int) -> tuple[str, Optional[Evento]]:
        if identificador in self.indice_activos:
            return "activo", self.indice_activos[identificador]
        if identificador in self.archivados:
            return "archivado", self.archivados[identificador]
        if identificador in self.eliminados:
            return "eliminado", None
        return "desconocido", None

    def corregir_evento(self, identificador: int, datos: dict[str, object], revision: Optional[int] = None) -> Evento:
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
        if candidato.clave() != clave_anterior:
            self.avl.eliminar(clave_anterior, balancear=not self.modo_estres)
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
        self.metricas["correcciones_aceptadas"] += 1
        self._registrar_accion(f"Corregir SIS-{identificador:06d}")
        return evento

    def marcar_revisado(self, identificador: int) -> Evento:
        evento = self.indice_activos.get(identificador)
        if evento is None:
            raise KeyError("No existe un evento activo con ese identificador.")
        evento.estado = EstadoAtencion.REVISADO
        self._registrar_accion(f"Marcar revisado SIS-{identificador:06d}")
        return evento

    def eliminar_evento(self, identificador: int) -> Evento:
        evento = self.indice_activos.get(identificador)
        if evento is None:
            raise KeyError("No existe un evento activo con ese identificador.")
        retirado = self.avl.eliminar(evento.clave(), balancear=not self.modo_estres)
        del self.indice_activos[identificador]
        self.eliminados.add(identificador)
        self.metricas["eliminaciones"] += 1
        self._registrar_accion(f"Eliminar SIS-{identificador:06d}")
        return retirado

    def encolar_reporte(self, reporte: Reporte) -> None:
        if not reporte.estacion.strip():
            raise ValueError("El reporte debe indicar su estacion emisora.")
        self.reportes_pendientes.encolar(reporte)

    def procesar_siguiente_reporte(self) -> str:
        """Resolve exactly one queued report under the mandatory revision table."""
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
        self._registrar_accion(f"Procesar reporte SIS-{recibido.identificador:06d}: {resultado}")
        return resultado

    def recuperar_balance(self) -> int:
        giros = self.avl.recuperar_balance()
        self.modo_estres = False
        self._registrar_accion("Recuperacion global del AVL")
        return giros

    def avanzar_reloj(self, nuevo_reloj: datetime | str) -> None:
        nuevo = fecha_utc(nuevo_reloj)
        if nuevo < self.reloj:
            raise ValueError("El reloj de simulacion no puede retroceder.")
        self.reloj = nuevo
        self._registrar_accion("Avanzar reloj de simulacion")

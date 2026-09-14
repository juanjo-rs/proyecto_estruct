"""Domain entities and mandatory validation rules."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Iterable


class ErrorValidacion(ValueError):
    """Raised when input breaks a rule from the project statement."""


class EstadoAtencion(str, Enum):
    PENDIENTE = "pendiente"
    REVISADO = "revisado"


def decimal_un_lugar(valor: object, minimo: str, maximo: str, nombre: str) -> Decimal:
    """Convert a value to a finite one-decimal-range Decimal."""
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, ValueError) as error:
        raise ErrorValidacion(f"{nombre} debe ser un numero decimal valido.") from error
    if not numero.is_finite() or numero < Decimal(minimo) or numero > Decimal(maximo):
        raise ErrorValidacion(f"{nombre} debe estar entre {minimo} y {maximo}.")
    if numero.as_tuple().exponent < -1:
        raise ErrorValidacion(f"{nombre} admite como maximo un decimal.")
    return numero.quantize(Decimal("0.0"))


def fecha_utc(valor: datetime | str) -> datetime:
    """Validate an instant with second precision and normalize it to UTC."""
    if isinstance(valor, str):
        try:
            valor = datetime.fromisoformat(valor.replace("Z", "+00:00"))
        except ValueError as error:
            raise ErrorValidacion("La fecha debe usar ISO 8601.") from error
    if not isinstance(valor, datetime) or valor.tzinfo is None:
        raise ErrorValidacion("La fecha debe incluir zona horaria UTC.")
    if valor.microsecond:
        raise ErrorValidacion("La fecha solo admite precision de segundos.")
    return valor.astimezone(timezone.utc)


@dataclass(frozen=True)
class Zona:
    """Immutable rectangular scenario zone."""

    nombre: str
    x_min: Decimal
    x_max: Decimal
    y_min: Decimal
    y_max: Decimal
    poblada: bool

    def contiene(self, x: Decimal, y: Decimal) -> bool:
        return self.x_min <= x <= self.x_max and self.y_min <= y <= self.y_max


@dataclass
class Evento:
    """Earthquake identity and its current accepted data."""

    identificador: int
    magnitud: Decimal
    profundidad_hipocentro: Decimal
    x: Decimal
    y: Decimal
    ocurrencia: datetime
    revision: int
    estaciones: set[str] = field(default_factory=set)
    estado: EstadoAtencion = EstadoAtencion.PENDIENTE
    en_zona_poblada: bool = False
    prioridad: int = 1

    def clave(self) -> tuple[int, Decimal, int]:
        return (self.prioridad, self.magnitud, self.identificador)

    def datos_reportables(self) -> tuple[Decimal, Decimal, Decimal, Decimal, datetime]:
        """Return exactly the fields used to compare reports at equal revision."""
        return (self.magnitud, self.profundidad_hipocentro, self.x, self.y, self.ocurrencia)

    def validar(self, reloj: datetime) -> None:
        if not isinstance(self.identificador, int) or isinstance(self.identificador, bool):
            raise ErrorValidacion("El identificador debe ser entero.")
        if not 1 <= self.identificador <= 999999:
            raise ErrorValidacion("El identificador debe estar entre 1 y 999999.")
        self.magnitud = decimal_un_lugar(self.magnitud, "-2.0", "10.0", "La magnitud")
        self.profundidad_hipocentro = decimal_un_lugar(
            self.profundidad_hipocentro, "0.0", "700.0", "La profundidad"
        )
        self.x = decimal_un_lugar(self.x, "0.0", "1000.0", "La coordenada x")
        self.y = decimal_un_lugar(self.y, "0.0", "1000.0", "La coordenada y")
        self.ocurrencia = fecha_utc(self.ocurrencia)
        if self.ocurrencia > fecha_utc(reloj):
            raise ErrorValidacion("La ocurrencia no puede ser posterior al reloj de simulacion.")
        if not isinstance(self.revision, int) or self.revision <= 0:
            raise ErrorValidacion("La revision debe ser un entero positivo.")
        if not self.estaciones or not all(isinstance(nombre, str) and nombre.strip() for nombre in self.estaciones):
            raise ErrorValidacion("Debe existir al menos una estacion valida.")


@dataclass(frozen=True)
class Reporte:
    """A full incoming report waiting in the FIFO queue."""

    evento: Evento
    estacion: str


def clasificar_zona_poblada(evento: Evento, zonas: Iterable[Zona]) -> bool:
    """A border shared with a populated zone is classified as populated."""
    return any(zona.poblada and zona.contiene(evento.x, evento.y) for zona in zonas)


def calcular_prioridad(evento: Evento) -> int:
    """Apply the mandatory priority rules in their specified order."""
    if evento.magnitud >= Decimal("6.0"):
        return 3
    if (
        evento.magnitud >= Decimal("4.5")
        and evento.profundidad_hipocentro <= Decimal("30.0")
        and evento.en_zona_poblada
    ):
        return 3
    if evento.magnitud >= Decimal("4.5"):
        return 2
    return 1

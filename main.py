"""Small executable smoke test for the initial project base."""

from datetime import datetime, timezone

from src.catalogo import CatalogoSismico
from src.dominio import Evento, Zona


def main() -> None:
    zonas = [Zona("Ciudad Central", 0, 500, 0, 500, True)]
    catalogo = CatalogoSismico(zonas, datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc))
    evento = Evento(
        identificador=10,
        magnitud=4.5,
        profundidad_hipocentro=30.0,
        x=100.0,
        y=100.0,
        ocurrencia="2026-09-07T10:00:00Z",
        revision=1,
        estaciones={"EST-01"},
    )
    catalogo.crear_evento(evento)
    print(f"{evento.clave()} -> prioridad {evento.prioridad}")
    print("Auditoria:", catalogo.avl.auditar())


if __name__ == "__main__":
    main()

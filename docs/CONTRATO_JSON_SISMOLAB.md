# Borrador del contrato JSON

Este documento es un borrador de persistencia para A3. No implementa carga ni
guardado. Los nombres y reglas confirmados por el repositorio se distinguen de
las decisiones que todavía requieren integración con fases posteriores.

## 1. Convenciones

- `identificador` es un entero entre `1` y `999999` y no se reutiliza después
  de una eliminación.
- `magnitud`, `profundidad_hipocentro`, `x` y `y` se serializan como números
  decimales con una cifra; el lector debe convertirlos a `Decimal` antes de
  validar.
- `ocurrencia` y `reloj` son fechas ISO 8601 con zona horaria, precisión de
  segundos, por ejemplo `2026-09-07T10:00:00Z`.
- La clave del AVL es ascendente `(prioridad, magnitud, identificador)`.
- `prioridad`, `en_zona_poblada` y la pertenencia a zonas son datos derivados:
  el cargador debe verificarlos, no confiar ciegamente en el JSON.

## 2. Carga por inserciones

La carga por inserciones representa eventos y los inserta en el orden del
arreglo. Cada evento debe tener un ID único dentro de la carga y no puede
repetir un ID activo, histórico o eliminado del escenario base.

```json
{
  "version": 1,
  "tipo_carga": "inserciones",
  "reloj": "2026-09-07T12:00:00Z",
  "modo": "normal",
  "zonas": [
    {
      "nombre": "Ciudad",
      "x_min": 0.0,
      "x_max": 500.0,
      "y_min": 0.0,
      "y_max": 500.0,
      "poblada": true
    }
  ],
  "eventos": [
    {
      "identificador": 10,
      "magnitud": 4.5,
      "profundidad_hipocentro": 30.0,
      "x": 100.0,
      "y": 100.0,
      "ocurrencia": "2026-09-07T10:00:00Z",
      "revision": 1,
      "estaciones": ["EST-01"]
    },
    {
      "identificador": 20,
      "magnitud": 5.0,
      "profundidad_hipocentro": 50.0,
      "x": 700.0,
      "y": 700.0,
      "ocurrencia": "2026-09-07T11:00:00Z",
      "revision": 1,
      "estaciones": ["EST-02"]
    }
  ]
}
```

En esta modalidad no se aceptan `prioridad`, `en_zona_poblada`, `altura` ni
enlaces como autoridad estructural. Se calculan al insertar mediante las
reglas del dominio y el AVL decide las rotaciones.

## 3. Carga por topología

La carga topológica conserva la forma exacta de un árbol ya construido. Cada
ID aparece una vez en `nodos`; `izquierdo` y `derecho` contienen otro ID o
`null`. La raíz también se referencia por ID.

```json
{
  "version": 1,
  "tipo_carga": "topologia",
  "reloj": "2026-09-07T12:00:00Z",
  "modo": "estres",
  "raiz": 20,
  "nodos": {
    "10": {
      "evento": {
        "identificador": 10,
        "magnitud": 4.0,
        "profundidad_hipocentro": 50.0,
        "x": 100.0,
        "y": 100.0,
        "ocurrencia": "2026-09-07T10:00:00Z",
        "revision": 1,
        "estaciones": ["EST-01"]
      },
      "altura": 0,
      "izquierdo": null,
      "derecho": null
    },
    "20": {
      "evento": {
        "identificador": 20,
        "magnitud": 5.0,
        "profundidad_hipocentro": 50.0,
        "x": 700.0,
        "y": 700.0,
        "ocurrencia": "2026-09-07T11:00:00Z",
        "revision": 1,
        "estaciones": ["EST-02"]
      },
      "altura": 1,
      "izquierdo": 10,
      "derecho": null
    }
  }
}
```

En una carga topológica normal, además de la conectividad, se valida que la
estructura esté balanceada. En modo `estres` se permite temporalmente un
factor de balance fuera de `{-1, 0, 1}`, pero siguen siendo obligatorios el
orden BST, las alturas coherentes y las referencias válidas.

## 4. Guardado estructural completo

El formato de guardado debe poder reconstruir el escenario sin depender de un
recorrido ordenado. La siguiente forma reúne los componentes exigidos:

```json
{
  "version": 1,
  "tipo_guardado": "escenario_completo",
  "reloj": "2026-09-07T12:00:00Z",
  "modo": "normal",
  "cola_pausada": false,
  "parametros": {
    "W": null,
    "R": null,
    "L": null,
    "T": null
  },
  "zonas": [],
  "estaciones": [],
  "avl": {
    "raiz": null,
    "nodos": {}
  },
  "eventos_activos": {},
  "eventos_historicos": {},
  "ids_eliminados": [],
  "cola_fifo": [],
  "historial": [],
  "metricas": {
    "correcciones_aceptadas": 0,
    "reportes_descartados": 0,
    "conflictos": 0,
    "eliminaciones": 0
  },
  "estado_atencion": {},
  "asociaciones": {}
}
```

### Campos confirmados y preguntas de integración

| Campo del borrador | Evidencia actual | Pregunta de integración |
| --- | --- | --- |
| `avl.raiz`, `avl.nodos`, `altura`, enlaces | `ArbolAVL.raiz`, `NodoArbol` y `auditar()` | ¿Se conservará este nombre o se expondrá un serializador en una API nueva? |
| `eventos_activos` | `CatalogoSismico.indice_activos` | ¿Será una copia por ID o la fuente desde la que se reconstruye el índice? |
| `eventos_historicos` | `CatalogoSismico.archivados` existe, pero no hay flujo de archivo | ¿Qué operación mueve eventos allí y qué metadatos conserva? |
| `ids_eliminados` | `CatalogoSismico.eliminados` | Confirmar si el JSON usa lista y el negocio reconstruye un `set`. |
| `cola_fifo` | `Cola[Reporte]` y `Reporte(evento, estacion)` | Definir si cada entrada guarda el evento completo o una referencia normalizada. |
| `historial` | Hoy guarda solo `descripcion` en `AccionPendienteDeInstantanea` | ¿La fase 5 reemplazará esto por instantáneas profundas completas? |
| `zonas` | `CatalogoSismico.zonas` y `Zona` | Confirmar si las coordenadas se guardan como números JSON y se convierten a `Decimal`. |
| `estaciones` | Solo existe `Evento.estaciones: set[str]` | No hay catálogo global de estaciones; definir identidad, coordenadas y validaciones. |
| `estado_atencion` | `Evento.estado` con `pendiente` o `revisado` | ¿Se duplica para consulta o se deriva exclusivamente de cada evento? |
| `asociaciones` | No existe todavía en las clases actuales | Definir forma, cardinalidad, reglas de identidad y prohibición de ciclos. |
| `W`, `R`, `L`, `T` | No son atributos de `CatalogoSismico` ni de `Evento` | Definir significado, tipo, rango, unidad y valor por defecto antes de cargar. |
| `metricas` | Hay cuatro contadores concretos en `CatalogoSismico.metricas` | Confirmar si fases futuras añadirán contadores y si los nombres serán estables. |
| `modo` y `cola_pausada` | Existen como `modo_estres` y `cola_pausada` | Definir si se conserva el nombre JSON o se traduce al atributo Python. |

Los campos derivados (`prioridad`, `en_zona_poblada`, factores de balance y
alturas) pueden incluirse para auditoría, pero la carga debe recalcularlos y
compararlos con los valores recibidos.

## 5. Mensajes de error y condiciones

Los códigos siguientes son una propuesta estable para el contrato. El texto
puede mapearse a `ErrorValidacion` o a `ValueError` sin cambiar las APIs
existentes hasta que se implemente persistencia.

| Mensaje | Condición exacta |
| --- | --- |
| `ID_DUPLICADO` | El mismo identificador aparece más de una vez en eventos, nodos o cola, o ya existe en activos, históricos o eliminados del escenario base. |
| `RANGO_INVALIDO` | Un identificador, magnitud, profundidad, coordenada, revisión, estación o zona no cumple el tipo, rango, precisión o no-vacío exigido por el dominio. |
| `FECHA_FUTURA` | `ocurrencia` es posterior al `reloj` cargado; una fecha sin zona horaria, con microsegundos o no ISO también se rechaza como fecha inválida. |
| `ENLACE_INEXISTENTE` | `raiz`, `izquierdo` o `derecho` referencia un ID que no está en `nodos`. |
| `CICLO` | Al seguir enlaces desde la raíz se visita un nodo que ya está en el camino actual. |
| `NODO_EN_DOS_POSICIONES` | Un nodo es raíz y además hijo, o aparece como hijo izquierdo/derecho de más de un padre. |
| `ORDEN_BST_GLOBAL_INVALIDO` | Algún nodo no satisface globalmente: toda clave izquierda es menor y toda clave derecha es mayor que la clave de cada ancestro, usando `(prioridad, magnitud, identificador)`. |
| `ALTURA_FB_INCOHERENTE` | `altura` no coincide con `1 + max(altura_izquierda, altura_derecha)`, o el factor guardado/calculado no coincide con `altura_izquierda - altura_derecha`. |
| `PRIORIDAD_DERIVADA_DIFERENTE` | La prioridad recibida no coincide con `calcular_prioridad(evento)` después de validar zonas y datos físicos. |
| `IDENTIDAD_ACTIVO_HISTORICO_REPETIDA` | Un mismo ID aparece simultáneamente en activos y eventos históricos, aunque el resto de sus datos sea igual. |
| `TOPOLOGIA_DESEQUILIBRADA` | La carga declara modo normal y existe un nodo con `abs(FB) > 1`; este error no aplica por sí solo al modo `estres`. |

También deben rechazarse una raíz no alcanzable, nodos no visitados desde la
raíz y un ID eliminado que aparezca como evento activo o histórico. Son
variantes de integridad topológica e identidad que conviene conservar como
errores separados en la implementación.

## 6. Regla de carga atómica

La carga se valida y construye en un escenario temporal, incluyendo zonas,
reloj, eventos, árboles, índices, históricos, eliminados, cola, historial,
parámetros, modo, métricas, estado de atención y asociaciones. Si cualquier
validación falla, se propaga el error y el escenario actual permanece idéntico:
no se modifican nodos, rotaciones, índices, cola ni métricas.

Solo cuando todas las validaciones terminan correctamente se sustituye el
escenario anterior en una única operación de negocio. La GUI debe invocar esa
operación y no manipular nodos ni ejecutar rotaciones.

## 7. Por qué un arreglo ordenado no recupera la topología

Un arreglo ordenado por `(prioridad, magnitud, identificador)` solo conserva el
recorrido inorden. Muchas topologías distintas producen exactamente el mismo
recorrido ordenado: por ejemplo, un árbol perfectamente balanceado y un árbol
degenerado pueden contener las mismas claves. Además, las rotaciones del AVL
cambian padre, hijo izquierdo y hijo derecho sin cambiar el orden inorden.

Por eso, para recuperar la topología real se deben guardar la raíz, el ID de
cada nodo y sus dos enlaces, junto con alturas y validaciones estructurales.
Una lista ordenada puede servir como entrada para insertar de nuevo, pero esa
operación calcula otra topología y no restaura la estructura guardada.
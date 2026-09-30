# Manual Técnico - SismoLab AVL

## 1. Esquema JSON

El sistema utiliza dos modos de carga JSON definidos en el contrato A3:

### 1.1 Carga por Inserciones (`tipo_carga: "inserciones"`)

Representa eventos como un arreglo y los inserta secuencialmente en el orden del arreglo. Cada evento debe tener un ID único dentro de la carga y no puede repetir IDs activos, históricos o eliminados del escenario base.

```json
{
  "version": 1,
  "tipo_carga": "inserciones",
  "reloj": "2026-09-07T12:00:00Z",
  "modo": "normal",
  "zonas": [...],
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
    }
  ]
}
```

**Características:**
- No acepta `prioridad`, `en_zona_poblada`, `altura` ni enlaces como autoridad estructural
- Estos campos se calculan al insertar mediante las reglas del dominio
- El AVL decide las rotaciones automáticamente
- La topología resultante depende del orden de inserción

### 1.2 Carga por Topología (`tipo_carga: "topologia"`)

Conserva la forma exacta de un árbol ya construido. Cada ID aparece una vez en `nodos`; `izquierdo` y `derecho` contienen otro ID o `null`. La raíz también se referencia por ID.

```json
{
  "version": 1,
  "tipo_carga": "topologia",
  "reloj": "2026-09-07T12:00:00Z",
  "modo": "normal",
  "raiz": 20,
  "nodos": {
    "10": {
      "evento": {...},
      "altura": 0,
      "izquierdo": null,
      "derecho": null
    },
    "20": {
      "evento": {...},
      "altura": 1,
      "izquierdo": 10,
      "derecho": null
    }
  }
}
```

**Características:**
- `altura` y `factor` se validan para coherencia
- En modo `normal`, se valida que `abs(factor) <= 1` para todos los nodos
- En modo `estres`, se permite temporalmente `abs(factor) > 1`
- La topología se reconstruye exactamente sin rotaciones

### 1.3 Guardado Estructural Completo (`tipo_guardado: "escenario_completo"`)

El formato de guardado puede reconstruir el escenario sin depender de un recorrido ordenado. Incluye todos los componentes del catálogo.

```json
{
  "version": 1,
  "tipo_guardado": "escenario_completo",
  "reloj": "2026-09-07T12:00:00Z",
  "modo": "normal",
  "cola_pausada": false,
  "parametros": {"W": null, "R": null, "L": null, "T": null},
  "zonas": [],
  "estaciones": [],
  "avl": {"raiz": null, "nodos": {}},
  "eventos_activos": {},
  "eventos_historicos": {},
  "ids_eliminados": [],
  "cola_fifo": [],
  "historial": [],
  "metricas": {...},
  "estado_atencion": {},
  "asociaciones": {}
}
```

**Limitaciones:**
- `historial` guarda solo descripciones, no instantáneas profundas completas
- `asociaciones` está vacío pendiente de especificación por Samuel
- `estaciones` se deduce de eventos activos, históricos y cola

---

## 2. Carga Atómica

La carga se valida y construye en un escenario temporal, incluyendo zonas, reloj, eventos, árboles, índices, históricos, eliminados, cola, historial, parámetros, modo, métricas, estado de atención y asociaciones.

### 2.1 Proceso de Carga Atómica

1. **Validación previa:** Se valida el formato JSON, version, tipo_carga, y campos obligatorios
2. **Construcción temporal:** Se crea un escenario temporal con:
   - AVL temporal (`avl_temp`)
   - BST temporal (`bst_temp`)
   - Índice temporal (`indice_temp`)
3. **Validación de dominio:** Cada evento se valida con `evento.validar(reloj_nuevo)`
4. **Validación de topología:** Si es carga por topología, se valida:
   - Referencias existentes (no enlaces a nodos inexistentes)
   - Unicidad de posición (cada nodo es hijo de a lo sumo un padre)
   - Alcanzabilidad desde la raíz
   - Ausencia de ciclos
   - Orden BST global con propagación de límites
   - Coherencia de alturas y factores
5. **Reemplazo atómico:** Solo cuando todas las validaciones pasan, se reemplaza el escenario anterior en una única operación

### 2.2 Garantía de Atomicidad

Si cualquier validación falla, se propaga el error y el escenario actual permanece idéntico:
- No se modifican nodos
- No se ejecutan rotaciones
- No se alteran índices
- No se cambia la cola
- No se modifican métricas

**Implementación:**
```python
# Construir escenario temporal
avl_temp = ArbolAVL()
bst_temp = ArbolBST()
indice_temp: dict[int, Evento] = {}

# Validar y construir
for evento_json in eventos_json:
    evento = Evento(...)
    evento.validar(reloj_nuevo)
    avl_temp.insertar(evento, balancear=(modo == "normal"))
    indice_temp[evento.identificador] = evento

# Solo si todo valida, reemplazar atómicamente
self.avl = avl_temp
self.bst = bst_temp
self.indice_activos = indice_temp
```

---

## 3. Topología

### 3.1 Por Qué Una Lista No Recupera Topología

Un recorrido inorden (lista ordenada) solo conserva el orden de las claves, no la estructura del árbol. Muchas topologías distintas producen exactamente el mismo recorrido inorden:

**Ejemplo:** Un árbol perfectamente balanceado y un árbol degenerado pueden contener las mismas claves en el mismo orden inorden, pero tener estructuras completamente diferentes.

```
Árbol balanceado (misma clave inorden):      Árbol degenerado (misma clave inorden):
       30                                         10
      /  \                                          \
    20    40                                          20
   /       \                                            \
  10        50                                            30
                                                           \
                                                            40
                                                             \
                                                              50

Inorden: [10, 20, 30, 40, 50]        Inorden: [10, 20, 30, 40, 50]
```

Además, las rotaciones del AVL cambian padre, hijo izquierdo y hijo derecho sin cambiar el orden inorden. Por eso, para recuperar la topología real se deben guardar:
- La raíz
- El ID de cada nodo
- Sus dos enlaces (`izquierdo`, `derecho`)
- Alturas y validaciones estructurales

### 3.2 Validación de Topología

El método `_validar_topologia()` valida:

1. **Referencias válidas:** `raiz`, `izquierdo`, `derecho` referencia IDs que existen en `nodos`
2. **Unicidad de posición:** Cada nodo es hijo de a lo sumo un padre
3. **Alcanzabilidad:** Todos los nodos son alcanzables desde la raíz
4. **Ausencia de ciclos:** No existe ningún ciclo en los enlaces
5. **Orden BST global:** Usando propagación de límites (min_key, max_key)
6. **Coherencia de alturas:** `altura = 1 + max(altura_izquierda, altura_derecha)`
7. **Balanceo (modo normal):** `abs(factor) <= 1` para todos los nodos

**Costo de validación:** O(n) donde n es el número de nodos, con múltiples recorridos DFS.

---

## 4. Instantánea Profunda

### 4.1 Estructura de Instantánea

`InstantaneaCatalogo` es un dataclass inmutable que captura una copia profunda de todo el estado mutable del catálogo:

```python
@dataclass(frozen=True)
class InstantaneaCatalogo:
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
```

### 4.2 Captura de Instantánea

El método `capturar()` usa `deepcopy` para crear una copia completa:

```python
estado = deepcopy({
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
})
```

**Costo de captura:** O(n) donde n es el número total de nodos y eventos.

### 4.3 Restauración de Instantánea

El método `restaurar()` reemplaza todos los campos del catálogo:

```python
catalogo.zonas = self.zonas
catalogo.reloj = self.reloj
catalogo.avl = self.avl
catalogo.bst = self.bst
catalogo.indice_activos = self.indice_activos
# ... resto de campos
```

**Costo de restauración:** O(1) (asignación de referencias).

---

## 5. Pila de Deshacer

### 5.1 Implementación

La pila de deshacer usa la estructura `Pila[InstantaneaCatalogo]` implementada con una lista Python:

```python
class Pila(Generic[T]):
    def __init__(self) -> None:
        self._elementos: list[T] = []
    
    def apilar(self, elemento: T) -> None:
        self._elementos.append(elemento)
    
    def desapilar(self) -> T:
        return self._elementos.pop()
```

### 5.2 Registro de Acciones

Cada operación mutadora registra una instantánea antes de ejecutarse:

```python
def crear_evento(self, evento: Evento, registrar_accion: bool = True) -> Evento:
    if registrar_accion:
        self._registrar_instantanea(f"Crear SIS-{evento.identificador:06d}")
    # ... ejecutar operación
```

### 5.3 Deshacer

El método `deshacer()` desapila la instantánea más reciente y la restaura:

```python
def deshacer(self) -> str:
    if self.historial.esta_vacia():
        raise IndexError("No hay acciones para deshacer.")
    instantanea = self.historial.desapilar()
    instantanea.restaurar(self)
    return f"Deshecho: {instantanea.descripcion}"
```

**Qué se restaura al deshacer un paso de cola:**
- Todo el estado anterior: zonas, reloj, AVL, BST, índice activos, archivados, eliminados, cola FIFO completa, parámetros, modo, métricas, asociaciones
- La cola se restaura completamente, no solo el último elemento procesado

**Costo de deshacer:** O(1) para desapilar + O(1) para restaurar referencias.

---

## 6. Versiones Persistentes

### 6.1 Diferencia Entre Instantánea y Versión

| Aspecto | Instantánea | Versión |
|---------|-------------|---------|
| **Ubicación** | Memoria (pila) | Disco (`versiones/`) |
| **Duración** | Sesión actual | Persistente entre sesiones |
| **Propósito** | Deshacer operaciones | Guardar/cargar escenarios |
| **Historial** | Solo descripciones | Escenario completo |
| **Restauración** | Desapilar y restaurar | Leer JSON y reconstruir |

### 6.2 Guardado de Versión

El método `guardar_version(nombre)`:

1. Valida que el nombre no esté vacío y no exista
2. Asegura que el directorio `versiones/` existe
3. Exporta el escenario completo con `exportar_escenario_completo()`
4. Escribe el JSON en `versiones/{nombre}.json`

**Costo de guardar:** O(n) para exportar + O(n) para escribir JSON.

### 6.3 Restauración de Versión

El método `restaurar_version(nombre)`:

1. Toma una instantánea D1 antes de restaurar (para permitir deshacer la restauración)
2. Lee el JSON desde `versiones/{nombre}.json`
3. Reconstruye:
   - Zonas desde el JSON
   - Reloj, modo, cola_pausada
   - Parámetros
   - AVL y BST desde topología
   - Índice activos y archivados
   - IDs eliminados
   - Cola FIFO
   - Métricas y asociaciones
4. Reemplaza atómicamente el escenario

**Costo de restaurar:** O(n) para leer JSON + O(n) para reconstruir estructuras.

---

## 7. Validaciones

### 7.1 Validaciones de Dominio

La clase `Evento` implementa `validar(reloj)` que verifica:

- `identificador`: entero entre 1 y 999999
- `magnitud`: decimal entre -2.0 y 10.0, máximo un decimal
- `profundidad_hipocentro`: decimal entre 0.0 y 700.0, máximo un decimal
- `x`, `y`: decimales entre 0.0 y 1000.0, máximo un decimal
- `ocurrencia`: fecha ISO 8601 con zona horaria UTC, precisión de segundos
- `ocurrencia <= reloj`: no puede ser posterior al reloj de simulación
- `revision`: entero positivo
- `estaciones`: al menos una estación válida no vacía

### 7.2 Validaciones de Topología

El método `_validar_topologia()` implementa:

- `ENLACE_INEXISTENTE`: referencia a nodo no definido
- `CICLO`: ciclo detectado en los enlaces
- `NODO_EN_DOS_POSICIONES`: nodo es hijo de más de un padre
- `ORDEN_BST_GLOBAL_INVALIDO`: violación de orden BST global
- `ALTURA_FB_INCOHERENTE`: altura o factor incoherente
- `TOPOLOGIA_DESEQUILIBRADA`: en modo normal, factor fuera de {-1, 0, 1}

### 7.3 Validaciones de Negocio

El catálogo valida:

- IDs únicos: no repetir IDs activos, históricos o eliminados
- IDs no reutilizables: IDs eliminados no pueden usarse nuevamente
- Prioridad derivada: se recalcula y valida contra la recibida (si existe)
- Modo consistente: balanceo según modo (normal vs estrés)

---

## 8. Costos de Tiempo y Memoria

### 8.1 Costos de Tiempo

| Operación | Costo | Notas |
|-----------|-------|-------|
| **Insertar evento** | O(log n) | AVL con rotaciones |
| **Eliminar evento** | O(log n) | AVL con rotaciones |
| **Buscar clave** | O(log n) | AVL balanceado |
| **Cargar por inserciones** | O(n log n) | n inserciones AVL |
| **Cargar por topología** | O(n) | Reconstrucción directa |
| **Validar topología** | O(n) | Múltiples DFS |
| **Capturar instantánea** | O(n) | deepcopy de n nodos |
| **Deshacer** | O(1) | Desapilar + restaurar |
| **Guardar versión** | O(n) | Exportar + escribir JSON |
| **Restaurar versión** | O(n) | Leer JSON + reconstruir |
| **Exportar escenario** | O(n) | Recorrido de estructuras |

### 8.2 Costos de Memoria

| Componente | Costo | Notas |
|------------|-------|-------|
| **Nodo AVL** | O(1) | Evento + 2 punteros + altura |
| **Árbol AVL** | O(n) | n nodos |
| **Árbol BST** | O(n) | n nodos (paralelo) |
| **Índice activos** | O(n) | diccionario de n eventos |
| **Archivados** | O(m) | diccionario de m eventos |
| **Eliminados** | O(k) | conjunto de k IDs |
| **Cola FIFO** | O(q) | q reportes pendientes |
| **Instantánea** | O(n + m + k + q) | Copia profunda completa |
| **Pila de deshacer** | O(h × (n + m + k + q)) | h instantáneas en historial |

### 8.3 Limitaciones de Memoria

1. **Historial ilimitado:** La pila de deshacer puede crecer indefinidamente. No hay límite configurado.
2. **Deepcopy costoso:** Cada instantánea copia completamente el AVL, BST, índices y cola.
3. **Versiones en disco:** No hay límite en el número de versiones persistidas.

**Decisión abierta:** El equipo debe decidir si implementar:
- Límite máximo de instantáneas en historial
- Compresión de instantáneas antiguas
- Limpieza automática de versiones antiguas

---

## 9. Limitaciones y Decisiones Abiertas

### 9.1 Limitaciones Actuales

1. **Historial simplificado:** El JSON guardado solo incluye descripciones del historial, no instantáneas profundas completas.
2. **Asociaciones vacías:** El campo `asociaciones` está pendiente de especificación por Samuel.
3. **Estaciones derivadas:** No hay catálogo global de estaciones; se deducen de eventos.
4. **Sin redo:** Solo existe deshacer, no rehacer.
5. **Sin validación de esquema:** No hay validación automática del esquema JSON antes de cargar.

### 9.2 Decisiones Abiertas Aprobadas por el Equipo

1. **Atomicidad estricta:** La carga falla completamente si cualquier validación falla. Aprobado como requisito no negociable.
2. **Topología vs lista:** Se usa preservación de topología en lugar de recorrido ordenado. Aprobado por necesidad de mantener estructura exacta.
3. **Instantáneas profundas:** Se usa deepcopy para capturar estado completo. Aprobado por simplicidad y corrección.
4. **Versión JSON simple:** No hay versioning del esquema JSON. Aprobado por alcance actual del proyecto.
5. **Separación GUI-negocio:** La GUI no muta nodos ni rota árboles. Aprobado como arquitectura base.

### 9.3 Decisiones Pendientes

1. **Límite de historial:** ¿Cuántas instantáneas mantener en memoria?
2. **Compresión:** ¿Comprimir instantáneas o versiones antiguas?
3. **Asociaciones:** ¿Estructura y validación de asociaciones (pendiente Samuel)?
4. **Redo:** ¿Implementar rehacer además de deshacer?
5. **Validación de esquema:** ¿Agregar validación automática del esquema JSON?

---

## 10. API Resumen

### 10.1 APIs de Carga

- `cargar_por_inserciones(datos: dict) -> dict`: Carga eventos por inserción
- `cargar_por_topologia(datos: dict) -> dict`: Carga preservando topología

### 10.2 APIs de Persistencia

- `guardar_version(nombre: str) -> str`: Guarda versión en disco
- `restaurar_version(nombre: str) -> None`: Restaura versión desde disco
- `listar_versiones() -> list[str]`: Lista versiones disponibles
- `exportar_escenario_completo() -> dict`: Exporta a JSON

### 10.3 APIs de Deshacer

- `deshacer() -> str`: Deshace última acción
- `_registrar_instantanea(descripcion: str) -> None`: Registra instantánea

### 10.4 APIs de Validación

- `_validar_topologia(nodos_dict, raiz_id, modo) -> list[str]`: Valida topología
- `auditar(exigir_balanceo: bool) -> ResultadoAuditoria`: Audita AVL

### 10.5 APIs Auxiliares

- `escribir_json_escenario(datos: dict, ruta: str) -> None`: Escribe JSON
- `leer_json_archivo(ruta: str) -> dict`: Lee JSON

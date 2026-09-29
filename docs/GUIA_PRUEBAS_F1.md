# Guía de Pruebas F1 - Archivos JSON de Prueba

Esta guía describe los archivos JSON de prueba creados para validar el esquema A3 y el comportamiento del sistema SismoLab AVL.

## Resumen de Archivos

| Archivo | Tipo Carga | Propósito |
|---------|------------|-----------|
| `limites_empates.json` | inserciones | Valida límites de rangos y desempate por ID |
| `correccion_reporte_antiguo.json` | inserciones | Simula corrección seguida de reporte con revisión menor |
| `reporte_tardio.json` | inserciones | Valida rechazo de reporte con fecha posterior al reloj |
| `cuatro_rotaciones.json` | topología | Demuestra las cuatro rotaciones AVL (LL, RR, LR, RL) |
| `estres_fb_mayor_2.json` | topología | Topología estrés con factor de balance > 2 |
| `archivo_masivo.json` | inserciones | Stress test con 50 eventos |
| `topologia_normal.json` | topología | Topología balanceada en modo normal |
| `topologia_estres.json` | topología | Topología desbalanceada en modo estrés |
| `json_invalido.json` | topología | JSON con ciclo (error de integridad) |
| `rafagas_fifo.json` | inserciones | Secuencia FIFO: altas, confirmaciones, correcciones |

---

## Detalle por Archivo

### 1. limites_empates.json

**Estado inicial:** Catálogo vacío con zona "Ciudad" poblada.

**Acción:** Carga 4 eventos con identificadores en los límites del rango válido (1, 100, 500000, 999999) y magnitudes variadas para probar el desempate por ID cuando la clave `(prioridad, magnitud, identificador)` es igual en prioridad y magnitud.

**Resultado esperado:**
- Valida que el sistema acepta IDs en los límites extremos (1 y 999999)
- Demuestra el desempate por identificador cuando prioridad y magnitud son iguales
- Verifica que el AVL mantiene el orden correcto por `(prioridad, magnitud, identificador)`

**Requisito A3 que demuestra:** `RANGO_INVALIDO` - validación de rangos de identificadores y desempate por ID en la clave del AVL.

---

### 2. correccion_reporte_antiguo.json

**Estado inicial:** Catálogo vacío con zona "Ciudad" poblada.

**Acción:** Carga 2 eventos donde el evento ID 10 tiene revisión 2 (ya corregido) y el evento ID 20 tiene revisión 1. Simula un escenario donde se recibió una corrección para el evento 10 (subió a revisión 2) y luego llega un reporte antiguo del mismo evento.

**Resultado esperado:**
- El evento 10 se carga con revisión 2 y estaciones ["EST-01", "EST-02"]
- Si posteriormente se encola un reporte con revisión 1 para el mismo ID, el sistema lo rechaza como "reporte antiguo"
- Valida la lógica de revisiones: solo se aceptan reportes con revisión mayor a la vigente

**Requisito A3 que demuestra:** Lógica de revisiones - `descartado: reporte antiguo` cuando `revision < revision_vigente`.

---

### 3. reporte_tardio.json

**Estado inicial:** Catálogo vacío con zona "Ciudad" poblada y reloj en 2026-09-07T12:00:00Z.

**Acción:** Intenta cargar un evento con `ocurrencia: "2026-09-07T13:00:00Z"`, que es posterior al reloj de simulación.

**Resultado esperado:**
- El sistema rechaza la carga con error `FECHA_FUTURA`
- El catálogo permanece vacío (atomicidad de la carga)
- Valida que ningún evento puede tener ocurrencia posterior al reloj

**Requisito A3 que demuestra:** `FECHA_FUTURA` - validación de que `ocurrencia <= reloj`.

---

### 4. cuatro_rotaciones.json

**Estado inicial:** Catálogo vacío con zona "Ciudad" poblada.

**Acción:** Carga una topología con 5 nodos configurados para demostrar las cuatro rotaciones AVL básicas:
- Nodo 20: hijo izquierdo de 30, con hijo izquierdo 10 (caso LL potencial)
- Nodo 50: hijo derecho de 30, con hijo derecho 40 (caso RR potencial)
- La estructura balanceada final muestra que el AVL aplicó las rotaciones necesarias

**Resultado esperado:**
- La topología se carga correctamente en modo normal
- El AVL valida que la estructura está balanceada (todos los factores de balance en {-1, 0, 1})
- El orden BST global se mantiene: claves izquierda < clave nodo < claves derecha
- Demuestra que las rotaciones LL, RR, LR, RL funcionan correctamente

**Requisito A3 que demuestra:** `ORDEN_BST_GLOBAL_INVALIDO` y `TOPOLOGIA_DESEQUILIBRADA` - validación de orden y balanceo en modo normal.

---

### 5. estres_fb_mayor_2.json

**Estado inicial:** Catálogo vacío con zona "Ciudad" poblada.

**Acción:** Carga una topología en modo estrés con 7 nodos en una cadena degenerada (todos hijos derechos). El nodo raíz (ID 7) tiene factor de balance 6, que excede el rango AVL normal.

**Resultado esperado:**
- La carga se acepta porque el modo es "estres"
- El sistema valida que el orden BST es correcto (no hay desorden global)
- El sistema valida que las alturas son coherentes con la estructura
- El sistema acepta factores de balance fuera de {-1, 0, 1} solo en modo estrés
- La función `recuperar_balance()` puede reconstruir el árbol balanceado

**Requisito A3 que demuestra:** `ALTURA_FB_INCOHERENTE` - validación de coherencia de alturas y factores, y excepción para modo estrés.

---

### 6. archivo_masivo.json

**Estado inicial:** Catálogo vacío con zona "Ciudad" poblada.

**Acción:** Carga 50 eventos con identificadores del 1 al 50, magnitudes incrementales de 4.0 a 8.9, y distintas prioridades (1, 2, 3 según magnitud). Esto stress-testea la capacidad del AVL para manejar volúmenes grandes.

**Resultado esperado:**
- Todos los 50 eventos se insertan correctamente
- El AVL mantiene el balanceo después de todas las inserciones
- El BST se mantiene sincronizado con el AVL
- La altura del AVL es O(log n) ≈ 6 para 50 nodos (balanceado)
- Valida rendimiento y estabilidad con cargas grandes

**Requisito A3 que demuestra:** `ID_DUPLICADO` - valida que no hay IDs duplicados en una carga masiva, y `RANGO_INVALIDO` para todos los campos numéricos.

---

### 7. topologia_normal.json

**Estado inicial:** Catálogo vacío con zona "Ciudad" poblada.

**Acción:** Carga una topología balanceada en modo normal con 6 nodos:
- Raíz: 30
- Subárbol izquierdo: 20 → 10, 25
- Subárbol derecho: 40 → 25 (reutilizado como hijo derecho de 40)

**Resultado esperado:**
- La topología se carga exitosamente en modo normal
- Todos los factores de balance están en {-1, 0, 1}
- El orden BST global es válido
- Las alturas son coherentes con la estructura
- No hay ciclos ni referencias inválidas

**Requisito A3 que demuestra:** `TOPOLOGIA_DESEQUILIBRADA` - valida que una topología balanceada es aceptada en modo normal.

---

### 8. topologia_estres.json

**Estado inicial:** Catálogo vacío con zona "Ciudad" poblada.

**Acción:** Carga una topología desbalanceada en modo estrés con 5 nodos en una cadena degenerada (10 → 20 → 30 → 40 → 50). Cada nodo tiene un solo hijo derecho, creando una estructura lineal.

**Resultado esperado:**
- La carga se acepta porque el modo es "estres"
- El modo estrés se activa en el catálogo
- El orden BST es válido (claves crecientes hacia la derecha)
- Las alturas son coherentes (0, 1, 2, 3, 4)
- Los factores de balance están fuera de {-1, 0, 1} pero aceptados en estrés
- La recuperación de balance puede reestructurar el árbol

**Requisito A3 que demuestra:** Excepción de `TOPOLOGIA_DESEQUILIBRADA` en modo estrés - permite factores fuera de rango temporalmente.

---

### 9. json_invalido.json

**Estado inicial:** Catálogo vacío con zona "Ciudad" poblada.

**Acción:** Intenta cargar una topología con un ciclo: nodo 10 tiene como hijo derecho a nodo 20, y nodo 20 tiene como hijo izquierdo a nodo 10. Esto crea un ciclo infinito.

**Resultado esperado:**
- El sistema detecta el ciclo durante la validación de topología
- La carga se rechaza con error `CICLO`
- El catálogo permanece vacío (atomicidad)
- Valida que la validación previene estructuras inválidas

**Requisito A3 que demuestra:** `CICLO` - validación de que no existen ciclos en la topología.

---

### 10. rafagas_fifo.json

**Estado inicial:** Catálogo vacío con zona "Ciudad" poblada.

**Acción:** Carga 10 eventos en un orden específico que simula una ráfaga de reportes FIFO:
- IDs 10, 20, 30, 40, 50: altas nuevas (primeros 5 eventos)
- ID 60: corrección de un evento existente (simula que cambió magnitud y pasó a prioridad 3)
- ID 70: confirmación de un evento existente (mismos datos, misma revisión)
- ID 80: alta nueva con prioridad alta (magnitud >= 6.0)
- IDs 90, 100: confirmaciones adicionales

**Resultado esperado:**
- Los eventos se insertan en el orden del arreglo
- El AVL mantiene el orden por `(prioridad, magnitud, identificador)`
- Las correcciones que cambian la clave causan re-inserción en el AVL
- Las confirmaciones no duplican eventos, solo agregan estaciones
- El orden FIFO se respeta en la cola de reportes
- Valida el procesamiento secuencial reproducible

**Requisito A3 que demuestra:** `ID_DUPLICADO` - valida que no hay IDs duplicados en una carga, y lógica de correcciones que cambian clave.

---

## Coordinación con Samuel (Asociaciones)

Según lo solicitado, los datos lógicos de asociaciones deben coordinarse con Samuel. Actualmente:

- El campo `asociaciones` en el esquema A3 está vacío en todos los archivos de prueba
- Cuando Samuel defina la estructura de asociaciones, estos archivos pueden extenderse para incluir casos de prueba de asociaciones
- La validación de asociaciones (prohibición de ciclos, cardinalidad, etc.) se agregará cuando la especificación esté disponible

---

## Validación del Esquema A3

Todos los archivos respetan el esquema A3 definido en `docs/CONTRATO_JSON_SISMOLAB.md`:

1. **Campos obligatorios:** `version`, `tipo_carga`, `reloj`, `modo`, `zonas`, y `eventos` o `nodos`/`raiz`
2. **Tipos de datos:** Decimales con un decimal, fechas ISO 8601 con zona horaria, enteros en rangos válidos
3. **Enumeraciones:** `modo` es "normal" o "estres"
4. **Clave AVL:** Orden por `(prioridad, magnitud, identificador)` donde prioridad y magnitud son derivados
5. **Atomicidad:** La carga falla completamente si cualquier validación falla

---

## Ejecución de Pruebas

Para ejecutar las pruebas con estos archivos:

```python
from src.catalogo import CatalogoSismico, leer_json_archivo
from src.dominio import Zona
from datetime import datetime, timezone

# Cargar un archivo JSON
datos = leer_json_archivo("tests/fixtures/limites_empates.json")

# Crear catálogo
zonas = [Zona("Ciudad", 0, 500, 0, 500, True)]
catalogo = CatalogoSismico(zonas, datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc))

# Cargar por inserciones o topología
if datos["tipo_carga"] == "inserciones":
    estadisticas = catalogo.cargar_por_inserciones(datos)
elif datos["tipo_carga"] == "topologia":
    # Convertir claves de string a int para nodos
    datos["nodos"] = {int(k): v for k, v in datos["nodos"].items()}
    datos["raiz"] = int(datos["raiz"]) if datos["raiz"] is not None else None
    estadisticas = catalogo.cargar_por_topologia(datos)

# Verificar resultados
print(f"Eventos activos: {len(catalogo.indice_activos)}")
print(f"Modo estrés: {catalogo.modo_estres}")
print(f"Altura AVL: {catalogo.avl.altura()}")
```

---

## Notas de Implementación

- Los archivos usan el estándar JSON válido sin comentarios
- Los identificadores son únicos dentro de cada archivo
- Las fechas usan formato ISO 8601 con sufijo 'Z' para UTC
- Los decimales tienen exactamente un decimal (ej: 4.5, no 4.50)
- Los nombres de estaciones siguen el formato "EST-XX"
- Las coordenadas (x, y) están dentro de los límites de las zonas definidas

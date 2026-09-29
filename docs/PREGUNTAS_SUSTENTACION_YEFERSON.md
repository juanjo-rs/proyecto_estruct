# Preguntas de Sustentación - SismoLab AVL

## P1: ¿Por qué una lista no recupera topología?

**Respuesta corta:** Una lista ordenada (recorrido inorden) solo conserva el orden de las claves, no la estructura del árbol. Muchas topologías distintas producen exactamente mismo recorrido inorden. Además, las rotaciones AVL cambian padre e hijos sin alterar el orden inorden. Para recuperar la topología exacta, se debe guardar la raíz, IDs de nodos, y sus enlaces izquierdo/derecho.

**Ejemplo:** Un árbol balanceado y uno degenerado con las mismas claves tienen el mismo inorden pero estructuras completamente diferentes.

---

## P2: ¿Cómo funciona la carga atómica?

**Respuesta corta:** La carga construye un escenario temporal (avl_temp, bst_temp, indice_temp) y valida todos los datos antes de reemplazar el escenario actual. Si cualquier validación falla, se propaga el error y el escenario original permanece intacto. Solo cuando todas las validaciones pasan, se reemplazan los árboles, índices y cola en una única operación.

**Garantía:** No hay estados intermedios corruptos; o todo carga o nada carga.

---

## P3: ¿Diferencia entre instantánea y versión?

**Respuesta corta:** 
- **Instantánea:** Vive en memoria (pila de deshacer), dura solo la sesión actual, contiene copia profunda completa, se usa para deshacer operaciones.
- **Versión:** Vive en disco (directorio `versiones/`), persiste entre sesiones, contiene escenario completo serializado en JSON, se usa para guardar/cargar escenarios.

**Restauración:** Instantánea desapila y restaura referencias (O(1)); versión lee JSON y reconstruye estructuras (O(n)).

---

## P4: ¿Qué se restaura al deshacer un paso de cola?

**Respuesta corta:** Se restaura **todo el estado anterior**, no solo el último elemento de la cola. Esto incluye: zonas, reloj, AVL completo, BST completo, índice activos, archivados, eliminados, cola FIFO completa (todos los reportes pendientes), parámetros, modo, métricas y asociaciones. La instantánea captura una copia profunda de todo el catálogo antes de la operación.

**Nota:** La cola se restaura completamente, no solo el elemento que se estaba procesando.

---

## P5: ¿Costos de guardar/restaurar?

**Respuesta corta:**
- **Guardar versión:** O(n) para exportar escenario + O(n) para escribir JSON
- **Restaurar versión:** O(n) para leer JSON + O(n) para reconstruir AVL/BST/índices
- **Capturar instantánea:** O(n) para deepcopy de n nodos y eventos
- **Deshacer:** O(1) para desapilar + O(1) para restaurar referencias

Donde n es el número de eventos/nodos en el escenario.

---

## P6: ¿Por qué se usa deepcopy para instantáneas?

**Respuesta corta:** Deepcopy garantiza que la instantánea sea inmutable y completamente independiente del estado actual. Si se usaran referencias superficiales, modificaciones posteriores afectarían la instantánea guardada, rompiendo la garantía de deshacer. Deepcopy copia recursivamente todos los objetos anidados (nodos, eventos, estructuras de datos).

---

## P7: ¿Cómo se valida el orden BST global?

**Respuesta corta:** Usando propagación de límites (min_key, max_key) en un recorrido DFS. Cada nodo recibe un rango válido: su clave debe ser > min_key y < max_key. Los límites se propagan: subárbol izquierdo recibe (min_key, clave_nodo) y subárbol derecho recibe (clave_nodo, max_key). Esto valida que toda clave izquierda es menor y toda clave derecha es mayor que la clave de cada ancestro.

---

## P8: ¿Qué pasa si la carga falla a mitad de proceso?

**Respuesta corta:** El escenario actual permanece completamente intacto. La carga usa un escenario temporal separado; si falla cualquier validación, se descarta el temporal y se propaga el error. No hay mutaciones parciales en el catálogo original. Esto es la garantía de atomicidad: o todo carga, o nada carga.

---

## P9: ¿Por qué el AVL y BST se sincronizan?

**Respuesta corta:** El BST existe como árbol de referencia para comparar estructuras y validar que el AVL mantiene las propiedades de búsqueda correctas. Ambos árboles se actualizan en paralelo en cada operación (crear, corregir, eliminar) para garantizar consistencia. Si el AVL pierde balanceo, el BST muestra la estructura no balanceada equivalente.

---

## P10: ¿Cómo se manejan los ciclos en topología?

**Respuesta corta:** La validación de topología detecta ciclos usando DFS con rastreo del camino actual. Si al visitar un nodo se encuentra que ya está en el camino actual, se detecta un ciclo y se rechaza la carga con error `CICLO`. Esto previene estructuras inválidas que causarían infinitos recorridos o corrupción de datos.

---

## P11: ¿Cuál es el costo de validar topología?

**Respuesta corta:** O(n) donde n es el número de nodos. La validación realiza múltiples recorridos DFS: uno para referencias, uno para ciclos, uno para orden BST, y uno para alturas. Cada recorrido es O(n), y el total sigue siendo O(n) porque el número de recorridos es constante.

---

## P12: ¿Por qué el historial JSON solo guarda descripciones?

**Respuesta corta:** Por diseño actual para simplificar el formato JSON. Guardar instantáneas profundas completas en el historial JSON aumentaría significativamente el tamaño del archivo y la complejidad de serialización. Las descripciones son suficientes para auditoría; las instantáneas profundas se guardan en memoria para deshacer en la sesión actual.

**Limitación:** No se puede deshacer acciones entre sesiones usando solo el JSON guardado.

---

## P13: ¿Cómo se decide qué rama archivar?

**Respuesta corta:** El sistema lista todas las ramas elegibles (subárboles donde todos los eventos son prioridad 1 y antigüedad > T minutos) y las ordena por: (1) más eventos, (2) más profunda, (3) mayor ID raíz. La rama ganadora es la primera en esta ordenación. La elección es determinista y reproducible.

---

## P14: ¿Qué sucede con las correcciones que cambian la clave AVL?

**Respuesta corta:** Si una corrección cambia la clave (prioridad, magnitud, o identificador), el evento se elimina del AVL con la clave anterior y se reinserta con la nueva clave. Esto asegura que el AVL mantenga el orden correcto. El BST se sincroniza con la misma operación. Si la clave no cambia, el evento se modifica in-place.

---

## P15: ¿Por qué se separa GUI de negocio?

**Respuesta corta:** Para mantener la arquitectura limpia y prevenir mutaciones directas de estructuras de datos. La GUI solo lee vistas inmutables (`VistaNodo`, `VistaEventoMapa`) y llama métodos de negocio. El negocio controla todas las mutaciones de nodos, rotaciones de árboles, y actualizaciones de índices. Esto simplifica testing, debugging y mantenimiento.

---

## P16: ¿Cómo se maneja el modo estrés en carga?

**Respuesta corta:** Si el JSON declara `modo: "estres"`, la carga permite factores de balance fuera de {-1, 0, 1} temporalmente. La validación de orden BST y alturas sigue siendo obligatoria. Al desactivar el modo estrés, se llama `recuperar_balance()` que repara el árbol con rotaciones. En modo normal, cualquier factor fuera de rango causa rechazo inmediato.

---

## P17: ¿Qué valida el esquema JSON?

**Respuesta corta:** Actualmente no hay validación automática del esquema JSON antes de cargar. Las validaciones ocurren durante la carga: versión debe ser 1, tipo_carga debe ser "inserciones" o "topologia", campos obligatorios deben existir, y los valores deben cumplir con los tipos y rangos del dominio. No hay validación separada del esquema JSON.

---

## P18: ¿Cómo se calcula la prioridad?

**Respuesta corta:** Prioridad 3 si magnitud >= 6.0, o si magnitud >= 4.5, profundidad <= 30.0 y en zona poblada. Prioridad 2 si magnitud >= 4.5. Prioridad 1 en cualquier otro caso. Este cálculo es derivado y se recalcula en cada carga/corrección; no se confía en el valor almacenado en JSON.

---

## P19: ¿Por qué los IDs eliminados no se reutilizan?

**Respuesta corta:** Por diseño para prevenir confusiones y asegurar trazabilidad completa. Una vez que un ID se elimina, se marca en el conjunto `eliminados` y cualquier intento de reutilizarlo causa error. Esto garantiza que cada ID sea único en la historia del sistema y simplifica auditoría y debugging.

---

## P20: ¿Cuál es el costo de búsqueda en AVL vs BST?

**Respuesta corta:** Ambos son O(log n) en el caso promedio, pero el AVL garantiza O(log n) incluso en el peor caso por balanceo, mientras el BST puede degradarse a O(n) si se desbalancea. En el sistema actual, el AVL se mantiene balanceado (excepto en modo estrés), por lo que ambos tienen rendimiento similar.

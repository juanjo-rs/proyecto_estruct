# Guia de implementacion y deduccion del proyecto

Esta guia traduce el PDF **Proyecto Arboles - Estructuras de Datos** a un plan
de trabajo verificable. Es la referencia del equipo: si una decision de codigo
la contradice, prevalece el enunciado.

## 1. Lectura correcta del problema

El problema no es solamente dibujar un arbol. El AVL es el catalogo de eventos
**activos** y se ordena por la clave ascendente `K = (P, M, I)`:

1. `P`: prioridad calculada (1 baja, 2 media, 3 alta).
2. `M`: magnitud vigente.
3. `I`: identificador numerico.

Por eso la raiz no tiene por que ser el evento mas urgente. El evento con
mayor clave se obtiene al recorrer primero hacia la derecha. El identificador
es inmutable y no es la clave completa: se usa un indice auxiliar por ID para
consultarlo aun despues de una correccion. Un `dict` por ID es valido como
indice auxiliar; no reemplaza al AVL ni mantiene el orden.

Las relaciones izquierda/derecha son solo estructura de almacenamiento. Nunca
deben utilizarse como relaciones sismicas o como asociaciones entre eventos:
las rotaciones las cambian.

## 2. Reglas que no se deben negociar

| Tema | Regla obligatoria |
| --- | --- |
| AVL central | Altas, consultas y actualizaciones usan el AVL propio. No ordenar una lista paralela. |
| Comparador | Tupla lexicografica `(prioridad, magnitud, id)`, ascendente. |
| Identidad | Un ID representa un solo terremoto; eliminado no se reutiliza; archivado puede reactivarse solo con revision mayor y valida. |
| Prioridad | Alta: M >= 6.0, o M >= 4.5 + H <= 30 + zona poblada. Media: lo restante con M >= 4.5. Baja: los demas. |
| Correccion | Validar todo primero; retirar por clave vieja, modificar, recalcular y reinsertar si cambio `P` o `M`; una sola accion de historial. |
| Pila y cola | Pila explicita para deshacer y cola FIFO explicita para reportes pendientes. |
| Estres | Conserva BST pero aplaza giros; recuperar con rotaciones, no reconstruyendo desde una lista ordenada. |
| Carga | JSON sin ruta fija; carga atomica: si algo falla, el escenario anterior no cambia. |
| GUI | Separada de negocio. La GUI llama servicios; no cambia nodos AVL directamente. |

## 3. Modelo de dominio propuesto

```text
Escenario
|- zonas inmutables, estaciones inmutables, reloj, W/R/L/T, modo y metricas
|- CatalogoSismico
|  |- AVL de eventos activos              <- estructura principal
|  |- indice_activos: ID -> Evento        <- localizar por identificador
|  |- historico: ID -> Evento             <- archivados, conserva identidad
|  |- eliminados: conjunto de ID          <- impide reutilizacion
|  |- Cola<Reporte>                       <- rafaga FIFO
|  `- Pila<InstantaneaAccion>             <- deshacer
`- Evento
   |- datos fisicos, revision y estaciones aceptadas
   |- prioridad y zona poblada derivadas
   `- estado pendiente/revisado y asociaciones por identidad
```

El codigo inicial cubre las cajas fundamentales y deja delimitadas las fases
pendientes. Los datos decimales se deben usar como `Decimal` para que
los decimales de una cifra se comparen sin errores de `float`.

## 4. Casos de uso y flujo correcto

### CU-01: crear evento manual

1. Validar ID, rangos, una cifra decimal, fecha UTC y que no sea futura frente
   al reloj.
2. Rechazar si el ID esta activo, archivado o eliminado.
3. Determinar si el epicentro pertenece a al menos una zona poblada, incluyendo
   bordes.
4. Calcular prioridad y clave; insertar en AVL con balanceo normal o sin giros
   en estres.
5. Actualizar indice, asociaciones, indicadores, dibujo e instantanea de
   deshacer solo despues de que toda la operacion sea valida.

### CU-02: procesar un reporte de la cola

Desencolar solo un reporte y resolverlo completamente antes del siguiente:

| Situacion | Resultado |
| --- | --- |
| ID desconocido y datos validos | Crear; la primera revision puede ser mayor que 1. |
| Revision mayor | Correccion completa, recalculo y reubicacion si cambia la clave. |
| Misma revision y mismos datos | Confirmacion; agregar estacion sin crear nodo. |
| Misma revision y datos diferentes | Conflicto, no modificar. |
| Revision menor | Reporte antiguo, descartar. |
| ID eliminado | Rechazar siempre hasta deshacer o restaurar. |
| ID archivado + revision mayor valida | Reactivar como pendiente. |

La igualdad compara magnitud, profundidad, coordenadas y ocurrencia, no el
nombre de estacion ni la forma original del texto.

### CU-03: corregir, revisar y eliminar

- **Corregir:** preservar la identidad `Evento`, incrementar revision manual,
  dejar pendiente y actualizar asociaciones. Si la clave no cambia, puede
  evitarse la reinsercion, pero nunca la revision.
- **Marcar revisado:** cambia solo estado; no modifica clave ni rota el arbol.
- **Eliminar:** retirar solo ese ID por algoritmo AVL. Sus descendientes quedan
  activos; guardar sus datos fuera del AVL y poner el ID en retirados.

### CU-04: archivar rama

Primero recorrer la topologia actual y fijar el conjunto de nodos de cada
subarbol. Es elegible solo si *todos* son prioridad baja y antiguedad `> T`.
Elegir: mas nodos, luego raiz mas profunda, luego ID de raiz mayor. Mostrar la
lista antes de tocar el arbol. Al eliminar los IDs fijados, las rotaciones no
pueden incorporar ni excluir otros eventos.

### CU-05: recuperar desde estres

Pausar la cola. Auditar orden, alturas y factores. Aplicar giros de abajo hacia
arriba repetidamente hasta que cada factor sea -1, 0 o 1. Una sola rotacion
puede no bastar para diferencias de altura mayores que 2; por eso se requieren
pasadas hasta que la auditoria valide el AVL. El orden BST se conserva porque
una rotacion no altera el recorrido inorden.

## 5. Fases de implementacion para el equipo

| Fase | Resultado verificable | Responsable sugerido |
| --- | --- | --- |
| 0. Contrato | Revisar esta guia, elegir politica determinista de asociaciones y esquema JSON. | Todo el equipo |
| 1. Nucleo | Validaciones, `Evento`, AVL/BST, pila/cola, auditoria y pruebas de giros. | Estructuras |
| 2. Catalogo | Altas, consultas por ID, correcciones, revisado, eliminacion y cola de reportes. | Logica |
| 3. Relaciones | Calculo de candidatos con W/R, politica determinista documentada y actualizaciones afectadas. | Logica |
| 4. Estres y archivo | Modo sin giros, recuperacion por rotaciones, seleccion y archivo atomico de rama. | Estructuras |
| 5. Estado | Instantaneas profundas para deshacer, versiones nombradas, importacion/exportacion JSON atomica. | Persistencia |
| 6. Interfaz | Dibujos AVL/BST, mapa geografico, formularios, cola, historico, auditoria e indicadores. | GUI |
| 7. Cierre | Casos minimos, costos, manuales, evidencia Git y sustentacion. | Todo el equipo |

No inicien la fase siguiente sin pruebas automatizadas de la anterior. Cada
pull request debe contener: caso de prueba, decision documentada si cambia una
regla abierta, y comentario de codigo en ingles cuando explique una decision
no obvia.

## 6. Decisiones abiertas que el equipo debe cerrar

1. **Referencia de replica:** proponer `mayor magnitud`, luego `ocurrencia mas
   cercana anterior`, y por ultimo `ID menor`; es determinista y no depende del
   AVL. Debe aprobarse y conservarse al guardar/cargar.
2. **Indice para asociaciones:** una exploracion completa de activos+historico
   es correcta inicialmente y cuesta O(n). Solo optimizar con una estructura
   explicada y propia si se justifica.
3. **Deshacer:** usar instantanea profunda completa antes de cada accion
   observable es la ruta mas segura para una primera entrega. La pila almacena
   la instantanea; no referencias compartidas que puedan mutar despues.
4. **JSON topologico:** guardar un diccionario por ID y para cada nodo sus IDs
   izquierdo/derecho o `null`, mas ID de raiz. Validar referencias, ciclos,
   pertenencia unica, orden global, alturas/factores y derivados antes de
   sustituir el escenario.

## 7. Invariantes para la auditoria

- Cada ID aparece a lo sumo una vez entre activos, historicos y eliminados.
- Todo nodo izquierdo tiene clave menor que su raiz y todo derecho mayor;
  verificar limites globales, no solo hijos inmediatos.
- Altura de vacio = -1; hoja = 0; `FB = altura_izq - altura_der`.
- En modo normal `FB` pertenece a `{-1, 0, 1}`. En estres, un FB fuera de ese
  rango es esperado, pero orden y metadatos siguen teniendo que ser correctos.
- La prioridad almacenada coincide con los datos y zonas vigentes.
- Las asociaciones solo usan identidades activas o archivadas, no eliminadas,
  y no contienen ciclos.
- Cada accion que modifica estado captura todo lo necesario para restaurar:
  topologia, datos, cola, reloj, parametros, modo, historico y metricas.

## 8. Pruebas obligatorias antes de entregar

1. Limites M=4.5, M=6.0, H=30.0, borde de zona y empate por ID.
2. Correccion de M=4.8/H=70 a M=6.2/H=15, luego reporte antiguo.
3. Reporte tardio 6.1 a las 09:55 frente a 5.6 a las 10:00 y 4.2 a las 10:20.
4. Casos LL, RR, LR y RL; estres con factor mayor que 2 y recuperacion.
5. Archivo de rama, desempates, rama invalida por descendiente no bajo y
   deshacer completo.
6. Guardar/cargar una topologia normal y otra estres; rechazar JSON invalido
   sin modificar el escenario actual.
7. Restaurar una version tras reiniciar y deshacer una correccion y un paso de
   cola (incluido un reporte descartado).

## 9. Analisis de costos que deben defender

| Operacion | Costo esperado | Nota |
| --- | --- | --- |
| Insertar/buscar/eliminar AVL normal | O(log n) | Incluye giros O(1) por nivel. |
| BST de comparacion | O(h), hasta O(n) | No se balancea. |
| Buscar por ID con indice | O(1) promedio + O(1) acceso a objeto | El AVL sigue siendo catalogo y orden. |
| Encolar/desencolar | O(1) | Cola enlazada propia. |
| Asociaciones por exploracion | O(n) por evento afectado | Correcto antes de optimizar. |
| Auditoria/recorridos | O(n) | Deben visitar toda la estructura. |
| Instantanea profunda | O(n) tiempo y memoria por accion | Simple y defendible para una primera version. |

## 10. Lista de control de entrega

- [ ] Sin biblioteca que implemente AVL/BST, pila, cola o coleccion ordenada.
- [ ] GUI y negocio en modulos diferentes.
- [ ] JSON seleccionado con explorador, nunca ruta fija.
- [ ] Comentarios de codigo en ingles.
- [ ] README con ejecucion, manual de usuario y manual tecnico separados.
- [ ] Pruebas y JSON reproducibles para los dos modos de carga y las rafagas.
- [ ] Git con aportes de cada integrante, video tecnico en segundo idioma y
  evidencia de uso de IA para el informe tecnico.

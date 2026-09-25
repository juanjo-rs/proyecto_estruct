# Tutoria para Samuel: C1, C2 y C3

Esta guia explica las tres tareas de logica/catalogo como si fueran una clase
entre compañeros. No intentes implementar todo de una vez: termina, prueba y
entiende una tarea antes de pasar a la siguiente.

## 0. La idea general antes de escribir codigo

El programa tiene tres niveles que no deben mezclarse:

```text
GUI (botones, formularios, tablas, canvas)
          |
          v
CatalogoSismico (reglas del escenario, asociaciones y consultas)
          |
          v
AVL / BST / Pila / Cola (estructuras de datos)
```

Tu trabajo esta en el nivel central, `CatalogoSismico`. La interfaz debe pedir
acciones al catalogo, y el catalogo usa el AVL para mantener los eventos
activos. No pongas reglas de asociaciones en la GUI y no hagas que la GUI cambie
directamente `raiz`, `izquierda`, `derecha`, `altura` o las rotaciones del AVL.

La clave del AVL es `(prioridad, magnitud, identificador)`. Por eso el arbol
sirve para ordenar por prioridad/magnitud/ID, **no** para deducir relaciones
sismicas. Las relaciones sismicas se guardan por identificadores de eventos,
porque una rotacion puede cambiar de padre a un nodo sin cambiar el evento ni
sus relaciones.

La version actual del repositorio ya tiene el esqueleto que vas a usar:

- `CatalogoSismico` tiene `reloj`, `zonas`, `metricas`, `parametros`,
  `asociaciones`, `indice_activos`, `archivados`, `eliminados` e historial.
- `InstantaneaCatalogo` ya toma copias profundas para deshacer.
- `Evento` tiene ID, magnitud, profundidad del hipocentro, coordenadas, fecha,
  revision, estaciones, estado, prioridad y zona poblada.
- `ArbolAVL.buscar_clave(clave)` ya devuelve el evento y el numero de nodos
  visitados durante una busqueda por clave.

Lo que falta es dar significado consistente a `parametros` y `asociaciones`, y
crear las consultas de la seccion 11.

## 1. Reglas del enunciado que mandan sobre el diseno

1. Las estaciones se parametrizan al iniciar/cargar el escenario y son
   **inmutables durante la ejecucion**.
2. Las zonas y su geometria tambien permanecen fijas durante el escenario.
3. El reloj es explicito. Un evento no puede ocurrir despues de ese reloj y el
   usuario solo puede avanzarlo, no retrocederlo.
4. Los parametros iniciales son `W = 48 horas`, `R = 40 km`, `L = 3` y
   `T = 4320 minutos (72 horas)`. W, R y T son positivos; L es entero no negativo.
5. Cambiar un parametro o avanzar el reloj es una accion independiente que se
   puede deshacer. Deshacer debe restaurar parametros, reloj, metricas y todo el
   escenario anterior.
6. Una asociacion usa eventos activos y archivados, pero nunca eliminados.
7. Una rotacion AVL no cambia asociaciones. Crear, corregir, eliminar o cambiar
   W/R si las cambia.
8. Cada consulta debe reportar cuantos nodos del AVL examino. No todas las
   consultas son O(log n); decir O(n) cuando corresponde es correcto.

## 2. C1 - Escenario: estaciones, parametros, reloj y metricas

### 2.1 Que es C1 en palabras simples

C1 es el "tablero de control" del observatorio. Antes de hablar de asociaciones
o consultas, el catalogo debe saber con que reglas esta funcionando:

- Que estaciones existen.
- Que zonas existen y cuales son pobladas.
- Cual es el reloj simulado actual.
- Cuanto es la ventana temporal W, el radio R, el limite de acceso L y el
  umbral de archivo T.
- Que contadores lleva la aplicacion.

No se trata de inventar otra estructura de arbol. Se trata de representar el
estado global de forma segura y modificable solo donde el PDF lo permite.

### 2.2 Que representa cada parametro

| Parametro | Valor inicial | Regla | Para que lo usan |
| --- | ---: | --- | --- |
| W | 48 horas | Decimal/numero positivo | Maximo tiempo entre un posible evento principal A y una posible replica B. |
| R | 40 km | Decimal/numero positivo | Maxima distancia entre epicentros de A y B. |
| L | 3 | Entero >= 0 | Un evento activo de prioridad alta tiene acceso costoso si su profundidad es estrictamente mayor que L. |
| T | 72 horas | Decimal/numero positivo | Umbral de antiguedad para que una rama pueda archivarse. |

Ejemplos de limites que suelen causar errores:

- Si la diferencia es exactamente `W`, el candidato **si** sirve: es `<= W`.
- Si la distancia es exactamente `R`, el candidato **si** sirve: es `<= R`.
- Si la profundidad de nodo es exactamente `L`, **no** es acceso costoso: la
  condicion es `profundidad > L`.
- Si la antiguedad es exactamente `T`, no alcanza para archivo: debe ser
  estrictamente `antiguedad > T`.

### 2.3 Como representar estaciones y parametros

No hace falta una arquitectura complicada. Una propuesta facil de defender es:

```text
Estacion (inmutable)
  - codigo: str unico, por ejemplo "EST-01"
  - nombre: str opcional para mostrar

CatalogoSismico
  - estaciones: tupla de Estacion
  - zonas: tupla o lista que la logica nunca modifique durante ejecucion
  - reloj: datetime UTC
  - parametros: {"W": Decimal("48"), "R": Decimal("40"),
                 "L": 3, "T": Decimal("72")}
  - metricas: diccionario de contadores
```

Una `dataclass(frozen=True)` para `Estacion` evita cambiar su codigo o nombre
accidentalmente. Una tupla de estaciones evita que un metodo haga `append` o
`remove`. Si el equipo ya usa solo codigos de estacion como `str`, tambien es
valido guardar una tupla o `frozenset` de esos codigos; lo importante es validar
que sean unicos y no exponer un metodo para cambiarlos durante la ejecucion.

`Decimal` es preferible para W y R si el proyecto esta normalizando los otros
decimales con `Decimal`: evita que un borde como R = 40 quede falsamente fuera
por redondeos de `float`. Para L usa `int`, porque representa cantidad de
niveles, no una medida fisica.

### 2.4 Pasos de implementacion de C1

#### Paso 1: ubicar y completar los valores iniciales

En el constructor de `CatalogoSismico`, reemplaza el diccionario vacio de
`parametros` por sus cuatro valores iniciales. No esperes a que la GUI los mande.
El escenario debe ser valido desde que se crea.

Tambien define todas las metricas que el proyecto pide, aunque algunas se
incrementen en tareas de otros compañeros. Por ejemplo:

```text
correcciones_aceptadas, reportes_descartados, conflictos,
archivos_masivos, eventos_archivados,
casos_ll, casos_rr, casos_lr, casos_rl,
giros_izquierda, giros_derecha
```

Las metricas de eventos por prioridad, pendientes y acceso costoso se pueden
calcular a demanda recorriendo el AVL; no necesariamente deben ser contadores
que se actualizan manualmente. Eso reduce el riesgo de que se desincronicen.

#### Paso 2: validar estaciones al crear/cargar escenario

Define una validacion unica para las estaciones:

1. Debe existir al menos una estacion si el equipo decide que el escenario no
   puede estar vacio; si permite cero, documentenlo.
2. Cada codigo debe ser texto no vacio.
3. No puede repetirse un codigo.
4. El origen de una creacion o reporte debe estar en el conjunto de estaciones
   configuradas. No aceptar "EST-FANTASMA" solo porque es texto no vacio.

No hagas que `Evento.estaciones` sustituya el catalogo de estaciones: el primer
campo dice "quien ha reportado este evento"; el segundo dice "quienes pueden
emitir reportes en este escenario". Son conceptos distintos.

#### Paso 3: crear una sola operacion para cambiar parametros

Implementa algo equivalente a `cambiar_parametro(nombre, valor)`. La operacion
debe seguir este orden exacto:

1. Validar que `nombre` sea W, R, L o T.
2. Validar el tipo/rango del nuevo valor sin cambiar nada aun.
3. Si no es valido, lanzar/error y no registrar instantanea.
4. Registrar **una** instantanea previa: `Cambiar parametro W`.
5. Guardar el valor nuevo.
6. Ejecutar solo los efectos derivados que correspondan.
7. Devolver un resultado claro para la interfaz.

Efectos derivados correctos:

| Cambio | Efecto que debe ocurrir |
| --- | --- |
| W o R | Recalcular asociaciones. Esto se conecta con C2. |
| L | Recalcular la marca/lista de acceso costoso. No cambia prioridad ni clave. |
| T | No cambia el AVL ni asociaciones; cambia que ramas serian elegibles cuando se ejecute archivo. |

No tomes una instantanea dentro de `cambiar_parametro` y otra dentro de
`recalcular_asociaciones`. Para el usuario es una sola accion y un `deshacer()`
debe regresar todo de una vez.

#### Paso 4: avanzar el reloj correctamente

Ya existe una base de `avanzar_reloj`. Debe:

1. Convertir la fecha a UTC y validar precision de segundos.
2. Rechazar una fecha menor que el reloj actual.
3. Tomar una instantanea previa.
4. Cambiar el reloj.
5. Actualizar los indicadores que dependan del reloj, especialmente los que se
   usen para archivo por antiguedad.

Avanzar el reloj no cambia la fecha de ocurrencia de los eventos, no cambia su
prioridad y no rota el AVL. La antiguedad se calcula cuando se necesita:

```text
antiguedad = reloj_simulado - evento.ocurrencia
```

#### Paso 5: conectar las metricas del AVL sin duplicarlas

El AVL ya conoce sus giros y casos LL/RR/LR/RL. En vez de incrementar un segundo
contador manual en cada sitio, el catalogo puede crear un metodo de lectura que
tome los valores actuales del AVL para sus indicadores. Si se decide copiarlos
a `metricas`, establece un unico punto de sincronizacion despues de cada
operacion estructural. Dos fuentes de verdad para el mismo contador terminan
descuadradas.

### 2.5 Pruebas minimas de C1

1. Al crear catalogo, W/R/L/T valen 48/40/3/72.
2. W = 0, R negativo, T = 0, L = -1 y L = 2.5 se rechazan sin cambiar estado ni
   aumentar historial.
3. Cambiar W y deshacer restaura W anterior y las asociaciones anteriores.
4. Cambiar L y deshacer restaura la marca de acceso costoso.
5. Avanzar reloj funciona; intentar retroceder falla sin mutar.
6. Un reporte de estacion no configurada se rechaza.
7. Deshacer una accion restaura tambien metricas y parametros.

### 2.6 Error comun de C1

No dejes que la interfaz haga directamente:

```text
catalogo.parametros["W"] = 12
```

Eso evita validacion, deshacer y recalculo de asociaciones. La GUI debe llamar
a `cambiar_parametro("W", 12)`.

---

## 3. C2 - Asociaciones entre eventos

### 3.1 Que problema resuelve C2

El programa no debe decir que un evento es "causa real" de otro. Solo debe
mostrar que un evento B puede ser una posible replica de un evento anterior A.

La pregunta correcta es: **para este evento B, que eventos A son candidatos a
referencia y cual de ellos se elige de forma determinista?**

La direccion es importante:

```text
A (evento mayor y anterior)  ---- referencia posible ---->  B (evento posterior)
```

En los datos puedes guardar esto desde B hacia A:

```text
asociaciones[B.id] = {
    candidatos: [A1.id, A2.id, ...],
    referencia_elegida: A1.id o None
}
```

Guarda IDs, no nodos AVL. Asi, aunque una rotacion cambie la forma del arbol,
la relacion entre los mismos terremotos sigue intacta.

### 3.2 Regla exacta de candidato

Un evento A es candidato para B solo si cumple **todas** estas condiciones:

1. `A.magnitud > B.magnitud` (estrictamente mayor; igualdad no sirve).
2. `A.ocurrencia < B.ocurrencia` (estrictamente anterior; misma hora no sirve).
3. `B.ocurrencia - A.ocurrencia <= W horas`.
4. La distancia entre epicentros es `<= R km`.
5. A y B estan activos o archivados; los eliminados se excluyen.

La distancia euclidiana es:

```text
dx = A.x - B.x
dy = A.y - B.y
distancia_al_cuadrado = dx*dx + dy*dy
es_candidato_por_distancia si distancia_al_cuadrado <= R*R
```

Comparar cuadrados evita llamar a raiz cuadrada y conserva exactamente la
comparacion de limites. Como `R` es positivo, `d <= R` y `d^2 <= R^2` son
equivalentes.

Para la ventana temporal, no uses valor absoluto: A tiene que ser anterior. Una
forma clara es comprobar primero `A.ocurrencia < B.ocurrencia`; despues compara
la diferencia en segundos contra `W * 3600`.

### 3.3 Politica determinista cuando hay varios candidatos

El PDF deja que el equipo elija, pero exige que la decision dependa de datos y
no de orden de llegada ni topologia AVL. Esta es una politica sencilla y buena
para proponer/aprobar como A2:

1. Elegir la mayor magnitud.
2. Si empatan, elegir el evento temporalmente mas cercano antes de B (menor
   diferencia de tiempo).
3. Si siguen empatados, elegir el menor identificador numerico.

En forma de clave de orden para A, respecto a B:

```text
(-A.magnitud, B.ocurrencia - A.ocurrencia, A.identificador)
```

Se elige el minimo de esa clave. El signo menos hace que mayor magnitud gane.

Ejemplo: B ocurrio a las 12:00 y tiene M 4.0. Hay tres candidatos validos:

| Evento | M | Hora | Resultado |
| --- | ---: | --- | --- |
| A1 | 5.2 | 11:00 | Gana por mayor magnitud. |
| A2 | 5.0 | 11:50 | Pierde aunque sea mas cercano. |
| A3 | 5.2 | 10:00 | Pierde frente a A1 por ser menos cercano. |

Esta politica debe documentarse en la guia/manual tecnico y mantenerse igual al
guardar/cargar. Si el equipo aprueba otra politica, sustituyan esta en toda la
documentacion y pruebas, pero nunca elijan "el primero que encontre".

### 3.4 Por que no debe haber ciclos

La regla temporal ya evita ciclos: si B referencia a A, entonces A ocurrio
antes que B. Un ciclo pediria, por ejemplo, A antes que B y B antes que A al
mismo tiempo, lo cual es imposible. Aun asi, es sano validar defensivamente que
una referencia no sea el propio evento y que el ID exista entre activos o
archivados.

### 3.5 Estructura de datos recomendada

Usa dos mapas por ID:

```text
asociaciones_por_evento[B.id] = Asociacion(
    candidatos=(A1.id, A2.id, ...),
    referencia_elegida=A1.id o None
)

referenciados_por[A.id] = {B1.id, B2.id, ...}
```

El primer mapa resuelve "quienes son los candidatos y referencia de B". El
segundo resuelve "quienes usan a A como referencia" sin recorrer todas las
asociaciones cada vez. La clase `Asociacion` puede ser una dataclass sencilla;
no tiene que conocer nodos del AVL.

Al recalcular todas las asociaciones, crea ambos mapas nuevos en variables
locales y reemplazalos al final. Esto evita dejar mitad de la informacion vieja
si aparece un error.

### 3.6 Algoritmo simple y correcto para primera version

No intentes optimizar con otra estructura antes de tener pruebas. Con pocos
eventos del curso, recalcular todo es suficiente y facil de justificar.

1. Construir una coleccion de eventos permitidos: activos + archivados.
2. Excluir todo ID eliminado y verificar que un ID no aparezca en ambas partes.
3. Para cada B, revisar cada A de esa coleccion.
4. Si A cumple las cinco condiciones, agregar su ID a candidatos de B.
5. Ordenar candidatos con la politica determinista.
6. Guardar el primero como referencia elegida, o `None` si la lista esta vacia.
7. Construir al mismo tiempo el indice inverso `referenciados_por`.
8. Reemplazar ambos mapas antiguos por los nuevos.

Pseudocodigo deliberadamente simple:

```text
recalcular_asociaciones():
    eventos = activos + archivados, sin eliminados
    nuevas_asociaciones = {}
    nuevo_inverso = {}

    para cada B en eventos:
        candidatos = []
        para cada A en eventos:
            si A cumple regla de candidato para B:
                candidatos.agregar(A)
        ordenar candidatos con politica aprobada
        referencia = primer candidato o None
        nuevas_asociaciones[B.id] = (IDs candidatos, ID referencia)
        si referencia existe:
            nuevo_inverso[referencia].agregar(B.id)

    asociaciones_por_evento = nuevas_asociaciones
    referenciados_por = nuevo_inverso
```

Su costo es O(n^2): cada evento se compara con todos los eventos permitidos.
Para este primer proyecto es una decision correcta si la explican. Guardar todas
las listas de candidatos puede usar O(n^2) memoria en el peor caso; guardar solo
una referencia por B usa O(n), pero no serviria para mostrar los candidatos que
el enunciado solicita.

### 3.7 Cuando se deben actualizar asociaciones

| Operacion | Que hacer | Motivo |
| --- | --- | --- |
| Alta de evento | Recalcular todas. | El nuevo evento puede ser candidato de otros o tener candidato. |
| Correccion aceptada | Recalcular todas. | Cambian M, hora, posicion, prioridad indirecta o datos de B/A. |
| Eliminacion | Retirar el evento y recalcular todas. | Nadie puede seguir apuntando a un eliminado. |
| Cambio W o R | Recalcular todas. | Cambia la regla de candidato. |
| Reactivacion archivada con revision mayor | Recalcular todas. | Es una correccion de datos y estado. |
| Rotacion AVL | No recalcular. | La identidad y datos fisicos no cambiaron. |
| Archivo simple | No recalcular. | El evento sigue en historico y aun cuenta como candidato. |
| Cambio L, T o reloj | No recalcular. | No son condiciones de asociacion. |

Un detalle importante: "archivo simple" significa mover activos a historico sin
cambiar datos. Si la operacion de reactivacion trae una revision mayor, ya no es
simple archivo: debe actualizarse como correccion.

### 3.8 Donde llamar el recalculo sin romper deshacer

Las operaciones de catalogo deben hacer una sola instantanea antes de la accion
completa. Ejemplo en una correccion:

```text
validar datos nuevos
tomar instantanea "Corregir SIS-..."
retirar/reinsertar AVL si cambia clave
aplicar datos al Evento
recalcular asociaciones
actualizar metricas y vista
```

No tomes otra instantanea dentro de `recalcular_asociaciones`, porque al
deshacer el usuario tendria que presionar dos veces para revertir una correccion.

### 3.9 Pruebas minimas de C2

1. A con mayor magnitud, anterior, dentro de W y R es candidato de B.
2. Igual magnitud, misma hora, evento posterior, distancia `> R` y tiempo `> W`
   no son candidatos.
3. Distancia exactamente R y tiempo exactamente W si son candidatos.
4. Dos candidatos prueban los tres desempates de la politica aprobada.
5. Un evento archivado puede ser candidato; un eliminado no.
6. Corregir A cambia correctamente los candidatos de otros B.
7. Cambiar W o R y luego deshacer restaura asociaciones anteriores.
8. Forzar una rotacion AVL sin cambiar datos conserva exactamente las
   asociaciones antes y despues.
9. La consulta inversa muestra los B que usan a A como referencia.

### 3.10 Errores comunes de C2

- Usar `abs(A.hora - B.hora)`: deja que un evento futuro sea referencia.
- Usar `>=` para magnitud: la regla dice "mayor magnitud".
- Guardar un puntero al nodo AVL: se rompe conceptualmente tras una rotacion.
- Recalcular por orden de llegada y elegir el primero: no es determinista.
- Borrar asociaciones al archivar: archivado sigue participando.
- Olvidar actualizar referencias de otros eventos al corregir A: por eso la
  primera solucion recomputa todas.

---

## 4. C3 - Consultas y nodos examinados

### 4.1 Que significa "nodos examinados"

No es tiempo en milisegundos. Es un contador pedagogico: cuantos nodos del AVL
tuvo que visitar/inspeccionar la consulta para encontrar o descartar resultados.

Cada metodo de consulta deberia devolver una estructura parecida a:

```text
ResultadoConsulta(
    resultados=[...],
    nodos_examinados=numero,
    descripcion_costo="O(log n) ..." o "O(n) ..."
)
```

No mezcles ese valor con las metricas acumuladas del sistema: es el resultado de
una consulta puntual. La interfaz lo muestra junto con los resultados.

Para no acceder a nodos desde la GUI, pide a Juan Jose una API de lectura del
AVL, por ejemplo una funcion que recorra y entregue evento, profundidad y conteo
de visitas. Si debes implementarla, que sea de solo lectura y no haga giros.

### 4.2 Consulta 1: primeros k pendientes, orden descendente de K

**Que se pide:** los primeros `k` eventos activos con estado `pendiente`, en
orden descendente de clave. Recordatorio: mayor K significa prioridad mayor;
si empatan prioridad, mayor magnitud; despues mayor ID.

**Como hacerlo:** recorrido inorden inverso: derecha, nodo, izquierda. No
ordenes una lista de todos los eventos despues de recorrerla, porque el AVL ya
da el orden. Detente en cuanto juntes k pendientes.

Pasos:

1. Validar que `k` sea entero positivo.
2. Recorrer el AVL primero por la rama derecha.
3. Cada vez que inspecciones un nodo, aumentar `nodos_examinados`.
4. Si `evento.estado` es pendiente, agregarlo.
5. Al tener k resultados, detener todo el recorrido.
6. Si hay menos de k pendientes, devolver los existentes.

Un evento revisado se visita, se cuenta, pero no se agrega. Marcar revisado no
cambia su clave ni lo mueve en el AVL.

**Costo:** O(h + k) en el mejor caso si los primeros nodos ya sirven; O(n) en
el peor caso si hay muchos revisados o pocos pendientes. `h` es altura del AVL.

### 4.3 Consulta 2: intervalo inclusivo de magnitud

**Que se pide:** todos los eventos activos con `min_magnitud <= M <=
max_magnitud`.

La trampa es que magnitud es el segundo componente de la clave, no el primero.
No es seguro decir "si este nodo tiene M baja, descarto todo su subarbol
izquierdo" porque alli puede haber otra prioridad con una magnitud alta.

Hay dos opciones:

1. **Primera version, simple y correcta:** recorrer todo el AVL y filtrar por
   magnitud. Costo O(n), nodos examinados n. Esta es perfectamente valida si se
   documenta que no se puede podar de forma global por M sola.
2. **Version que aprovecha K:** hacer tres busquedas de rango, una por cada
   prioridad P. Para cada P buscar claves entre `(P, minM, 1)` y
   `(P, maxM, 999999)`. En una busqueda de rango BST, si la clave es menor que
   limite inferior, se descarta la izquierda; si es mayor que limite superior,
   se descarta la derecha. Es correcto porque ahora el rango si esta expresado
   en la misma clave K.

Para Samuel, la opcion 1 es recomendada primero: es mas facil de probar. Si el
equipo necesita justificar poda, pueden implementar opcion 2 despues y contar
cada visita real, incluso si el mismo nodo se examina al iniciar otro rango.

Siempre validar `min_magnitud <= max_magnitud` y los limites de magnitud.

### 4.4 Consulta 3: profundidad del hipocentro y rango de fechas

**Que se pide:** eventos activos con profundidad fisica `H <= limite` y fecha
de ocurrencia dentro de `[fecha_inicio, fecha_fin]`, ambos extremos inclusivos.

Esta profundidad H es la del hipocentro en km. No es profundidad del nodo AVL.
No uses `nodo.altura` ni nivel del nodo para responderla.

Como H y fecha no estan en K = (P, M, I), el AVL no permite descartar ramas por
esas condiciones. Haz recorrido completo, aumentando el contador por cada nodo
inspeccionado, y filtra:

```text
si evento.profundidad_hipocentro <= limite
   y fecha_inicio <= evento.ocurrencia <= fecha_fin:
       agregar resultado
```

Costo O(n), nodos examinados n. Validar que las dos fechas sean UTC y que inicio
no sea posterior a fin.

### 4.5 Consulta 4: asociaciones de un evento

**Que se pide:** candidatos de un evento, referencia elegida y eventos que lo
usan como referencia. Debe indicar si cada resultado esta activo o archivado.

Usa los dos mapas creados en C2:

1. Buscar el ID en `indice_activos`, `archivados` o `eliminados` para conocer
   su estado.
2. Si esta eliminado, explicar que no participa en asociaciones.
3. Leer `asociaciones_por_evento[id]` para obtener candidatos y referencia.
4. Para cada ID mostrado, consultar su estado actual (activo/archivado).
5. Leer `referenciados_por[id]` para la lista inversa.

Esta consulta puede examinar `0` nodos del AVL si el ID se resuelve mediante los
indices auxiliares. Eso no es trampa: se debe reportar claramente
`nodos_examinados_avl = 0` y explicar que se uso el indice por ID y el mapa de
asociaciones. El costo es O(c + r), donde c es numero de candidatos mostrados y
r el numero de eventos que lo referencian.

### 4.6 Consulta 5: prioridad alta con acceso costoso

**Que se pide:** eventos activos de prioridad alta que tengan profundidad de
nodo estrictamente mayor que L. Por cada resultado mostrar: profundidad de nodo,
L y numero de nodos visitados al buscar su clave.

No confundir tres datos diferentes:

| Dato | Significado |
| --- | --- |
| `profundidad_hipocentro` | Dato fisico H en km. |
| `profundidad_nodo` | Nivel en AVL: raiz 0, hijo 1, etc. |
| `altura` | Distancia maxima del nodo hacia abajo; no es profundidad. |

Implementacion inicial segura:

1. Recorrer el AVL con un parametro `profundidad`, iniciando en 0.
2. Incrementar `nodos_examinados` por cada nodo visitado.
3. Si el evento tiene prioridad 3 y `profundidad > L`, agregarlo.
4. Para cada resultado, llamar a `buscar_clave(evento.clave())`; el segundo
   valor devuelto es su costo simulado de localizacion por clave.

El recorrido completo cuesta O(n). Despues, las busquedas por clave de m eventos
cuestan O(m log n) en AVL normal. Es valido y claro para una primera entrega.

Como mejora opcional, se puede podar parte del arbol usando que prioridad 3 es
la parte alta de K, pero no lo hagas antes de que la version completa funcione.
La marca debe recalcularse tras cada cambio de estructura/datos/L: insercion,
eliminacion, correccion que reubique, recuperacion de estres y cambio de L. Una
rotacion puede cambiar la profundidad y por tanto la marca, aunque no cambie la
clave.

### 4.7 Orden recomendado para implementar C3

1. Crear `ResultadoConsulta` y acordar formato para todos los metodos.
2. Implementar top-k pendiente con recorrido inverso y parada temprana.
3. Implementar profundidad H + fechas con recorrido completo.
4. Implementar intervalo de magnitud primero completo; optimizar por rangos P
   solo si hay tiempo y pruebas.
5. Implementar consulta de asociaciones sobre los mapas de C2.
6. Implementar acceso costoso junto con el refresco de marcas de C1.
7. Agregar pruebas y una salida que muestre resultados + nodos examinados.

### 4.8 Pruebas minimas de C3

1. Top-k con eventos de misma prioridad/magnitud para comprobar desempate por
   ID y con revisados que se saltan.
2. `k=0`, negativo, decimal o texto se rechazan.
3. Magnitud: extremos inclusivos y un evento de prioridad distinta que demuestra
   por que el filtro global visita todos.
4. H/fechas: extremos inclusivos, fecha inicial posterior a final invalida y
   diferencia entre H fisica y profundidad de nodo.
5. Asociaciones: mostrar candidato activo, archivado y referencia inversa; ID
   eliminado no aparece.
6. Acceso costoso: L=0, raiz no costosa, hijo alto si es costoso; una rotacion o
   recuperacion cambia profundidad y actualiza la marca.
7. Cada prueba debe verificar tambien `nodos_examinados`, no solo IDs resultado.

---

## 5. Plan de trabajo en sesiones cortas

### Sesion 1: C1 sin asociaciones

1. Leer `src/catalogo.py`, `src/dominio.py` y `src/pila.py`.
2. Escribir una prueba que espere valores iniciales W/R/L/T.
3. Crear validacion y metodo `cambiar_parametro` sin llamar aun C2.
4. Probar deshacer parametro y avanzar reloj.
5. Hacer un commit pequeño, por ejemplo: `feat(catalogo): add validated scenario parameters`.

### Sesion 2: C2

1. Escribir la clase/mapas de asociaciones y aprobar la politica de desempate.
2. Crear primero una funcion pura `es_candidato(A, B, W, R)` con pruebas de
   bordes.
3. Crear luego `recalcular_asociaciones()` y pruebas con dos/tres eventos.
4. Conectarla a alta, correccion, eliminacion y cambio W/R.
5. Probar que una rotacion no la llama ni cambia resultado.
6. Commit: `feat(catalogo): maintain deterministic event associations`.

### Sesion 3: C3

1. Acordar una estructura uniforme de resultados y conteo.
2. Crear consultas una a una con pruebas antes de conectarlas a GUI.
3. Mostrar nodos examinados en cada resultado.
4. Commit: `feat(consultas): add catalog query results and AVL visit counts`.

## 6. Lista final de revision para Samuel

- [ ] W/R/L/T tienen valores iniciales y validacion.
- [ ] Estaciones y zonas no se pueden cambiar en plena ejecucion.
- [ ] Cambiar parametro y avanzar reloj se deshacen con una sola accion.
- [ ] Asociaciones guardan IDs, no punteros a nodos AVL.
- [ ] La politica de desempate esta escrita y no depende de llegada/topologia.
- [ ] Activos y archivados participan; eliminados no.
- [ ] Alta/correccion/eliminacion/W/R actualizan asociaciones; rotacion y archivo
  simple no.
- [ ] Cada consulta devuelve resultados y nodos AVL examinados.
- [ ] Ninguna consulta ordena una lista para reemplazar el AVL.
- [ ] Las pruebas cubren limites inclusivos/estrictos y deshacer.

Si una parte no esta clara, se recomienda hacer primero una prueba con dos o
tres eventos y dibujar en papel: fecha, magnitud, coordenadas, W y R. Si el
resultado esperado se entiende en papel, la implementacion se vuelve mucho mas
sencilla de revisar.

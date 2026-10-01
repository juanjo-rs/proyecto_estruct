# Analisis previo — Componente C1-C6 (Logica / catalogo, Samuel)

Documento de analisis a revisar **antes** de escribir o modificar codigo. No contiene
implementacion. Cubre: alcance exacto de C1-C6 segun la imagen de requisitos, su
trazabilidad al PDF base, el estado real del codigo actual (brechas con evidencia de
archivo/linea), los riesgos de romper el trabajo de otros integrantes, y las decisiones
de diseno que deben confirmarse antes de codear.

Fuentes revisadas:

- `docs/Requisitos1.jpeg` — tabla de asignacion de tareas C1-C6 (Samuel lider; Juan Jose
  en fronteras AVL).
- `docs/Proyecto de estructuras de datos SismoLab AVL.pdf` — enunciado oficial (10
  paginas, prevalece sobre cualquier guia si hay contradiccion).
- `docs/GUIA_IMPLEMENTACION.md` — plan de equipo derivado del PDF.
- `docs/TUTORIA_SAMUEL_C1_C3.md` — guia paso a paso ya escrita para C1, C2 y C3.
- `docs/CONTRATO_JSON_SISMOLAB.md` y `docs/MANUAL_TECNICO_ YEFERSON.md` — contrato de
  persistencia (A3, responsable Yeferson) con el que C1-C4 deben ser compatibles.
- `docs/GUIA_PRUEBAS_F1.md`, `docs/TAREA_B1/B4_*.md`, `docs/TAREA_E1_FORMULARIOS.md` —
  alcance de otros responsables (estructuras AVL/BST = Juan Jose; GUI = Jefferson).
- Codigo actual: `src/dominio.py`, `src/catalogo.py`, `src/arbol_avl.py`, `src/arbol_bst.py`,
  `src/pila.py`, `src/cola.py`, `src/nodo.py`, `main.py`, `interfaz.py`,
  `tests/test_base.py`.

---

## 1. Alcance exacto de C1-C6 (segun la imagen)

| ID | Tarea (texto de la imagen) | Responsable | Criterio "hecho" |
| --- | --- | --- | --- |
| C1 | Escenario: estaciones inmutables, W/R/L/T, reloj, metricas | Samuel | Parametros mutables con accion deshacible |
| C2 | Asociaciones §7: candidatos, sin ciclos, update en alta/correccion/elim/W/R | Samuel | Politica A2 aplicada; rotacion no cambia asociaciones |
| C3 | Consultas §11: top-k pendientes, magnitud/fechas/H, refs, acceso costoso + nodos examinados | Samuel | Cada consulta reporta nodos visitados |
| C4 | Huecos catalogo: guardar cuerpo eliminado; reactivacion archivada; marca acceso costoso | Samuel | Cumple §6 y §9 |
| C5 | Cola: rafaga N reportes, paso a paso / continuo; retroalimentacion de decision | Samuel (+ Jefferson UI) | Demuestra altas/confirmaciones/antiguos/correcciones |
| C6 | Pruebas de dominio: limites prioridad, correccion+reporte antiguo, reporte tardio §16 | Samuel | Casos minimos 1-3 verdes |

Todo el bloque C vive en la capa `CatalogoSismico` (`src/catalogo.py`) y sus modelos
(`src/dominio.py`). **No** toca `ArbolAVL`/`ArbolBST` salvo para llamarlos (eso es
"fronteras AVL" de Juan Jose) ni la ventana Tk (`interfaz.py`, de Jefferson), salvo el
pedazo de UI de cola que la imagen marca como compartido en C5.

---

## 2. Trazabilidad C1-C6 -> secciones del PDF

| Modulo | Secciones del PDF que debe cumplir |
| --- | --- |
| C1 | §3 (datos de escenario, reloj), §4 (prioridad, ya implementado en `dominio.py`), fragmentos de §9 (parametro L) |
| C2 | §7 completa (asociaciones) |
| C3 | §11 completa (4 consultas + conteo de nodos examinados) |
| C4 | §6 completa (alta/consulta/correccion/revisado/eliminacion/reportes) + §9 completa (profundidad de nodo y marca de acceso costoso) + §10 (diferencia eliminacion/archivo, ya cubierta por `archivar_rama`) |
| C5 | §8 completa (rafagas, cola FIFO, tabla de resolucion de reportes) |
| C6 | §16 completa (casos minimos obligatorios 1 a 3; los casos 4-6 son de estructuras/estres/persistencia, fuera de este bloque) |

`TUTORIA_SAMUEL_C1_C3.md` ya desarrolla C1, C2 y C3 en detalle pedagogico y **es
consistente** con el PDF; se usa como guia de implementacion para esos tres modulos. No
existe una guia escrita equivalente para C4, C5 y C6 — este documento la suple a nivel de
analisis, pero falta un documento tipo tutoria para esos tres si se quiere mantener el
mismo formato que C1-C3 (decision abierta, ver seccion 6).

---

## 3. Guardrails globales (no negociables, aplican a los 6 modulos)

1. **Sin bibliotecas de estructuras.** `catalogo.py` y `dominio.py` solo pueden usar
   `dataclasses`, `enum`, `datetime`, `decimal`, `typing`, `copy`, `json`, `pathlib`,
   `os` — nunca `collections.OrderedDict`, `heapq`, `bisect`, `sortedcontainers`, ni
   ordenar una lista para sustituir al AVL. El AVL/BST (`ArbolAVL`/`ArbolBST`,
   propiedad de Juan Jose) son las unicas estructuras de orden; C1-C6 las consume, no
   las reemplaza.
2. **Separacion GUI/negocio.** Ningun metodo nuevo debe asumir Tk ni mutar nada que la
   GUI lea directamente sin pasar por un metodo publico de `CatalogoSismico`.
3. **Una instantanea por accion observable.** Todo metodo que cambie estado debe llamar
   `self._registrar_instantanea(...)` **una sola vez**, antes de mutar, y nunca anidar
   una instantanea dentro de otra operacion que ya tomo la suya (p. ej.
   `recalcular_asociaciones()` NO debe registrar su propia instantanea si se llama desde
   `crear_evento`/`corregir_evento`/`eliminar_evento`/`cambiar_parametro`).
4. **Decimal, no float, para datos fisicos.** `magnitud`, `profundidad_hipocentro`, `x`,
   `y` ya usan `Decimal` vía `decimal_un_lugar` (`src/dominio.py:21`). W y R deben seguir
   el mismo patron si se seleccionan como `Decimal` (ver decision abierta 6.1).
5. **Limites inclusivos/estrictos exactos del PDF** — no asumir ninguno por simetria:
   - Prioridad alta: `M >= 6.0` o (`M >= 4.5` y `H <= 30.0` y zona poblada) — inclusive.
   - Candidato de asociacion: `A.magnitud > B.magnitud` (estricto), `A.ocurrencia <
     B.ocurrencia` (estricto), `diferencia <= W` (inclusive), `distancia <= R` (inclusive).
   - Acceso costoso: `profundidad_nodo > L` (estricto).
   - Archivo de rama: `antiguedad > T` (estricto).
6. **Rotaciones y archivo simple nunca disparan recalculo de asociaciones**; alta,
   correccion, eliminacion individual y cambio de W/R si lo disparan (tabla completa en
   `TUTORIA_SAMUEL_C1_C3.md` seccion 3.7).
7. **Comentarios de codigo en ingles** (requisito de entrega §17), breves, solo donde el
   porque no sea obvio.
8. **No usar rutas de archivo fijas** para JSON de escenario (ya respetado por
   `cargar_por_inserciones`/`cargar_por_topologia`, que reciben `dict`, no rutas).
9. **Cada consulta de C3 debe reportar nodos examinados**, incluso cuando ese numero sea
   `0` (caso de la consulta de asociaciones que resuelve por indice, no por el AVL).

---

## 4. Estado real del codigo por modulo (brechas con evidencia)

### C1 — Escenario (estaciones, W/R/L/T, reloj, metricas)

**Lo que ya existe:**
- `CatalogoSismico.__init__` (`src/catalogo.py:103-122`) inicializa `zonas`, `reloj`,
  `avl`, `bst`, indices, `historial`, `modo_estres`, `cola_pausada`.
- `avanzar_reloj` (`src/catalogo.py:410-415`) ya valida que el reloj no retroceda y toma
  instantanea.
- `indicadores()` (`src/catalogo.py:159-194`) ya lee giros/casos del AVL sin duplicarlos
  (patron recomendado en TUTORIA 2.4 Paso 5).

**Brechas confirmadas:**
- `self.parametros: dict[str, object] = {}` se inicializa **vacio**
  (`src/catalogo.py:113`). El PDF (§3, tabla) exige W=48h, R=40km, L=3, T=72h desde la
  creacion del escenario. Hoy el catalogo nace sin parametros validos.
- **No existe el metodo `cambiar_parametro`** en `catalogo.py`. Los tests actuales
  mutan el diccionario directamente: `self.catalogo.parametros["T"] = 60`
  (`tests/test_base.py:198,210,217,225,...`) y `self.catalogo.parametros["L"] = 0`
  (`tests/test_base.py:137,144`). Esto es exactamente el "error comun de C1" que
  `TUTORIA_SAMUEL_C1_C3.md` seccion 2.6 advierte evitar — hoy el proyecto completo
  depende de ese atajo. Ver riesgo de ruptura en seccion 5.
- **No existe un catalogo de estaciones** a nivel de `CatalogoSismico`. Solo existe
  `Evento.estaciones: set[str]` (dato por evento). No hay validacion de que una
  estacion emisora pertenezca a un conjunto configurado (`TUTORIA` seccion 2.2 Paso 2,
  punto 4): hoy se puede crear un evento con `estaciones={"EST-FANTASMA"}` sin que nada
  lo rechace, porque `Evento.validar()` (`src/dominio.py:86-103`) solo exige que el set
  no este vacio y que los nombres no sean cadenas vacias.
- `self.metricas` (`src/catalogo.py:117-122`) solo tiene 4 contadores
  (`correcciones_aceptadas`, `reportes_descartados`, `conflictos`, `eliminaciones`).
  Faltan `archivos_masivos` y `eventos_archivados` (`archivar_rama`,
  `src/catalogo.py:325-340`, no incrementa ninguna metrica hoy). `casos_ll/rr/lr/rl` y
  `giros_izquierda/derecha` ya se leen desde el AVL via `indicadores()`, consistente con
  "no duplicar" — pero esos nombres de metrica que pide la TUTORIA (seccion 2.4 Paso 1)
  no existen literalmente como claves de `self.metricas`; si el equipo requiere que
  `exportar_escenario_completo()["metricas"]` los incluya para persistencia, hay que
  decidir si se copian alli en el momento de exportar o se guardan tambien como claves
  vivas (ver decision abierta 6.4).

### C2 — Asociaciones (§7)

**Estado:** no implementado. `self.asociaciones: dict[object, object] = {}`
(`src/catalogo.py:114`) es un placeholder vacio sin tipo real.
`docs/MANUAL_TECNICO_ YEFERSON.md` seccion 9.1 lo confirma explicitamente:
*"Asociaciones vacias: El campo `asociaciones` esta pendiente de especificacion por
Samuel"*; `docs/GUIA_PRUEBAS_F1.md` seccion "Coordinacion con Samuel" dice lo mismo:
las fixtures de carga ya tienen el campo `asociaciones` reservado en el JSON pero vacio,
a la espera de este modulo.

No existe: dataclass `Asociacion`, funcion `es_candidato(A, B, W, R)`,
`recalcular_asociaciones()`, mapas `asociaciones_por_evento` / `referenciados_por`, ni
los enganches en `crear_evento`/`corregir_evento`/`eliminar_evento`/`cambiar_parametro`
que deben dispararlo.

### C3 — Consultas (§11)

**Estado:** no implementado como tal. Lo mas cercano es `indicadores()["acceso_costoso"]`
(`src/catalogo.py:163-174`), que calcula eventos de prioridad alta con
`profundidad > L` y SI cuenta nodos examinados via `self.avl.buscar_clave(...)`, pero:
- No existe el dataclass `ResultadoConsulta` unificado (resultados + nodos_examinados +
  descripcion_costo) que pide `TUTORIA` seccion 4.1.
- No existen las otras 3 consultas obligatorias: top-k pendientes en orden descendente
  de K, intervalo de magnitud + H/fechas, ni la consulta de asociaciones de un evento
  (esta ultima depende de que C2 exista primero).
- `consultar(identificador)` (`src/catalogo.py:211-218`) devuelve solo
  `(estado, Evento | None)` — no es una de las 4 consultas de §11, es la consulta simple
  de §6 (ver C4 mas abajo, que es donde falta enriquecerla).

### C4 — Huecos de catalogo (§6 y §9)

**Lectura de la tarea:** la imagen agrupa tres cosas bajo "huecos": cuerpo del evento
eliminado, reactivacion de archivados, y marca de acceso costoso. Evidencia por item:

1. **"Guardar cuerpo eliminado".** `eliminar_evento` (`src/catalogo.py:271-281`) retira
   el nodo del AVL/BST, borra `indice_activos[id]` y solo agrega el **id** a
   `self.eliminados: set[int]` (`src/catalogo.py:110`) — el cuerpo del `Evento` se
   descarta de cualquier estructura "viva" fuera de la instantanea de deshacer. El PDF
   (§6, "Eliminacion individual") dice literalmente: *"El evento solo puede recuperarse
   al deshacer la eliminacion o al restaurar una version anterior. Los datos necesarios
   para estas operaciones deben conservarse fuera del catalogo activo."* — Esto ya esta
   cubierto por `InstantaneaCatalogo.capturar()` (`src/catalogo.py:54-73`, deepcopy antes
   de cada eliminacion) para el caso "deshacer", y por `restaurar_version` para el caso
   "version anterior" (ambos ya implementados). **No es evidente que haga falta una
   estructura nueva**; ver decision abierta 6.2 antes de agregar
   `cuerpos_eliminados: dict[int, Evento]`.
2. **"Reactivacion archivada".** Ya implementada dentro de
   `procesar_siguiente_reporte` (`src/catalogo.py:365-374`): si el id esta en
   `self.archivados` y la revision entrante es mayor, se saca de archivados y se
   recrea como activo pendiente. Confirmado correcto contra la tabla del PDF (§6,
   "Procesamiento de reportes recibidos"). Falta: no incrementa ninguna metrica
   (`eventos_archivados` deberia decrecer o reflejarse de algun modo), y no hay prueba
   dedicada en `tests/test_base.py` que cubra especificamente la reactivacion (solo se
   infiere del flujo de cola).
3. **"Marca de acceso costoso".** Calculada on-demand en `indicadores()` — correcto
   segun TUTORIA 2.4 Paso 5 (evita doble fuente de verdad), y se recalcula siempre que
   se llama porque no se cachea. Pero la consulta por evento individual
   (`consultar(identificador)`) **no expone** profundidad de nodo, altura, factor de
   balance ni la marca de acceso costoso para ese evento puntual, pese a que el PDF
   (§6, "Consulta de un evento") exige mostrarlos: *"Para un evento activo se muestran
   sus datos vigentes, revision, estaciones..., profundidad del nodo, altura, factor de
   balance y asociaciones."* Esta es la brecha real y concreta de C4 contra §6: hay que
   enriquecer `consultar()` (o anadir un metodo nuevo tipo `consultar_detalle`) para
   que devuelva esos campos, usando lecturas de solo lectura del AVL (sin rotar), tal
   como pide TUTORIA seccion 4.1 ("pide a Juan Jose una API de lectura del AVL").

### C5 — Cola (rafaga, paso a paso/continuo)

**Estado: mayormente implementado**, a diferencia de C2/C3. Confirmado:
- `encolar_reporte` / `procesar_siguiente_reporte` (`src/catalogo.py:343-404`) ya
  implementan la tabla completa de §6 "Procesamiento de reportes recibidos" (alta nueva,
  revision mayor, confirmacion, conflicto, reporte antiguo, eliminado rechazado,
  archivado reactivado).
- `interfaz.py` ya tiene la ventana "Gestion de Cola de Reportes"
  (`interfaz.py:445-631`) con preparar N reportes, tabla FIFO visible, boton de
  procesamiento paso a paso y boton "Iniciar Continuo" con pausa entre pasos
  (`ventana_cola.after(500, ...)`, `interfaz.py:571`) — esto cubre la parte de UI que la
  imagen marca compartida con Jefferson.
- `tests/fixtures/rafagas_fifo.json` ya cubre altas, correccion que cambia clave y
  confirmaciones en una sola rafaga (`docs/GUIA_PRUEBAS_F1.md` seccion 10).

**Brechas puntuales:**
- `main.py` opcion "4. Crear rafaga" (`main.py:104-120`) **no usa la cola real**: llama
  `crear_evento` directo en un loop, sin pasar por `Reporte`/`encolar_reporte`. Es solo
  un smoke test, pero si se usa como "demostracion" de C5 séria enganoso — hay que
  decidir si se corrige o se deja claro que la demo real vive en `interfaz.py` y en los
  fixtures (ver decision abierta 6.5).
- Falta un caso de prueba de dominio dedicado a "conflicto" (misma revision, datos
  distintos) y a "reactivacion desde archivado" en `tests/test_base.py` — hoy se infiere
  del codigo pero no hay un `test_...` que lo verifique explicitamente linea por linea.
- El criterio de C5 pide demostrar explicitamente **correcciones** dentro de la rafaga —
  ya existe en `rafagas_fifo.json` (ID 60) pero conviene una prueba unitaria equivalente
  en Python puro, no solo JSON, para que sea mas facil de sustentar en vivo.

### C6 — Pruebas de dominio (§16, casos 1-3)

| Caso §16 | Cobertura actual | Brecha |
| --- | --- | --- |
| 1. Limites y empates (M=4.5, M=6.0, H=30.0, borde de zona, empate por ID) | Parcial: `test_prioridad_alta_en_limites` (`tests/test_base.py:32-36`) cubre un solo punto; `tests/fixtures/limites_empates.json` cubre desempate por ID. Falta un caso explicito de M=4.5 sin zona poblada (prioridad 2) vs M=4.5 con zona poblada y H=30.0 exacto (prioridad 3), y el caso de epicentro exactamente sobre el borde de una zona. | Completar matriz de casos limite como pruebas unitarias en `tests/test_base.py`, no solo fixtures JSON. |
| 2. Correccion y reporte antiguo (M=4.8/H=70 -> M=6.2/H=15, luego revision menor) | Parcial: `test_correccion_vuelve_pendiente_y_cambia_clave` (`tests/test_base.py:66-75`) prueba la correccion; `tests/fixtures/correccion_reporte_antiguo.json` prueba el reporte antiguo, pero como fixture de carga, no como secuencia correccion+reporte-antiguo en una sola prueba Python. | Falta una prueba que encadene: crear -> corregir (sube de P2 a P3) -> encolar reporte con revision menor -> verificar que se descarta sin crear otro nodo ni revertir la correccion. |
| 3. Reporte tardio (5.6 a las 10:00, 4.2 a las 10:20, luego 6.1 a las 09:55; mostrar candidatos y politica de seleccion) | No implementable todavia: depende de C2 (asociaciones) y de la politica de desempate aprobada. `tests/fixtures/reporte_tardio.json` hoy solo prueba `FECHA_FUTURA`, no es el mismo caso que pide §16 (ese es sobre fecha posterior al reloj, no sobre tardanza relativa entre eventos). | Bloqueado por C2. Una vez exista `recalcular_asociaciones`, escribir el caso exacto del PDF como prueba unitaria mostrando los candidatos nuevos tras el reporte tardio. |

---

## 5. Riesgos de romper trabajo de otros integrantes / codigo existente

Estos son los puntos donde una implementacion ingenua de C1-C6 rompe algo que ya pasa
hoy. Deben resolverse como decisiones explicitas (seccion 6), no sobre la marcha.

1. **`CatalogoSismico.__init__(zonas, reloj)` tiene 2 parametros posicionales.** Toda
   la suite (`tests/test_base.py:30`), `main.py:11` e `interfaz.py` lo instancian asi.
   Si C1 agrega `estaciones` como tercer parametro **obligatorio**, los ~40 tests
   existentes y los dos entry points dejan de arrancar. Debe ser opcional con default
   seguro (lista/tupla vacia = "sin registro de estaciones configurado todavia"), o
   agregarse como metodo `configurar_estaciones(...)` separado llamado despues del
   constructor.
2. **Mutacion directa de `self.catalogo.parametros[...]`.** Usada hoy en al menos 6
   lugares de `tests/test_base.py` (lineas 137, 144, 198, 210, 217, 225, 948, 957, 973,
   365) y es el mecanismo que usan las pruebas de B4 (archivar rama, parametro T) y de
   persistencia (W). Si `cambiar_parametro` se implementa pero el diccionario se vuelve
   de solo lectura (p. ej. encapsulado detras de propiedad), **todas esas pruebas
   truenan**. Recomendado: dejar `parametros` como dict mutable igual que hoy (no
   romper acceso directo existente) y anadir `cambiar_parametro()` como la via
   *correcta y nueva* que ademas valida, dispara recalculo de asociaciones/marca de
   acceso costoso y registra instantanea — documentando que el acceso directo queda
   para pruebas/carga interna, no para flujos de usuario desde la GUI.
3. **Cambiar el tipo de `self.eliminados` rompe comparaciones exactas con `set()`.**
   `tests/test_base.py:98` y `:235` comparan `self.catalogo.eliminados == set()`. Si
   C4 decide guardar el cuerpo del evento eliminado, **no debe hacerse convirtiendo
   `eliminados` en `dict[int, Evento]`** (un dict vacio no es igual a un set vacio en
   Python) — usar una estructura nueva y separada (p. ej.
   `self.cuerpos_eliminados: dict[int, Evento]`) si se decide que hace falta.
4. **`exportar_escenario_completo()` ya tiene un formato acordado con Yeferson**
   (`docs/CONTRATO_JSON_SISMOLAB.md` seccion 4, `docs/MANUAL_TECNICO_ YEFERSON.md`
   seccion 1.3) y pruebas que verifican sus claves exactas
   (`tests/test_base.py:352-431`). Cualquier campo nuevo que C1/C2/C4 necesiten
   persistir (estaciones configuradas, asociaciones reales, metricas nuevas) debe
   **anadirse sin renombrar ni quitar** claves existentes, y coordinarse con Yeferson
   si cambia la forma de `asociaciones` (hoy vive vacio a proposito, esperando este
   trabajo) o de `metricas`.
5. **`listar_ramas_archivables` / `archivar_rama`** (`src/catalogo.py:313-340`, de B4,
   ya con pruebas verdes) no deben tocarse al resolver C4; si C4 agrega el contador
   `eventos_archivados`/`archivos_masivos`, debe sumarse dentro de `archivar_rama` sin
   alterar su logica de seleccion ya probada (`tests/test_base.py:197-281`).
6. **`main.py` opcion 4 ("Crear rafaga")** no es la cola real — si se usa como material
   de sustentacion de C5 sin corregirlo, se mostraria un flujo que no pasa por
   `Reporte`/cola FIFO, contradiciendo lo que pide §8. Confirmar con el equipo si se
   corrige o se usa solo `interfaz.py` + fixtures como demo.

---

## 6. Decisiones de diseno que requieren confirmacion antes de codear

1. **Representacion de W y R:** `Decimal` (consistente con el resto del dominio) vs
   `float`. Recomendado `Decimal` para evitar que `distancia <= R` falle por
   redondeo cuando `R` es exactamente 40 — igual razonamiento que `TUTORIA` seccion 2.3.
   `L` debe ser `int`, `T` se sugiere en minutos (igual unidad que usa `archivar_rama`
   hoy, ver `TAREA_B4_ARCHIVAR_RAMA.md` "T en minutos") aunque el PDF lo expresa en
   horas — **hay que confirmar la unidad de T** porque TUTORIA (horas, "T = 4320
   minutos (72 horas)") y la tarea B4 ya implementada (minutos) deben coincidir, y hoy
   `_evento_cumple_archivo` (`src/catalogo.py:283-286`) ya asume minutos.
2. **Catalogo de estaciones:** lista fija pasada al constructor vs metodo
   `configurar_estaciones()` llamado una sola vez tras crear el catalogo vs permitir que
   el escenario no tenga restriccion de estaciones si nunca se configura (modo
   permisivo por default para no romper tests/entry points existentes, segun riesgo 1).
3. **`cuerpos_eliminados`:** ¿hace falta una estructura nueva fuera del catalogo activo
   para el cuerpo del evento eliminado, o el mecanismo de instantaneas +
   `restaurar_version` ya satisface el requisito del PDF tal como esta hoy? Si se decide
   que si hace falta (p. ej. para mostrarlo en una consulta aunque no se pueda
   reactivar), confirmar su forma exacta y si se expone en `exportar_escenario_completo`.
4. **Nombres de metricas nuevas:** confirmar las claves exactas
   `archivos_masivos`/`eventos_archivados` (y si `casos_ll/rr/lr/rl` y
   `giros_izquierda/derecha` deben copiarse tambien como claves vivas de `self.metricas`
   para persistencia, o si `exportar_escenario_completo` los lee directo del AVL al
   momento de exportar).
5. **`main.py` opcion "Crear rafaga":** ¿se corrige para usar `Reporte`/`encolar_reporte`
   o se deja como smoke test y la demo de C5 vive solo en `interfaz.py`/fixtures?
6. **Politica determinista de asociaciones (C2):** el PDF deja la politica abierta;
   `TUTORIA_SAMUEL_C1_C3.md` seccion 3.3 propone: mayor magnitud -> menor diferencia de
   tiempo -> menor identificador. Esta politica debe aprobarse formalmente por el equipo
   (es la "Politica A2" que menciona el criterio "hecho" de C2 en la imagen) antes de
   codear `recalcular_asociaciones`, porque despues de aprobada no se puede cambiar sin
   invalidar pruebas y el manual tecnico.
7. **Formato de documentacion:** ¿se espera un `docs/TUTORIA_SAMUEL_C4_C6.md` con el
   mismo estilo pedagogico que `TUTORIA_SAMUEL_C1_C3.md` para C4-C6, o este analisis mas
   la implementacion y sus docstrings/README son suficientes?

---

## 7. Plan de implementacion propuesto (una vez confirmadas las decisiones)

Orden sugerido, cada paso con pruebas antes de pasar al siguiente (igual que exige
`GUIA_IMPLEMENTACION.md` seccion 5):

1. **C1**: `Estacion` (si aplica, dataclass frozen en `dominio.py`), valores iniciales
   de `parametros`, `cambiar_parametro()` con el orden exacto de TUTORIA 2.4 Paso 3,
   validacion de estaciones en `crear_evento`/`procesar_siguiente_reporte` si se
   configura un catalogo de estaciones.
2. **C2**: `Asociacion` dataclass, `es_candidato(A, B, W, R)` puro y testeado por
   separado, `recalcular_asociaciones()` O(n²) documentado, enganches en
   crear/corregir/eliminar/cambiar W-R, sin tocar rotaciones ni archivo simple.
3. **C3**: `ResultadoConsulta`, las 4 consultas de §11 en el orden que sugiere TUTORIA
   4.7 (top-k -> H/fechas -> magnitud -> asociaciones -> acceso costoso), reutilizando
   `avl.buscar_clave` y recorridos de solo lectura ya existentes.
4. **C4**: enriquecer `consultar()` con profundidad/altura/factor/asociaciones,
   metricas de archivo, y resolver la decision 6.3 sobre cuerpo eliminado.
5. **C5**: pruebas unitarias puras (no solo fixtures) para conflicto y reactivacion;
   decidir y resolver la discrepancia de `main.py` opcion 4.
6. **C6**: completar la matriz de casos limite de §16-1, la prueba encadenada de §16-2,
   y dejar §16-3 preparado para completarse en cuanto C2 este aprobado y codeado.

Cada paso debe cerrar con `python -m unittest discover -s tests -v` en verde antes de
continuar al siguiente, sin tocar `src/arbol_avl.py`, `src/arbol_bst.py`, `src/pila.py`
ni `src/cola.py` (propiedad de Juan Jose) salvo para consumir su API publica de solo
lectura.

---

## 8. Checklist de aceptacion por modulo (criterio "hecho" de la imagen)

- [ ] **C1** — Parametros W/R/L/T mutables unicamente via `cambiar_parametro`, accion
      deshacible de una sola instantanea, estaciones con regla de inmutabilidad definida
      y documentada.
- [ ] **C2** — Politica de desempate aprobada y aplicada; rotacion AVL demostrablemente
      no cambia `asociaciones_por_evento` ni `referenciados_por` (prueba dedicada).
- [ ] **C3** — Las 4 consultas de §11 devuelven resultados + nodos examinados con el
      mismo formato (`ResultadoConsulta`).
- [ ] **C4** — `consultar()` cumple integramente §6 (incluye profundidad de nodo,
      altura, factor de balance, asociaciones); marca de acceso costoso correcta tras
      insercion/eliminacion/correccion/cambio de L; reactivacion archivada probada
      explicitamente.
- [ ] **C5** — Rafaga de N reportes demostrando alta, confirmacion, reporte antiguo y
      correccion en una sola corrida, paso a paso y en modo continuo.
- [ ] **C6** — Casos 1, 2 y 3 de §16 verdes como pruebas automatizadas (no solo
      fixtures JSON).

---

## 9. Explicitamente fuera de este bloque (para no duplicar trabajo de otros)

- Rotaciones, balanceo, recorridos de bajo nivel, auditoria estructural del AVL/BST
  (`src/arbol_avl.py`, `src/arbol_bst.py`) — Juan Jose / tareas B1-B6.
- Formularios y ventanas Tk fuera de la cola compartida de C5
  (`docs/TAREA_E1_FORMULARIOS.md`) — Jefferson.
- Esquema y validacion de carga/guardado JSON (`docs/CONTRATO_JSON_SISMOLAB.md`,
  `cargar_por_inserciones`, `cargar_por_topologia`, `exportar_escenario_completo`) —
  Yeferson (A3), salvo los campos puntuales que C1/C2/C4 deban anadir, coordinados por
  separado.
- Modo estres y recuperacion de balance (`activar_modo_estres`,
  `recuperar_desde_estres`) — ya implementado y probado (Tarea B1), C1-C6 solo lo
  consume (p. ej., `cambiar_parametro` debe seguir respetando `modo_estres` igual que
  hoy hace `crear_evento`/`corregir_evento`).

---

## 10. Resumen para decidir antes de avanzar

El analisis confirma que **C1, C2 y C3 no tienen implementacion real todavia** (mas
alla de placeholders vacios), que **C5 ya esta mayormente resuelto**, y que **C4 es mas
pequeno de lo que su nombre sugiere** una vez se separa lo que ya esta cubierto por el
mecanismo de instantaneas de lo que realmente falta (enriquecer `consultar()` y las
metricas de archivo). El mayor riesgo tecnico no es la logica de negocio en si, sino
**romper contratos ya probados** (firma del constructor, acceso directo a `parametros`,
tipo de `eliminados`, forma del JSON de Yeferson) al resolverla. Se recomienda cerrar
las 7 decisiones de la seccion 6 explicitamente antes de escribir una sola linea de
`cambiar_parametro` o `recalcular_asociaciones`.

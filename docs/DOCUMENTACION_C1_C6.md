# Documentacion del codigo generado — Componente C1-C6 (Samuel)

Este documento describe **lo que se implemento**, **donde vive**, **como se conecta**
con el codigo existente de los demas integrantes, y **como se valido**. Complementa a
`docs/ANALISIS_REQUISITOS_C1_C6_SAMUEL.md` (el analisis previo): aqui se registran las
decisiones que ese analisis dejaba abiertas y la forma final que tomaron.

Archivos modificados: `src/dominio.py`, `src/catalogo.py`, `tests/test_base.py`.
Archivos **no** tocados (fuera de este bloque, ver seccion 7): `src/arbol_avl.py`,
`src/arbol_bst.py`, `src/pila.py`, `src/cola.py`, `src/nodo.py`, `main.py`, `interfaz.py`.

---

## 1. C1 — Escenario (estaciones, W/R/L/T, reloj, metricas)

### Que se agrego

- **`CatalogoSismico.__init__`** (`src/catalogo.py`) ahora acepta un tercer parametro
  opcional `estaciones: Iterable[str] = ()` y arranca `self.parametros` con los valores
  obligatorios del PDF (secciones 3/6/9/10) en vez de un diccionario vacio:
  `W = Decimal("48")`, `R = Decimal("40")`, `L = 3`, `T = Decimal("4320")` (minutos,
  equivalentes a 72 horas — ver seccion 6.1 de este documento sobre la unidad de T).
- **`self.estaciones: frozenset[str]`**: registro inmutable de codigos de estacion
  configurados. Si no se pasa nada (caso por defecto), queda vacio y el catalogo es
  **permisivo**: no exige que las estaciones de un evento/reporte pertenezcan a ningun
  conjunto. En cuanto se configura (constructor o `configurar_estaciones(...)`), toda
  alta/correccion/reporte queda sujeta a esa lista.
- **`CatalogoSismico.cambiar_parametro(nombre, valor)`**: unica via validada para tocar
  W/R/L/T. Sigue el orden exacto de `docs/TUTORIA_SAMUEL_C1_C3.md` seccion 2.4 paso 3:
  valida tipo/rango sin mutar nada, registra **una** instantanea, aplica el valor, y solo
  si `nombre` es `W` o `R` dispara `recalcular_asociaciones()` (C2). `L` y `T` no afectan
  asociaciones (`L` solo afecta la marca de acceso costoso, que se calcula al vuelo;
  `T` solo afecta elegibilidad futura de archivo).
- **`CatalogoSismico.configurar_estaciones(estaciones)`**: reemplaza el registro,
  validando codigos no vacios y sin duplicados. Pensado para configurarse al iniciar o
  cargar el escenario, no a mitad de ejecucion (PDF seccion 3: estaciones inmutables
  durante la ejecucion) — por eso **no** registra instantanea de deshacer.
- Nuevas claves de metrica: `archivos_masivos`, `eventos_archivados` (ver C4).

### Decision de diseno: `parametros` sigue siendo un dict mutable

El analisis (seccion 5, riesgo 2) advertia que varios tests de otros integrantes
(B1/B4/persistencia) mutan `catalogo.parametros["T"] = 60` directamente. Se decidio
**no** encapsular `parametros` detras de una propiedad de solo lectura: sigue siendo un
`dict` comun. `cambiar_parametro` es la via nueva y correcta (valida, deshace, recalcula
asociaciones) para flujos de usuario/GUI; el acceso directo queda disponible para
pruebas y para los flujos internos de carga (`cargar_por_inserciones`,
`cargar_por_topologia`, `restaurar_version`), que ya construian el escenario sin pasar
por un setter. Esto evito romper ningun test existente (ver seccion 5 de este
documento).

### Decision de diseno: estaciones, modo permisivo por defecto

En vez de un tercer parametro obligatorio (que hubiera roto el constructor en ~40 usos
existentes: `tests/test_base.py`, `main.py`, `interfaz.py`), `estaciones` es opcional con
default `()`. Un catalogo sin estaciones configuradas se comporta exactamente igual que
antes de este cambio. Esto resuelve el riesgo 1 del analisis sin perder la regla de
negocio: basta llamar `configurar_estaciones([...])` o pasar el argumento al crear el
catalogo para activarla.

### Donde se conecta

`_normalizar_y_clasificar` (llamado por `crear_evento`, `corregir_evento` y
`procesar_siguiente_reporte`) es el **unico punto** donde se valida pertenencia de
estaciones — asi cualquier camino de entrada de datos queda cubierto sin duplicar la
regla.

---

## 2. C2 — Asociaciones (PDF seccion 7)

### Que se agrego

- **`Asociacion`** (dataclass frozen, `src/dominio.py`): `candidatos: tuple[int, ...]`,
  `referencia_elegida: Optional[int]`. Guarda **identidades** (IDs), nunca nodos del AVL,
  tal como exige el PDF (una rotacion no debe invalidar la asociacion).
- **`es_candidato(a, b, w_horas, r_km)`** (funcion pura, `src/dominio.py`): regla exacta
  de la seccion 7 — `A.magnitud > B.magnitud` (estricto), `A.ocurrencia < B.ocurrencia`
  (estricto), diferencia en horas `<= W` (inclusive), distancia euclidiana `<= R`
  (inclusive, comparada al cuadrado para evitar `sqrt`).
- **`CatalogoSismico.recalcular_asociaciones()`**: reconstruye **todas** las asociaciones
  desde cero, O(n²), sobre `activos + archivados` (nunca eliminados). Aplica la
  **politica A2** (la que nombra el criterio "hecho" de C2 en la imagen de requisitos):
  mayor magnitud -> menor diferencia de tiempo con B -> menor identificador. Clave de
  orden: `(-magnitud, B.ocurrencia - A.ocurrencia, A.identificador)`, tomando el minimo.
- **`CatalogoSismico._referenciados_por(id)`**: mapa inverso ("quien usa a A como
  referencia") calculado **a demanda** (O(n), escaneando `self.asociaciones`) en vez de
  mantenerse como segunda estructura viva — el PDF seccion 12 permite explicitamente
  reconstruir en vez de persistir, y esto evita duplicar estado que podria desincronizarse.

### Donde se engancha (y donde deliberadamente NO)

| Operacion | Recalcula asociaciones | Por que |
| --- | --- | --- |
| `crear_evento` | Si (incondicional, al final) | Nuevo evento puede ser candidato o tener candidatos. |
| `corregir_evento` | Si (incondicional, incluso si la clave AVL no cambio) | x/y/ocurrencia pueden mover la ventana W/R sin cambiar P/M. |
| `eliminar_evento` | Si | Nadie puede seguir referenciando un ID eliminado. |
| `cambiar_parametro("W"/"R", ...)` | Si | Redefine la regla de candidato. |
| `cambiar_parametro("L"/"T", ...)` | No | No son condicion de asociacion. |
| `archivar_rama` | **No** | Archivo simple no cambia relaciones (PDF seccion 7); solo pasa eventos a historico, que sigue siendo candidato valido. |
| Rotacion AVL (`arbol_avl.py`) | No se toca ese archivo | Identidad y datos fisicos no cambian con una rotacion. |
| `cargar_por_inserciones` / `cargar_por_topologia` | Si, al final de la carga | Esos esquemas JSON no traen un campo `asociaciones` (ver `CONTRATO_JSON_SISMOLAB.md` seccion 2/3); sin este call, un escenario recien cargado quedaria con asociaciones vacias hasta la primera alta/correccion. |
| `restaurar_version` | No (se reconstruyen desde el JSON guardado) | El formato `escenario_completo` si persiste asociaciones (ver seccion 2.1 de este documento); se honra el estado exacto guardado en vez de recalcularlo. |

### Persistencia (coordinacion con el contrato JSON de Yeferson)

`docs/MANUAL_TECNICO_ YEFERSON.md` y `docs/GUIA_PRUEBAS_F1.md` dejaban el campo
`asociaciones` vacio "pendiente de especificacion por Samuel". Se definio asi:

```json
"asociaciones": {
  "<id_B>": {
    "candidatos": [<id_A1>, <id_A2>, "..."],
    "referencia_elegida": <id_A1> | null
  }
}
```

`exportar_escenario_completo()` ahora serializa `self.asociaciones` a esta forma (antes
hacia `self.asociaciones.copy()`, lo cual **hubiera roto** `json.dump` en cuanto el dict
dejara de estar vacio, porque `Asociacion` es un dataclass, no un tipo nativo de JSON).
`restaurar_version()` reconstruye objetos `Asociacion` desde ese mismo formato. El mapa
inverso `referenciados_por` **no se persiste** (se deriva siempre con
`_referenciados_por`), asi que no hay que coordinar un campo adicional en el contrato.

---

## 3. C3 — Consultas (PDF seccion 11)

### Que se agrego

- **`ResultadoConsulta`** (dataclass, `src/dominio.py`): envoltorio uniforme
  `resultados: list`, `nodos_examinados: int`, `descripcion_costo: str`, usado por las
  cinco consultas nuevas. Cada una documenta por que puede o no podar ramas segun K.
- **`consultar_top_k_pendientes(k)`**: recorrido inverso (derecha, nodo, izquierda) con
  pila explicita, se detiene apenas junta `k` pendientes. Cuenta **todo** nodo visitado,
  incluidos los revisados que se descartan. Costo `O(h + k)` mejor caso, `O(n)` peor caso.
- **`consultar_por_magnitud(min, max)`**: recorrido completo (magnitud es el segundo
  componente de K, no se puede podar por prioridad sola). `O(n)`.
- **`consultar_por_profundidad_y_fecha(limite_h, inicio, fin)`**: recorrido completo (H
  fisica y fecha no son parte de K). `O(n)`.
- **`consultar_asociaciones(id)`**: resuelve candidatos/referencia/referenciado-por
  **sin tocar el AVL** (`nodos_examinados = 0`), usando los indices de C2. Si el ID esta
  eliminado, devuelve un resultado explicando que no participa en asociaciones (en vez de
  lanzar error), siguiendo `TUTORIA` seccion 4.5.
- **`consultar_acceso_costoso()`**: recorrido completo + una busqueda por clave
  (`buscar_clave`) por cada evento de prioridad alta con profundidad `> L`, sumando ambos
  costos al contador. Mismo filtro que `indicadores()["acceso_costoso"]` pero con la
  forma rica que pide esta consulta especifica (ver nota de duplicacion abajo).
- **`_recorrer_avl_completo()`**: helper privado de recorrido preorden reutilizado por las
  dos consultas de recorrido completo, para no repetir la recursion dos veces.

### Nota de diseno: por que `consultar_acceso_costoso` no reutiliza `indicadores()`

`indicadores()` (preexistente, usado por la GUI del mapa) ya calculaba una lista de
acceso costoso con una forma de diccionario distinta
(`identificador/profundidad/examinados`) que **ya tiene pruebas pasando** con esa forma
exacta. Refactorizar para compartir codigo hubiera significado tocar una funcion ya
validada por otro flujo (mapa geografico) solo para ahorrar ~10 lineas. Se opto por una
pequena duplicacion documentada en vez de arriesgar esa funcion existente.

---

## 4. C4 — Huecos de catalogo (PDF secciones 6 y 9)

Tal como anticipaba el analisis (seccion 4, lectura de C4): la reactivacion de
archivados **ya existia** en `procesar_siguiente_reporte` y no se toco. Lo que
realmente faltaba:

- **`CatalogoSismico.consultar_detalle(id)`**: cumple integramente "Consulta de un
  evento" (PDF seccion 6). Devuelve estado, datos vigentes, revision, estaciones,
  `en_zona_poblada`, prioridad, clave, estado de atencion, y — solo para eventos
  **activos** — `profundidad_nodo`, `altura_nodo`, `factor_balance` (via el nuevo helper
  de solo lectura `_posicion_en_avl`) y la marca `acceso_costoso`. Siempre incluye
  `asociaciones` (reutiliza `consultar_asociaciones`). Para `eliminado` devuelve un
  mensaje explicando por que no hay datos vigentes; para `desconocido` devuelve solo el
  estado. No registra instantanea (es de solo lectura, igual que `consultar()`).
- **`CatalogoSismico._posicion_en_avl(clave)`**: camina el AVL comparando claves (mismo
  patron que ya usaba `obtener_vista_arbol` para `ArbolAVL._factor`), sin rotar, hasta
  encontrar el nodo exacto. Lanza `KeyError` si la clave no esta en el arbol activo.
- **Metricas de archivo**: `archivar_rama()` ahora incrementa
  `metricas["archivos_masivos"]` (+1 por operacion) y `metricas["eventos_archivados"]`
  (+ cantidad de IDs archivados), cerrando el hueco que el analisis senalaba (la funcion
  no tocaba ninguna metrica antes).

### Decision de diseno: no se agrego una estructura nueva para "cuerpo eliminado"

El analisis (decision abierta 6.3) dejaba dos lecturas posibles. Se eligio la lectura
liviana: el mecanismo ya existente de `InstantaneaCatalogo` (deshacer) y
`restaurar_version` (version anterior) ya satisface literalmente la frase del PDF *"el
evento solo puede recuperarse al deshacer la eliminacion o al restaurar una version
anterior"*. Agregar un `cuerpos_eliminados: dict[int, Evento]` habria sido una
estructura nueva sin un requisito que la exija explicitamente, y el analisis ya advertia
no convertir `self.eliminados` en `dict` (rompe comparaciones `== set()` en tests
existentes). Si el equipo decide en sustentacion que hace falta mostrar el cuerpo de un
evento eliminado en alguna consulta, es un agregado pequeño y aislado a partir de aqui.

---

## 5. C5 — Cola (confirmacion, sin cambios estructurales)

Como anticipaba el analisis, **C5 ya estaba resuelto** (cola FIFO, procesamiento paso a
paso/continuo en `interfaz.py`, tabla completa de resolucion de reportes en
`procesar_siguiente_reporte`). No se modifico ningun codigo de C5. Lo que se agrego es
**cobertura de prueba explicita** que antes solo se infiere del flujo:

- `test_reporte_conflicto_misma_revision_datos_distintos`: caso "conflicto" de la tabla
  del PDF seccion 6, antes sin una prueba unitaria dedicada.
- `test_reporte_con_revision_mayor_reactiva_evento_archivado` /
  `test_reporte_antiguo_no_reactiva_evento_archivado`: cubren explicitamente la
  reactivacion archivada y su contraparte (reporte antiguo que NO reactiva), ambas ya
  implementadas pero no probadas directamente antes.

`main.py` opcion "4. Crear rafaga" **no se modifico**: sigue sin pasar por la cola real
(usa `crear_evento` en loop). Se deja constancia aqui — y en el analisis previo, decision
abierta 6.5 — de que la demostracion real de C5 vive en `interfaz.py` y en
`tests/fixtures/rafagas_fifo.json`, no en ese menu de consola.

---

## 6. C6 — Pruebas de dominio (PDF seccion 16, casos 1-3)

Se completaron los tres casos obligatorios de esta seccion, ahora como pruebas unitarias
en Python (no solo fixtures JSON), en `tests/test_base.py`:

- **`test_caso16_1_limites_de_prioridad_y_zona`**: M=4.5 exacto con H=30.0 exacto dentro y
  fuera de zona poblada (prioridad 3 vs 2), M=6.0 solo basta, epicentro exactamente sobre
  el borde de una zona, y desempate por identificador verificado sobre el orden real del
  AVL (`sorted(claves) == claves`).
- **`test_caso16_2_correccion_y_reporte_antiguo_no_revierte`**: encadena exactamente el
  ejemplo del PDF — M=4.8/H=70.0 (prioridad 2) corregido a M=6.2/H=15.0 (prioridad 3),
  luego un reporte con revision menor llega y se descarta sin crear otro nodo ni revertir
  la correccion.
- **`test_caso16_3_reporte_tardio_cambia_candidatos`**: el ejemplo exacto del PDF — M=5.6
  a las 10:00 y M=4.2 a las 10:20, luego M=6.1 ocurrido a las 09:55 llega tarde y
  desplaza al evento anterior como referencia elegida de ambos. **Este caso estaba
  bloqueado hasta que C2 existiera**; ahora esta implementado y verde.

Ademas se agregaron pruebas de borde propias de C1-C4 (ver listas de nombres de test en
cada seccion anterior) que, sin ser parte literal de la seccion 16, refuerzan el mismo
objetivo de "casos minimos verdes" para el bloque completo.

---

## 7. Validacion realizada y como reproducirla

### 7.1 Limitacion del entorno de esta sesion

Esta maquina no tiene instalado un Python 3.11+ (el `__pycache__` del repo muestra que el
proyecto normalmente corre con **Python 3.14**; aqui solo hay 3.6, 3.9 y 2.7 registrados
via `py -0p`). `tests/test_base.py` importa `typing.assert_type`, disponible solo desde
3.11. Por eso la validacion en esta sesion se hizo en dos pasos:

1. Un script independiente (`validar_c1_c6.py`, fuera del repo, en el scratchpad de la
   sesion) que ejercita cada metodo nuevo directamente contra `src/catalogo.py` bajo
   Python 3.9, sin pasar por `tests/test_base.py`. Cubrio: valores iniciales de C1,
   validacion/undo de `cambiar_parametro`, rechazo de estaciones no configuradas,
   calculo de candidatos y politica A2 de C2 (incluyendo que una rotacion y un cambio de
   W/R se comporten como exige el PDF), las 5 consultas de C3, `consultar_detalle` de
   C4, las metricas de `archivar_rama`, y los tres casos de la seccion 16 (C6) — **todos
   verdes**.
2. Una ejecucion real de `tests/test_base.py` (y `tests/test_fixtures_f1.py`,
   `tests/integration/`, `tests/test_vista_arbol.py`, `tests/test_vista_mapa.py`) bajo
   Python 3.9, inyectando un `typing.assert_type` inocuo (nunca usado en tiempo de
   ejecucion dentro del archivo, solo importado) para poder cargar el modulo. Esto si
   corrio el archivo real del repositorio, con las 31 pruebas nuevas agregadas mas las
   43 preexistentes:

   ```
   Ran 74 tests in tests/test_base.py -> OK (0 failures, 0 errors)
   Ran 12 tests in tests/test_fixtures_f1.py -> OK
   Ran 13 tests in tests/integration/ -> 12 OK, 1 error preexistente (ver 7.3)
   Ran 6 tests in tests/test_vista_arbol.py -> OK
   Ran 9 tests in tests/test_vista_mapa.py -> OK
   ```

**Para re-verificar en un Python 3.11+ real** (como usa el equipo normalmente), basta:

```powershell
python -m unittest discover -s tests -v
```

sin ningun shim, porque alli `typing.assert_type` existe de forma nativa.

### 7.2 Regresion real encontrada y corregida durante la validacion

Inicializar `parametros` con valores `Decimal` (necesario para C1) rompio
`exportar_escenario_completo()`: `json.dump` no sabe serializar `Decimal`, y antes del
cambio el diccionario nacia vacio asi que el problema nunca se manifestaba. Se corrigio
agregando `serializar_parametro()` (convierte a `float`, igual que el resto de
cantidades fisicas en ese mismo metodo) antes de escribir el JSON. Confirmado: los 5
tests de guardado/restauracion de version que fallaban con `TypeError: Object of type
Decimal is not JSON serializable` pasan despues del fix.

### 7.3 Bugs preexistentes encontrados (no introducidos por este trabajo)

- `tests/test_base.py::test_desempate_id_raiz_mayor` llamaba al helper `evento(...)` con
  un argumento `ocurrencia=` que el helper no aceptaba (`TypeError`). Se corrigio
  **ampliando el helper** (`ocurrencia`, `x`, `y` ahora son parametros opcionales con los
  mismos valores por defecto de antes), lo cual arreglo esta prueba como efecto
  colateral sin tocar su logica.
- `src/dominio.py` usaba `Optional[int]` en `VistaNodo` sin importar `Optional` —
  inofensivo en la practica porque `from __future__ import annotations` pospone la
  evaluacion, pero se corrigio el import (`from typing import Iterable, Optional`) para
  que `ResultadoConsulta`/`Asociacion` y el resto del modulo queden correctos ante
  cualquier herramienta que si resuelva anotaciones (p. ej. `typing.get_type_hints`).
- `tests/integration/test_guardar_cargar_topologia_normal.py` usa `int | None` como
  anotacion de tipo evaluada en tiempo de ejecucion (sin `from __future__ import
  annotations`), lo cual requiere Python 3.10+. Falla bajo Python 3.9 con o sin mis
  cambios — **no se modifico** ese archivo porque es de Yeferson (A3) y el problema es
  anterior a este trabajo; se deja registrado aqui para que se corrija con un
  Python 3.11+ real (donde no falla) o agregando `from __future__ import annotations`.

---

## 8. Checklist de aceptacion (vuelta a la tabla de la imagen de requisitos)

- [x] **C1** — W/R/L/T con valores iniciales correctos, mutables solo via
      `cambiar_parametro` (validado, una instantanea, deshacible), estaciones con regla
      de inmutabilidad opcional y documentada.
- [x] **C2** — Politica A2 implementada y probada; rotacion AVL y cambio de parametros
      no relacionados (L/T) demostrablemente no tocan `asociaciones`; W/R si lo hacen.
- [x] **C3** — Las 5 consultas (incluye la de asociaciones) devuelven resultados +
      nodos examinados en el formato uniforme `ResultadoConsulta`.
- [x] **C4** — `consultar_detalle` cumple integramente la seccion 6 del PDF; metricas de
      archivo cerradas; reactivacion archivada confirmada con prueba dedicada.
- [x] **C5** — Cola ya operativa (preexistente); se agrego cobertura explicita de
      conflicto y reactivacion/no-reactivacion.
- [x] **C6** — Los tres casos obligatorios de la seccion 16 estan implementados como
      pruebas automatizadas y en verde.

## 9. Pendientes explicitos para el equipo (no resueltos aqui a proposito)

1. **`main.py` opcion "Crear rafaga"**: sigue sin usar la cola real. Confirmar si se
   corrige o se documenta como smoke test no representativo.
2. **Unidad de T**: se mantuvo en minutos (consistente con `archivar_rama`, ya
   implementado por B4), aunque el PDF la expresa en horas. Si el equipo prefiere
   cambiar la unidad canonica a horas en todo el proyecto, es un cambio coordinado que
   toca `_evento_cumple_archivo` (B4) ademas de esta entrega.
3. **Tutoria pedagogica C4-C6**: este documento cubre el "que y por que" a nivel tecnico;
   si se quiere el mismo formato paso a paso que `TUTORIA_SAMUEL_C1_C3.md` para C4-C6,
   falta escribirlo aparte.
4. **Entorno de Python**: se recomienda fijar explicitamente la version minima del
   proyecto (3.11 por `assert_type`, de facto 3.14 segun el `__pycache__`) en el
   `README.md`, para que cualquier integrante sepa que interprete usar sin tener que
   descubrirlo por un `ImportError`.

# Manual de usuario — SismoLab AVL

Cómo operar la ventana. Las reglas del árbol, el JSON y el deshacer están en el manual técnico.

## Abrir la aplicación

Desde la carpeta del proyecto:

```powershell
python interfaz.py
```

Hace falta Python 3 con Tkinter (viene con la instalación estándar). No hay que instalar librerías.

Al abrir, el escenario está vacío: cero eventos, cola vacía y modo normal. El reloj es la hora UTC del momento en que se abrió la ventana. La zona inicial cubre el mapa de 0 a 1000 y no está poblada.

La barra de estado se actualiza sola después de cada formulario. **Actualizar indicadores** la refresca a mano. Muestra eventos activos, tamaño de la cola, modo, altura y hojas del AVL, giros acumulados y cuántos eventos tienen acceso costoso.

Si un dato es inválido, aparece un mensaje y el escenario no cambia.

## Crear un evento

**Crear evento** pide:

| Campo | Qué escribir |
| --- | --- |
| Identificador | Entero de 1 a 999999. No se puede repetir ni reutilizar uno eliminado. |
| Magnitud | De -2.0 a 10.0, como máximo un decimal. |
| Profundidad (km) | De 0.0 a 700.0, como máximo un decimal. |
| X, Y | De 0.0 a 1000.0, como máximo un decimal. |
| Ocurrencia UTC | Viene llena con el reloj. Puedes escribir `2026-10-01 18:30` o pulsar **Usar reloj**. No puede ser posterior al reloj. |
| Estacion | Nombre no vacío, por ejemplo `EST-01`. |

Al aceptar, un cuadro muestra el id con seis dígitos (`SIS-000010`) y la prioridad calculada:

- Prioridad 3 si la magnitud es 6.0 o más.
- Prioridad 3 si la magnitud es 4.5 o más, la profundidad es 30.0 km o menos y el punto cae en una zona poblada.
- Prioridad 2 si la magnitud es 4.5 o más y no se cumplió lo anterior.
- Prioridad 1 en cualquier otro caso.

La zona inicial cubre todo el mapa y no está poblada, así que la prioridad 3 por zona no aparece hasta que crees una zona poblada. Una magnitud de 6.0 o más sí queda en prioridad 3.

## Consultar, corregir, revisar y eliminar

**Consultar evento.** Escribe el identificador. El cuadro dice si está activo, archivado, eliminado o desconocido. Si está activo o archivado, muestra prioridad, magnitud, profundidad, coordenadas, revisión y estado (`pendiente` o `revisado`). Consultar no modifica el escenario.

**Corregir evento.** El identificador es obligatorio. Los demás campos son opcionales: una caja vacía no se envía. Tiene que haber al menos un campo con dato. La revisión sube en 1 y el estado vuelve a `pendiente`. Si cambia la prioridad o la magnitud, el evento se reubica en los árboles.

**Marcar revisado.** Pasa un evento activo de `pendiente` a `revisado`. La clave del árbol no cambia. Solo funciona con un evento activo.

**Eliminar evento.** Pide confirmación. El identificador queda eliminado y no se puede volver a usar. Cancelar deja el escenario igual.

## Modo estrés

**Activar modo estres** deja de balancear el AVL en altas y eliminaciones. El orden de las claves se mantiene; el factor de balance puede salir de -1, 0 y 1.

**Desactivar (recuperar)** vuelve al modo normal y rebalancea el árbol. La barra pasa a decir `Modo normal`.

## Cola de reportes

**Gestionar cola de reportes** abre otra ventana.

1. Escribe una cantidad entera positiva y pulsa **Preparar**. Se encolan esa cantidad de reportes al azar (magnitud, profundidad, coordenadas y estación). El identificador continúa después del mayor que ya exista.
2. La tabla muestra la cola en orden de llegada: estación, id y revisión. El primero de la tabla es el siguiente en procesarse.
3. **Procesar Uno** resuelve solo ese reporte y escribe en el log la estación, el id, la revisión, la decisión y cuántos giros hubo.
4. **Iniciar Continuo** procesa uno cada medio segundo. **Pausar** / **Reanudar** detiene o sigue. **Detener** corta el ciclo. Cerrar la ventana también lo detiene.

La decisión del log puede ser, entre otras: `alta nueva`, `confirmacion aceptada`, `correccion aceptada`, `conflicto: misma revision con datos distintos`, `descartado: reporte antiguo` o `rechazado: identificador eliminado`.

## Árboles y mapa

**Visualizar arboles** muestra el AVL a la izquierda y el BST a la derecha. Cada círculo lleva el identificador. Debajo está la prioridad y la magnitud; en el AVL también la altura (`h`) y el factor (`f`). Si el árbol no cabe, usa la rueda para bajar y Shift+rueda para ir a los lados, o las barras de desplazamiento. Un clic en el círculo muestra prioridad, magnitud, estaciones y estado. **Redibujar** vuelve a leer el catálogo.

**Visualizar mapa** dibuja el cuadrado de 0 a 1000. El color del punto es la prioridad: verde = 1, amarillo = 2, rojo = 3. Un borde rojo grueso marca acceso costoso. La zona poblada se pinta en amarillo claro y la no poblada en gris. Un clic en un punto muestra sus datos. **Redibujar** actualiza el mapa.

## Versiones

**Guardar version** pide un nombre. El escenario queda en `versiones/<nombre>.json`. El nombre no puede estar vacío ni repetir uno que ya exista.

**Restaurar version** lista los archivos de esa carpeta. Elige uno y pulsa **Restaurar**. Si no hay archivos, avisa que no hay versiones. La restauración sustituye el escenario actual (eventos, cola, modo y métricas guardadas en ese archivo).

Estas versiones siguen en disco después de cerrar el programa.

## Consola de prueba

`python main.py` no abre la ventana. Crea tres eventos de ejemplo (ids 10, 20 y 30), imprime prioridades, auditoría y alturas, y deja este menú:

1. Activar modo estrés.
2. Desactivar modo estrés (imprime cuántos giros hizo la recuperación).
3. Crear un evento con datos fijos y el siguiente id desde 1.
4. Crear una ráfaga: pide un número e inserta esa cantidad de eventos iguales, luego imprime si el AVL quedó balanceado.
0. Salir.

## Pruebas automáticas

```powershell
python -m unittest discover -s tests -v
```

## Parámetros, estaciones y consultas

**Cambiar parametro.** Nombre `W`, `R`, `L` o `T`, y el valor. W, R y T son números positivos. L es un entero de 0 en adelante. Un valor inválido no cambia el escenario. Cambiar W o R recalcula las asociaciones.

**Configurar estaciones.** Códigos separados por coma, por ejemplo `EST-01, EST-02`. Después de esto, un evento con una estación que no esté en la lista se rechaza. Deshacer vuelve a la lista anterior.

**Gestionar zonas.** La primera de la lista es la zona inicial. **Agregar** crea otra, pero sus límites tienen que quedar dentro de esa inicial. **Editar** cambia el nombre, los límites o si está poblada (`si` o `no`) de la zona elegida; si editas la inicial y la achicas, las demás tienen que seguir adentro. **Quitar** borra una zona que no sea la inicial. Si un evento activo cambia de prioridad, se reubica en los árboles. Deshacer restaura las zonas y las prioridades anteriores. El mapa se actualiza con **Redibujar**.

**Avanzar reloj.** Fecha UTC posterior o igual a la actual. Una fecha anterior se rechaza.

**Consultar asociaciones.** Identificador. Muestra candidatos, la referencia elegida y cuántos nodos del AVL se examinaron (en esta consulta, cero: se resuelve por identificador).

**Top-k pendientes.** Un entero k. Los k eventos activos pendientes, de la clave mayor a la menor.

**Consultar por magnitud.** Mínimo y máximo, ambos inclusive.

**Consultar por profundidad y fecha.** Profundidad máxima en km, fecha inicio y fecha fin UTC.

**Acceso costoso.** Eventos de prioridad 3 cuya profundidad en el AVL supera L.

Consultar un evento eliminado muestra sus datos guardados (magnitud, coordenadas, fecha). Ese identificador no se puede volver a crear.

## Qué no está en esta ventana

No hay botón para archivar una rama ni para cargar un JSON. Esas operaciones siguen en el catálogo.

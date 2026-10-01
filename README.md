# SismoLab AVL

Base inicial para el proyecto **SismoLab AVL** de Estructuras de Datos.
Catálogo sísmico del proyecto de Estructuras de Datos. El AVL propio ordena por
`(prioridad, magnitud, identificador)`. El BST compara la misma secuencia de
claves. Pila, cola y árboles son estructuras del repositorio: solo se usa la
biblioteca estándar de Python.

La carpeta `TallerArbolesBinarios/` se conserva sin cambios como referencia del
taller original. Esta nueva base sigue el enunciado del PDF y usa solamente la
biblioteca estandar de Python: no hay bibliotecas de arboles, colas, pilas ni
colecciones ordenadas.
La carpeta `TallerArbolesBinarios/` queda como referencia del taller y no forma
parte de la entrega.

## Ejecucion
## Requisitos

Python 3 con Tkinter. No hay dependencias que instalar.

## Ejecución

Desde esta carpeta:

```powershell
python main.py
python -m unittest discover -s tests -v
python interfaz.py
```

Para abrir la ventana inicial:
Abre la ventana: formularios, modo estrés, cola de reportes, vista de árboles,
mapa y versiones. El uso de cada botón está en
[`docs/MANUAL_USUARIO.md`](docs/MANUAL_USUARIO.md).

Comprobación por consola (tres eventos de ejemplo y un menú de estrés):


```powershell
python interfaz.py
python main.py
```

## Estado de la plantilla

Ya implementado y probado:
Pruebas:

- Modelo de eventos, zonas y prioridad obligatoria.
- AVL propio por clave `(prioridad, magnitud, identificador)` y BST de comparacion.
- Insercion, busqueda por clave, eliminacion, recorridos, auditoria y recuperacion
  del balance del AVL.
- Catalogo inicial: altas, consulta por identificador, correccion, revision,
  eliminacion y procesamiento FIFO de reportes.
- Pila y cola propias, preparadas para el historial y las rafagas.
```powershell
python -m unittest discover -s tests -v
```

La guia en `docs/GUIA_IMPLEMENTACION.md` define las fases restantes, los
invariantes y los casos de prueba obligatorios. No se debe considerar esta base
como una entrega terminada: faltan, entre otros, asociaciones, archivo de ramas,
persistencia completa, deshacer por instantaneas y las vistas graficas finales.
## Documentos

## Plan de trabajo
| Documento | Contenido |
| --- | --- |
| [`docs/MANUAL_USUARIO.md`](docs/MANUAL_USUARIO.md) | Cómo operar la ventana |
| [`docs/GUIA_IMPLEMENTACION.md`](docs/GUIA_IMPLEMENTACION.md) | Fases, invariantes y casos del enunciado |
| [`docs/WORKPLAN.md`](docs/WORKPLAN.md) | Roles y tareas hasta la entrega |
| [`docs/CONTRATO_JSON_SISMOLAB.md`](docs/CONTRATO_JSON_SISMOLAB.md) | Esquema JSON |

Roles, tareas (A–F) y cronograma hasta la entrega: [`docs/WORKPLAN.md`](docs/WORKPLAN.md).
El manual técnico (dominio, costos, JSON y deshacer) es un documento aparte y
todavía no está cerrado.

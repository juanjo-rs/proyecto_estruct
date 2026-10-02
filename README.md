# SismoLab AVL

Catálogo sísmico del proyecto de Estructuras de Datos. El AVL propio ordena por
`(prioridad, magnitud, identificador)`. El BST compara la misma secuencia de
claves. Pila, cola y árboles son estructuras del repositorio: solo se usa la
biblioteca estándar de Python.

La carpeta `TallerArbolesBinarios/` queda como referencia del taller y no forma
parte de la entrega.

## Requisitos

Python 3 con Tkinter. No hay dependencias que instalar.

## Ejecución

Desde esta carpeta:

```powershell
python interfaz.py
```

Abre la ventana: formularios, modo estrés, cola de reportes, vista de árboles,
mapa y versiones. El uso de cada botón está en
[`docs/MANUAL_USUARIO.md`](docs/MANUAL_USUARIO.md).

Comprobación por consola (tres eventos de ejemplo y un menú de estrés):

```powershell
python main.py
```

Pruebas:

```powershell
python -m unittest discover -s tests -v
```

## Documentos

| Documento | Contenido |
| --- | --- |
| [`docs/MANUAL_USUARIO.md`](docs/MANUAL_USUARIO.md) | Cómo operar la ventana |
| [`docs/GUIA_IMPLEMENTACION.md`](docs/GUIA_IMPLEMENTACION.md) | Fases, invariantes y casos del enunciado |
| [`docs/WORKPLAN.md`](docs/WORKPLAN.md) | Roles y tareas hasta la entrega |
| [`docs/CONTRATO_JSON_SISMOLAB.md`](docs/CONTRATO_JSON_SISMOLAB.md) | Esquema JSON |

El manual técnico (dominio, costos, JSON y deshacer) es un documento aparte y
todavía no está cerrado.

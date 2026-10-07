# SismoLab AVL

Catálogo sísmico del proyecto de Estructuras de Datos. El AVL propio ordena por
`(prioridad, magnitud, identificador)`. El BST compara la misma secuencia de
claves. Pila, cola y árboles son estructuras del repositorio: solo se usa la
biblioteca estándar de Python.

## Requisitos

Python 3 con Tkinter. No hay dependencias que instalar.

## Ejecución

Desde esta carpeta:

```powershell
python interfaz.py
```

Abre la ventana: formularios, modo estrés, cola de reportes, vista de árboles,
mapa y versiones. Cómo usar cada botón está en el manual de usuario, que se
entrega por correo junto con el manual técnico.

Comprobación por consola (tres eventos de ejemplo y un menú de estrés):

```powershell
python main.py
```

Pruebas:

```powershell
python -m unittest discover -s tests -v
```

## Carpetas

- `src/`: AVL, BST, pila, cola y catálogo.
- `interfaz.py`: ventana.
- `main.py`: prueba corta por consola.
- `tests/`: pruebas y los JSON de `tests/fixtures/`.

## Documentos de la entrega

El manual de usuario y el manual técnico no van en este repositorio. Se adjuntan
al correo, como pide el enunciado. Aquí solo quedan las instrucciones para
ejecutar el programa y las pruebas.

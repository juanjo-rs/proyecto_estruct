# Tarea E1 — Formularios

## Objetivo

Crear, consultar, corregir, marcar revisado y eliminar desde la ventana. Cada boton llama un metodo de `CatalogoSismico`. La GUI no recorre ni gira nodos.

## Archivos

- `interfaz.py` — formularios

## Como probar

```powershell
python interfaz.py
```

Crear un evento, consultarlo, corregir la magnitud, marcarlo revisado y eliminarlo. Un id invalido muestra el error y deja el escenario igual.

## Decisiones

- Las cajas vacias de corregir no se envian.
- Eliminar pide confirmacion.
- Consultar no registra deshacer: no cambia el arbol.

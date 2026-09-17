# Tarea B2 — Sincronizar BST en correccion y eliminacion

## Objetivo

Mantener el BST de comparacion alineado con el AVL en crear, corregir (cambio de clave) y eliminar, para poder comparar busquedas y recorridos.

## Archivos

- `src/arbol_bst.py` — `eliminar(clave)` sin rotaciones (casos 0/1/2 hijos + sucesor)
- `src/catalogo.py` — `corregir_evento` y `eliminar_evento` actualizan el BST
- `tests/test_base.py` — `test_sincronizacion_arboles_avl_y_bst`

## Como probar

```powershell
python -m unittest tests.test_base.PruebasBase.test_sincronizacion_arboles_avl_y_bst -v
python -m unittest tests.test_base -v
```

## Decisiones

- El BST elimina por clave `(P, M, I)`, igual que el AVL; el catalogo traduce ID → clave.
- En correccion: si la clave cambia, `bst.eliminar(clave_anterior)` y luego `bst.insertar(evento)`.
- No se reconstruye el BST desde una lista; solo insert/delete nodo a nodo.
- `crear_evento` ya insertaba en ambos arboles; B2 completo el hueco en corregir/eliminar.

## Criterio hecho

Tras crear, corregir y eliminar, `avl.inorden()` y `bst.inorden()` exponen los mismos identificadores en el mismo orden.

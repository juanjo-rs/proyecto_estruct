# Tarea B1 — Modo estrés (activar / recuperar / desactivar)

## Objetivo

Permitir que el usuario active y desactive el modo estrés del catálogo. En estrés, altas y bajas del AVL no rotan. Al desactivar, se recupera el balance solo con rotaciones y luego se sale del modo.

## Archivos

- `src/catalogo.py` — `activar_modo_estres`, `desactivar_modo_estres`, `recuperar_desde_estres`
- `main.py` — menú interactivo
- `interfaz.py` — botones de activar/desactivar
- `tests/test_base.py` — `test_activar_estres_y_desactivar_recuperar`

## Cómo probar

```powershell
python -m unittest tests.test_base.PruebasBase.test_activar_estres_y_desactivar_recuperar -v
python main.py
```

En el menú: `1` → `4` (ráfaga 7) → ver `balanceado False` → `2` → modo normal y giros ≥ 1.

## Decisiones

- Desactivar exige recuperar primero (no salir de estrés con `|FB| > 1`).
- La GUI y `main` solo llaman al catálogo; no mutan nodos AVL.
- Durante la recuperación se pausa la cola (`cola_pausada`).

## Comentarios de código

Funciones nuevas llevan docstring/comentario breve en inglés en el catálogo y la GUI.

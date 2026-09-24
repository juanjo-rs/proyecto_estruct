# Tarea B3 — Recuperacion desde estres

## Objetivo

Recuperar el AVL solo con rotaciones: pausar la cola, pasadas de abajo hacia arriba hasta que la auditoria valide el balance, y tratar un FB fuera de rango como esperado solo en estres. El recorrido inorden no cambia.

## Archivos

- `src/arbol_avl.py` — `auditar(exigir_balanceo=True)`
- `src/catalogo.py` — cola pausada al procesar reportes; `recuperar_balance` delega en `recuperar_desde_estres`
- `tests/test_base.py` — `test_recuperacion_estres_conserva_orden_y_pausa_cola`

## Como probar

```powershell
python -m unittest tests.test_base.PruebasBase.test_recuperacion_estres_conserva_orden_y_pausa_cola -v
python -m unittest tests.test_base -v
```

## Decisiones

- En estres, `balanceado` puede ser False y eso no entra en `errores`.
- La cola se pausa solo durante la recuperacion, no todo el modo estres.
- Si la recuperacion lanza error, `modo_estres` sigue True (no se sale torcido).
- No se reconstruye el arbol desde una lista; solo giros.

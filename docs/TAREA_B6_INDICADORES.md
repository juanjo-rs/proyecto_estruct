# Tarea B6 — Indicadores estructurales

## Objetivo

Exponer giros, casos LL/RR/LR/RL, altura, hojas y profundidad del AVL y del BST sin que la GUI recorra nodos. Un evento de prioridad alta tiene acceso costoso solo si su profundidad de nodo es estrictamente mayor que `L`.

## Archivos

- `src/arbol_avl.py` — `nodos_con_profundidad`
- `src/catalogo.py` — `indicadores`
- `interfaz.py` — el boton lee `indicadores()`
- `tests/test_base.py` — deshacer restaura contadores; `L` excluye la profundidad igual

## Como probar

```powershell
python -m unittest tests.test_base.PruebasBase.test_indicadores_de_giro_se_restauran_al_deshacer tests.test_base.PruebasBase.test_acceso_costoso_si_profundidad_supera_L -v
python -m unittest tests.test_base -v
```

## Decisiones

- Los contadores se leen del AVL vivo. No se copian a `metricas`.
- La instantanea profunda ya guarda el arbol, asi que `deshacer` devuelve los giros.
- `L` ausente o invalido deja `acceso_costoso` vacio. El valor inicial de `L` sigue siendo de C1.
- Profundidad igual a `L` no es acceso costoso.

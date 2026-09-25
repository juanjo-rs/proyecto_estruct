# Tarea B5 — Tests estructurales

## Objetivo

Cubrir §16 de rotaciones y archivo: LL, RR, LR, RL, estres con `|FB| > 2` y recuperacion, y desempate de rama por raiz mas profunda.

## Archivos

- `tests/test_base.py` — tests de giro, factor y empate de profundidad
- `src/arbol_avl.py` — contadores `casos_ll`, `casos_rr`, `casos_lr`, `casos_rl` y `_factor` (ya existian)

## Como probar

```powershell
python -m unittest tests.test_base.PruebasBase.test_casos_balanceo_RR tests.test_base.PruebasBase.test_casos_balanceo_LL tests.test_base.PruebasBase.test_casos_balanceo_RL tests.test_base.PruebasBase.test_casos_balanceo_LR tests.test_base.PruebasBase.test_factor_nodo_desbalance tests.test_base.PruebasBase.test_desempate_raiz_mas_profunda -v
python -m unittest tests.test_base -v
```

## Decisiones

- Misma prioridad y magnitud: el ID define LL/RR/LR/RL.
- `|FB| > 2` solo en modo estres (sin giros); se mide `abs(avl._factor(raiz))`.
- Empate de archivo a igual tamano: gana la raiz mas profunda.

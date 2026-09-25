# Tarea B4 — Archivar rama

## Objetivo

Listar subarboles elegibles y archivar la ganadora. Destino historico (`archivados`), no eliminados. IDs fijos antes de borrar.

## Archivos

- `src/catalogo.py` — `listar_ramas_archivables`, `archivar_rama`
- `tests/test_base.py` — error, arbol completo, descendiente invalido, empate por ID

## Como probar

```powershell
python -m unittest tests.test_base.PruebasBase.test_archivar_rama_completa tests.test_base.PruebasBase.test_archivar_sin_rama_elegible_informa_error tests.test_base.PruebasBase.test_rama_invalida_por_descendiente tests.test_base.PruebasBase.test_desempate_id_raiz_mayor -v
python -m unittest tests.test_base -v
```

## Decisiones

- `T` en minutos. Listar no muta; archivar usa `candidatas[0]`.
- Quitar AVL+BST por clave. No llamar `eliminar_evento`.

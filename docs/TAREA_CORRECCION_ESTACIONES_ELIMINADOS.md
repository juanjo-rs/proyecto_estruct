# Corrección estaciones y cuerpo eliminado

## Qué se corrigió

- El registro de estaciones entra en la instantánea y en el JSON de versión (`registro_estaciones`). Deshacer y restaurar lo devuelven. `configurar_estaciones` ahora es una acción deshacible.
- `eliminar_evento` guarda una copia del evento en `cuerpos_eliminados`. Consultar un eliminado muestra magnitud, coordenadas y fecha. El id sigue sin poder reutilizarse y el nodo no vuelve al AVL.

## Botones

En `interfaz.py`, cada botón nuevo llama un método de `CatalogoSismico`: cambiar parámetro, configurar estaciones, avanzar reloj, asociaciones, top-k, magnitud, profundidad y fecha, acceso costoso.

## Cómo probar

```powershell
python -m unittest tests.test_base.PruebasBase.test_deshacer_restaura_el_registro_de_estaciones tests.test_base.PruebasBase.test_consultar_detalle_desconocido_y_eliminado tests.test_base.PruebasBase.test_version_restaura_estaciones_y_cuerpo_eliminado -v
python interfaz.py
```

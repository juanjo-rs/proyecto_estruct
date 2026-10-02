# Tareas F2 y F4 — manual de usuario y README

## Qué se hizo

- F2: `docs/MANUAL_USUARIO.md` describe solo los botones que hoy tiene `interfaz.py`.
- F4: `README.md` indica cómo abrir la ventana, la consola y los tests, y enlaza el manual.

## Cómo probar

```powershell
python interfaz.py
python main.py
python -m unittest discover -s tests -v
```

## Decisiones

- El manual no inventa botones de deshacer, archivo de rama ni carga JSON: el método de carga existe en la ventana, pero no está conectado a un botón.
- Los comentarios del código ya están en inglés; no se reescribieron los mensajes que ve el usuario.

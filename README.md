# SismoLab AVL

Base inicial para el proyecto **SismoLab AVL** de Estructuras de Datos.

La carpeta `TallerArbolesBinarios/` se conserva sin cambios como referencia del
taller original. Esta nueva base sigue el enunciado del PDF y usa solamente la
biblioteca estandar de Python: no hay bibliotecas de arboles, colas, pilas ni
colecciones ordenadas.

## Ejecucion

Desde esta carpeta:

```powershell
python main.py
python -m unittest discover -s tests -v
```

Para abrir la ventana inicial:

```powershell
python interfaz.py
```

## Estado de la plantilla

Ya implementado y probado:

- Modelo de eventos, zonas y prioridad obligatoria.
- AVL propio por clave `(prioridad, magnitud, identificador)` y BST de comparacion.
- Insercion, busqueda por clave, eliminacion, recorridos, auditoria y recuperacion
  del balance del AVL.
- Catalogo inicial: altas, consulta por identificador, correccion, revision,
  eliminacion y procesamiento FIFO de reportes.
- Pila y cola propias, preparadas para el historial y las rafagas.

La guia en `docs/GUIA_IMPLEMENTACION.md` define las fases restantes, los
invariantes y los casos de prueba obligatorios. No se debe considerar esta base
como una entrega terminada: faltan, entre otros, asociaciones, archivo de ramas,
persistencia completa, deshacer por instantaneas y las vistas graficas finales.

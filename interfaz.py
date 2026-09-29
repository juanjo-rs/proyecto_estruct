"""Minimal GUI shell; widgets must call the catalog service, never the AVL directly."""

from datetime import datetime, timezone
from decimal import Decimal
import random
import tkinter as tk
from tkinter import filedialog, simpledialog, ttk, messagebox

from src.catalogo import CatalogoSismico, leer_json_archivo
from src.dominio import Evento, Reporte, Zona


class VentanaSismoLab(tk.Tk):
    """Initial window that makes the required separation GUI/business explicit."""

    def __init__(self) -> None:
        super().__init__()
        self.title("SismoLab AVL")
        self.minsize(720, 420)
        self.catalogo = CatalogoSismico(
            [Zona("Zona inicial", 0, 1000, 0, 1000, False)],
            datetime.now(timezone.utc).replace(microsecond=0),
        )
        ttk.Label(self, text="SismoLab AVL", font=("Segoe UI", 20, "bold")).pack(pady=(24, 8))
        ttk.Label(
            self,
            text="Base inicial. La interfaz debe usar CatalogoSismico; no debe manipular nodos AVL directamente.",
            wraplength=620,
        ).pack(padx=28)
        self.estado = ttk.Label(self, text="Eventos activos: 0 | Cola: 0 | Modo normal")
        self.estado.pack(pady=20)
        ttk.Button(self, text="Crear evento", command=self.abrir_crear_evento).pack(pady=4)
        ttk.Button(self, text="Consultar evento", command=self.abrir_consultar_evento).pack(pady=4)
        ttk.Button(self, text="Corregir evento", command=self.abrir_corregir_evento).pack(pady=4)
        ttk.Button(self, text="Marcar revisado", command=self.abrir_marcar_revisado).pack(pady=4)
        ttk.Button(self, text="Eliminar evento", command=self.abrir_eliminar_evento).pack(pady=4)
        ttk.Button(self, text="Actualizar indicadores", command=self.actualizar_indicadores).pack()
        ttk.Button(self, text="Activar modo estres", command=self.activar_estres).pack(pady=4)
        ttk.Button(self, text="Desactivar (recuperar)", command=self.desactivar_estres).pack(pady=4)
        ttk.Button(self, text="Gestionar cola de reportes", command=self.abrir_ventana_cola).pack(pady=4)
        ttk.Button(self, text="Visualizar arboles", command=self.abrir_ventana_visualizacion).pack(pady=4)
        ttk.Button(self, text="Visualizar mapa", command=self.abrir_ventana_mapa).pack(pady=4)
        ttk.Button(self, text="Guardar version", command=self.guardar_version).pack(pady=4)
        ttk.Button(self, text="Restaurar version", command=self.restaurar_version).pack(pady=4)

    def _abrir_formulario(self, titulo: str, campos: tuple[tuple[str, str], ...], al_aceptar) -> None:
        """Show labeled entries. al_aceptar receives the stripped text of each field."""
        dialogo = tk.Toplevel(self)
        dialogo.title(titulo)
        dialogo.transient(self)
        entradas: dict[str, ttk.Entry] = {}
        for fila, (clave, etiqueta) in enumerate(campos):
            ttk.Label(dialogo, text=etiqueta).grid(row=fila, column=0, padx=8, pady=4, sticky="w")
            caja = ttk.Entry(dialogo, width=28)
            caja.grid(row=fila, column=1, padx=8, pady=4)
            entradas[clave] = caja

        def aceptar() -> None:
            valores = {clave: caja.get().strip() for clave, caja in entradas.items()}
            if al_aceptar(dialogo, valores):
                dialogo.destroy()
                self.actualizar_indicadores()

        ttk.Button(dialogo, text="Aceptar", command=aceptar).grid(
            row=len(campos), column=1, padx=8, pady=8, sticky="e"
        )

    def _leer_identificador(self, texto: str) -> int:
        """Convert a form id into an int. ValueError is shown by the caller."""
        return int(texto)

    def abrir_crear_evento(self) -> None:
        """Create one event by calling the catalog with the form values."""
        campos = (
            ("identificador", "Identificador"),
            ("magnitud", "Magnitud"),
            ("profundidad_hipocentro", "Profundidad (km)"),
            ("x", "X"),
            ("y", "Y"),
            ("ocurrencia", "Ocurrencia UTC"),
            ("estacion", "Estacion"),
        )

        def al_aceptar(dialogo: tk.Toplevel, valores: dict[str, str]) -> bool:
            try:
                nuevo = Evento(
                    identificador=self._leer_identificador(valores["identificador"]),
                    magnitud=valores["magnitud"],
                    profundidad_hipocentro=valores["profundidad_hipocentro"],
                    x=valores["x"],
                    y=valores["y"],
                    ocurrencia=valores["ocurrencia"],
                    revision=1,
                    estaciones={valores["estacion"]},
                )
                creado = self.catalogo.crear_evento(nuevo)
            except (ValueError, KeyError) as error:
                messagebox.showerror("Crear evento", str(error), parent=dialogo)
                return False
            messagebox.showinfo(
                "Crear evento",
                f"SIS-{creado.identificador:06d} prioridad {creado.prioridad}",
                parent=dialogo,
            )
            return True

        self._abrir_formulario("Crear evento", campos, al_aceptar)

    def abrir_consultar_evento(self) -> None:
        """Show the catalog state of one id without changing the trees."""
        def al_aceptar(dialogo: tk.Toplevel, valores: dict[str, str]) -> bool:
            try:
                identificador = self._leer_identificador(valores["identificador"])
                estado, evento = self.catalogo.consultar(identificador)
            except (ValueError, KeyError) as error:
                messagebox.showerror("Consultar evento", str(error), parent=dialogo)
                return False
            if evento is None:
                texto = f"SIS-{identificador:06d}: {estado}"
            else:
                texto = (
                    f"SIS-{evento.identificador:06d}: {estado}\n"
                    f"prioridad {evento.prioridad} | magnitud {evento.magnitud}\n"
                    f"profundidad {evento.profundidad_hipocentro} km | "
                    f"({evento.x}, {evento.y})\n"
                    f"revision {evento.revision} | {evento.estado.value}"
                )
            messagebox.showinfo("Consultar evento", texto, parent=dialogo)
            return True

        self._abrir_formulario("Consultar evento", (("identificador", "Identificador"),), al_aceptar)

    def abrir_corregir_evento(self) -> None:
        """Send only the filled fields to corregir_evento."""
        campos = (
            ("identificador", "Identificador"),
            ("magnitud", "Magnitud"),
            ("profundidad_hipocentro", "Profundidad (km)"),
            ("x", "X"),
            ("y", "Y"),
            ("ocurrencia", "Ocurrencia UTC"),
        )

        def al_aceptar(dialogo: tk.Toplevel, valores: dict[str, str]) -> bool:
            try:
                identificador = self._leer_identificador(valores["identificador"])
                datos = {
                    campo: valores[campo]
                    for campo in ("magnitud", "profundidad_hipocentro", "x", "y", "ocurrencia")
                    if valores[campo]
                }
                if not datos:
                    raise ValueError("Escribe al menos un campo para corregir.")
                corregido = self.catalogo.corregir_evento(identificador, datos)
            except (ValueError, KeyError) as error:
                messagebox.showerror("Corregir evento", str(error), parent=dialogo)
                return False
            messagebox.showinfo(
                "Corregir evento",
                f"SIS-{corregido.identificador:06d} revision {corregido.revision} "
                f"prioridad {corregido.prioridad}",
                parent=dialogo,
            )
            return True

        self._abrir_formulario("Corregir evento", campos, al_aceptar)

    def abrir_marcar_revisado(self) -> None:
        """Mark one active event as reviewed. The key does not change."""
        def al_aceptar(dialogo: tk.Toplevel, valores: dict[str, str]) -> bool:
            try:
                identificador = self._leer_identificador(valores["identificador"])
                evento = self.catalogo.marcar_revisado(identificador)
            except (ValueError, KeyError) as error:
                messagebox.showerror("Marcar revisado", str(error), parent=dialogo)
                return False
            messagebox.showinfo(
                "Marcar revisado",
                f"SIS-{evento.identificador:06d} quedo {evento.estado.value}",
                parent=dialogo,
            )
            return True

        self._abrir_formulario("Marcar revisado", (("identificador", "Identificador"),), al_aceptar)

    def abrir_eliminar_evento(self) -> None:
        """Remove one active event through the catalog after confirmation."""
        def al_aceptar(dialogo: tk.Toplevel, valores: dict[str, str]) -> bool:
            try:
                identificador = self._leer_identificador(valores["identificador"])
            except ValueError as error:
                messagebox.showerror("Eliminar evento", str(error), parent=dialogo)
                return False
            if not messagebox.askyesno(
                "Eliminar evento",
                f"Eliminar SIS-{identificador:06d}?",
                parent=dialogo,
            ):
                return False
            try:
                self.catalogo.eliminar_evento(identificador)
            except (ValueError, KeyError) as error:
                messagebox.showerror("Eliminar evento", str(error), parent=dialogo)
                return False
            messagebox.showinfo(
                "Eliminar evento",
                f"SIS-{identificador:06d} quedo eliminado",
                parent=dialogo,
            )
            return True

        self._abrir_formulario("Eliminar evento", (("identificador", "Identificador"),), al_aceptar)

    def actualizar_indicadores(self) -> None:
        modo = "estres" if self.catalogo.modo_estres else "normal"
        datos = self.catalogo.indicadores()
        avl = datos["avl"]
        self.estado.config(
            text=(
                f"Eventos activos: {len(self.catalogo.indice_activos)} | "
                f"Cola: {len(self.catalogo.reportes_pendientes)} | Modo {modo} | "
                f"AVL h={avl['altura']} hojas={avl['hojas']} "
                f"giros={avl['giros_izquierda'] + avl['giros_derecha']} | "
                f"Acceso costoso: {len(datos['acceso_costoso'])}"
            )
        )

    def activar_estres(self) -> None:
        self.catalogo.activar_modo_estres()
        self.actualizar_indicadores()

    def desactivar_estres(self) -> None:
        self.catalogo.desactivar_modo_estres()
        self.actualizar_indicadores()

    def seleccionar_y_cargar_json(self) -> None:
        """GUI function to select a JSON file and load it via the business API."""
        ruta = filedialog.askopenfilename(
            title="Seleccionar archivo JSON de carga",
            filetypes=[("Archivos JSON", "*.json"), ("Todos los archivos", "*.*")],
        )
        if ruta:
            try:
                datos = leer_json_archivo(ruta)
                estadisticas = self.catalogo.cargar_por_inserciones(datos)
                self.actualizar_indicadores()
                print(f"Carga exitosa. Estadísticas: {estadisticas}")
            except Exception as e:
                print(f"Error al cargar JSON: {e}")

    def guardar_version(self) -> None:
        """GUI function to save the current scenario as a version."""
        nombre = simpledialog.askstring(
            "Guardar version",
            "Ingrese el nombre de la version:",
            parent=self,
        )
        if nombre:
            try:
                ruta = self.catalogo.guardar_version(nombre)
                messagebox.showinfo("Version guardada", f"Version guardada exitosamente en:\n{ruta}")
            except ValueError as e:
                messagebox.showerror("Error", str(e))
            except PermissionError as e:
                messagebox.showerror("Error de permisos", str(e))
            except Exception as e:
                messagebox.showerror("Error", f"Error inesperado: {e}")

    def restaurar_version(self) -> None:
        """GUI function to restore a version from the list."""
        versiones = self.catalogo.listar_versiones()
        if not versiones:
            messagebox.showinfo("Versiones", "No hay versiones disponibles para restaurar.")
            return

        # Create a dialog to select a version
        dialog = tk.Toplevel(self)
        dialog.title("Restaurar version")
        dialog.geometry("400x300")

        ttk.Label(dialog, text="Seleccione una version para restaurar:").pack(pady=10)

        listbox = tk.Listbox(dialog)
        listbox.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        for version in versiones:
            listbox.insert(tk.END, version)

        def confirmar_restauracion():
            seleccion = listbox.curselection()
            if not seleccion:
                messagebox.showwarning("Seleccion", "Seleccione una version.")
                return
            nombre = versiones[seleccion[0]]
            dialog.destroy()
            try:
                self.catalogo.restaurar_version(nombre)
                self.actualizar_indicadores()
                messagebox.showinfo("Version restaurada", f"Version '{nombre}' restaurada exitosamente.")
            except ValueError as e:
                messagebox.showerror("Error", str(e))
            except PermissionError as e:
                messagebox.showerror("Error de permisos", str(e))
            except Exception as e:
                messagebox.showerror("Error", f"Error inesperado: {e}")

        ttk.Button(dialog, text="Restaurar", command=confirmar_restauracion).pack(pady=10)
        ttk.Button(dialog, text="Cancelar", command=dialog.destroy).pack(pady=5)

    def abrir_ventana_cola(self) -> None:
        """Open the queue management window."""
        ventana_cola = tk.Toplevel(self)
        ventana_cola.title("Gestion de Cola de Reportes")
        ventana_cola.geometry("800x600")

        # Control variables for continuous processing
        self._procesando = False
        self._pausado = False
        self._procesar_job = None

        # Frame for preparing reports
        frame_preparar = ttk.LabelFrame(ventana_cola, text="Preparar Reportes")
        frame_preparar.pack(fill=tk.X, padx=10, pady=10)

        ttk.Label(frame_preparar, text="Cantidad:").pack(side=tk.LEFT, padx=5)
        entrada_cantidad = ttk.Entry(frame_preparar, width=10)
        entrada_cantidad.pack(side=tk.LEFT, padx=5)

        def preparar_n_reportes():
            try:
                n = int(entrada_cantidad.get())
                if n <= 0:
                    messagebox.showerror("Error", "La cantidad debe ser un entero positivo.")
                    return
                self._generar_reportes_aleatorios(n)
                self._actualizar_vista_cola(tree_cola)
                messagebox.showinfo("Exito", f"Se prepararon {n} reportes.")
            except ValueError:
                messagebox.showerror("Error", "Ingrese un numero entero valido.")

        ttk.Button(frame_preparar, text="Preparar", command=preparar_n_reportes).pack(side=tk.LEFT, padx=5)

        # Frame for queue view
        frame_cola = ttk.LabelFrame(ventana_cola, text="Cola FIFO (Orden de Llegada)")
        frame_cola.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        tree_cola = ttk.Treeview(frame_cola, columns=("estacion", "id", "revision"), show="headings")
        tree_cola.heading("estacion", text="Estacion")
        tree_cola.heading("id", text="ID")
        tree_cola.heading("revision", text="Revision")
        tree_cola.pack(fill=tk.BOTH, expand=True)

        # Frame for processing controls
        frame_procesar = ttk.LabelFrame(ventana_cola, text="Procesamiento")
        frame_procesar.pack(fill=tk.X, padx=10, pady=10)

        # Log area for results
        frame_log = ttk.LabelFrame(ventana_cola, text="Log de Procesamiento")
        frame_log.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        log_text = tk.Text(frame_log, height=8, state=tk.DISABLED)
        scrollbar = ttk.Scrollbar(frame_log, orient=tk.VERTICAL, command=log_text.yview)
        log_text.configure(yscrollcommand=scrollbar.set)
        log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        def agregar_log(mensaje: str) -> None:
            log_text.config(state=tk.NORMAL)
            log_text.insert(tk.END, mensaje + "\n")
            log_text.see(tk.END)
            log_text.config(state=tk.DISABLED)

        def procesar_uno():
            if self.catalogo.reportes_pendientes.esta_vacia():
                messagebox.showinfo("Info", "La cola esta vacia.")
                return

            # Get report before processing
            reporte = self.catalogo.reportes_pendientes.frente()

            # Get balance before
            giros_antes = self.catalogo.recuperar_balance()

            # Process the report
            resultado = self.catalogo.procesar_siguiente_reporte()

            # Get balance after
            giros_despues = self.catalogo.recuperar_balance()
            giros_ocurridos = giros_despues - giros_antes

            # Log the result
            log_mensaje = (
                f"Estacion: {reporte.estacion} | "
                f"ID: {reporte.evento.identificador} | "
                f"Revision: {reporte.evento.revision} | "
                f"Decision: {resultado} | "
                f"Giros: {giros_ocurridos}"
            )
            agregar_log(log_mensaje)

            # Update queue view
            self._actualizar_vista_cola(tree_cola)
            self.actualizar_indicadores()

        def iniciar_procesamiento_continuo():
            self._procesando = True
            self._pausado = False
            btn_iniciar.config(state=tk.DISABLED)
            btn_pausar.config(state=tk.NORMAL)
            btn_detener.config(state=tk.NORMAL)
            self._ciclo_procesamiento(tree_cola, log_text)

        def pausar_procesamiento():
            self._pausado = not self._pausado
            btn_pausar.config(text="Reanudar" if self._pausado else "Pausar")

        def detener_procesamiento():
            self._procesando = False
            self._pausado = False
            btn_iniciar.config(state=tk.NORMAL)
            btn_pausar.config(state=tk.DISABLED)
            btn_pausar.config(text="Pausar")
            btn_detener.config(state=tk.DISABLED)
            if self._procesar_job:
                ventana_cola.after_cancel(self._procesar_job)
                self._procesar_job = None

        def _ciclo_procesamiento(tree, log):
            if not self._procesando:
                return

            if not self._pausado and not self.catalogo.reportes_pendientes.esta_vacia():
                procesar_uno()

            # Schedule next iteration (500ms delay)
            self._procesar_job = ventana_cola.after(500, lambda: _ciclo_procesamiento(tree, log))

        # Processing buttons
        btn_uno = ttk.Button(frame_procesar, text="Procesar Uno", command=procesar_uno)
        btn_uno.pack(side=tk.LEFT, padx=5)

        btn_iniciar = ttk.Button(frame_procesar, text="Iniciar Continuo", command=iniciar_procesamiento_continuo)
        btn_iniciar.pack(side=tk.LEFT, padx=5)

        btn_pausar = ttk.Button(frame_procesar, text="Pausar", command=pausar_procesamiento, state=tk.DISABLED)
        btn_pausar.pack(side=tk.LEFT, padx=5)

        btn_detener = ttk.Button(frame_procesar, text="Detener", command=detener_procesamiento, state=tk.DISABLED)
        btn_detener.pack(side=tk.LEFT, padx=5)

        # Initial queue view update
        self._actualizar_vista_cola(tree_cola)

        # Clean up when window closes
        def on_cerrar():
            detener_procesamiento()
            ventana_cola.destroy()

        ventana_cola.protocol("WM_DELETE_WINDOW", on_cerrar)

    def _generar_reportes_aleatorios(self, n: int) -> None:
        """Generate N random reports and enqueue them."""
        estaciones = [f"EST-{i:02d}" for i in range(1, 11)]
        next_id = 1
        if self.catalogo.indice_activos:
            next_id = max(self.catalogo.indice_activos.keys()) + 1
        if self.catalogo.archivados:
            next_id = max(next_id, max(self.catalogo.archivados.keys()) + 1)

        for i in range(n):
            evento = Evento(
                identificador=next_id + i,
                magnitud=Decimal(str(round(random.uniform(4.0, 7.0), 1))),
                profundidad_hipocentro=Decimal(str(round(random.uniform(10.0, 100.0), 1))),
                x=Decimal(str(round(random.uniform(0.0, 1000.0), 1))),
                y=Decimal(str(round(random.uniform(0.0, 1000.0), 1))),
                ocurrencia=self.catalogo.reloj.isoformat(),
                revision=1,
                estaciones=set(),
            )
            estacion = random.choice(estaciones)
            reporte = Reporte(evento=evento, estacion=estacion)
            self.catalogo.encolar_reporte(reporte)

    def _actualizar_vista_cola(self, tree: ttk.Treeview) -> None:
        """Update the queue view with current reports in FIFO order."""
        # Clear existing items
        for item in tree.get_children():
            tree.delete(item)

        # Add current reports
        for reporte in self.catalogo.reportes_pendientes:
            tree.insert("", tk.END, values=(
                reporte.estacion,
                reporte.evento.identificador,
                reporte.evento.revision,
            ))

    def abrir_ventana_visualizacion(self) -> None:
        """Open the tree visualization window with AVL and BST side by side."""
        ventana_vis = tk.Toplevel(self)
        ventana_vis.title("Visualizacion de Arboles AVL y BST")
        ventana_vis.geometry("1200x700")

        # Control variables
        self._coordenadas_nodos_avl = {}  # id -> (x, y)
        self._coordenadas_nodos_bst = {}  # id -> (x, y)
        self._radio_nodo = 25

        # Frame for AVL
        frame_avl = ttk.LabelFrame(ventana_vis, text="AVL (Balanceado)")
        frame_avl.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        canvas_avl = tk.Canvas(frame_avl, bg="white")
        canvas_avl.pack(fill=tk.BOTH, expand=True)

        # Frame for BST
        frame_bst = ttk.LabelFrame(ventana_vis, text="BST (No Balanceado)")
        frame_bst.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        canvas_bst = tk.Canvas(frame_bst, bg="white")
        canvas_bst.pack(fill=tk.BOTH, expand=True)

        # Frame for controls and info
        frame_control = ttk.Frame(ventana_vis)
        frame_control.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=5)

        ttk.Button(frame_control, text="Redibujar", command=lambda: self._redibujar_arboles(canvas_avl, canvas_bst)).pack(side=tk.LEFT, padx=5)

        # Info panel for node inspection
        frame_info = ttk.LabelFrame(frame_control, text="Informacion del Nodo")
        frame_info.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)

        info_label = ttk.Label(frame_info, text="Click en un nodo para inspeccionar", wraplength=400)
        info_label.pack(padx=5, pady=5)

        # Bind click events
        canvas_avl.bind("<Button-1>", lambda e: self._inspeccionar_nodo(e, canvas_avl, "avl", info_label))
        canvas_bst.bind("<Button-1>", lambda e: self._inspeccionar_nodo(e, canvas_bst, "bst", info_label))

        # Initial draw
        self._redibujar_arboles(canvas_avl, canvas_bst)

    def _redibujar_arboles(self, canvas_avl: tk.Canvas, canvas_bst: tk.Canvas) -> None:
        """Redraw both trees from the catalog."""
        # Clear canvases
        canvas_avl.delete("all")
        canvas_bst.delete("all")
        self._coordenadas_nodos_avl.clear()
        self._coordenadas_nodos_bst.clear()

        # Draw AVL
        vista_avl, raiz_avl = self.catalogo.obtener_vista_arbol("avl")
        if raiz_avl is None:
            canvas_avl.create_text(
                canvas_avl.winfo_width() / 2,
                canvas_avl.winfo_height() / 2,
                text="Arbol AVL vacio",
                font=("Segoe UI", 14),
                fill="gray"
            )
        else:
            self._dibujar_arbol(canvas_avl, vista_avl, raiz_avl, "blue")

        # Draw BST
        vista_bst, raiz_bst = self.catalogo.obtener_vista_arbol("bst")
        if raiz_bst is None:
            canvas_bst.create_text(
                canvas_bst.winfo_width() / 2,
                canvas_bst.winfo_height() / 2,
                text="Arbol BST vacio",
                font=("Segoe UI", 14),
                fill="gray"
            )
        else:
            self._dibujar_arbol(canvas_bst, vista_bst, raiz_bst, "green")

    def _dibujar_arbol(
        self,
        canvas: tk.Canvas,
        vista: dict[int, "VistaNodo"],
        raiz_id: int,
        color: str,
    ) -> None:
        """
        Draw a tree on the canvas using the view data.

        Strategy:
        - Root at top center
        - Horizontal width halves at each level
        - Vertical spacing fixed (60px per level)
        - Left child X = parent X - width/2
        - Right child X = parent X + width/2
        - Child Y = parent Y + level_height
        """
        canvas_width = canvas.winfo_width()
        canvas_height = canvas.winfo_height()
        if canvas_width < 100:
            canvas_width = 500  # Default if not yet rendered
        if canvas_height < 100:
            canvas_height = 500

        # Calculate tree height to adjust spacing
        alturas = {nodo_id: nodo.altura for nodo_id, nodo in vista.items()}
        max_altura = max(alturas.values()) if alturas else 0
        nivel_height = min(60, canvas_height / (max_altura + 2))  # Adjust for tall trees

        # Calculate coordinates recursively
        def calcular_coordenadas(
            nodo_id: int,
            x: float,
            y: float,
            ancho_disponible: float,
            profundidad: int,
        ) -> None:
            nodo = vista[nodo_id]
            coordenadas = (x, y)

            # Store coordinates for click detection
            if color == "blue":
                self._coordenadas_nodos_avl[nodo_id] = coordenadas
            else:
                self._coordenadas_nodos_bst[nodo_id] = coordenadas

            # Calculate child positions
            ancho_hijo = ancho_disponible / 2
            y_hijo = y + nivel_height

            if nodo.izquierdo_id is not None:
                x_izquierdo = x - ancho_hijo / 2
                calcular_coordenadas(nodo.izquierdo_id, x_izquierdo, y_hijo, ancho_hijo, profundidad + 1)

            if nodo.derecho_id is not None:
                x_derecho = x + ancho_hijo / 2
                calcular_coordenadas(nodo.derecho_id, x_derecho, y_hijo, ancho_hijo, profundidad + 1)

        # Start from root
        x_raiz = canvas_width / 2
        y_raiz = 50
        ancho_inicial = canvas_width * 0.8  # Use 80% of canvas width
        calcular_coordenadas(raiz_id, x_raiz, y_raiz, ancho_inicial, 0)

        # Draw edges first (so they appear behind nodes)
        def dibujar_enlaces(nodo_id: int) -> None:
            nodo = vista[nodo_id]
            x_padre, y_padre = (
                self._coordenadas_nodos_avl[nodo_id] if color == "blue"
                else self._coordenadas_nodos_bst[nodo_id]
            )

            if nodo.izquierdo_id is not None:
                x_hijo, y_hijo = (
                    self._coordenadas_nodos_avl[nodo.izquierdo_id] if color == "blue"
                    else self._coordenadas_nodos_bst[nodo.izquierdo_id]
                )
                canvas.create_line(x_padre, y_padre, x_hijo, y_hijo, fill="black", width=2)
                dibujar_enlaces(nodo.izquierdo_id)

            if nodo.derecho_id is not None:
                x_hijo, y_hijo = (
                    self._coordenadas_nodos_avl[nodo.derecho_id] if color == "blue"
                    else self._coordenadas_nodos_bst[nodo.derecho_id]
                )
                canvas.create_line(x_padre, y_padre, x_hijo, y_hijo, fill="black", width=2)
                dibujar_enlaces(nodo.derecho_id)

        dibujar_enlaces(raiz_id)

        # Draw nodes
        for nodo_id, nodo in vista.items():
            x, y = (
                self._coordenadas_nodos_avl[nodo_id] if color == "blue"
                else self._coordenadas_nodos_bst[nodo_id]
            )

            # Draw circle
            radio = self._radio_nodo
            canvas.create_oval(
                x - radio, y - radio,
                x + radio, y + radio,
                fill=color,
                outline="black",
                width=2
            )

            # Draw key (P, M, I)
            clave_texto = f"({nodo.clave[0]}, {nodo.clave[1]}, {nodo.clave[2]})"
            canvas.create_text(
                x, y,
                text=clave_texto,
                font=("Segoe UI", 8),
                fill="white"
            )

            # Draw height and factor for AVL
            if nodo.factor is not None:
                info_texto = f"h:{nodo.altura} f:{nodo.factor}"
                canvas.create_text(
                    x, y + radio + 10,
                    text=info_texto,
                    font=("Segoe UI", 7),
                    fill="black"
                )

    def _inspeccionar_nodo(
        self,
        evento: tk.Event,
        canvas: tk.Canvas,
        tipo: str,
        info_label: ttk.Label,
    ) -> None:
        """Inspect a node when clicked."""
        x_click, y_click = evento.x, evento.y

        coordenadas = (
            self._coordenadas_nodos_avl if tipo == "avl"
            else self._coordenadas_nodos_bst
        )

        # Find clicked node
        for nodo_id, (x, y) in coordenadas.items():
            distancia = ((x_click - x) ** 2 + (y_click - y) ** 2) ** 0.5
            if distancia <= self._radio_nodo:
                # Get event data from catalog
                if nodo_id in self.catalogo.indice_activos:
                    evento_data = self.catalogo.indice_activos[nodo_id]
                    info_texto = (
                        f"ID: {evento_data.identificador} | "
                        f"Prioridad: {evento_data.prioridad} | "
                        f"Magnitud: {evento_data.magnitud} | "
                        f"Estaciones: {', '.join(sorted(evento_data.estaciones))} | "
                        f"Estado: {evento_data.estado}"
                    )
                else:
                    info_texto = f"ID: {nodo_id} (No encontrado en indice activos)"
                info_label.config(text=info_texto)
                return

        info_label.config(text="Click en un nodo para inspeccionar")

    def abrir_ventana_mapa(self) -> None:
        """Open the map visualization window with zones and events."""
        ventana_mapa = tk.Toplevel(self)
        ventana_mapa.title("Mapa de Eventos Sismicos")
        ventana_mapa.geometry("900x700")

        # Control variables
        self._coordenadas_eventos = {}  # id -> (x, y)
        self._radio_evento = 10
        self._escala = 0.6  # Canvas pixels per km

        # Frame for map canvas
        frame_mapa = ttk.Frame(ventana_mapa)
        frame_mapa.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        canvas_mapa = tk.Canvas(frame_mapa, bg="white", width=600, height=600)
        canvas_mapa.pack(fill=tk.BOTH, expand=True)

        # Frame for legend and info
        frame_lateral = ttk.Frame(ventana_mapa)
        frame_lateral.pack(side=tk.RIGHT, fill=tk.Y, padx=5, pady=5)

        # Legend
        frame_leyenda = ttk.LabelFrame(frame_lateral, text="Leyenda")
        frame_leyenda.pack(fill=tk.X, pady=5)

        # Priority colors
        ttk.Label(frame_leyenda, text="Prioridad:").pack(anchor=tk.W, padx=5)
        
        canvas_p1 = tk.Canvas(frame_leyenda, width=20, height=20, bg="white")
        canvas_p1.pack(padx=5, pady=2)
        canvas_p1.create_oval(5, 5, 15, 15, fill="green", outline="black")
        ttk.Label(frame_leyenda, text="1 (Baja)").pack(anchor=tk.W, padx=5)
        
        canvas_p2 = tk.Canvas(frame_leyenda, width=20, height=20, bg="white")
        canvas_p2.pack(padx=5, pady=2)
        canvas_p2.create_oval(5, 5, 15, 15, fill="yellow", outline="black")
        ttk.Label(frame_leyenda, text="2 (Media)").pack(anchor=tk.W, padx=5)
        
        canvas_p3 = tk.Canvas(frame_leyenda, width=20, height=20, bg="white")
        canvas_p3.pack(padx=5, pady=2)
        canvas_p3.create_oval(5, 5, 15, 15, fill="red", outline="black")
        ttk.Label(frame_leyenda, text="3 (Alta)").pack(anchor=tk.W, padx=5)

        # Expensive access symbol
        ttk.Separator(frame_leyenda, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=5)
        ttk.Label(frame_leyenda, text="Acceso Costoso:").pack(anchor=tk.W, padx=5)
        
        canvas_costoso = tk.Canvas(frame_leyenda, width=20, height=20, bg="white")
        canvas_costoso.pack(padx=5, pady=2)
        canvas_costoso.create_rectangle(3, 3, 17, 17, outline="red", width=3)
        ttk.Label(frame_leyenda, text="Borde rojo grueso").pack(anchor=tk.W, padx=5)

        # Zone types
        ttk.Separator(frame_leyenda, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=5)
        ttk.Label(frame_leyenda, text="Zonas:").pack(anchor=tk.W, padx=5)
        
        canvas_zp = tk.Canvas(frame_leyenda, width=20, height=20, bg="white")
        canvas_zp.pack(padx=5, pady=2)
        canvas_zp.create_rectangle(3, 3, 17, 17, fill="#FFFFCC", outline="black")
        ttk.Label(frame_leyenda, text="Poblada").pack(anchor=tk.W, padx=5)
        
        canvas_zn = tk.Canvas(frame_leyenda, width=20, height=20, bg="white")
        canvas_zn.pack(padx=5, pady=2)
        canvas_zn.create_rectangle(3, 3, 17, 17, fill="#E0E0E0", outline="gray")
        ttk.Label(frame_leyenda, text="No poblada").pack(anchor=tk.W, padx=5)

        # Info panel for event inspection
        frame_info = ttk.LabelFrame(frame_lateral, text="Informacion del Evento")
        frame_info.pack(fill=tk.BOTH, expand=True, pady=5)

        info_label = ttk.Label(frame_info, text="Click en un evento para inspeccionar", wraplength=250)
        info_label.pack(padx=5, pady=5)

        # Redraw button
        ttk.Button(frame_lateral, text="Redibujar", command=lambda: self._redibujar_mapa(canvas_mapa, info_label)).pack(pady=5)

        # Bind click event
        canvas_mapa.bind("<Button-1>", lambda e: self._inspeccionar_evento_mapa(e, info_label))

        # Initial draw
        self._redibujar_mapa(canvas_mapa, info_label)

    def _redibujar_mapa(self, canvas: tk.Canvas, info_label: ttk.Label) -> None:
        """Redraw the map from the catalog."""
        canvas.delete("all")
        self._coordenadas_eventos.clear()

        # Get map view
        vista_zonas, vista_eventos = self.catalogo.obtener_vista_mapa()

        # Draw zones
        for zona in vista_zonas:
            self._dibujar_zona(canvas, zona)

        # Draw events
        for evento in vista_eventos:
            self._dibujar_evento_mapa(canvas, evento)

        # Draw axes labels
        canvas.create_text(10, 10, text="(0,0)", anchor=tk.NW, font=("Segoe UI", 8))
        canvas.create_text(590, 590, text="(1000,1000)", anchor=tk.SE, font=("Segoe UI", 8))

    def _dibujar_zona(self, canvas: tk.Canvas, zona: "VistaZona") -> None:
        """Draw a zone rectangle on the canvas."""
        # Convert world coordinates to canvas coordinates
        x1 = float(zona.x_min) * self._escala
        y1 = 600 - float(zona.y_max) * self._escala  # Invert Y
        x2 = float(zona.x_max) * self._escala
        y2 = 600 - float(zona.y_min) * self._escala  # Invert Y

        # Choose color based on populated status
        fill_color = "#FFFFCC" if zona.poblada else "#E0E0E0"  # Light yellow or light gray
        outline_color = "black" if zona.poblada else "gray"

        # Draw rectangle
        canvas.create_rectangle(x1, y1, x2, y2, fill=fill_color, outline=outline_color, width=2)

        # Draw zone name in center
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        canvas.create_text(cx, cy, text=zona.nombre, font=("Segoe UI", 9, "bold"))

    def _dibujar_evento_mapa(self, canvas: tk.Canvas, evento: "VistaEventoMapa") -> None:
        """Draw an event circle on the canvas."""
        # Convert world coordinates to canvas coordinates
        x = float(evento.x) * self._escala
        y = 600 - float(evento.y) * self._escala  # Invert Y

        # Store coordinates for click detection
        self._coordenadas_eventos[evento.id] = (x, y)

        # Choose color based on priority
        if evento.prioridad == 1:
            fill_color = "green"
        elif evento.prioridad == 2:
            fill_color = "yellow"
        else:  # priority 3
            fill_color = "red"

        # Draw circle
        radio = self._radio_evento
        canvas.create_oval(x - radio, y - radio, x + radio, y + radio, fill=fill_color, outline="black", width=2)

        # Draw expensive access indicator (red thick border or square)
        if evento.acceso_costoso:
            canvas.create_rectangle(x - radio - 3, y - radio - 3, x + radio + 3, y + radio + 3, outline="red", width=3)

        # Draw event ID above circle
        canvas.create_text(x, y - radio - 8, text=str(evento.id), font=("Segoe UI", 8, "bold"))

    def _inspeccionar_evento_mapa(self, evento: tk.Event, info_label: ttk.Label) -> None:
        """Inspect an event when clicked."""
        x_click, y_click = evento.x, evento.y

        # Find clicked event
        for evento_id, (x, y) in self._coordenadas_eventos.items():
            distancia = ((x_click - x) ** 2 + (y_click - y) ** 2) ** 0.5
            if distancia <= self._radio_evento + 5:  # +5 for easier clicking
                # Get event data from catalog
                if evento_id in self.catalogo.indice_activos:
                    evento_data = self.catalogo.indice_activos[evento_id]
                    info_texto = (
                        f"ID: {evento_data.identificador}\n"
                        f"Prioridad: {evento_data.prioridad}\n"
                        f"Magnitud: {evento_data.magnitud}\n"
                        f"Coordenadas: ({evento_data.x}, {evento_data.y})\n"
                        f"Estaciones: {', '.join(sorted(evento_data.estaciones))}\n"
                        f"Estado: {evento_data.estado}\n"
                        f"Zona poblada: {'Si' if evento_data.en_zona_poblada else 'No'}"
                    )
                else:
                    info_texto = f"ID: {evento_id} (No encontrado en indice activos)"
                info_label.config(text=info_texto)
                return

        info_label.config(text="Click en un evento para inspeccionar")


if __name__ == "__main__":
    VentanaSismoLab().mainloop()

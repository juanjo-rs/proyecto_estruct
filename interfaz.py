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
        ttk.Button(self, text="Actualizar indicadores", command=self.actualizar_indicadores).pack()
        ttk.Button(self, text="Activar modo estres", command=self.activar_estres).pack(pady=4)
        ttk.Button(self, text="Desactivar (recuperar)", command=self.desactivar_estres).pack(pady=4)
        ttk.Button(self, text="Gestionar cola de reportes", command=self.abrir_ventana_cola).pack(pady=4)
        ttk.Button(self, text="Guardar version", command=self.guardar_version).pack(pady=4)
        ttk.Button(self, text="Restaurar version", command=self.restaurar_version).pack(pady=4)

    def actualizar_indicadores(self) -> None:
        modo = "estres" if self.catalogo.modo_estres else "normal"
        self.estado.config(
            text=f"Eventos activos: {len(self.catalogo.indice_activos)} | "
            f"Cola: {len(self.catalogo.reportes_pendientes)} | Modo {modo}"
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


if __name__ == "__main__":
    VentanaSismoLab().mainloop()

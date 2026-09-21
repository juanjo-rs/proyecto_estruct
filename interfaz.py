"""Minimal GUI shell; widgets must call the catalog service, never the AVL directly."""

from datetime import datetime, timezone
import tkinter as tk
from tkinter import filedialog, simpledialog, ttk, messagebox

from src.catalogo import CatalogoSismico, leer_json_archivo
from src.dominio import Zona


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


if __name__ == "__main__":
    VentanaSismoLab().mainloop()

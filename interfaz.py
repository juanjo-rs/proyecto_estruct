"""Minimal GUI shell; widgets must call the catalog service, never the AVL directly."""

from datetime import datetime, timezone
import tkinter as tk
from tkinter import ttk

from src.catalogo import CatalogoSismico
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

if __name__ == "__main__":
    VentanaSismoLab().mainloop()

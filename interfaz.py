"""Page-style window. Widgets call the catalog service and never the AVL directly."""

from datetime import datetime, timezone
from decimal import Decimal
import random
import tkinter as tk
from tkinter import filedialog, simpledialog, ttk, messagebox

from src.catalogo import CatalogoSismico, leer_json_archivo
from src.dominio import (
    Evento,
    Reporte,
    ResultadoConsulta,
    VistaEventoMapa,
    VistaNodo,
    VistaZona,
    Zona,
    fecha_utc,
)

def texto_a_fecha_utc(texto: str) -> str:
    """Turn a short date into the ISO UTC string the catalog expects.

    Accepts 2026-10-01 18:30, with or without seconds, and a full ISO value
    that already includes Z or an offset. The catalog rules stay unchanged.
    """
    limpio = texto.strip()
    if not limpio:
        raise ValueError("Falta la fecha.")
    if limpio.endswith("Z") or "+" in limpio[10:]:
        return fecha_utc(limpio).strftime("%Y-%m-%dT%H:%M:%SZ")
    for formato in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            fecha = datetime.strptime(limpio, formato).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        return fecha.strftime("%Y-%m-%dT%H:%M:%SZ")
    raise ValueError("Usa fecha y hora, por ejemplo 2026-10-01 18:30. Se guarda en UTC.")


def aplicar_carga_json(catalogo: CatalogoSismico, datos: dict) -> dict:
    """Send a parsed document to the loader named by tipo_carga.

    A missing or unknown type raises before either loader runs. Each loader
    builds a temporary scenario and replaces the current one only if every
    check passes.
    """
    tipo = datos.get("tipo_carga")
    if tipo == "inserciones":
        return catalogo.cargar_por_inserciones(datos)
    if tipo == "topologia":
        # A file stores object keys as text. The loader addresses nodes by int id.
        preparado = dict(datos)
        preparado["nodos"] = {int(clave): valor for clave, valor in datos.get("nodos", {}).items()}
        raiz = datos.get("raiz")
        preparado["raiz"] = int(raiz) if raiz is not None else None
        return catalogo.cargar_por_topologia(preparado)
    raise ValueError("El JSON debe indicar tipo_carga 'inserciones' o 'topologia'.")


def texto_resultado_carga(tipo: str, estadisticas: dict) -> str:
    """Short success text: load kind plus AVL and BST height."""
    avl = estadisticas["avl"]
    bst = estadisticas["bst"]
    return (
        f"Carga por {tipo} lista.\n"
        f"AVL raiz {avl['raiz_id']} altura {avl['altura']}\n"
        f"BST raiz {bst['raiz_id']} altura {bst['altura']}"
    )


def filas_historial_sismico(catalogo: CatalogoSismico) -> list[str]:
    """Read-only lines for archived events, ordered by identifier.

    This is the seismic history (archivados), not the undo stack.
    """
    filas = []
    for identificador in sorted(catalogo.archivados):
        evento = catalogo.archivados[identificador]
        filas.append(
            f"SIS-{identificador:06d}   P{evento.prioridad}   M{evento.magnitud}   "
            f"rev {evento.revision}   {evento.estado.value}   {evento.ocurrencia.strftime('%Y-%m-%d %H:%M')}"
        )
    return filas


def texto_detalle_evento(detalle: dict) -> str:
    """Format consultar_detalle for the dialog. Read-only; the catalog already queried."""
    identificador = int(detalle["identificador"])
    estado = str(detalle["estado"])
    if estado == "desconocido":
        return f"SIS-{identificador:06d}: desconocido"
    lineas = [
        f"SIS-{identificador:06d}: {estado}",
        f"prioridad {detalle['prioridad']} | magnitud {detalle['magnitud']}",
        f"profundidad {detalle['profundidad_hipocentro']} km | ({detalle['x']}, {detalle['y']})",
        f"revision {detalle['revision']} | {detalle['estado_atencion']}",
    ]
    if "mensaje" in detalle:
        lineas.append(str(detalle["mensaje"]))
    if "profundidad_nodo" in detalle:
        lineas.append(
            f"AVL profundidad {detalle['profundidad_nodo']} | "
            f"altura {detalle['altura_nodo']} | factor {detalle['factor_balance']}"
        )
        lineas.append("acceso costoso: " + ("si" if detalle["acceso_costoso"] else "no"))
    asociaciones = detalle.get("asociaciones")
    if isinstance(asociaciones, dict) and "candidatos" in asociaciones:
        candidatos = ", ".join(str(item["identificador"]) for item in asociaciones["candidatos"]) or "ninguno"
        referencia = asociaciones["referencia_elegida"]
        referencia_txt = str(referencia["identificador"]) if referencia else "ninguna"
        lineas.append(f"candidatos: {candidatos}")
        lineas.append(f"referencia: {referencia_txt}")
    return "\n".join(lineas)


SEPARACION_X_NODO = 100
SEPARACION_Y_NODO = 84
MARGEN_ARBOL = 48


def posiciones_arbol(vista: dict[int, VistaNodo], raiz_id: int) -> dict[int, tuple[float, float]]:
    """Place nodes by inorder rank and depth with a fixed gap.

    X grows one slot per node, so a wide balanced tree stays readable and
    scrolls sideways. Y grows with depth, so a long BST scrolls downward
    instead of being squeezed into the window.
    """
    posiciones: dict[int, tuple[float, float]] = {}
    cursor = 0

    def visitar(nodo_id: int, profundidad: int) -> None:
        nonlocal cursor
        nodo = vista[nodo_id]
        if nodo.izquierdo_id is not None:
            visitar(nodo.izquierdo_id, profundidad + 1)
        posiciones[nodo_id] = (
            MARGEN_ARBOL + cursor * SEPARACION_X_NODO,
            MARGEN_ARBOL + profundidad * SEPARACION_Y_NODO,
        )
        cursor += 1
        if nodo.derecho_id is not None:
            visitar(nodo.derecho_id, profundidad + 1)

    visitar(raiz_id, 0)
    return posiciones


class VentanaSismoLab(tk.Tk):
    """Initial window that makes the required separation GUI/business explicit."""

    PAGINA = "#f3efe6"
    TINTA = "#1e2933"
    ENCABEZADO = "#243044"
    ACENTO = "#d4543c"
    TARJETA = "#fffdf8"
    SUAVE = "#5c6b73"

    def __init__(self) -> None:
        super().__init__()
        self.title("SismoLab AVL")
        self.minsize(860, 560)
        self.geometry("980x720")
        self.configure(bg=self.PAGINA)
        self.catalogo = CatalogoSismico(
            [Zona("Zona inicial", 0, 1000, 0, 1000, False)],
            datetime.now(timezone.utc).replace(microsecond=0),
        )
        self._armar_pagina()

    def _armar_pagina(self) -> None:
        """Build the colored page. Buttons only call catalog methods."""
        encabezado = tk.Frame(self, bg=self.ENCABEZADO)
        encabezado.pack(fill="x")
        tk.Label(
            encabezado,
            text="SismoLab AVL",
            bg=self.ENCABEZADO,
            fg="#fffdf8",
            font=("Segoe UI", 22, "bold"),
        ).pack(anchor="w", padx=28, pady=(18, 0))
        tk.Label(
            encabezado,
            text="Observatorio sismico  ·  la ventana pide acciones al catalogo",
            bg=self.ENCABEZADO,
            fg="#d7c4b8",
            font=("Segoe UI", 10),
        ).pack(anchor="w", padx=28, pady=(0, 16))

        franja = tk.Frame(self, bg="#efe6d8")
        franja.pack(fill="x")
        self.estado = tk.Label(
            franja,
            text="Eventos activos: 0 | Cola: 0 | Modo normal",
            bg="#efe6d8",
            fg=self.TINTA,
            font=("Segoe UI", 10),
            anchor="w",
            justify="left",
            wraplength=900,
        )
        self.estado.pack(fill="x", padx=28, pady=10)

        lienzo = tk.Canvas(self, bg=self.PAGINA, highlightthickness=0)
        barra = ttk.Scrollbar(self, orient="vertical", command=lienzo.yview)
        lienzo.configure(yscrollcommand=barra.set)
        barra.pack(side="right", fill="y")
        lienzo.pack(side="left", fill="both", expand=True)
        contenido = tk.Frame(lienzo, bg=self.PAGINA)
        ventana = lienzo.create_window((0, 0), window=contenido, anchor="nw")

        def ajustar(_evento=None) -> None:
            lienzo.configure(scrollregion=lienzo.bbox("all"))
            lienzo.itemconfigure(ventana, width=lienzo.winfo_width())

        contenido.bind("<Configure>", ajustar)
        lienzo.bind("<Configure>", ajustar)

        def al_rueda(evento: tk.Event) -> None:
            lienzo.yview_scroll(int(-evento.delta / 120), "units")

        lienzo.bind("<Enter>", lambda _evento: lienzo.bind_all("<MouseWheel>", al_rueda))
        lienzo.bind("<Leave>", lambda _evento: lienzo.unbind_all("<MouseWheel>"))

        rejilla = tk.Frame(contenido, bg=self.PAGINA)
        rejilla.pack(fill="both", expand=True, padx=22, pady=18)
        rejilla.columnconfigure(0, weight=1)
        rejilla.columnconfigure(1, weight=1)

        eventos = self._tarjeta(rejilla, "Eventos", self.ACENTO)
        self._boton(eventos, "Crear evento", self.abrir_crear_evento)
        self._boton(eventos, "Consultar evento", self.abrir_consultar_evento)
        self._boton(eventos, "Corregir evento", self.abrir_corregir_evento)
        self._boton(eventos, "Marcar revisado", self.abrir_marcar_revisado)
        self._boton(eventos, "Eliminar evento", self.abrir_eliminar_evento)
        eventos.master.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

        escenario = self._tarjeta(rejilla, "Escenario", "#2f6f6a")
        self._boton(escenario, "Cambiar parametro", self.abrir_cambiar_parametro)
        self._boton(escenario, "Configurar estaciones", self.abrir_configurar_estaciones)
        self._boton(escenario, "Gestionar zonas", self.abrir_gestionar_zonas)
        self._boton(escenario, "Avanzar reloj", self.abrir_avanzar_reloj)
        self._boton(escenario, "Activar modo estres", self.activar_estres)
        self._boton(escenario, "Desactivar (recuperar)", self.desactivar_estres)
        escenario.master.grid(row=0, column=1, sticky="nsew", padx=8, pady=8)

        consultas = self._tarjeta(rejilla, "Consultas", "#3d5a80")
        self._boton(consultas, "Consultar asociaciones", self.abrir_consultar_asociaciones)
        self._boton(consultas, "Top-k pendientes", self.abrir_top_k_pendientes)
        self._boton(consultas, "Consultar por magnitud", self.abrir_consultar_magnitud)
        self._boton(consultas, "Consultar por profundidad y fecha", self.abrir_consultar_profundidad_fecha)
        self._boton(consultas, "Acceso costoso", self.abrir_acceso_costoso)
        consultas.master.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)

        estructura = self._tarjeta(rejilla, "Estructura", "#8a5a2b")
        self._boton(estructura, "Visualizar arboles", self.abrir_ventana_visualizacion)
        self._boton(estructura, "Visualizar mapa", self.abrir_ventana_mapa)
        self._boton(estructura, "Archivar rama", self.abrir_archivar_rama)
        self._boton(estructura, "Verificar estructura", self.verificar_estructura)
        self._boton(estructura, "Indicadores detallados", self.mostrar_indicadores_detallados)
        self._boton(estructura, "Actualizar indicadores", self.actualizar_indicadores)
        estructura.master.grid(row=1, column=1, sticky="nsew", padx=8, pady=8)

        operacion = self._tarjeta(rejilla, "Operacion", "#3f4c5a")
        self._boton(operacion, "Gestionar cola de reportes", self.abrir_ventana_cola)
        self._boton(operacion, "Cargar JSON", self.abrir_cargar_json)
        self._boton(operacion, "Historial sismico", self.abrir_historial_sismico)
        self._boton(operacion, "Deshacer", self.deshacer_accion)
        self._boton(operacion, "Gestionar versiones", self.abrir_ventana_versiones)
        operacion.master.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=8, pady=8)

    def _tarjeta(self, parent: tk.Frame, titulo: str, color: str) -> tk.Frame:
        """Return the inner frame of one colored card."""
        caja = tk.Frame(parent, bg=self.TARJETA, highlightbackground="#e4ddd0", highlightthickness=1)
        tk.Frame(caja, bg=color, width=6).pack(side="left", fill="y")
        cuerpo = tk.Frame(caja, bg=self.TARJETA)
        cuerpo.pack(side="left", fill="both", expand=True, padx=14, pady=12)
        tk.Label(
            cuerpo,
            text=titulo,
            bg=self.TARJETA,
            fg=color,
            font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w", pady=(0, 8))
        return cuerpo

    def _boton(self, parent: tk.Frame, texto: str, comando) -> None:
        """Flat page button. comando is a catalog-facing method of this window."""
        tk.Button(
            parent,
            text=texto,
            command=comando,
            bg="#f7f1e8",
            fg=self.TINTA,
            activebackground=self.ACENTO,
            activeforeground="#fffdf8",
            relief="flat",
            bd=0,
            font=("Segoe UI", 10),
            padx=12,
            pady=7,
            cursor="hand2",
            anchor="w",
        ).pack(fill="x", pady=3)

    def _abrir_formulario(
        self,
        titulo: str,
        campos: tuple[tuple[str, str], ...],
        al_aceptar,
        valores_iniciales: dict[str, str] | None = None,
        ayuda: str | None = None,
        campo_reloj: str | None = None,
    ) -> None:
        """Show labeled entries. al_aceptar receives the stripped text of each field."""
        dialogo = tk.Toplevel(self)
        dialogo.title(titulo)
        dialogo.transient(self)
        entradas: dict[str, ttk.Entry] = {}
        iniciales = valores_iniciales or {}
        for fila, (clave, etiqueta) in enumerate(campos):
            ttk.Label(dialogo, text=etiqueta).grid(row=fila, column=0, padx=8, pady=4, sticky="w")
            caja = ttk.Entry(dialogo, width=28)
            caja.grid(row=fila, column=1, padx=8, pady=4)
            if clave in iniciales:
                caja.insert(0, iniciales[clave])
            entradas[clave] = caja
            if campo_reloj == clave:
                ttk.Button(
                    dialogo,
                    text="Usar reloj",
                    command=lambda caja=caja: self._poner_reloj(caja),
                ).grid(row=fila, column=2, padx=4)

        if ayuda:
            ttk.Label(dialogo, text=ayuda, wraplength=360).grid(
                row=len(campos), column=0, columnspan=3, padx=8, pady=(4, 0), sticky="w"
            )

        def aceptar() -> None:
            valores = {clave: caja.get().strip() for clave, caja in entradas.items()}
            if al_aceptar(dialogo, valores):
                dialogo.destroy()
                self.actualizar_indicadores()

        ttk.Button(dialogo, text="Aceptar", command=aceptar).grid(
              row=len(campos) + (1 if ayuda else 0), column=1, padx=8, pady=8, sticky="e"
        )

    def _texto_reloj(self) -> str:
        """Current simulation clock as the UTC text the form can show."""
        return self.catalogo.reloj.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _poner_reloj(self, caja: ttk.Entry) -> None:
        """Replace one entry with the simulation clock."""
        caja.delete(0, tk.END)
        caja.insert(0, self._texto_reloj())

    def _siguiente_identificador(self) -> int:
        """Smallest free id so the form does not ask the user to invent one."""
        usados = (
            set(self.catalogo.indice_activos)
            | set(self.catalogo.archivados)
            | set(self.catalogo.eliminados)
        )
        candidato = 1
        while candidato in usados and candidato < 999999:
            candidato += 1
        return candidato

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
                    ocurrencia=texto_a_fecha_utc(valores["ocurrencia"]),
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

        self._abrir_formulario(
            "Crear evento",
            campos,
            al_aceptar,
            valores_iniciales={
                "identificador": str(self._siguiente_identificador()),
                "magnitud": "4.5",
                "profundidad_hipocentro": "30.0",
                "x": "100.0",
                "y": "100.0",
                "ocurrencia": self._texto_reloj(),
                "estacion": "EST-01",
            },
            ayuda="La fecha puede ser 2026-10-01 18:30. No hace falta escribir la Z.",
            campo_reloj="ocurrencia",
        )

    def abrir_consultar_evento(self) -> None:
        """Show the catalog state of one id without changing the trees."""
        def al_aceptar(dialogo: tk.Toplevel, valores: dict[str, str]) -> bool:
            try:
                identificador = self._leer_identificador(valores["identificador"])
                detalle = self.catalogo.consultar_detalle(identificador)
            except (ValueError, KeyError) as error:
                messagebox.showerror("Consultar evento", str(error), parent=dialogo)
                return False
            messagebox.showinfo("Consultar evento", texto_detalle_evento(detalle), parent=dialogo)
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
                if "ocurrencia" in datos:
                    datos["ocurrencia"] = texto_a_fecha_utc(datos["ocurrencia"])
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
    
    def _texto_consulta(self, resultado: ResultadoConsulta) -> str:
        """Format a catalog query for a message box. Does not touch the trees."""
        lineas = [
            f"Nodos examinados: {resultado.nodos_examinados}",
            resultado.descripcion_costo,
        ]
        if not resultado.resultados:
            lineas.append("Sin resultados.")
        for item in resultado.resultados:
            if isinstance(item, Evento):
                lineas.append(
                    f"SIS-{item.identificador:06d} prioridad {item.prioridad} magnitud {item.magnitud}"
                )
            else:
                lineas.append(str(item))
        return "\n".join(lineas)

    def abrir_cambiar_parametro(self) -> None:
        """Send W, R, L or T to cambiar_parametro. The catalog validates and snapshots."""
        campos = (("nombre", "Parametro (W, R, L o T)"), ("valor", "Valor"))

        def al_aceptar(dialogo: tk.Toplevel, valores: dict[str, str]) -> bool:
            nombre = valores["nombre"].upper()
            try:
                valor: object = int(valores["valor"]) if nombre == "L" else valores["valor"]
                nuevo = self.catalogo.cambiar_parametro(nombre, valor)
            except (ValueError, KeyError) as error:
                messagebox.showerror("Cambiar parametro", str(error), parent=dialogo)
                return False
            messagebox.showinfo("Cambiar parametro", f"{nombre} = {nuevo}", parent=dialogo)
            return True

        self._abrir_formulario("Cambiar parametro", campos, al_aceptar)

    def abrir_configurar_estaciones(self) -> None:
        """Replace the station registry through the catalog."""
        def al_aceptar(dialogo: tk.Toplevel, valores: dict[str, str]) -> bool:
            codigos = [parte.strip() for parte in valores["estaciones"].split(",") if parte.strip()]
            try:
                if not codigos:
                    raise ValueError("Escribe al menos una estacion.")
                self.catalogo.configurar_estaciones(codigos)
            except (ValueError, KeyError) as error:
                messagebox.showerror("Configurar estaciones", str(error), parent=dialogo)
                return False
            messagebox.showinfo(
                "Configurar estaciones",
                "Estaciones: " + ", ".join(sorted(self.catalogo.estaciones)),
                parent=dialogo,
            )
            return True

        self._abrir_formulario(
            "Configurar estaciones",
            (("estaciones", "Codigos separados por coma"),),
            al_aceptar,
        )

    def abrir_gestionar_zonas(self) -> None:
        """Add or remove zones. The catalog reclassifies events and can undo."""
        dialogo = tk.Toplevel(self)
        dialogo.title("Gestionar zonas")
        dialogo.transient(self)
        ttk.Label(
            dialogo,
            text=(
                "La primera zona es la inicial. Las demas tienen que quedar dentro de ella. "
                "Editar cambia una zona que ya existe. Deshacer vuelve a la lista anterior."
            ),
            wraplength=420,
        ).pack(padx=8, pady=(8, 4), anchor="w")
        lista = tk.Listbox(dialogo, width=64, height=8)
        lista.pack(padx=8, pady=4, fill="x")

        def texto_zona(zona: Zona) -> str:
            marca = "poblada" if zona.poblada else "no poblada"
            return f"{zona.nombre}   x {zona.x_min}-{zona.x_max}   y {zona.y_min}-{zona.y_max}   {marca}"

        def refrescar() -> None:
            lista.delete(0, tk.END)
            for zona in self.catalogo.zonas:
                lista.insert(tk.END, texto_zona(zona))

        campos_zona = (
            ("nombre", "Nombre"),
            ("x_min", "X minima"),
            ("x_max", "X maxima"),
            ("y_min", "Y minima"),
            ("y_max", "Y maxima"),
            ("poblada", "Poblada (si o no)"),
        )

        def zona_desde_formulario(formulario: tk.Toplevel, valores: dict[str, str], titulo: str) -> Zona | None:
            marca = valores["poblada"].strip().lower()
            if marca not in ("si", "no"):
                messagebox.showerror(titulo, "En poblada escribe si o no.", parent=formulario)
                return None
            return Zona(
                valores["nombre"],
                valores["x_min"],
                valores["x_max"],
                valores["y_min"],
                valores["y_max"],
                marca == "si",
            )

        def aplicar(formulario: tk.Toplevel, titulo: str, nuevas: list[Zona]) -> bool:
            try:
                self.catalogo.configurar_zonas(nuevas)
            except ValueError as error:
                messagebox.showerror(titulo, str(error), parent=formulario)
                return False
            refrescar()
            self.actualizar_indicadores()
            return True

        def quitar() -> None:
            seleccion = lista.curselection()
            if not seleccion:
                messagebox.showerror("Gestionar zonas", "Elige una zona de la lista.", parent=dialogo)
                return
            indice = seleccion[0]
            if indice == 0:
                messagebox.showerror(
                    "Gestionar zonas",
                    "La zona inicial no se quita. Usa Editar para cambiarla.",
                    parent=dialogo,
                )
                return
            restantes = [zona for i, zona in enumerate(self.catalogo.zonas) if i != indice]
            try:
                self.catalogo.configurar_zonas(restantes)
            except ValueError as error:
                messagebox.showerror("Gestionar zonas", str(error), parent=dialogo)
                return
            refrescar()
            self.actualizar_indicadores()

        def agregar() -> None:
            def al_aceptar(formulario: tk.Toplevel, valores: dict[str, str]) -> bool:
                zona = zona_desde_formulario(formulario, valores, "Agregar zona")
                if zona is None:
                    return False
                return aplicar(formulario, "Agregar zona", [*self.catalogo.zonas, zona])

            self._abrir_formulario(
                "Agregar zona",
                campos_zona,
                al_aceptar,
                ayuda="Tiene que quedar dentro de la zona inicial. Coordenadas de 0.0 a 1000.0, un decimal como maximo.",
            )

        def editar() -> None:
            seleccion = lista.curselection()
            if not seleccion:
                messagebox.showerror("Gestionar zonas", "Elige una zona de la lista.", parent=dialogo)
                return
            indice = seleccion[0]
            actual = self.catalogo.zonas[indice]
            ayuda = (
                "Si cambias los limites, las demas zonas tienen que seguir dentro."
                if indice == 0
                else "Tiene que quedar dentro de la zona inicial."
            )

            def al_aceptar(formulario: tk.Toplevel, valores: dict[str, str]) -> bool:
                zona = zona_desde_formulario(formulario, valores, "Editar zona")
                if zona is None:
                    return False
                nuevas = list(self.catalogo.zonas)
                nuevas[indice] = zona
                return aplicar(formulario, "Editar zona", nuevas)

            self._abrir_formulario(
                "Editar zona",
                campos_zona,
                al_aceptar,
                valores_iniciales={
                    "nombre": actual.nombre,
                    "x_min": str(actual.x_min),
                    "x_max": str(actual.x_max),
                    "y_min": str(actual.y_min),
                    "y_max": str(actual.y_max),
                    "poblada": "si" if actual.poblada else "no",
                },
                ayuda=ayuda,
            )

        botones = ttk.Frame(dialogo)
        botones.pack(padx=8, pady=8, fill="x")
        ttk.Button(botones, text="Agregar", command=agregar).pack(side="left", padx=4)
        ttk.Button(botones, text="Editar", command=editar).pack(side="left", padx=4)
        ttk.Button(botones, text="Quitar", command=quitar).pack(side="left", padx=4)
        refrescar()

    def abrir_avanzar_reloj(self) -> None:
        """Advance the simulation clock. The catalog rejects a time in the past."""
        def al_aceptar(dialogo: tk.Toplevel, valores: dict[str, str]) -> bool:
            try:
                self.catalogo.avanzar_reloj(texto_a_fecha_utc(valores["reloj"]))
            except (ValueError, KeyError) as error:
                messagebox.showerror("Avanzar reloj", str(error), parent=dialogo)
                return False
            messagebox.showinfo("Avanzar reloj", f"Reloj: {self.catalogo.reloj.isoformat()}", parent=dialogo)
            return True

        self._abrir_formulario("Avanzar reloj", (("reloj", "Nuevo reloj UTC"),), al_aceptar)

    def abrir_consultar_asociaciones(self) -> None:
        """Show candidates and the chosen reference for one id."""
        def al_aceptar(dialogo: tk.Toplevel, valores: dict[str, str]) -> bool:
            try:
                identificador = self._leer_identificador(valores["identificador"])
                resultado = self.catalogo.consultar_asociaciones(identificador)
            except (ValueError, KeyError) as error:
                messagebox.showerror("Consultar asociaciones", str(error), parent=dialogo)
                return False
            messagebox.showinfo("Consultar asociaciones", self._texto_consulta(resultado), parent=dialogo)
            return True

        self._abrir_formulario(
            "Consultar asociaciones",
            (("identificador", "Identificador"),),
            al_aceptar,
        )

    def abrir_top_k_pendientes(self) -> None:
        """Ask the catalog for the first k pending events in descending key order."""
        def al_aceptar(dialogo: tk.Toplevel, valores: dict[str, str]) -> bool:
            try:
                resultado = self.catalogo.consultar_top_k_pendientes(int(valores["k"]))
            except (ValueError, KeyError) as error:
                messagebox.showerror("Top-k pendientes", str(error), parent=dialogo)
                return False
            messagebox.showinfo("Top-k pendientes", self._texto_consulta(resultado), parent=dialogo)
            return True

        self._abrir_formulario("Top-k pendientes", (("k", "Cantidad k"),), al_aceptar)

    def abrir_consultar_magnitud(self) -> None:
        """Ask the catalog for active events inside a magnitude interval."""
        campos = (("minimo", "Magnitud minima"), ("maximo", "Magnitud maxima"))

        def al_aceptar(dialogo: tk.Toplevel, valores: dict[str, str]) -> bool:
            try:
                resultado = self.catalogo.consultar_por_magnitud(valores["minimo"], valores["maximo"])
            except (ValueError, KeyError) as error:
                messagebox.showerror("Consultar por magnitud", str(error), parent=dialogo)
                return False
            messagebox.showinfo("Consultar por magnitud", self._texto_consulta(resultado), parent=dialogo)
            return True

        self._abrir_formulario("Consultar por magnitud", campos, al_aceptar)

    def abrir_consultar_profundidad_fecha(self) -> None:
        """Ask the catalog for active events up to a depth and inside a date range."""
        campos = (
            ("limite", "Profundidad maxima (km)"),
            ("inicio", "Fecha inicio UTC"),
            ("fin", "Fecha fin UTC"),
        )

        def al_aceptar(dialogo: tk.Toplevel, valores: dict[str, str]) -> bool:
            try:
                resultado = self.catalogo.consultar_por_profundidad_y_fecha(
                    valores["limite"],
                    texto_a_fecha_utc(valores["inicio"]),
                    texto_a_fecha_utc(valores["fin"]),
                )
            except (ValueError, KeyError) as error:
                messagebox.showerror("Consultar por profundidad y fecha", str(error), parent=dialogo)
                return False
            messagebox.showinfo(
                "Consultar por profundidad y fecha",
                self._texto_consulta(resultado),
                parent=dialogo,
            )
            return True

        self._abrir_formulario("Consultar por profundidad y fecha", campos, al_aceptar)

    def abrir_acceso_costoso(self) -> None:
        """Show priority-3 events deeper than L. Read-only."""
        try:
            resultado = self.catalogo.consultar_acceso_costoso()
        except ValueError as error:
            messagebox.showerror("Acceso costoso", str(error))
            return
        messagebox.showinfo("Acceso costoso", self._texto_consulta(resultado))


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
        """Leave stress mode and tell the user how many rotations the repair used."""
        giros = self.catalogo.desactivar_modo_estres()
        self.actualizar_indicadores()
        messagebox.showinfo("Recuperar AVL", f"Modo normal. Giros de recuperacion: {giros}")

    def abrir_cargar_json(self) -> None:
        """Pick a JSON file and load it by tipo_carga. A failure leaves the scenario."""
        ruta = filedialog.askopenfilename(
            title="Seleccionar archivo JSON de carga",
            filetypes=[("Archivos JSON", "*.json"), ("Todos los archivos", "*.*")],
        )
        if not ruta:
            return
        try:
            datos = leer_json_archivo(ruta)
            estadisticas = aplicar_carga_json(self.catalogo, datos)
        except (ValueError, OSError) as error:
            messagebox.showerror("Cargar JSON", str(error))
            return
        self.actualizar_indicadores()
        messagebox.showinfo(
            "Cargar JSON",
            texto_resultado_carga(str(datos.get("tipo_carga")), estadisticas),
        )

    def abrir_historial_sismico(self) -> None:
        """List archived events. Reading the list does not change the catalog."""
        dialogo = tk.Toplevel(self)
        dialogo.title("Historial sismico")
        dialogo.transient(self)
        ttk.Label(
            dialogo,
            text="Eventos archivados. No estan en el arbol. Deshacer es otra lista: la de acciones de esta sesion.",
            wraplength=460,
        ).pack(padx=8, pady=(8, 4), anchor="w")
        lista = tk.Listbox(dialogo, width=78, height=12)
        lista.pack(padx=8, pady=4, fill="both", expand=True)
        filas = filas_historial_sismico(self.catalogo)
        if not filas:
            lista.insert(tk.END, "No hay eventos archivados.")
        else:
            for fila in filas:
                lista.insert(tk.END, fila)
        ttk.Button(dialogo, text="Cerrar", command=dialogo.destroy).pack(pady=8)

    def deshacer_accion(self) -> None:
        """Undo the last action using the catalog's history stack."""
        try:
            mensaje = self.catalogo.deshacer()
            messagebox.showinfo("Deshacer", mensaje)
            self.actualizar_indicadores()
        except IndexError as e:
            messagebox.showwarning("Deshacer", str(e))
        except Exception as e:
            messagebox.showerror("Error", f"Error al deshacer: {e}")

    def abrir_ventana_versiones(self) -> None:
        """Open the version management window with save/restore/delete functionality."""
        ventana_versiones = tk.Toplevel(self)
        ventana_versiones.title("Gestion de Versiones")
        ventana_versiones.geometry("500x400")

        # Frame for version list
        frame_lista = ttk.Frame(ventana_versiones)
        frame_lista.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        ttk.Label(frame_lista, text="Versiones disponibles:").pack(anchor=tk.W)

        listbox = tk.Listbox(frame_lista)
        listbox.pack(fill=tk.BOTH, expand=True, pady=5)

        scrollbar = ttk.Scrollbar(frame_lista, orient=tk.VERTICAL, command=listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        listbox.config(yscrollcommand=scrollbar.set)

        # Refresh version list
        def actualizar_lista():
            listbox.delete(0, tk.END)
            versiones = self.catalogo.listar_versiones()
            for version in versiones:
                listbox.insert(tk.END, version)

        actualizar_lista()

        # Frame for buttons
        frame_botones = ttk.Frame(ventana_versiones)
        frame_botones.pack(fill=tk.X, padx=10, pady=10)

        def guardar_nueva_version():
            nombre = simpledialog.askstring(
                "Guardar version",
                "Ingrese el nombre de la version:",
                parent=ventana_versiones,
            )
            if nombre:
                try:
                    ruta = self.catalogo.guardar_version(nombre)
                    messagebox.showinfo("Version guardada", f"Version guardada exitosamente en:\n{ruta}")
                    actualizar_lista()
                except ValueError as e:
                    messagebox.showerror("Error", str(e))
                except PermissionError as e:
                    messagebox.showerror("Error de permisos", str(e))
                except Exception as e:
                    messagebox.showerror("Error", f"Error inesperado: {e}")

        def restaurar_seleccionada():
            seleccion = listbox.curselection()
            if not seleccion:
                messagebox.showwarning("Seleccion", "Seleccione una version.")
                return
            nombre = listbox.get(seleccion[0])
            if messagebox.askyesno("Confirmar", f"¿Restaurar version '{nombre}'?"):
                try:
                    self.catalogo.restaurar_version(nombre)
                    messagebox.showinfo("Version restaurada", f"Version '{nombre}' restaurada exitosamente.")
                    self.actualizar_indicadores()
                    actualizar_lista()
                except FileNotFoundError as e:
                    messagebox.showerror("Error", str(e))
                except Exception as e:
                    messagebox.showerror("Error", f"Error al restaurar: {e}")

        def eliminar_seleccionada():
            seleccion = listbox.curselection()
            if not seleccion:
                messagebox.showwarning("Seleccion", "Seleccione una version.")
                return
            nombre = listbox.get(seleccion[0])
            if messagebox.askyesno("Confirmar", f"¿Eliminar version '{nombre}'?"):
                try:
                    import os
                    from src.catalogo import _obtener_ruta_version
                    ruta = _obtener_ruta_version(nombre)
                    os.remove(ruta)
                    messagebox.showinfo("Version eliminada", f"Version '{nombre}' eliminada exitosamente.")
                    actualizar_lista()
                except FileNotFoundError as e:
                    messagebox.showerror("Error", str(e))
                except PermissionError as e:
                    messagebox.showerror("Error de permisos", str(e))
                except Exception as e:
                    messagebox.showerror("Error", f"Error al eliminar: {e}")

        ttk.Button(frame_botones, text="Guardar nueva version", command=guardar_nueva_version).pack(side=tk.LEFT, padx=2)
        ttk.Button(frame_botones, text="Restaurar seleccionada", command=restaurar_seleccionada).pack(side=tk.LEFT, padx=2)
        ttk.Button(frame_botones, text="Eliminar seleccionada", command=eliminar_seleccionada).pack(side=tk.LEFT, padx=2)
        ttk.Button(frame_botones, text="Actualizar lista", command=actualizar_lista).pack(side=tk.LEFT, padx=2)

    def abrir_archivar_rama(self) -> None:
        """Show the winning eligible subtree, then archive it only after confirmation."""
        try:
            candidatas = self.catalogo.listar_ramas_archivables()
        except ValueError as error:
            messagebox.showerror("Archivar rama", str(error))
            return
        if not candidatas:
            messagebox.showinfo(
                "Archivar rama",
                "No hay rama elegible. Hace falta prioridad 1 y antiguedad mayor que T.",
            )
            return
        ganadora = candidatas[0]
        identificadores = ", ".join(f"SIS-{identificador:06d}" for identificador in ganadora.identificadores)
        confirmar = messagebox.askyesno(
            "Archivar rama",
            (
                f"Raiz SIS-{ganadora.id_raiz:06d}, profundidad {ganadora.profundidad}.\n"
                f"{len(ganadora.identificadores)} eventos: {identificadores}\n\n"
                "Esos eventos salen del AVL y del BST y quedan en el historial."
            ),
        )
        if not confirmar:
            return
        try:
            archivada = self.catalogo.archivar_rama()
        except ValueError as error:
            messagebox.showerror("Archivar rama", str(error))
            return
        self.actualizar_indicadores()
        messagebox.showinfo(
            "Archivar rama",
            f"Archivada la rama de SIS-{archivada.id_raiz:06d} ({len(archivada.identificadores)} eventos).",
        )

    def verificar_estructura(self) -> None:
        """Verify AVL structure and show results, distinguishing expected imbalance in stress mode."""
        exigir_balanceo = not self.catalogo.modo_estres
        resultado = self.catalogo.avl.auditar(exigir_balanceo=exigir_balanceo)

        ventana_resultado = tk.Toplevel(self)
        ventana_resultado.title("Verificacion de Estructura AVL")
        ventana_resultado.geometry("500x400")

        frame_resultado = ttk.Frame(ventana_resultado)
        frame_resultado.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Show mode
        modo = "Modo ESTRES (desbalance esperado)" if self.catalogo.modo_estres else "Modo NORMAL (balance requerido)"
        ttk.Label(frame_resultado, text=modo, font=("Segoe UI", 10, "bold")).pack(pady=5)

        # Show results
        orden_texto = "✓ Orden BST correcto" if resultado.orden_correcto else "✗ Orden BST incorrecto"
        alturas_texto = "✓ Alturas correctas" if resultado.alturas_correctas else "✗ Alturas incorrectas"
        balance_texto = "✓ Balance AVL correcto" if resultado.balanceado else "✗ Balance AVL incorrecto"

        ttk.Label(frame_resultado, text=orden_texto, foreground="green" if resultado.orden_correcto else "red").pack(anchor=tk.W, pady=2)
        ttk.Label(frame_resultado, text=alturas_texto, foreground="green" if resultado.alturas_correctas else "red").pack(anchor=tk.W, pady=2)
        ttk.Label(frame_resultado, text=balance_texto, foreground="green" if resultado.balanceado else "red").pack(anchor=tk.W, pady=2)

        # Show errors if any
        if resultado.errores:
            ttk.Separator(frame_resultado, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)
            ttk.Label(frame_resultado, text="Errores encontrados:", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)
            text_errores = tk.Text(frame_resultado, height=10, wrap=tk.WORD)
            text_errores.pack(fill=tk.BOTH, expand=True, pady=5)
            scrollbar_errores = ttk.Scrollbar(frame_resultado, orient=tk.VERTICAL, command=text_errores.yview)
            scrollbar_errores.pack(side=tk.RIGHT, fill=tk.Y)
            text_errores.config(yscrollcommand=scrollbar_errores.set)
            for error in resultado.errores:
                text_errores.insert(tk.END, error + "\n")
            text_errores.config(state=tk.DISABLED)
        else:
            ttk.Label(frame_resultado, text="No se encontraron errores.", foreground="green").pack(pady=10)

    def mostrar_indicadores_detallados(self) -> None:
        """Show detailed indicators in a popup window."""
        indicadores = self.catalogo.indicadores()

        ventana_indicadores = tk.Toplevel(self)
        ventana_indicadores.title("Indicadores Detallados")
        ventana_indicadores.geometry("500x450")

        frame_indicadores = ttk.Frame(ventana_indicadores)
        frame_indicadores.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # AVL indicators
        ttk.Label(frame_indicadores, text="Indicadores AVL", font=("Segoe UI", 12, "bold")).pack(anchor=tk.W, pady=5)
        avl_data = indicadores["avl"]
        ttk.Label(frame_indicadores, text=f"Altura: {avl_data['altura']}").pack(anchor=tk.W)
        ttk.Label(frame_indicadores, text=f"Hojas: {avl_data['hojas']}").pack(anchor=tk.W)
        ttk.Label(frame_indicadores, text=f"Profundidad maxima: {avl_data['profundidad_maxima']}").pack(anchor=tk.W)
        ttk.Label(frame_indicadores, text=f"Giros izquierda: {avl_data['giros_izquierda']}").pack(anchor=tk.W)
        ttk.Label(frame_indicadores, text=f"Giros derecha: {avl_data['giros_derecha']}").pack(anchor=tk.W)
        ttk.Label(frame_indicadores, text=f"Casos LL: {avl_data['casos_ll']}").pack(anchor=tk.W)
        ttk.Label(frame_indicadores, text=f"Casos RR: {avl_data['casos_rr']}").pack(anchor=tk.W)
        ttk.Label(frame_indicadores, text=f"Casos LR: {avl_data['casos_lr']}").pack(anchor=tk.W)
        ttk.Label(frame_indicadores, text=f"Casos RL: {avl_data['casos_rl']}").pack(anchor=tk.W)

        ttk.Separator(frame_indicadores, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        # BST indicators
        ttk.Label(frame_indicadores, text="Indicadores BST", font=("Segoe UI", 12, "bold")).pack(anchor=tk.W, pady=5)
        bst_data = indicadores["bst"]
        ttk.Label(frame_indicadores, text=f"Altura: {bst_data['altura']}").pack(anchor=tk.W)
        ttk.Label(frame_indicadores, text=f"Hojas: {bst_data['hojas']}").pack(anchor=tk.W)
        ttk.Label(frame_indicadores, text=f"Profundidad maxima: {bst_data['profundidad_maxima']}").pack(anchor=tk.W)

        ttk.Separator(frame_indicadores, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        # Expensive access
        ttk.Label(frame_indicadores, text="Acceso Costoso (profundidad > L)", font=("Segoe UI", 12, "bold")).pack(anchor=tk.W, pady=5)
        costosos = indicadores["acceso_costoso"]
        if costosos:
            text_costosos = tk.Text(frame_indicadores, height=8, wrap=tk.WORD)
            text_costosos.pack(fill=tk.BOTH, expand=True, pady=5)
            scrollbar_costosos = ttk.Scrollbar(frame_indicadores, orient=tk.VERTICAL, command=text_costosos.yview)
            scrollbar_costosos.pack(side=tk.RIGHT, fill=tk.Y)
            text_costosos.config(yscrollcommand=scrollbar_costosos.set)
            for item in costosos:
                text_costosos.insert(tk.END, f"ID: {item['identificador']}, Profundidad: {item['profundidad']}, Examinados: {item['examinados']}\n")
            text_costosos.config(state=tk.DISABLED)
        else:
            ttk.Label(frame_indicadores, text="No hay eventos con acceso costoso.").pack(anchor=tk.W)

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

        def encolar_elegido() -> None:
            """Enqueue one report whose fields the user typed, not a random one."""
            def al_aceptar(formulario: tk.Toplevel, valores: dict[str, str]) -> bool:
                try:
                    revision = int(valores["revision"])
                    nuevo = Evento(
                        identificador=self._leer_identificador(valores["identificador"]),
                        magnitud=valores["magnitud"],
                        profundidad_hipocentro=valores["profundidad_hipocentro"],
                        x=valores["x"],
                        y=valores["y"],
                        ocurrencia=texto_a_fecha_utc(valores["ocurrencia"]),
                        revision=revision,
                        estaciones={valores["estacion"]},
                    )
                    nuevo.validar(self.catalogo.reloj)
                    if self.catalogo.estaciones and valores["estacion"] not in self.catalogo.estaciones:
                        raise ValueError(f"Estacion no configurada: {valores['estacion']}.")
                    self.catalogo.encolar_reporte(Reporte(evento=nuevo, estacion=valores["estacion"]))
                except (ValueError, KeyError) as error:
                    messagebox.showerror("Encolar reporte", str(error), parent=formulario)
                    return False
                self._actualizar_vista_cola(tree_cola)
                self.actualizar_indicadores()
                return True

            self._abrir_formulario(
                "Encolar reporte",
                (
                    ("identificador", "Identificador"),
                    ("magnitud", "Magnitud"),
                    ("profundidad_hipocentro", "Profundidad (km)"),
                    ("x", "X"),
                    ("y", "Y"),
                    ("ocurrencia", "Ocurrencia UTC"),
                    ("revision", "Revision"),
                    ("estacion", "Estacion"),
                ),
                al_aceptar,
                valores_iniciales={
                    "identificador": str(self._siguiente_identificador()),
                    "magnitud": "4.5",
                    "profundidad_hipocentro": "30.0",
                    "x": "100.0",
                    "y": "100.0",
                    "ocurrencia": self._texto_reloj(),
                    "revision": "1",
                    "estacion": "EST-01",
                },
                ayuda="Sirve para un reporte antiguo, uno tardio o una revision mayor de un archivado.",
                campo_reloj="ocurrencia",
            )

        ttk.Button(frame_preparar, text="Encolar uno", command=encolar_elegido).pack(side=tk.LEFT, padx=5)

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

    def _lienzo_arbol(self, parent: tk.Widget) -> tk.Canvas:
        """Canvas with both scrollbars. The wheel moves vertically; Shift moves sideways."""
        marco = ttk.Frame(parent)
        marco.pack(fill=tk.BOTH, expand=True)
        canvas = tk.Canvas(marco, bg="white", highlightthickness=0)
        barra_y = ttk.Scrollbar(marco, orient=tk.VERTICAL, command=canvas.yview)
        barra_x = ttk.Scrollbar(marco, orient=tk.HORIZONTAL, command=canvas.xview)
        canvas.configure(xscrollcommand=barra_x.set, yscrollcommand=barra_y.set)
        barra_y.pack(side=tk.RIGHT, fill=tk.Y)
        barra_x.pack(side=tk.BOTTOM, fill=tk.X)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        def al_rueda(evento: tk.Event) -> None:
            pasos = int(-evento.delta / 120) or (-1 if evento.delta > 0 else 1)
            if evento.state & 0x0001:
                canvas.xview_scroll(pasos, "units")
            else:
                canvas.yview_scroll(pasos, "units")

        canvas.bind("<MouseWheel>", al_rueda)
        return canvas

    def abrir_ventana_visualizacion(self) -> None:
        """Open the tree visualization window with AVL and BST side by side."""
        ventana_vis = tk.Toplevel(self)
        ventana_vis.title("Visualizacion de Arboles AVL y BST")
        ventana_vis.geometry("1200x700")

        self._coordenadas_nodos_avl = {}  # id -> (x, y)
        self._coordenadas_nodos_bst = {}  # id -> (x, y)
        self._radio_nodo = 16

        frame_control = ttk.Frame(ventana_vis)
        frame_control.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=5)

        frame_avl = ttk.LabelFrame(ventana_vis, text="AVL (Balanceado)")
        frame_avl.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        canvas_avl = self._lienzo_arbol(frame_avl)

        frame_bst = ttk.LabelFrame(ventana_vis, text="BST (No Balanceado)")
        frame_bst.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        canvas_bst = self._lienzo_arbol(frame_bst)

        ttk.Button(frame_control, text="Redibujar", command=lambda: self._redibujar_arboles(canvas_avl, canvas_bst)).pack(side=tk.LEFT, padx=5)

        # Info panel for node inspection
        frame_info = ttk.LabelFrame(frame_control, text="Informacion del Nodo")
        frame_info.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)

        info_label = ttk.Label(
            frame_info,
            text="Click en un nodo para inspeccionar. Rueda para bajar; Shift+rueda para ir a los lados.",
            wraplength=400,
        )
        info_label.pack(padx=5, pady=5)

        canvas_avl.bind("<Button-1>", lambda e: self._inspeccionar_nodo(e, canvas_avl, "avl", info_label))
        canvas_bst.bind("<Button-1>", lambda e: self._inspeccionar_nodo(e, canvas_bst, "bst", info_label))

        ventana_vis.update_idletasks()
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
            self._marcar_arbol_vacio(canvas_avl, "Arbol AVL vacio")
        else:
            self._dibujar_arbol(canvas_avl, vista_avl, raiz_avl, "blue", self._coordenadas_nodos_avl)

        vista_bst, raiz_bst = self.catalogo.obtener_vista_arbol("bst")
        if raiz_bst is None:
            self._marcar_arbol_vacio(canvas_bst, "Arbol BST vacio")
        else:
            self._dibujar_arbol(canvas_bst, vista_bst, raiz_bst, "green", self._coordenadas_nodos_bst)

    def _marcar_arbol_vacio(self, canvas: tk.Canvas, texto: str) -> None:
        """Show an empty-tree message and drop any previous scroll range."""
        ancho = max(canvas.winfo_width(), 200)
        alto = max(canvas.winfo_height(), 200)
        canvas.configure(scrollregion=(0, 0, ancho, alto))
        canvas.create_text(ancho / 2, alto / 2, text=texto, font=("Segoe UI", 14), fill="gray")

    def _dibujar_arbol(
        self,
        canvas: tk.Canvas,
        vista: dict[int, VistaNodo],
        raiz_id: int,
        color: str,
        coordenadas: dict[int, tuple[float, float]],
    ) -> None:
        """Draw one tree. Positions come from inorder slots, then the canvas scrolls."""
        posiciones = posiciones_arbol(vista, raiz_id)
        ancho_vista = max(canvas.winfo_width(), 200)
        alto_vista = max(canvas.winfo_height(), 200)
        ancho = max(x for x, _y in posiciones.values()) + MARGEN_ARBOL
        alto = max(y for _x, y in posiciones.values()) + MARGEN_ARBOL + 28
        desplazamiento_x = (ancho_vista - ancho) / 2 if ancho < ancho_vista else 0
        canvas.configure(scrollregion=(0, 0, max(ancho, ancho_vista), max(alto, alto_vista)))
        canvas.xview_moveto(0)
        canvas.yview_moveto(0)

        for nodo_id, (x, y) in posiciones.items():
            coordenadas[nodo_id] = (x + desplazamiento_x, y)

        def dibujar_enlaces(nodo_id: int) -> None:
            nodo = vista[nodo_id]
            x_padre, y_padre = coordenadas[nodo_id]
            for hijo_id in (nodo.izquierdo_id, nodo.derecho_id):
                if hijo_id is None:
                    continue
                x_hijo, y_hijo = coordenadas[hijo_id]
                canvas.create_line(x_padre, y_padre, x_hijo, y_hijo, fill="black", width=2)
                dibujar_enlaces(hijo_id)

        dibujar_enlaces(raiz_id)

        radio = self._radio_nodo
        for nodo_id, nodo in vista.items():
            x, y = coordenadas[nodo_id]
            canvas.create_oval(
                x - radio, y - radio, x + radio, y + radio,
                fill=color, outline="black", width=2,
            )
            canvas.create_text(x, y, text=str(nodo.id), font=("Segoe UI", 8, "bold"), fill="white")
            canvas.create_text(
                x, y + radio + 11,
                text=f"({nodo.clave[0]}, {nodo.clave[1]})",
                font=("Segoe UI", 7),
                fill="black",
            )
            if nodo.factor is not None:
                canvas.create_text(
                    x, y + radio + 22,
                    text=f"h:{nodo.altura} f:{nodo.factor}",
                    font=("Segoe UI", 7),
                    fill="black",
                )

    def _inspeccionar_nodo(
        self,
        evento: tk.Event,
        canvas: tk.Canvas,
        tipo: str,
        info_label: ttk.Label,
    ) -> None:
        """Inspect a node when clicked. Coordinates include the scroll offset."""
        x_click, y_click = canvas.canvasx(evento.x), canvas.canvasy(evento.y)

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

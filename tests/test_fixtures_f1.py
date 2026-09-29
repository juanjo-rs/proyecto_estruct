"""Unit tests for F1 JSON fixtures to validate schema A3 compliance."""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest import TestCase

from src.catalogo import CatalogoSismico, leer_json_archivo
from src.dominio import Zona


RELOJ = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestFixturesF1(TestCase):
    """Validate that F1 JSON fixtures respect schema A3."""

    def setUp(self) -> None:
        self.zonas = [Zona("Ciudad", 0, 500, 0, 500, True)]

    def test_limites_empates_json_valido(self) -> None:
        """Test that limites_empates.json has valid schema and loads correctly."""
        ruta = FIXTURES_DIR / "limites_empates.json"
        datos = leer_json_archivo(str(ruta))
        
        self.assertEqual(datos["version"], 1)
        self.assertEqual(datos["tipo_carga"], "inserciones")
        self.assertEqual(datos["modo"], "normal")
        self.assertIn("eventos", datos)
        self.assertEqual(len(datos["eventos"]), 4)
        
        catalogo = CatalogoSismico(self.zonas, RELOJ)
        estadisticas = catalogo.cargar_por_inserciones(datos)
        
        self.assertEqual(len(catalogo.indice_activos), 4)
        self.assertIn(1, catalogo.indice_activos)
        self.assertIn(100, catalogo.indice_activos)
        self.assertIn(500000, catalogo.indice_activos)
        self.assertIn(999999, catalogo.indice_activos)

    def test_correccion_reporte_antiguo_json_valido(self) -> None:
        """Test that correccion_reporte_antiguo.json has valid schema."""
        ruta = FIXTURES_DIR / "correccion_reporte_antiguo.json"
        datos = leer_json_archivo(str(ruta))
        
        self.assertEqual(datos["version"], 1)
        self.assertEqual(datos["tipo_carga"], "inserciones")
        self.assertEqual(len(datos["eventos"]), 2)
        
        catalogo = CatalogoSismico(self.zonas, RELOJ)
        estadisticas = catalogo.cargar_por_inserciones(datos)
        
        self.assertEqual(len(catalogo.indice_activos), 2)
        self.assertEqual(catalogo.indice_activos[10].revision, 2)
        self.assertEqual(catalogo.indice_activos[20].revision, 1)

    def test_reporte_tardio_json_rechaza_fecha_futura(self) -> None:
        """Test that reporte_tardio.json is rejected due to future date."""
        ruta = FIXTURES_DIR / "reporte_tardio.json"
        datos = leer_json_archivo(str(ruta))
        
        catalogo = CatalogoSismico(self.zonas, RELOJ)
        
        with self.assertRaises(ValueError) as context:
            catalogo.cargar_por_inserciones(datos)
        self.assertIn("posterior", str(context.exception).lower())

    def test_cuatro_rotaciones_json_valido(self) -> None:
        """Test that cuatro_rotaciones.json has valid topology schema."""
        ruta = FIXTURES_DIR / "cuatro_rotaciones.json"
        datos = leer_json_archivo(str(ruta))
        
        self.assertEqual(datos["version"], 1)
        self.assertEqual(datos["tipo_carga"], "topologia")
        self.assertEqual(datos["modo"], "normal")
        self.assertIn("nodos", datos)
        self.assertIn("raiz", datos)
        
        datos["nodos"] = {int(k): v for k, v in datos["nodos"].items()}
        datos["raiz"] = int(datos["raiz"]) if datos["raiz"] is not None else None
        
        catalogo = CatalogoSismico(self.zonas, RELOJ)
        estadisticas = catalogo.cargar_por_topologia(datos)
        
        self.assertEqual(len(catalogo.indice_activos), 4)
        auditoria = catalogo.avl.auditar()
        self.assertTrue(auditoria.orden_correcto, auditoria.errores)
        self.assertTrue(auditoria.balanceado, auditoria.errores)

    def test_estres_fb_mayor_2_json_valido(self) -> None:
        """Test that estres_fb_mayor_2.json loads in stress mode."""
        ruta = FIXTURES_DIR / "estres_fb_mayor_2.json"
        datos = leer_json_archivo(str(ruta))
        
        self.assertEqual(datos["modo"], "estres")
        
        datos["nodos"] = {int(k): v for k, v in datos["nodos"].items()}
        datos["raiz"] = int(datos["raiz"]) if datos["raiz"] is not None else None
        
        catalogo = CatalogoSismico(self.zonas, RELOJ)
        estadisticas = catalogo.cargar_por_topologia(datos)
        
        self.assertTrue(catalogo.modo_estres)
        self.assertEqual(len(catalogo.indice_activos), 7)
        auditoria = catalogo.avl.auditar(exigir_balanceo=False)
        self.assertTrue(auditoria.orden_correcto, auditoria.errores)

    def test_archivo_masivo_json_valido(self) -> None:
        """Test that archivo_masivo.json loads 50 events correctly."""
        ruta = FIXTURES_DIR / "archivo_masivo.json"
        datos = leer_json_archivo(str(ruta))
        
        self.assertEqual(len(datos["eventos"]), 50)
        
        catalogo = CatalogoSismico(self.zonas, RELOJ)
        estadisticas = catalogo.cargar_por_inserciones(datos)
        
        self.assertEqual(len(catalogo.indice_activos), 50)
        auditoria = catalogo.avl.auditar()
        self.assertTrue(auditoria.orden_correcto, auditoria.errores)
        self.assertTrue(auditoria.balanceado, auditoria.errores)

    def test_topologia_normal_json_valido(self) -> None:
        """Test that topologia_normal.json loads balanced topology."""
        ruta = FIXTURES_DIR / "topologia_normal.json"
        datos = leer_json_archivo(str(ruta))
        
        self.assertEqual(datos["modo"], "normal")
        
        datos["nodos"] = {int(k): v for k, v in datos["nodos"].items()}
        datos["raiz"] = int(datos["raiz"]) if datos["raiz"] is not None else None
        
        catalogo = CatalogoSismico(self.zonas, RELOJ)
        estadisticas = catalogo.cargar_por_topologia(datos)
        
        self.assertEqual(len(catalogo.indice_activos), 4)
        self.assertFalse(catalogo.modo_estres)
        auditoria = catalogo.avl.auditar()
        self.assertTrue(auditoria.balanceado, auditoria.errores)

    def test_topologia_estres_json_valido(self) -> None:
        """Test that topologia_estres.json loads unbalanced topology in stress mode."""
        ruta = FIXTURES_DIR / "topologia_estres.json"
        datos = leer_json_archivo(str(ruta))
        
        self.assertEqual(datos["modo"], "estres")
        
        datos["nodos"] = {int(k): v for k, v in datos["nodos"].items()}
        datos["raiz"] = int(datos["raiz"]) if datos["raiz"] is not None else None
        
        catalogo = CatalogoSismico(self.zonas, RELOJ)
        estadisticas = catalogo.cargar_por_topologia(datos)
        
        self.assertTrue(catalogo.modo_estres)
        auditoria = catalogo.avl.auditar(exigir_balanceo=False)
        self.assertTrue(auditoria.orden_correcto, auditoria.errores)

    def test_json_invalido_json_rechaza_ciclo(self) -> None:
        """Test that json_invalido.json is rejected due to cycle."""
        ruta = FIXTURES_DIR / "json_invalido.json"
        datos = leer_json_archivo(str(ruta))
        
        datos["nodos"] = {int(k): v for k, v in datos["nodos"].items()}
        datos["raiz"] = int(datos["raiz"]) if datos["raiz"] is not None else None
        
        catalogo = CatalogoSismico(self.zonas, RELOJ)
        
        with self.assertRaises(ValueError) as context:
            catalogo.cargar_por_topologia(datos)
        self.assertIn("ciclo", str(context.exception).lower())

    def test_rafagas_fifo_json_valido(self) -> None:
        """Test that rafagas_fifo.json loads FIFO sequence correctly."""
        ruta = FIXTURES_DIR / "rafagas_fifo.json"
        datos = leer_json_archivo(str(ruta))
        
        self.assertEqual(len(datos["eventos"]), 10)
        
        catalogo = CatalogoSismico(self.zonas, RELOJ)
        estadisticas = catalogo.cargar_por_inserciones(datos)
        
        self.assertEqual(len(catalogo.indice_activos), 10)
        auditoria = catalogo.avl.auditar()
        self.assertTrue(auditoria.orden_correcto, auditoria.errores)
        self.assertTrue(auditoria.balanceado, auditoria.errores)

    def test_todos_los_archivos_tienen_version_1(self) -> None:
        """Test that all fixture files have version 1."""
        for nombre_archivo in [
            "limites_empates.json",
            "correccion_reporte_antiguo.json",
            "reporte_tardio.json",
            "cuatro_rotaciones.json",
            "estres_fb_mayor_2.json",
            "archivo_masivo.json",
            "topologia_normal.json",
            "topologia_estres.json",
            "json_invalido.json",
            "rafagas_fifo.json",
        ]:
            ruta = FIXTURES_DIR / nombre_archivo
            datos = leer_json_archivo(str(ruta))
            self.assertEqual(datos["version"], 1, f"{nombre_archivo} should have version 1")

    def test_todos_los_archivos_tienen_tipo_carga_valido(self) -> None:
        """Test that all fixture files have valid tipo_carga."""
        for nombre_archivo in [
            "limites_empates.json",
            "correccion_reporte_antiguo.json",
            "reporte_tardio.json",
            "archivo_masivo.json",
            "rafagas_fifo.json",
        ]:
            ruta = FIXTURES_DIR / nombre_archivo
            datos = leer_json_archivo(str(ruta))
            self.assertEqual(datos["tipo_carga"], "inserciones", f"{nombre_archivo} should be inserciones")
        
        for nombre_archivo in [
            "cuatro_rotaciones.json",
            "estres_fb_mayor_2.json",
            "topologia_normal.json",
            "topologia_estres.json",
            "json_invalido.json",
        ]:
            ruta = FIXTURES_DIR / nombre_archivo
            datos = leer_json_archivo(str(ruta))
            self.assertEqual(datos["tipo_carga"], "topologia", f"{nombre_archivo} should be topologia")

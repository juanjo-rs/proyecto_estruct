from unittest import TestCase

from interfaz import texto_a_fecha_utc


class PruebasFechaFormulario(TestCase):
    def test_fecha_corta_se_guarda_en_utc(self) -> None:
        self.assertEqual(texto_a_fecha_utc("2026-10-01 18:30"), "2026-10-01T18:30:00Z")

    def test_fecha_con_z_se_conserva(self) -> None:
        self.assertEqual(texto_a_fecha_utc("2026-10-01T18:30:00Z"), "2026-10-01T18:30:00Z")

    def test_fecha_incompleta_se_rechaza(self) -> None:
        with self.assertRaises(ValueError):
            texto_a_fecha_utc("mañana")

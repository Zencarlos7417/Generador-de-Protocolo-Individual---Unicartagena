import unittest
import os
import sys
import tempfile
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import validar_formato_clave, validar_variable_entorno
from pdf_reader import recortar_texto


class TestConfigValidation(unittest.TestCase):
    def test_valid_aq_key_format(self):
        result = validar_formato_clave("AQ.Ab8" + "X" * 40)
        self.assertEqual(result["formato"], "AQ (Auth Key, nuevo formato Google, 2026)")
        self.assertTrue(result["clave_valida"])

    def test_valid_aiza_key_format(self):
        result = validar_formato_clave("AI" + "za" + "Sy" + "D" * 33)
        self.assertEqual(result["formato"], "AIza (Standard Key, formato legacy)")
        self.assertTrue(result["clave_valida"])

    def test_unknown_key_format(self):
        result = validar_formato_clave("not-a-valid-key")
        self.assertFalse(result["clave_valida"])
        self.assertEqual(result["formato"], "desconocido")

    def test_empty_key_format(self):
        result = validar_formato_clave("")
        self.assertFalse(result["clave_valida"])
        self.assertEqual(result["formato"], "desconocido")

    def test_valid_variable_env(self):
        config = validar_variable_entorno()
        self.assertIn("gemini_key", config)
        self.assertIn("flask_secret", config)
        self.assertIn("max_content_length", config)
        self.assertEqual(config["max_content_length"], 25 * 1024 * 1024)


class TestRecortarTexto(unittest.TestCase):
    def test_text_under_limit(self):
        texto = "Texto corto"
        resultado = recortar_texto(texto, max_caracteres=100)
        self.assertEqual(resultado, "Texto corto")

    def test_text_over_limit(self):
        texto = "A" * 1000
        resultado = recortar_texto(texto, max_caracteres=100)
        self.assertLessEqual(len(resultado), 100 + 200)
        self.assertIn("[NOTA: el texto original era más extenso", resultado)

    def test_empty_text(self):
        resultado = recortar_texto("", max_caracteres=100)
        self.assertEqual(resultado, "")

    def test_boundary_text(self):
        texto = "A" * 60000
        resultado = recortar_texto(texto, max_caracteres=60000)
        self.assertEqual(resultado, texto)


class TestApiKeyValidation(unittest.TestCase):
    def test_key_starts_with_aq(self):
        key = "AQ.Ab8" + "X" * 40
        self.assertTrue(key.startswith("AQ."))

    def test_key_starts_with_aiza(self):
        key = "AI" + "za" + "Sy" + "D" * 33
        self.assertTrue(key.startswith("AIza"))


class TestDocxFillerTags(unittest.TestCase):
    def test_all_expected_tags_present(self):
        from ai_processor import CLAVES_ESPERADAS
        expected = {
            "descripcion", "palabras_clave", "objetivos", "conceptos_clave",
            "resumen", "metodologia", "conclusiones", "discusiones", "bibliografia"
        }
        self.assertEqual(set(CLAVES_ESPERADAS), expected)
        self.assertEqual(len(CLAVES_ESPERADAS), 9)


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    unittest.main()
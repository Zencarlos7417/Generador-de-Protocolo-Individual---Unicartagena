import os
import unittest

os.environ["GEMINI_API_KEY"] = "AQ.TestKeyForValidation"
from app import resolver_ruta_plantilla


class TestTemplateSelection(unittest.TestCase):
    def test_resuelve_plantilla_individual_por_defecto(self):
        ruta = resolver_ruta_plantilla("individual")
        self.assertTrue(ruta.endswith("plantilla_protocolo.docx"))

    def test_resuelve_plantilla_colaborativa(self):
        ruta = resolver_ruta_plantilla("colaborativo")
        self.assertTrue(
            ruta.endswith("plantilla_protocolo_colaborativo.docx")
            or ruta.endswith("plantilla_protocolo.docx")
        )


if __name__ == "__main__":
    unittest.main()

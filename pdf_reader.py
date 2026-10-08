"""
pdf_reader.py
--------------
Extrae el texto completo de un PDF académico usando pdfplumber.

Se eligió pdfplumber sobre alternativas como PyPDF2 porque:
- Maneja mejor PDFs con columnas, tablas y saltos de línea irregulares.
- Permite extraer texto página por página, lo que facilita el debug
  si un módulo específico da problemas.

Si en el futuro necesitas procesar PDFs escaneados (imágenes, sin texto
seleccionable), esto NO funcionará: necesitarías OCR (ej. pytesseract).
"""

import pdfplumber


def extraer_texto_pdf(ruta_pdf: str, max_paginas: int | None = None) -> str:
    """
    Extrae y concatena el texto de todas las páginas de un PDF.

    Args:
        ruta_pdf: ruta al archivo .pdf en disco.
        max_paginas: límite opcional de páginas a leer (útil para módulos
                     muy largos y controlar el tamaño enviado a la IA).

    Returns:
        Texto completo del PDF como un solo string, con separadores
        simples entre páginas.
    """
    texto_completo = []

    with pdfplumber.open(ruta_pdf) as pdf:
        paginas = pdf.pages
        if max_paginas:
            paginas = paginas[:max_paginas]

        for i, pagina in enumerate(paginas, start=1):
            texto_pagina = pagina.extract_text() or ""
            if texto_pagina.strip():
                texto_completo.append(f"\n--- Página {i} ---\n{texto_pagina}")

    resultado = "\n".join(texto_completo).strip()

    if not resultado:
        raise ValueError(
            "No se pudo extraer texto del PDF. "
            "Es posible que sea un PDF escaneado (imagen) sin texto seleccionable."
        )

    return resultado


def recortar_texto(texto: str, max_caracteres: int = 60000) -> str:
    """
    Limita el tamaño del texto enviado a la API para controlar costos
    y evitar exceder límites de contexto en módulos extremadamente largos.
    Si el texto excede el límite, se recorta y se añade una nota.
    """
    if len(texto) <= max_caracteres:
        return texto

    return (
        texto[:max_caracteres]
        + "\n\n[NOTA: el texto original era más extenso y fue truncado "
        "para el procesamiento. El análisis se basa en esta porción.]"
    )

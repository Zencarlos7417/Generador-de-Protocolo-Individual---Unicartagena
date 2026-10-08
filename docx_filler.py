"""
docx_filler.py
----------------
Rellena la plantilla `plantilla_protocolo.docx` con el contenido generado
por la IA, usando docxtpl (basado en python-docx + Jinja2).

docxtpl reemplaza únicamente el texto dentro de los tags {{ }}, dejando
intacto todo lo demás: encabezado institucional, logos, bordes de tabla,
fuentes y estilos definidos en el .docx original.

IMPORTANTE sobre saltos de línea:
Los campos que pueden tener varias líneas (objetivos, conceptos_clave,
bibliografia) deben escribirse en la plantilla como CAMPOS ENRIQUECIDOS,
usando el prefijo "r" de docxtpl:

    {{r objetivos }}
    {{r conceptos_clave }}
    {{r bibliografia }}

Los campos de párrafo simple (descripcion, palabras_clave, resumen,
metodologia, conclusiones, discusiones) se dejan como texto normal:

    {{ descripcion }}
"""

from docxtpl import DocxTemplate, RichText

# Campos que deben renderizarse como texto enriquecido (multilínea real,
# no como "\n" literal dentro de un solo párrafo).
CAMPOS_MULTILINEA = {"objetivos", "conceptos_clave", "bibliografia"}


def _a_richtext(texto: str) -> RichText:
    """
    Convierte un string con saltos de línea (\n) en un objeto RichText
    de docxtpl, generando saltos de línea reales dentro de la celda de
    Word (no texto plano con \n visible).
    """
    rt = RichText()
    lineas = texto.split("\n")
    for i, linea in enumerate(lineas):
        rt.add(linea.strip())
        if i < len(lineas) - 1:
            rt.add("\n")  # salto de línea real dentro de la misma celda
    return rt


def generar_docx(datos: dict, ruta_plantilla: str, ruta_salida: str) -> str:
    """
    Rellena la plantilla con los datos generados por la IA y guarda
    el .docx final.

    Args:
        datos: dict con las 9 claves (descripcion, palabras_clave, etc.)
        ruta_plantilla: ruta a plantilla_protocolo.docx
        ruta_salida: ruta donde se guardará el documento final

    Returns:
        ruta_salida (para encadenar fácilmente con el envío del archivo)
    """
    doc = DocxTemplate(ruta_plantilla)

    contexto = {}
    for clave, valor in datos.items():
        if clave in CAMPOS_MULTILINEA:
            contexto[clave] = _a_richtext(str(valor))
        else:
            # Reemplaza \n por espacio en campos de párrafo simple,
            # por si la IA los incluyó igualmente.
            contexto[clave] = str(valor).replace("\n", " ").strip()

    doc.render(contexto)
    doc.save(ruta_salida)

    return ruta_salida

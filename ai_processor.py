"""
ai_processor.py
-----------------
Envía el texto extraído del PDF a la API de Gemini (Google) y devuelve
un diccionario Python con las 9 secciones del protocolo individual.

Modelo usado: gemini-2.5-flash
  - Rápido y económico, buen balance para esta tarea de resumen/síntesis
    académica con salida JSON estructurada.
  - Si necesitas más calidad de razonamiento para lecturas muy densas o
    técnicas, puedes cambiar a un modelo Gemini Pro más reciente
    (revisa https://ai.google.dev/gemini-api/docs/models para ver las
    versiones disponibles en el momento en que lo uses).

Requiere la librería oficial "google-genai" (no confundir con la librería
antigua "google-generativeai", que está en proceso de deprecación).
"""

import json
import logging
import os
import time
from google import genai
from google.genai import types
from google.genai import errors as genai_errors

logger = logging.getLogger("protocolo-app")

MODEL = "gemini-2.5-flash"
MAX_REINTENTOS = 3
ESPERA_BASE_SEGUNDOS = 5  # 5s, 10s, 20s entre reintentos


def _build_system_prompt(tipo_protocolo: str = "individual", formato_salida: str = "estandar") -> str:
    tipo = (tipo_protocolo or "individual").strip().lower()
    nombre_tipo = "Colaborativo" if tipo == "colaborativo" else "Individual"
    descripcion_tipo = (
        "un protocolo colaborativo universitario, pensado para trabajo en equipo o análisis conjunto "
        "de una lectura o actividad compartida."
        if tipo == "colaborativo"
        else "un protocolo individual universitario, pensado para la reflexión y el análisis personal de una lectura o actividad."
    )

    estilo_instruccion = (
        "Escribe estrictamente como un estudiante universitario de Quinto Semestre de Ingeniería de Software de la Universidad de Cartagena (Centro Tutorial Magangué). Su vocabulario debe ser técnico pero natural, mostrando el esfuerzo de un alumno que comprende los conceptos (como código, arquitectura, algoritmos, bases de datos o metodologías ágiles), sin sonar robótico ni como una IA corporativa."
        if formato_salida == "estandar"
        else "Organiza los contenidos principales en esquemas jerárquicos estructurados con viñetas claras y lenguaje técnico propio de un estudiante de quinto semestre de ingeniería."
    )

    return """Eres un estudiante universitario de Quinto Semestre de Ingeniería de Software en la Universidad de Cartagena (CTEV Magangué), redactando tu propio protocolo académico de lectura.

Recibirás el texto completo extraído de un PDF (módulo o lectura académica). Tu tarea es analizarlo y redactar el "Protocolo {nombre_tipo}" en español, con un tono universitario genuino, riguroso pero humano (evita lenguaje excesivamente pulido de IA, usa un estilo de redacción propio de un estudiante talentoso de ingeniería).

La salida debe corresponder a {descripcion_tipo}

Debes devolver EXCLUSIVAMENTE un objeto JSON válido, sin texto antes ni después, sin bloques de código markdown (nada de ```), con exactamente estas 9 claves:

{{
  "descripcion": "Breve descripción (3-4 líneas) redactada en primera o tercera persona por el estudiante sobre el texto o actividad analizada: de qué trata, autor/fuente si se identifica, y por qué es clave para la ingeniería de software.",
  "palabras_clave": "Entre 6 y 10 términos técnicos de ingeniería de software separados por comas.",
  "objetivos": "Entre 2 y 4 objetivos del análisis, cada uno en una línea separada por salto de línea (\\n), redactados con verbo en infinitivo.",
  "conceptos_clave": "Lista de 4 a 8 conceptos técnicos clave definidos con criterio de estudiante de 5to semestre, formato 'Concepto: definición', cada uno separado por salto de línea (\\n).",
  "resumen": "Resumen coherente y analítico de 200 a 350 palabras, redactado en prosa natural, conectando la teoría del texto con la práctica de desarrollo de software.",
  "metodologia": "Descripción de 4 a 6 líneas de la metodología de estudio aplicada (lectura crítica, revisión de diagramas, pruebas de concepto, análisis por secciones), redactada en primera persona ('analicé', 'revisé', 'identifiqué').",
  "conclusiones": "2 a 3 párrafos cortos con conclusiones reflexivas desde la perspectiva de un futuro ingeniero de software.",
  "discusiones": "1 a 2 párrafos con discusiones críticas, retos de implementación, preguntas abiertas o aplicabilidad en proyectos reales.",
  "bibliografia": "Referencia(s) en formato APA 7. Si el texto no trae metadatos suficientes, indica exactamente: 'No se identifican datos suficientes en el documento para una referencia APA completa; se recomienda verificar con la fuente original.'"
}}

Reglas estrictas:
- No inventes datos bibliográficos que no estén en el texto.
- No agregues claves adicionales ni comentarios fuera del JSON.
- Usa \\n para separar líneas dentro de un mismo valor de string.

ANTI-IA / HUMANIZACIÓN OBLIGATORIA (aplica a cada sección de prosa):
- PROHIBIDO usar estas muletillas típicas de IA: "es importante destacar", "cabe resaltar",
  "cabe mencionar", "cabe destacar", "cabe señalar", "juega un papel fundamental",
  "desempeña un papel fundamental", "en la actualidad", "en conclusión", "en resumen",
  "en términos generales", "por otro lado", "es fundamental", "es crucial", "es esencial",
  "sin lugar a dudas", "vale la pena", "en este sentido", "a lo largo de",
  "de manera significativa", "panorama general", "de forma integral" o "enfoque holístico".
- Varía la longitud de las oraciones: mezcla frases cortas y directas con otras más
  desarrolladas; evita empezar párrafos seguidos con el mismo conector ("Además",
  "Asimismo", "Por lo tanto").
- Usa voz activa y vocabulario técnico concreto de ingeniería (código, consultas,
  diagramas, pruebas, arquitectura) en lugar de abstracciones genéricas.
- Escribe en primera persona donde aplique ("analicé", "identifiqué", "probé") y con
  criterio propio: dudas razonadas, comparaciones con otras unidades y aplicación práctica.
- El resultado debe leerse como el borrador honesto de un estudiante talentoso de 5to
  semestre, NO como un texto corporativo perfectamente simétrico.""".format(
        tipo=tipo,
        nombre_tipo=nombre_tipo,
        descripcion_tipo=descripcion_tipo,
        estilo_instruccion=estilo_instruccion,
    )

CLAVES_ESPERADAS = [
    "descripcion",
    "palabras_clave",
    "objetivos",
    "conceptos_clave",
    "resumen",
    "metodologia",
    "conclusiones",
    "discusiones",
    "bibliografia",
]


def generar_protocolo(texto_pdf: str, tipo_protocolo: str = "individual", unidad_num: str = "1", formato_salida: str = "estandar") -> dict:
    """
    Llama a la API de Gemini con el texto del PDF y devuelve un dict
    con las 9 claves del protocolo, ya validado.

    Requiere la variable de entorno GEMINI_API_KEY configurada
    (ver .env.example). El cliente la toma automáticamente del entorno.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY no está configurada. "
            "Crea un archivo .env con tu clave de Gemini en https://aistudio.google.com/app/apikey"
        )
    key_info = _verificar_formato_clave(api_key)
    logger.info(f"Usando API Key formato: {key_info['formato']}")
    if key_info["formato"] == "desconocido":
        logger.warning(f"Formato de API Key no reconocido: {key_info['mensaje']}")

    client = genai.Client(api_key=api_key)
    system_prompt = _build_system_prompt(tipo_protocolo, formato_salida)

    respuesta = None
    ultimo_error = None

    for intento in range(1, MAX_REINTENTOS + 1):
        try:
            logger.info(f"Intento {intento}/{MAX_REINTENTOS}: enviando texto a Gemini (Unidad {unidad_num}, modelo={MODEL})")
            respuesta = client.models.generate_content(
                model=MODEL,
                contents=(
                    f"Este es el texto extraído del PDF del módulo/lectura correspondiente a la UNIDAD {unidad_num}. "
                    f"Genera el protocolo {('colaborativo' if tipo_protocolo == 'colaborativo' else 'individual')} enfocado en esta unidad en el formato JSON indicado:\n\n"
                    f"{texto_pdf}"
                ),
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    temperature=0.75,
                ),
            )
            logger.info(f"Intento {intento}: respuesta exitosa de Gemini")
            break

        except genai_errors.ServerError as e:
            ultimo_error = e
            logger.warning(f"Intento {intento}: ServerError ({e}), reintentando...")
            if intento < MAX_REINTENTOS:
                espera = ESPERA_BASE_SEGUNDOS * (2 ** (intento - 1))
                time.sleep(espera)
            continue

        except genai_errors.ClientError as e:
            logger.error(f"Intento {intento}: ClientError no reintentable: {e}")
            raise ValueError(
                f"Error de la API de Gemini (no reintentable): {e}"
            ) from e

    if respuesta is None:
        raise ValueError(
            "Gemini no respondió después de varios intentos. El servicio está "
            f"temporalmente saturado. Detalle del último error: {ultimo_error}\n"
            "Espera un par de minutos y vuelve a intentarlo."
        )

    texto_json = (respuesta.text or "").strip()

    datos = _parsear_json_seguro(texto_json)
    _validar_claves(datos)

    return datos


def _verificar_formato_clave(api_key: str) -> dict:
    if api_key.startswith("AQ."):
        return {"formato": "AQ (Auth Key, nuevo formato)", "clave_valida": True}
    elif api_key.startswith("AIza"):
        return {"formato": "AIza (Standard, formato legacy)", "clave_valida": True}
    else:
        return {"formato": "desconocido", "clave_valida": False}


def _parsear_json_seguro(texto: str) -> dict:
    """
    Limpia posibles restos de markdown (```json ... ```) y parsea el JSON.
    Con response_mime_type="application/json" Gemini casi nunca añade
    estos restos, pero se deja como red de seguridad.
    """
    limpio = texto.strip()
    if limpio.startswith("```"):
        limpio = limpio.strip("`")
        if limpio.lower().startswith("json"):
            limpio = limpio[4:]
        limpio = limpio.strip()

    try:
        return json.loads(limpio)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"La IA no devolvió un JSON válido. Respuesta recibida:\n{texto}"
        ) from e


def _validar_claves(datos: dict) -> None:
    faltantes = [clave for clave in CLAVES_ESPERADAS if clave not in datos]
    if faltantes:
        raise ValueError(
            f"El JSON generado no contiene las siguientes claves requeridas: {faltantes}"
        )
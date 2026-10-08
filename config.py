import os
import sys

import logging

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("protocolo_app.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("protocolo-app")


def validar_api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        logger.error("GEMINI_API_KEY no está configurada. Copiala de https://aistudio.google.com/app/apikey")
        sys.exit("ERROR: Variable de entorno GEMINI_API_KEY no encontrada. Crea un archivo .env con tu clave de Gemini.")
    return key


def validar_formato_clave(key: str) -> dict:
    info = {"clave_valida": False, "formato": "desconocido", "mensaje": ""}
    if key.startswith("AQ."):
        info["formato"] = "AQ (Auth Key, nuevo formato Google, 2026)"
        info["clave_valida"] = True
        info["mensaje"] = "Clave con formato AQ (nuevo formato de Google). Debería funcionar correctamente."
    elif key.startswith("AIza"):
        info["formato"] = "AIza (Standard Key, formato legacy)"
        info["clave_valida"] = True
        info["mensaje"] = "Clave con formato AIza (legacy). Sigue funcionando pero Google la eliminará en septiembre 2026."
    else:
        info["formato"] = "desconocido"
        info["mensaje"] = "Formato de clave no reconocido. Asegúrate de usar una clave de Google AI Studio."
    return info


def validar_variable_entorno() -> dict:
    config = {}
    config["gemini_key"] = os.environ.get("GEMINI_API_KEY", "")
    config["flask_secret"] = os.environ.get("FLASK_SECRET_KEY", "clave-dev-cambiar-en-produccion")
    config["max_content_length"] = 25 * 1024 * 1024
    return config
"""
Lanza el túnel de Cloudflare, detecta su URL pública y la envía
a tu WhatsApp (vía CallMeBot, gratis) para compartirla fácilmente.

Configura en .env:
  WHATSAPP_PHONE=573207545995          (tu número con código país, sin +)
  WHATSAPP_CALLMEBOT_APIKEY=tu-apikey  (la obtienes activando CallMeBot una vez)

Activación única de CallMeBot:
  1. Guarda en tu celular el número +34 644 10 55 84 (bot de CallMeBot).
  2. Envíale por WhatsApp:  I allow callmebot to send me messages
  3. Te responde con tu apikey. Pégala en el .env.

Uso: python publicar_tunel.py   (déjalo abierto: si lo cierras, muere el túnel)
"""

import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CLOUDFLARED = os.environ.get("CLOUDFLARED_PATH", "cloudflared").strip() or "cloudflared"
PHONE = os.environ.get("WHATSAPP_PHONE", "573207545995").strip()
APIKEY = os.environ.get("WHATSAPP_CALLMEBOT_APIKEY", "").strip()

URL_RE = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")


def avisar_whatsapp(url):
    if not APIKEY:
        print("Sin WHATSAPP_CALLMEBOT_APIKEY: no se envía aviso (ver instrucciones arriba).")
        return
    texto = f"SIMA UdeC en línea. Enlace de hoy para compartir: {url}"
    params = urllib.parse.urlencode({"phone": PHONE, "text": texto, "apikey": APIKEY})
    try:
        with urllib.request.urlopen(
            f"https://api.callmebot.com/whatsapp.php?{params}", timeout=30
        ) as r:
            print("Aviso WhatsApp enviado:", r.status)
    except Exception as e:
        print(f"No se pudo avisar por WhatsApp: {e}")


def main():
    print("Iniciando túnel de Cloudflare...")
    try:
        proc = subprocess.Popen(
            [CLOUDFLARED, "tunnel", "--url", "http://localhost:5000"],
            cwd=BASE_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError:
        print("No encontré `cloudflared`. Instala con: winget install Cloudflare.cloudflared")
        sys.exit(1)

    url = None
    assert proc.stdout is not None
    for linea in proc.stdout:
        print(linea, end="")
        if url is None:
            m = URL_RE.search(linea)
            if m:
                url = m.group(0)
                print(f"\n>>> ENLACE PÚBLICO: {url}\n")
                avisar_whatsapp(url)
    proc.wait()


if __name__ == "__main__":
    main()

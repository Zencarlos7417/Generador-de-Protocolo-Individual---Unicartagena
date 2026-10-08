"""
Bot de Telegram para encender la plataforma SIMA UdeC a distancia.

El bot vive en tu PC y escucha TUS mensajes. Cuando le escribes
"prender", arranca el servidor Flask + el túnel de Cloudflare y te
responde con el enlace público para compartir.

Requiere en .env:
  TELEGRAM_BOT_TOKEN=token que te da @BotFather
  TELEGRAM_CHAT_ID=tu id numérico (te lo dice @userinfobot)

Uso:
  python bot_telegram.py   (déjalo corriendo o prográmalo al inicio de Windows)
Comandos (solo desde tu chat autorizado):
  prender  -> inicia servidor + túnel y devuelve el enlace
  estado   -> dice si el servidor y el túnel están activos
  apagar   -> detiene servidor y túnel
  ayuda    -> lista de comandos
"""

import os
import re
import socket
import subprocess
import sys
import time

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_PERMITIDO = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
CLOUDFLARED = os.environ.get("CLOUDFLARED_PATH", "cloudflared").strip() or "cloudflared"

API = f"https://api.telegram.org/bot{TOKEN}" if TOKEN else ""
URL_RE = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")

proc_server = None
proc_tunel = None
url_tunel = None


def _get(url, **params):
    import urllib.request
    import urllib.parse
    import json as _js
    full = url + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(full, timeout=30) as r:
        return _js.loads(r.read().decode("utf-8"))


def _post(url, data):
    import urllib.request
    import json as _js
    req = urllib.request.Request(
        url, data=_js.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return _js.loads(r.read().decode("utf-8"))


def enviar(texto):
    try:
        _post(API + "/sendMessage", {"chat_id": CHAT_PERMITIDO, "text": texto})
    except Exception as e:
        print(f"No se pudo enviar mensaje: {e}")


def puerto_abierto():
    s = socket.socket()
    s.settimeout(2)
    try:
        return s.connect_ex(("127.0.0.1", 5000)) == 0
    finally:
        s.close()


def prender():
    global proc_server, proc_tunel, url_tunel
    msgs = []
    if not puerto_abierto():
        proc_server = subprocess.Popen(
            [sys.executable, os.path.join(BASE_DIR, "app.py")],
            cwd=BASE_DIR,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(30):
            if puerto_abierto():
                break
            time.sleep(1)
        msgs.append("✅ Servidor Flask encendido (puerto 5000)." if puerto_abierto()
                    else "⚠️ El servidor tardó en arrancar; revisa la ventana del PC.")
    else:
        msgs.append("ℹ️ El servidor ya estaba encendido.")

    if proc_tunel is None or proc_tunel.poll() is not None:
        url_tunel = None
        try:
            proc_tunel = subprocess.Popen(
                [CLOUDFLARED, "tunnel", "--url", "http://localhost:5000"],
                cwd=BASE_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError:
            return ("❌ No encontré `cloudflared` en el PC. "
                    "Instálalo con: winget install Cloudflare.cloudflared")
        inicio = time.time()
        while time.time() - inicio < 45:
            linea = proc_tunel.stdout.readline() if proc_tunel.stdout else ""
            if not linea:
                time.sleep(0.5)
                continue
            m = URL_RE.search(linea)
            if m:
                url_tunel = m.group(0)
                break
        if url_tunel:
            msgs.append(f"🌐 Enlace público listo para compartir:\n{url_tunel}")
        else:
            msgs.append("⚠️ Túnel iniciado pero aún no muestra el enlace; míralo en el PC.")
    else:
        msgs.append(f"ℹ️ El túnel ya estaba activo:\n{url_tunel or '(revisa la ventana del PC)'}")
    return "\n\n".join(msgs)


def _matar_por_puerto(puerto=5000):
    """Mata (excepto este proceso) lo que escuche en el puerto dado."""
    import re as _re
    mio = os.getpid()
    try:
        out = subprocess.run(
            ["netstat", "-ano"], capture_output=True, text=True, timeout=10
        ).stdout
    except Exception:
        return False
    mato = False
    for linea in out.splitlines():
        m = _re.search(r"TCP\s+\S+:5000\s+\S+\s+LISTENING\s+(\d+)".replace("5000", str(puerto)), linea)
        if m:
            pid = m.group(1)
            if pid != str(mio):
                try:
                    subprocess.run(["taskkill", "/F", "/PID", pid],
                                   capture_output=True, timeout=10)
                    mato = True
                except Exception:
                    pass
    return mato


def apagar():
    global proc_server, proc_tunel, url_tunel
    for p in (proc_server, proc_tunel):
        try:
            if p is not None and p.poll() is None:
                p.terminate()
        except Exception:
            pass
    # Aunque el servidor lo hayas iniciado manualmente (doble clic),
    # se apaga igual buscando lo que ocupe el puerto 5000.
    _matar_por_puerto(5000)
    try:
        subprocess.run(["taskkill", "/F", "/IM", "cloudflared.exe"],
                       capture_output=True, timeout=10)
    except Exception:
        pass
    proc_server, proc_tunel, url_tunel = None, None, None
    srv_off = not puerto_abierto()
    return ("🛑 Servidor y túnel detenidos."
            if srv_off else "⚠️ El puerto 5000 sigue ocupado; revisa la ventana del PC.")


def estado():
    srv = "encendido ✅" if puerto_abierto() else "apagado ❌"
    tun = "activo ✅" if (proc_tunel is not None and proc_tunel.poll() is None) else "inactivo ❌"
    extra = f"\nEnlace: {url_tunel}" if url_tunel else ""
    return f"📊 Estado\nServidor: {srv}\nTúnel: {tun}{extra}"


def main():
    if not TOKEN or not CHAT_PERMITIDO:
        print("Falta TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID en .env")
        sys.exit(1)
    print("Bot SIMA UdeC escuchando en Telegram...")
    offset = 0
    while True:
        try:
            data = _get(API + "/getUpdates", offset=offset, timeout=25)
            for upd in data.get("result", []):
                offset = upd["update_id"] + 1
                msg = upd.get("message", {})
                chat_id = str(msg.get("chat", {}).get("id", ""))
                texto = (msg.get("text") or "").strip().lower()
                if chat_id != CHAT_PERMITIDO or not texto:
                    continue
                if texto in ("prender", "prender server", "/prender", "iniciar"):
                    enviar("⏳ Encendiendo la plataforma...")
                    enviar(prender())
                elif texto in ("estado", "/estado"):
                    enviar(estado())
                elif texto in ("apagar", "/apagar"):
                    enviar(apagar())
                else:
                    enviar("Comandos: prender • estado • apagar")
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Reintentando... ({e})")
            time.sleep(5)


if __name__ == "__main__":
    main()

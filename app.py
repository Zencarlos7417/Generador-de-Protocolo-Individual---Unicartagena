"""
app.py
--------
Aplicación web mínima (Flask) para automatizar el llenado de Protocolos
Individuales a partir de un PDF de módulo/lectura.

Flujo:
  1. El usuario sube un PDF desde el formulario web (/).
  2. Se extrae el texto del PDF (pdf_reader.py).
  3. Se envía el texto a Gemini, que devuelve un JSON con las 9 secciones
     (ai_processor.py).
  4. Se inyecta ese JSON en plantilla_protocolo.docx sin alterar el
     diseño (docx_filler.py).
  5. Se descarga automáticamente el .docx final.

Ejecutar:
    pip install -r requirements.txt
    cp .env.example .env   # y pega tu GEMINI_API_KEY real
    python app.py
    # abrir http://localhost:5000
"""

import logging
import os
import uuid

from dotenv import load_dotenv
from flask import Flask, render_template, request, send_file, flash, redirect, url_for, session, jsonify

from config import validar_api_key, validar_formato_clave, logger
from pdf_reader import extraer_texto_pdf, recortar_texto
from ai_processor import generar_protocolo
from docx_filler import generar_docx

try:
    from supabase_client import (
        get_supabase, supabase_configurado, guardar_protocolo,
        guardar_nota_quiz, obtener_historial, obtener_notas,
        guardar_perfil, obtener_perfil,
    )
except Exception:  # Supabase es opcional; la app funciona en modo local
    get_supabase = lambda: None
    supabase_configurado = lambda: False
    guardar_protocolo = lambda *a, **k: {"ok": False, "motivo": "supabase-no-disponible"}
    guardar_nota_quiz = lambda *a, **k: {"ok": False, "motivo": "supabase-no-disponible"}
    guardar_perfil = lambda *a, **k: {"ok": False, "motivo": "supabase-no-disponible"}
    obtener_perfil = lambda *a, **k: {}
    obtener_historial = lambda *a, **k: []
    obtener_notas = lambda *a, **k: []

load_dotenv()


def _usuario_actual() -> str:
    return session.get("usuario") or "invitado"


# Solo el admin puede crear materias y subir módulos. El resto son estudiantes.
ADMIN_USERS = set(
    u.strip().lower()
    for u in os.environ.get("ADMIN_USERS", "1052959016").split(",")
    if u.strip()
)


def _es_admin(usuario: str | None = None) -> bool:
    usuario = (usuario or _usuario_actual()).strip().lower()
    return usuario in ADMIN_USERS or session.get("rol") == "admin"


def _rol_para(usuario: str) -> str:
    return "admin" if usuario.strip().lower() in ADMIN_USERS else "estudiante"


def _slug_curso(course_name: str) -> str:
    import re
    import unicodedata
    c_low = (course_name or "").lower()
    if "ciencia" in c_low:
        return "ciencia_de_datos"
    if "app" in c_low:
        return "desarrollo_de_apps"
    if "matemática" in c_low or "matematica" in c_low:
        return "matematicas_discretas"
    if "metodología" in c_low or "metodologia" in c_low or "investigación" in c_low or "investigacion" in c_low:
        return "metodologia_investigacion"
    if "probabilidad" in c_low:
        return "probabilidad_y_estadistica"
    if "sistemas" in c_low:
        return "sistemas_digitales"
    if "autómata" in c_low or "automata" in c_low:
        return "automatas"
    base = unicodedata.normalize("NFKD", c_low)
    base = "".join(c for c in base if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "_", base).strip("_") or "general"


def _ruta_modulo(slug_curso: str, unidad: str) -> str | None:
    """Localiza el PDF del módulo aunque el nombre varíe
    (ej. probabilidad_y_estadistica vs probabilidad_y_estadisticas)."""
    import re as _re
    import unicodedata as _ud
    d = os.path.join(BASE_DIR, "modulos")
    if not os.path.isdir(d):
        return None

    def norm(s: str) -> str:
        s = _ud.normalize("NFKD", s.lower())
        return "".join(c for c in s if not _ud.combining(c))

    # 1) Nombre exacto esperado (caso rápido)
    for cand in (f"{slug_curso}_u{unidad}.pdf", f"{slug_curso}.pdf"):
        p = os.path.join(d, cand)
        if os.path.exists(p):
            return p
    # 2) Búsqueda flexible: palabra clave del curso + marcador de unidad
    token = (slug_curso or "").split("_")[0]
    try:
        archivos = [f for f in os.listdir(d) if f.lower().endswith(".pdf")]
    except Exception:
        return None
    for f in archivos:
        nf = norm(f)
        if token and token in nf and _re.search(r"_u" + _re.escape(str(unidad)) + r"(?:\.|_)", nf):
            return os.path.join(d, f)
    # 3) Último recurso: cualquier PDF del curso
    for f in archivos:
        if token and token in norm(f):
            return os.path.join(d, f)
    return None


CURSOS_BASE = [
    {"clave": "CIENCIA DE DATOS I", "titulo": "INGENIERÍA DE SOFTWARE - MAGANGUÉ - CIENCIA DE DATOS I - G1 - 2026 - 2", "docente": "JOSE LUIS TRESPALACIO MULET", "img": "img/course_ciencia_datos.jpg", "actividades": "35 de 35 actividades completadas", "porcentaje": 100},
    {"clave": "DESARROLLO DE APPS", "titulo": "INGENIERÍA DE SOFTWARE - MAGANGUÉ - DESARROLLO DE APPS - G1 - 2026 - 2", "docente": "ELKIN J NAVARRO OSORIO", "img": "img/course_desarrollo_apps.jpg", "actividades": "35 de 35 actividades completadas", "porcentaje": 100},
    {"clave": "MATEMÁTICAS DISCRETAS", "titulo": "INGENIERÍA DE SOFTWARE - MAGANGUÉ - MATEMÁTICAS DISCRETAS - G1 - 2026 - 2", "docente": "ALEXANDER BENAVIDES ACUNA", "img": "img/course_matematicas_discretas.jpg", "actividades": "35 de 35 actividades completadas", "porcentaje": 100},
    {"clave": "METODOLOGÍA DE LA INVESTIGACIÓN", "titulo": "INGENIERÍA DE SOFTWARE - MAGANGUÉ - METODOLOGÍA DE LA INVESTIGACIÓN - G1 - 2026 - 2", "docente": "BIVIAN ROBLES ACOSTA", "img": "img/course_metodologia_investigacion.jpg", "actividades": "35 de 35 actividades completadas", "porcentaje": 100},
    {"clave": "PROBABILIDAD Y ESTADÍSTICA", "titulo": "INGENIERÍA DE SOFTWARE - MAGANGUÉ - PROBABILIDAD Y ESTADÍSTICA - G1 - 2026 - 2", "docente": "EVELIN BARCO LLERENA", "img": "img/course_probabilidad.jpg", "actividades": "35 de 35 actividades completadas", "porcentaje": 100},
    {"clave": "SISTEMAS DIGITALES", "titulo": "INGENIERÍA DE SOFTWARE - MAGANGUÉ - SISTEMAS DIGITALES - G1 - 2026 - 2", "docente": "RANFIS ENRIQUE IBARRA DAVILA", "img": "img/course_sistemas_digitales.jpg", "actividades": "35 de 35 actividades completadas", "porcentaje": 100},
    {"clave": "TEORÍAS DE AUTÓMATAS Y LENGUAJES", "titulo": "INGENIERÍA DE SOFTWARE - MAGANGUÉ - TEORÍAS DE AUTÓMATAS Y LENGUAJES - G1 - 2026 - 2", "docente": "JOSE ALDEMAR PEREZ OLIVARES", "img": "img/course_automatas.jpg", "actividades": "35 de 35 actividades completadas", "porcentaje": 100},
]


def _cursos_dashboard() -> tuple[list, dict]:
    """Cursos base + materias creadas por el admin (Supabase)."""
    cursos = [dict(c) for c in CURSOS_BASE]
    unidades_extra: dict = {}
    if supabase_configurado():
        try:
            from supabase_client import listar_materias, listar_unidades
            for m in listar_materias():
                nombre = (m.get("nombre") or "").strip()
                if not nombre:
                    continue
                if any(c["clave"].upper() == nombre.upper() for c in cursos):
                    continue
                cursos.append({
                    "clave": nombre.upper(),
                    "titulo": f"INGENIERÍA DE SOFTWARE - {m.get('centro', 'MAGANGUÉ')} - {nombre} - G1 - 2026 - 2",
                    "docente": m.get("docente", ""),
                    "img": m.get("thumbnail") or "img/course_ciencia_datos.jpg",
                    "actividades": "35 de 35 actividades completadas",
                    "porcentaje": 100,
                    "nueva": True,
                })
            for u in listar_unidades():
                mat = u.get("materias") or {}
                nombre = (mat.get("nombre") or "").strip().upper()
                if not nombre:
                    continue
                unidades_extra.setdefault(nombre, {})[str(u.get("numero"))] = (
                    f"Unidad {u.get('numero')} - {u.get('nombre', '')}"
                )
        except Exception as e:
            logger.warning(f"No se pudieron cargar materias dinámicas: {e}")
    return cursos, unidades_extra

api_key = validar_api_key()
key_info = validar_formato_clave(api_key)
logger.info(f"Iniciando aplicación. Formato de API Key: {key_info['formato']}")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CARPETA_TEMPORAL = os.path.join(BASE_DIR, "tmp")

TIPOS_PLANTILLA = {
    "individual": {
        "archivo": "plantilla_protocolo.docx",
        "nombre": "Protocolo Individual",
    },
    "colaborativo": {
        "archivo": "plantilla_protocolo_colaborativo.docx",
        "nombre": "Protocolo Colaborativo",
    },
}


def resolver_ruta_plantilla(tipo_plantilla: str | None) -> str:
    clave = (tipo_plantilla or "individual").strip().lower()
    config = TIPOS_PLANTILLA.get(clave, TIPOS_PLANTILLA["individual"])
    ruta = os.path.join(BASE_DIR, config["archivo"])

    if os.path.exists(ruta):
        return ruta

    if clave == "colaborativo":
        ruta_fallback = os.path.join(BASE_DIR, TIPOS_PLANTILLA["individual"]["archivo"])
        if os.path.exists(ruta_fallback):
            return ruta_fallback

    raise FileNotFoundError(
        f"No se encontró la plantilla '{config['archivo']}' en la raíz del proyecto. "
        "Colócala junto a app.py antes de continuar."
    )


os.makedirs(CARPETA_TEMPORAL, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "clave-dev-cambiar-en-produccion")
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # 25 MB máx por PDF


def _validar_pdf_archivo(archivo) -> str | None:
    errores = []
    if not archivo or archivo.filename == "":
        return "No se seleccionó ningún archivo."
    if not archivo.filename.lower().endswith(".pdf"):
        errores.append("El archivo debe tener extensión .pdf.")
    if archivo.content_length and archivo.content_length > 25 * 1024 * 1024:
        errores.append("El archivo excede el tamaño máximo de 25 MB.")
    try:
        import pdfplumber
        archivo.seek(0)
        with pdfplumber.open(archivo) as pdf:
            if len(pdf.pages) == 0:
                errores.append("El PDF no tiene páginas.")
        archivo.seek(0)
    except Exception:
        errores.append("El archivo no es un PDF válido o está corrupto.")
    if errores:
        return " ".join(errores)
    return None


@app.route("/", methods=["GET"])
@app.route("/landing", methods=["GET"])
def index():
    return render_template("landing.html")


# Base de datos de usuarios autorizados (cédula / usuario y contraseña)
USUARIOS_AUTORIZADOS = {
    "1052959016": "carlos2026",
    "123456789": "unicartagena",
    "estudiante": "sima2026"
}

def _email_para_usuario(username: str) -> str:
    """Supabase Auth exige email: mapeamos 'usuario' -> 'usuario@sima.udec.local'."""
    username = username.strip().lower()
    if "@" in username:
        return username
    return f"{username}@sima.udec.local"


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        # 1) Intentar Auth real con Supabase (nombre de usuario o correo)
        sb = get_supabase()
        if sb is not None and username and password:
            try:
                sb.auth.sign_in_with_password(
                    {"email": _email_para_usuario(username), "password": password}
                )
                session["usuario"] = username
                session["auth"] = "supabase"
                session["rol"] = _rol_para(username)
                logger.info(f"Acceso Supabase para: {username}")
                return redirect(url_for("dashboard"))
            except Exception as e:
                logger.warning(f"Login Supabase falló para {username}: {e}")
                # Sigue al modo local como respaldo

        # 2) Modo local: usuarios autorizados fijos
        if username in USUARIOS_AUTORIZADOS and USUARIOS_AUTORIZADOS[username] == password:
            session["usuario"] = username
            session["auth"] = "local"
            session["rol"] = _rol_para(username)
            logger.info(f"Acceso autorizado para usuario SIMA: {username}")
            return redirect(url_for("dashboard"))
        else:
            flash("Credenciales incorrectas o usuario no autorizado en SIMA.")
            return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/registro", methods=["GET", "POST"])
def registro():
    """Registro con nombre de usuario + contraseña, guardado en Supabase Auth."""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        if len(username) < 4 or len(password) < 6:
            flash("El usuario debe tener mínimo 4 caracteres y la contraseña mínimo 6.")
            return redirect(url_for("registro"))
        sb = get_supabase()
        if sb is None:
            flash("Registro en la nube no disponible: configura SUPABASE_URL y SUPABASE_KEY en .env")
            return redirect(url_for("registro"))
        try:
            sb.auth.sign_up({
                "email": _email_para_usuario(username),
                "password": password,
                "options": {"data": {"username": username}},
            })
            flash(f"Cuenta '{username}' creada. Ya puedes iniciar sesión con tu nombre de usuario y contraseña.")
            return redirect(url_for("login"))
        except Exception as e:
            flash(f"No se pudo crear la cuenta: {e}")
            return redirect(url_for("registro"))
    return render_template("registro.html")


@app.route("/logout", methods=["GET"])
def logout():
    sb = get_supabase()
    if sb is not None:
        try:
            sb.auth.sign_out()
        except Exception:
            pass
    session.clear()
    return redirect(url_for("index"))


@app.route("/dashboard", methods=["GET"])
@app.route("/area-personal", methods=["GET"])
def dashboard():
    usuario = _usuario_actual()
    historial = obtener_historial(usuario) if supabase_configurado() else []
    notas = obtener_notas(usuario) if supabase_configurado() else []
    cursos, unidades_extra = _cursos_dashboard()
    perfil = obtener_perfil(usuario) if supabase_configurado() else {}
    return render_template(
        "dashboard.html",
        usuario=usuario,
        rol="admin" if _es_admin() else "estudiante",
        perfil=perfil,
        historial=historial,
        notas=notas,
        supabase_ok=supabase_configurado(),
        cursos=cursos,
        cursos_nuevos=[c for c in cursos if c.get("nueva")],
        unidades_extra=unidades_extra,
    )


def _requerir_admin():
    if not _es_admin():
        flash("Solo el administrador puede gestionar materias y módulos.")
        return False
    if not supabase_configurado():
        flash("Configura SUPABASE_URL y SUPABASE_KEY para gestionar materias en la nube.")
        return False
    return True


@app.route("/admin/materias", methods=["GET", "POST"])
def admin_materias():
    if not _requerir_admin():
        return redirect(url_for("dashboard"))
    from supabase_client import (
        listar_materias, crear_materia, registrar_unidad,
        eliminar_materia, eliminar_unidad,
    )
    if request.method == "POST":
        accion = request.form.get("accion", "crear").strip()

        if accion == "eliminar_materia":
            slug = request.form.get("slug", "").strip()
            res = eliminar_materia(slug)
            try:
                import glob as _glob
                for p in _glob.glob(os.path.join(BASE_DIR, "modulos", f"{slug}_u*.pdf")):
                    os.remove(p)
            except Exception:
                pass
            flash("Materia eliminada." if res.get("ok") else f"No se pudo eliminar: {res.get('motivo')}")
            return redirect(url_for("admin_materias"))

        if accion == "eliminar_unidad":
            slug = request.form.get("slug", "").strip()
            numero = request.form.get("numero", "").strip()
            res = eliminar_unidad(slug, numero)
            try:
                p = os.path.join(BASE_DIR, "modulos", f"{slug}_u{numero}.pdf")
                if os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass
            flash("Unidad eliminada." if res.get("ok") else f"No se pudo eliminar: {res.get('motivo')}")
            return redirect(url_for("admin_materias"))

        if accion == "agregar_unidad":
            slug = request.form.get("slug", "").strip()
            unidad_num = request.form.get("unidad_num", "1").strip()
            unidad_nombre = request.form.get("unidad_nombre", "").strip()
            archivo = request.files.get("pdf")
            if not slug or not unidad_nombre or not archivo or archivo.filename == "":
                flash("Elige la materia, escribe el nombre de la unidad y arrastra su PDF.")
                return redirect(url_for("admin_materias"))
            if not archivo.filename.lower().endswith(".pdf"):
                flash("El módulo debe ser un archivo PDF.")
                return redirect(url_for("admin_materias"))
            contenido = archivo.read()
            res_uni = registrar_unidad(slug, unidad_num, unidad_nombre, contenido)
            if not res_uni.get("ok"):
                flash(f"No se pudo agregar la unidad: {res_uni.get('motivo')}")
                return redirect(url_for("admin_materias"))
            try:
                with open(os.path.join(BASE_DIR, "modulos", f"{slug}_u{unidad_num}.pdf"), "wb") as f:
                    f.write(contenido)
            except Exception:
                pass
            flash(f"Unidad {unidad_num} agregada a la materia. Ya genera protocolos con ella.")
            return redirect(url_for("admin_materias"))

        # accion == "crear": nueva materia + su primera unidad
        nombre = request.form.get("nombre", "").strip()
        semestre = request.form.get("semestre", "SEMESTRE V").strip()
        centro = request.form.get("centro", "MAGANGUÉ").strip()
        docente = request.form.get("docente", "").strip()
        unidad_num = request.form.get("unidad_num", "1").strip()
        unidad_nombre = request.form.get("unidad_nombre", "").strip()
        archivo = request.files.get("pdf")
        if not nombre or not unidad_nombre or not archivo or archivo.filename == "":
            flash("Completa nombre de materia, nombre de unidad y arrastra el PDF del módulo.")
            return redirect(url_for("admin_materias"))
        if not archivo.filename.lower().endswith(".pdf"):
            flash("El módulo debe ser un archivo PDF.")
            return redirect(url_for("admin_materias"))
        res_mat = crear_materia(nombre, semestre, centro, docente, _usuario_actual())
        if not res_mat.get("ok"):
            flash(f"No se pudo crear la materia: {res_mat.get('motivo')}")
            return redirect(url_for("admin_materias"))
        contenido = archivo.read()
        res_uni = registrar_unidad(res_mat["slug"], unidad_num, unidad_nombre, contenido)
        if not res_uni.get("ok"):
            flash(f"Materia creada, pero falló la unidad: {res_uni.get('motivo')}")
            return redirect(url_for("admin_materias"))
        # Copia local de respaldo para modo sin nube
        try:
            with open(os.path.join(BASE_DIR, "modulos", f"{res_mat['slug']}_u{unidad_num}.pdf"), "wb") as f:
                f.write(contenido)
        except Exception:
            pass
        flash(f"Materia '{nombre}' + Unidad {unidad_num} publicadas. Ya aparece como tarjeta en el dashboard.")
        return redirect(url_for("admin_materias"))
    return render_template("admin_materias.html", materias=listar_materias(), usuario=_usuario_actual())


@app.route("/perfil", methods=["GET", "POST"])
def perfil():
    usuario = _usuario_actual()
    if request.method == "POST":
        nombre = request.form.get("nombre_mostrado", "").strip()[:60]
        avatar = request.form.get("avatar", "🎓").strip()[:8]
        if not nombre:
            nombre = usuario
        res = guardar_perfil(usuario, nombre, avatar)
        if res.get("ok"):
            session["avatar"] = avatar
            session["nombre_mostrado"] = nombre
            flash("Perfil actualizado.")
        else:
            flash(f"No se pudo guardar (nube no disponible): {res.get('motivo')}")
        return redirect(url_for("perfil"))
    perfil = obtener_perfil(usuario) if supabase_configurado() else {}
    return render_template("perfil.html", usuario=usuario, perfil=perfil,
                           supabase_ok=supabase_configurado())


@app.route("/historial", methods=["GET"])
def historial():
    usuario = _usuario_actual()
    return render_template(
        "historial.html",
        usuario=usuario,
        historial=obtener_historial(usuario),
        notas=obtener_notas(usuario),
        supabase_ok=supabase_configurado(),
    )


@app.route("/api/supabase-status", methods=["GET"])
def supabase_status():
    return jsonify({"supabase_ok": supabase_configurado()})


@app.errorhandler(413)
def archivo_muy_grande(e):
    flash("El archivo excede el tamaño máximo permitido (25 MB). Comprímelo o usa un módulo más liviano.")
    logger.warning(f"413 archivo muy grande. Referer: {request.referrer}")
    return redirect(url_for("dashboard"))


@app.route("/simple", methods=["GET"])
@app.route("/generador-directo", methods=["GET"])
def generador_directo():
    return render_template("index.html")


@app.route("/api/key-status", methods=["GET"])
def key_status():
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return {"status": "missing", "formato": ""}, 200
    if api_key.startswith("AQ."):
        return {"status": "ok", "formato": "AQ (Auth Key, nuevo formato Google)"}, 200
    elif api_key.startswith("AIza"):
        return {"status": "ok", "formato": "AIza (Standard, formato legacy)"}, 200
    else:
        return {"status": "warn", "formato": "desconocido"}, 200


@app.route("/generar", methods=["POST"])
def generar():
    archivo = request.files.get("pdf")
    tipo_plantilla = request.form.get("tipo_plantilla", "individual")
    course_name = request.form.get("course_name", "").strip()
    unidad_num = request.form.get("unidad_num", "1").strip()
    formato_salida = request.form.get("formato_salida", "estandar").strip()

    # El generador vive en el dashboard: los errores siempre vuelven ahí,
    # nunca al inicio, para no perder el contexto del usuario remoto.
    redirect_target = "dashboard"
    if request.referrer and ("generador-directo" in request.referrer or "/simple" in request.referrer):
        redirect_target = "generador_directo"

    id_trabajo = uuid.uuid4().hex
    ruta_pdf_temp = os.path.join(CARPETA_TEMPORAL, f"{id_trabajo}.pdf")
    ruta_docx_salida = os.path.join(CARPETA_TEMPORAL, f"protocolo_{id_trabajo}.docx")

    try:
        # Si el usuario subió un archivo válido, usarlo. Si no (o si viene vacío), buscar en la carpeta 'modulos/'
        if archivo and (archivo.filename or "").strip() != "":
            error_val = _validar_pdf_archivo(archivo)
            if error_val:
                flash(f"Archivo inválido: {error_val}")
                return redirect(url_for(redirect_target))
            archivo.save(ruta_pdf_temp)
            nombre_origen = archivo.filename
            # Guardar copia del PDF subido por el estudiante en la nube (bucket `subidos/`)
            try:
                if supabase_configurado():
                    sb_up = get_supabase()
                    with open(ruta_pdf_temp, "rb") as f:
                        sb_up.storage.from_("subidos").upload(
                            f"{_usuario_actual()}/{id_trabajo}_{nombre_origen}",
                            f.read(),
                            {"content-type": "application/pdf", "upsert": "true"},
                        )
            except Exception as e:
                logger.warning(f"No se pudo archivar el PDF subido en Supabase: {e}")
        else:
            # Buscar módulo precargado: carpeta local y luego nube (Supabase Storage)
            slug_curso = _slug_curso(course_name)

            ruta_precargada = _ruta_modulo(slug_curso, unidad_num)

            if not ruta_precargada and supabase_configurado():
                try:
                    from supabase_client import descargar_modulo
                    for candidato in (f"{slug_curso}_u{unidad_num}.pdf", f"{slug_curso}.pdf"):
                        datos = descargar_modulo(candidato)
                        if datos:
                            with open(ruta_pdf_temp, "wb") as f:
                                f.write(datos)
                            nombre_origen = candidato
                            logger.info(f"Usando módulo desde Supabase Storage: {candidato}")
                            ruta_precargada = ruta_pdf_temp
                            break
                except Exception as e:
                    logger.warning(f"No se pudo descargar módulo de Supabase: {e}")

            if ruta_precargada and os.path.exists(ruta_precargada):
                if ruta_precargada != ruta_pdf_temp:
                    import shutil
                    shutil.copy(ruta_precargada, ruta_pdf_temp)
                nombre_origen = os.path.basename(ruta_precargada)
                logger.info(f"Usando módulo precargado: {ruta_precargada}")
            else:
                if (course_name or "").strip().upper() == "LIBRE":
                    flash("Para una lectura libre debes subir el PDF del módulo o lectura en el formulario.")
                else:
                    flash("Debes subir un archivo PDF o colocar el módulo correspondiente en la carpeta 'modulos/'.")
                return redirect(url_for(redirect_target))

        try:
            ruta_plantilla = resolver_ruta_plantilla(tipo_plantilla)
        except FileNotFoundError as e:
            flash(str(e))
            return redirect(url_for(redirect_target))

        texto_pdf = extraer_texto_pdf(ruta_pdf_temp)
        texto_pdf = recortar_texto(texto_pdf, max_caracteres=60000)
        logger.info(f"Texto extraído (Unidad {unidad_num}): {len(texto_pdf)} caracteres")

        datos_protocolo = generar_protocolo(texto_pdf, tipo_plantilla, unidad_num, formato_salida)
        logger.info("Protocolo generado exitosamente por Gemini")

        generar_docx(datos_protocolo, ruta_plantilla, ruta_docx_salida)
        logger.info(f"Documento Word generado: {ruta_docx_salida}")

        etiqueta = TIPOS_PLANTILLA.get((tipo_plantilla or "individual").strip().lower(), TIPOS_PLANTILLA["individual"])["nombre"]
        prefijo_curso = f"{course_name.split('-')[0].strip()}_" if course_name else ""
        nombre_base = nombre_origen.rsplit('.', 1)[0].replace(" ", "_")
        nombre_descarga = f"{etiqueta.replace(' ', '_')}_Unidad_{unidad_num}_{prefijo_curso}{nombre_base}.docx"

        # Guardar en Supabase (historial + Storage). No bloquea la descarga.
        try:
            if supabase_configurado():
                res_sb = guardar_protocolo(
                    _usuario_actual(), course_name, unidad_num,
                    (tipo_plantilla or "individual").strip().lower(),
                    nombre_descarga, ruta_docx_salida,
                )
                if not res_sb.get("ok"):
                    logger.warning(f"Supabase historial no guardado: {res_sb}")
        except Exception as e:
            logger.warning(f"Error guardando historial en Supabase: {e}")

        return send_file(
            ruta_docx_salida,
            as_attachment=True,
            download_name=nombre_descarga,
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

    except ValueError as e:
        msg = str(e)
        if "AUTH" in msg.upper() or "401" in msg or "CREDENTIAL" in msg.upper():
            flash(f"Error de autenticación: {msg}. Verifica tu GEMINI_API_KEY en https://aistudio.google.com/app/apikey")
        else:
            flash(f"Error procesando el documento: {msg}")
        logger.error(f"Error procesando documento: {e}")
        return redirect(url_for(redirect_target))

    except Exception as e:
        flash(f"Error inesperado: {e}")
        logger.error(f"Error inesperado: {e}", exc_info=True)
        return redirect(url_for(redirect_target))

    finally:
        if os.path.exists(ruta_pdf_temp):
            os.remove(ruta_pdf_temp)


@app.route("/diapositivas", methods=["GET", "POST"])
def diapositivas():
    slides_html = None
    sel_course = None
    sel_unidad = None

    if request.method == "POST":
        sel_course = request.form.get("course_name", "CIENCIA DE DATOS I")
        sel_unidad = request.form.get("unidad_seleccion", "1")

        # Determinar el slug del curso
        slug_curso = "ciencia_de_datos"
        c_low = sel_course.lower()
        if "desarrollo" in c_low or "app" in c_low: slug_curso = "desarrollo_de_apps"
        elif "matemática" in c_low or "matematica" in c_low: slug_curso = "matematicas_discretas"
        elif "metodología" in c_low or "metodologia" in c_low or "investigación" in c_low: slug_curso = "metodologia_investigacion"
        elif "probabilidad" in c_low: slug_curso = "probabilidad_y_estadistica"
        elif "sistemas" in c_low: slug_curso = "sistemas_digitales"
        elif "autómata" in c_low or "automata" in c_low: slug_curso = "automatas"

        texto_acumulado = ""
        unidades_a_leer = [sel_unidad] if sel_unidad != "todas" else ["1", "2", "3", "4"]

        for u in unidades_a_leer:
            ruta_pdf = _ruta_modulo(slug_curso, u)

            if ruta_pdf:
                try:
                    texto_acumulado += f"\n\n--- UNIDAD {u} ---\n" + extraer_texto_pdf(ruta_pdf)
                except Exception:
                    pass

        if not texto_acumulado.strip():
            flash("No se encontraron los PDFs precargados en la carpeta 'modulos/' para esta selección.")
            return render_template("diapositivas.html", slides_html=None)

        texto_acumulado = recortar_texto(texto_acumulado, max_caracteres=50000)

        try:
            slides_html = ""
            ultimo_err_slides = None

            prompt_slides = f"""Eres un experto diseñador instruccional universitario. A partir del siguiente texto de la asignatura '{sel_course}' (Alcance: {sel_unidad}), genera una estructura detallada para una presentación de diapositivas en formato HTML limpio.
Crea entre 5 y 8 diapositivas. Para cada diapositiva devuelve un bloque con título claro y de 3 a 5 viñetas (bullet points) resumidas.
Usa exactamente este formato HTML por cada diapositiva:
<div class="slide-item">
  <h4>Diapositiva X: [Título]</h4>
  <ul>
    <li>Punto clave 1</li>
    <li>Punto clave 2</li>
    <li>Punto clave 3</li>
  </ul>
</div>
Texto base de estudio:
{texto_acumulado}"""
            
            # Intento 1: OpenRouter (DeepSeek / Llama 3) si está configurado
            openrouter_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
            if openrouter_key:
                try:
                    import urllib.request
                    import json as js
                    req_data = js.dumps({
                        "model": "deepseek/deepseek-chat",
                        "messages": [{"role": "user", "content": prompt_slides}],
                        "temperature": 0.5
                    }).encode('utf-8')
                    req = urllib.request.Request(
                        "https://openrouter.ai/api/v1/chat/completions",
                        data=req_data,
                        headers={
                            "Authorization": f"Bearer {openrouter_key}",
                            "Content-Type": "application/json",
                            "HTTP-Referer": "http://localhost:5000",
                            "X-Title": "SIMA UdeC Slides"
                        }
                    )
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        res_json = js.loads(resp.read().decode('utf-8'))
                        slides_html = res_json['choices'][0]['message']['content'].strip()
                except Exception as ex:
                    ultimo_err_slides = ex
                    logger.warning(f"OpenRouter falló en diapositivas: {ex}. Probando Gemini...")

            # Intento 2 y 3: Gemini con respaldo automático
            if not slides_html:
                for modelo_gemini in ["gemini-2.5-flash", "gemini-3.5-flash-lite"]:
                    try:
                        from google import genai
                        client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
                        resp = client.models.generate_content(model=modelo_gemini, contents=prompt_slides)
                        if resp and resp.text:
                            slides_html = resp.text.strip()
                            break
                    except Exception as ex2:
                        ultimo_err_slides = ex2
                        logger.warning(f"Gemini {modelo_gemini} falló en diapositivas: {ex2}")
                        continue

            if not slides_html:
                raise Exception(f"Todos los proveedores de IA fallaron por alta demanda (503). Detalle: {ultimo_err_slides}")

            # Limpiar posibles bloques de markdown ```html ... ``` si los devuelve Gemini u OpenRouter
            if slides_html.startswith("```"):
                slides_html = slides_html.strip("`")
                if slides_html.lower().startswith("html"):
                    slides_html = slides_html[4:]
                slides_html = slides_html.strip()
        except Exception as e:
            flash(f"Error generando diapositivas con IA: {e}")

    pptx_filename = None
    if slides_html:
        try:
            from pptx import Presentation
            from bs4 import BeautifulSoup
            
            prs = Presentation()
            slide_layout = prs.slide_layouts[1] # title and content
            
            # Slide de título principal
            title_slide_layout = prs.slide_layouts[0]
            slide_title = prs.slides.add_slide(title_slide_layout)
            slide_title.shapes.title.text = f"Presentación: {sel_course}"
            slide_title.placeholders[1].text = f"Universidad de Cartagena - CTEV\nAlcance: Unidad {sel_unidad}"

            soup = BeautifulSoup(slides_html, 'html.parser')
            slide_divs = soup.find_all('div', class_='slide-item')
            
            for s_div in slide_divs:
                h4 = s_div.find('h4')
                title_text = h4.get_text(strip=True) if h4 else "Diapositiva"
                
                slide = prs.slides.add_slide(slide_layout)
                title_shape = slide.shapes.title
                if title_shape:
                    title_shape.text = title_text
                    
                body_shape = slide.placeholders[1]
                tf = body_shape.text_frame
                tf.text = "" # limpiar texto por defecto
                
                uls = s_div.find_all('ul')
                for ul in uls:
                    lis = ul.find_all('li')
                    for li in lis:
                        p = tf.add_paragraph()
                        p.text = li.get_text(strip=True)
                        p.level = 0
            
            pptx_filename = f"presentacion_{uuid.uuid4().hex}.pptx"
            ruta_pptx = os.path.join(CARPETA_TEMPORAL, pptx_filename)
            prs.save(ruta_pptx)
            logger.info(f"Presentación PowerPoint generada: {ruta_pptx}")
        except Exception as err:
            logger.error(f"Error generando archivo pptx: {err}")

    return render_template("diapositivas.html", slides_html=slides_html, sel_course=sel_course, sel_unidad=sel_unidad, pptx_filename=pptx_filename)


@app.route("/api/descargar-pptx", methods=["GET"])
def descargar_pptx():
    filename = request.args.get("file", "").strip()
    if not filename or ".." in filename or "/" in filename or "\\" in filename:
        return "Archivo inválido", 400
    
    ruta = os.path.join(CARPETA_TEMPORAL, filename)
    if os.path.exists(ruta):
        return send_file(
            ruta,
            as_attachment=True,
            download_name=f"Presentacion_UdeC.pptx",
            mimetype="application/vnd.openxmlformats-officedocument.presentationml.presentation"
        )
    return "Archivo no encontrado o expirado", 404


@app.route("/tutor", methods=["GET"])
def tutor():
    course = request.args.get("course", "CIENCIA DE DATOS I")
    unidad = request.args.get("unidad", "1")
    return render_template("tutor.html", initial_course=course, initial_unidad=unidad)


@app.route("/api/tutor-chat", methods=["POST"])
def tutor_chat():
    data = request.get_json() or {}
    user_message = data.get("message", "").strip()
    course_name = data.get("course_name", "CIENCIA DE DATOS I").strip()
    unidad_num = str(data.get("unidad_num", "1")).strip()

    if not user_message:
        return {"reply": "Por favor escribe una pregunta válida."}, 400

    # Determinar el slug del curso
    slug_curso = "general"
    c_low = course_name.lower()
    if "ciencia" in c_low: slug_curso = "ciencia_de_datos"
    elif "app" in c_low: slug_curso = "desarrollo_de_apps"
    elif "matemática" in c_low or "matematica" in c_low: slug_curso = "matematicas_discretas"
    elif "metodología" in c_low or "metodologia" in c_low or "investigación" in c_low or "investigacion" in c_low: slug_curso = "metodologia_investigacion"
    elif "probabilidad" in c_low: slug_curso = "probabilidad_y_estadistica"
    elif "sistemas" in c_low: slug_curso = "sistemas_digitales"
    elif "autómata" in c_low or "automata" in c_low: slug_curso = "automatas"

    # Buscar el PDF específico de la unidad o de todas las unidades
    contexto_modulos = ""
    unidades_a_buscar = ["1", "2", "3", "4"] if unidad_num == "todas" else [unidad_num]

    for u in unidades_a_buscar:
        ruta_especifica = _ruta_modulo(slug_curso, u)

        if ruta_especifica:
            try:
                texto_extraido = extraer_texto_pdf(ruta_especifica)
                contexto_modulos += f"\n\n--- DOCUMENTO OFICIAL UdeC: {slug_curso.upper()} - UNIDAD {u} ---\n" + texto_extraido[:35000]
            except Exception as e:
                logger.warning(f"No se pudo extraer texto de {ruta_especifica}: {e}")

    scope_desc = f"la UNIDAD {unidad_num}" if unidad_num != "todas" else "TODAS las unidades del curso"
    
    prompt = f"""Eres un profesor universitario experto, pedagógico y empático de la Universidad de Cartagena (CTEV), sede Magangué, especializado en la asignatura '{course_name}'.

Tu estudiante te está consultando específicamente sobre {scope_desc}.

REGLAS DE ORO:
1. Responde de manera DIRECTA, CLARA y FOCALIZADA estrictamente en la materia '{course_name}' y {scope_desc}.
2. No mezcles contenidos de otras materias ni de otras unidades no solicitadas.
3. Si dispones del texto oficial del módulo (incluido abajo), úsalo como fuente principal y cita conceptos exactos de los autores o temas del programa.
4. Si el estudiante te pide resúmenes, explicaciones de código, ejemplos o cómo preparar su protocolo o exposición, dale respuestas estructuradas, con viñetas y tono académico accesible.

CONTENIDO OFICIAL DEL MÓDULO CARGADO:
{contexto_modulos if contexto_modulos.strip() else '[Nota: Aún no se ha colocado el PDF específico en la carpeta modulos/, responde basándote en el plan de estudios oficial de Ingeniería de Software de la UdeC para esta asignatura y unidad.]'}

PREGUNTA DEL ESTUDIANTE:
{user_message}"""

    # Sistema de respaldo multinivel (Gemini Flash -> Gemini Flash-Lite -> Groq / Llama 3)
    ultimo_error = None

    # Intento 1: Gemini 2.5 Flash
    try:
        from google import genai
        client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
        resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        if resp and resp.text:
            return {"reply": resp.text.strip()}
    except Exception as e:
        ultimo_error = e
        logger.warning(f"Gemini Flash falló: {e}. Intentando respaldo Gemini 3.5 Flash-Lite...")

    # Intento 2: Gemini 3.5 Flash-Lite
    try:
        from google import genai
        client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
        resp = client.models.generate_content(model="gemini-3.5-flash-lite", contents=prompt)
        if resp and resp.text:
            return {"reply": resp.text.strip()}
    except Exception as e:
        ultimo_error = e
        logger.warning(f"Gemini Flash-Lite falló: {e}. Intentando respaldo Groq (Llama 3)...")

    # Intento 3: Groq API (Llama 3.1 8B Instant)
    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    if groq_key:
        try:
            from groq import Groq
            groq_client = Groq(api_key=groq_key)
            completion = groq_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": "Eres un profesor universitario experto de la Universidad de Cartagena."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.6,
                max_tokens=1500
            )
            if completion.choices and completion.choices[0].message.content:
                return {"reply": completion.choices[0].message.content.strip()}
        except Exception as e:
            ultimo_error = e
            logger.warning(f"Groq API respaldo falló: {e}")

    logger.error(f"Todos los respaldos fallaron en tutor_chat: {ultimo_error}")
    return {"reply": f"Lo siento, los servidores de IA están experimentando alta demanda (503 Temporal). Por favor espera un momento y vuelve a intentar. Detalle: {ultimo_error}"}, 500


@app.route("/actividad", methods=["GET"])
def actividad_page():
    return render_template("actividad.html")


@app.route("/api/resolver-actividad", methods=["POST"])
def resolver_actividad():
    data = request.get_json() or {}
    course_name = data.get("course_name", "CIENCIA DE DATOS I").strip()
    unidad_num = str(data.get("unidad_num", "1")).strip()
    enunciado = data.get("enunciado", "").strip()

    if not enunciado:
        return {"solution": "Por favor ingresa el enunciado de la actividad."}, 400

    slug_curso = "general"
    c_low = course_name.lower()
    if "ciencia" in c_low: slug_curso = "ciencia_de_datos"
    elif "app" in c_low: slug_curso = "desarrollo_de_apps"
    elif "matemática" in c_low or "matematica" in c_low: slug_curso = "matematicas_discretas"
    elif "metodología" in c_low or "metodologia" in c_low or "investigación" in c_low or "investigacion" in c_low: slug_curso = "metodologia_investigacion"
    elif "probabilidad" in c_low: slug_curso = "probabilidad_y_estadistica"
    elif "sistemas" in c_low: slug_curso = "sistemas_digitales"
    elif "autómata" in c_low or "automata" in c_low: slug_curso = "automatas"

    contexto_modulos = ""
    es_modo_libre = (course_name.upper() == "LIBRE" or unidad_num.lower() == "libre")

    if not es_modo_libre:
        unidades_a_buscar = ["1", "2", "3", "4"] if unidad_num == "todas" else [unidad_num]
        for u in unidades_a_buscar:
            ruta_especifica = _ruta_modulo(slug_curso, u)
            if ruta_especifica:
                try:
                    contexto_modulos += f"\n--- UNIDAD {u} ---\n" + extraer_texto_pdf(ruta_especifica)[:25000]
                except Exception:
                    pass

    if es_modo_libre:
        prompt = f"""Eres un investigador y docente universitario experto de la Universidad de Cartagena.
Tu misión es resolver de manera magistral, completa, impecablemente organizada y fundamentada la siguiente actividad o preguntas académicas:

ENUNCIADO / PREGUNTAS DE LA TAREA:
{enunciado}

INSTRUCCIONES CRÍTICAS DE RESOLUCIÓN:
1. Responde cada una de las preguntas o puntos planteados con profundidad teórica, citas o metodologías reconocidas y explicaciones claras.
2. Organiza la entrega de forma limpia y profesional:
   - **Introducción / Contextualización**
   - **Desarrollo detallado de cada pregunta (con sus subtítulos correspondientes)**
   - **Ejemplos claros o casos aplicados**
   - **Conclusiones / Síntesis final**
3. El tono debe ser el de un estudiante universitario destacado de quinto semestre que domina el tema a la perfección y entrega un trabajo listo para calificar con la máxima nota."""
    else:
        prompt = f"""Eres un investigador y docente universitario experto de la Universidad de Cartagena.
Tu tarea es resolver con absoluto rigor, claridad y estructura impecable la siguiente actividad de {course_name} (Unidad: {unidad_num}):

ENUNCIADO DE LA ACTIVIDAD:
{enunciado}

CONTEXTO DISPONIBLE DE MÓDULOS:
{contexto_modulos if contexto_modulos.strip() else '[Utiliza conocimiento técnico global y metodología universitaria de la UdeC]'}

REGLAS DE RESOLUCIÓN:
1. Responde y desarrolla exactamente lo que pide el enunciado punto por punto.
2. Estructura la respuesta con títulos claros, desarrollo técnico paso a paso, ejemplos y conclusiones.
3. Tono de estudiante universitario sobresaliente de 5to semestre."""

    # Sistema multi-IA con respaldo en cadena (OpenRouter -> Gemini Flash -> Gemini 3.5 Flash-Lite)
    solucion_texto = ""
    ultimo_err = None

    # 1. OpenRouter (DeepSeek / Llama 3)
    openrouter_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if openrouter_key:
        try:
            import urllib.request
            import json as js
            req_data = js.dumps({
                "model": "deepseek/deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.5
            }).encode('utf-8')
            req = urllib.request.Request(
                "https://openrouter.ai/api/v1/chat/completions",
                data=req_data,
                headers={
                    "Authorization": f"Bearer {openrouter_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "http://localhost:5000",
                    "X-Title": "SIMA UdeC Actividad"
                }
            )
            with urllib.request.urlopen(req, timeout=40) as resp:
                res_json = js.loads(resp.read().decode('utf-8'))
                solucion_texto = res_json['choices'][0]['message']['content'].strip()
        except Exception as e:
            ultimo_err = e
            logger.warning(f"OpenRouter falló en actividad: {e}")

    # 2. Gemini Flash
    if not solucion_texto:
        try:
            from google import genai
            client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
            resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
            if resp and resp.text:
                solucion_texto = resp.text.strip()
        except Exception as e:
            ultimo_err = e
            logger.warning(f"Gemini Flash falló en actividad: {e}")

    # 3. Gemini 3.5 Flash-Lite
    if not solucion_texto:
        try:
            from google import genai
            client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
            resp = client.models.generate_content(model="gemini-3.5-flash-lite", contents=prompt)
            if resp and resp.text:
                solucion_texto = resp.text.strip()
        except Exception as e:
            ultimo_err = e
            logger.warning(f"Gemini Flash-Lite falló en actividad: {e}")

    if not solucion_texto:
        return {"solution": f"No se pudo completar la actividad debido a alta demanda en los servidores de IA. Detalle: {ultimo_err}"}, 500

    return {"solution": solucion_texto}


@app.route("/quiz", methods=["GET"])
def quiz_page():
    return render_template("quiz.html", usuario=_usuario_actual())


@app.route("/api/generar-quiz", methods=["POST"])
def generar_quiz():
    import json as _json
    import random as _random
    data = request.get_json(silent=True) or {}
    course_name = (data.get("course_name") or "CIENCIA DE DATOS I").strip()
    unidad_num = str(data.get("unidad_num") or "1").strip()

    slug_curso = "general"
    c_low = course_name.lower()
    if "ciencia" in c_low:
        slug_curso = "ciencia_de_datos"
    elif "app" in c_low:
        slug_curso = "desarrollo_de_apps"
    elif "matemática" in c_low or "matematica" in c_low:
        slug_curso = "matematicas_discretas"
    elif "metodología" in c_low or "metodologia" in c_low or "investigación" in c_low or "investigacion" in c_low:
        slug_curso = "metodologia_investigacion"
    elif "probabilidad" in c_low:
        slug_curso = "probabilidad_y_estadistica"
    elif "sistemas" in c_low:
        slug_curso = "sistemas_digitales"
    elif "autómata" in c_low or "automata" in c_low:
        slug_curso = "automatas"

    contexto = ""
    unidades = ["1", "2", "3", "4"] if unidad_num == "todas" else [unidad_num]
    for u in unidades:
        ruta = _ruta_modulo(slug_curso, u)
        if ruta:
            try:
                contexto += f"\n--- UNIDAD {u} ---\n" + extraer_texto_pdf(ruta)[:12000]
            except Exception:
                pass
    contexto = recortar_texto(contexto, max_caracteres=30000) if contexto.strip() else ""
    semilla = _random.randint(1, 999999)

    prompt = (
        "Eres un profesor universitario de la Universidad de Cartagena. "
        f"Con base en el siguiente contenido de {course_name} (unidad: {unidad_num}), "
        "genera EXACTAMENTE 20 preguntas de opción múltiple (A/B/C/D), variadas y sin repetir. "
        f"Semilla aleatoria {semilla}: cambia el orden, el enfoque y los distractores. "
        "Devuelve SOLO un JSON válido: una lista de 20 objetos con claves "
        "'pregunta', 'opciones' (lista de 4 textos) y 'respuesta' (0-3, índice correcto). "
        "Sin markdown, sin texto extra.\n\nCONTENIDO:\n"
        + (contexto if contexto.strip() else f"{course_name} unidad {unidad_num}")
    )

    texto_json, ultimo_err = "", None
    openrouter_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if openrouter_key:
        try:
            import urllib.request
            req_data = _json.dumps({
                "model": "deepseek/deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.9,
            }).encode("utf-8")
            req = urllib.request.Request(
                "https://openrouter.ai/api/v1/chat/completions",
                data=req_data,
                headers={"Authorization": f"Bearer {openrouter_key}",
                         "Content-Type": "application/json",
                         "HTTP-Referer": "http://localhost:5000",
                         "X-Title": "SIMA UdeC Quiz"},
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                res_json = _json.loads(resp.read().decode("utf-8"))
                texto_json = res_json["choices"][0]["message"]["content"].strip()
        except Exception as e:
            ultimo_err = e
    if not texto_json:
        try:
            from google import genai
            client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
            resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
            if resp and resp.text:
                texto_json = resp.text.strip()
        except Exception as e:
            ultimo_err = e
    if texto_json.startswith("```"):
        texto_json = texto_json.strip("`")
        if texto_json.lower().startswith("json"):
            texto_json = texto_json[4:]
        texto_json = texto_json.strip()
    try:
        preguntas = _json.loads(texto_json)
        assert isinstance(preguntas, list) and len(preguntas) == 20
        return jsonify({"preguntas": preguntas})
    except Exception as e:
        logger.error(f"Quiz inválido: {e} / {texto_json[:300]} / {ultimo_err}")
        return jsonify({"error": "La IA no devolvió 20 preguntas válidas. Intenta de nuevo."}), 502


@app.route("/api/guardar-nota", methods=["POST"])
def guardar_nota():
    data = request.get_json(silent=True) or {}
    try:
        res = guardar_nota_quiz(
            _usuario_actual(),
            str(data.get("curso", "")),
            str(data.get("unidad", "1")),
            int(data.get("correctas", 0)),
            int(data.get("total", 20)),
            float(data.get("nota", 0)),
        )
        return jsonify(res)
    except Exception as e:
        return jsonify({"ok": False, "motivo": str(e)}), 400


if __name__ == "__main__":
    puerto = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=puerto, debug=os.environ.get("FLASK_DEBUG", "1") == "1")

"""Cliente Supabase opcional para SIMA UdeC.

Si SUPABASE_URL y SUPABASE_KEY están en .env, se activa:
- Auth (registro / login en la nube)
- Historial de protocolos (tabla `protocolos`)
- Notas de quiz (tabla `quiz_notas`)
- Storage de módulos y documentos (buckets `modulos`, `protocolos`)

Si no están configuradas, todo sigue funcionando en modo local.
"""

import os

_supabase = None
_supabase_error = None


def get_supabase():
    """Devuelve el cliente Supabase o None si no está configurado."""
    global _supabase, _supabase_error
    if _supabase is not None:
        return _supabase
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_KEY", "").strip()
    if not url or not key:
        return None
    try:
        from supabase import create_client
        _supabase = create_client(url, key)
        return _supabase
    except Exception as e:
        _supabase_error = str(e)
        return None


def supabase_configurado() -> bool:
    return get_supabase() is not None


def guardar_protocolo(usuario: str, curso: str, unidad: str, tipo: str,
                      nombre_archivo: str, ruta_local: str | None = None) -> dict:
    """Guarda un registro del protocolo y sube el .docx a Storage (si hay)."""
    sb = get_supabase()
    if sb is None:
        return {"ok": False, "motivo": "supabase-no-configurado"}
    storage_path = None
    try:
        if ruta_local and os.path.exists(ruta_local):
            bucket = sb.storage.from_("protocolos")
            storage_path = f"{usuario}/{nombre_archivo}"
            with open(ruta_local, "rb") as f:
                bucket.upload(
                    storage_path,
                    f.read(),
                    {"content-type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                     "upsert": "true"},
                )
    except Exception as e:
        # No bloqueamos la descarga local por un fallo de Storage
        return _insert_protocolo(sb, usuario, curso, unidad, tipo, nombre_archivo, None, f"storage: {e}")
    return _insert_protocolo(sb, usuario, curso, unidad, tipo, nombre_archivo, storage_path, None)


def _insert_protocolo(sb, usuario, curso, unidad, tipo, nombre_archivo, storage_path, aviso):
    try:
        sb.table("protocolos").insert({
            "usuario": usuario,
            "curso": curso,
            "unidad": unidad,
            "tipo": tipo,
            "nombre_archivo": nombre_archivo,
            "storage_path": storage_path,
        }).execute()
        r = {"ok": True, "storage_path": storage_path}
        if aviso:
            r["aviso"] = aviso
        return r
    except Exception as e:
        return {"ok": False, "motivo": str(e)}


def guardar_nota_quiz(usuario: str, curso: str, unidad: str,
                      correctas: int, total: int, nota: float) -> dict:
    sb = get_supabase()
    if sb is None:
        return {"ok": False, "motivo": "supabase-no-configurado"}
    try:
        sb.table("quiz_notas").insert({
            "usuario": usuario,
            "curso": curso,
            "unidad": unidad,
            "correctas": correctas,
            "total": total,
            "nota": nota,
        }).execute()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "motivo": str(e)}


def obtener_historial(usuario: str, limite: int = 20) -> list:
    sb = get_supabase()
    if sb is None:
        return []
    try:
        res = sb.table("protocolos").select("*").eq("usuario", usuario)\
            .order("created_at", desc=True).limit(limite).execute()
        return res.data or []
    except Exception:
        return []


def guardar_perfil(usuario: str, nombre_mostrado: str, avatar: str) -> dict:
    sb = get_supabase()
    if sb is None:
        return {"ok": False, "motivo": "supabase-no-configurado"}
    try:
        sb.table("perfiles").upsert({
            "usuario": usuario,
            "nombre_mostrado": nombre_mostrado,
            "avatar": avatar,
        }, on_conflict="usuario").execute()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "motivo": str(e)}


def obtener_perfil(usuario: str) -> dict:
    sb = get_supabase()
    if sb is None:
        return {}
    try:
        res = sb.table("perfiles").select("*").eq("usuario", usuario).execute()
        return (res.data or [{}])[0]
    except Exception:
        return {}


def obtener_notas(usuario: str, limite: int = 20) -> list:
    sb = get_supabase()
    if sb is None:
        return []
    try:
        res = sb.table("quiz_notas").select("*").eq("usuario", usuario)\
            .order("created_at", desc=True).limit(limite).execute()
        return res.data or []
    except Exception:
        return []


def listar_materias() -> list:
    """Todas las materias creadas por el admin (para el dashboard)."""
    sb = get_supabase()
    if sb is None:
        return []
    try:
        res = sb.table("materias").select("*").order("created_at").execute()
        return res.data or []
    except Exception:
        return []


def crear_materia(nombre: str, semestre: str, centro: str, docente: str,
                  creada_por: str, thumbnail: str = "img/course_ciencia_datos.jpg") -> dict:
    import re
    import unicodedata
    sb = get_supabase()
    if sb is None:
        return {"ok": False, "motivo": "supabase-no-configurado"}
    base = unicodedata.normalize("NFKD", nombre.lower())
    base = "".join(c for c in base if not unicodedata.combining(c))
    slug = re.sub(r"[^a-z0-9]+", "_", base).strip("_") or "materia"
    try:
        res = sb.table("materias").upsert({
            "nombre": nombre, "slug": slug, "semestre": semestre,
            "centro": centro, "docente": docente,
            "thumbnail": thumbnail, "created_by": creada_por,
        }, on_conflict="slug").execute()
        return {"ok": True, "slug": slug, "data": res.data}
    except Exception as e:
        return {"ok": False, "motivo": str(e)}


def registrar_unidad(slug_materia: str, numero: str, nombre_unidad: str,
                     contenido_pdf: bytes) -> dict:
    """Sube el PDF al bucket `modulos` y registra la unidad."""
    sb = get_supabase()
    if sb is None:
        return {"ok": False, "motivo": "supabase-no-configurado"}
    try:
        mat = sb.table("materias").select("id").eq("slug", slug_materia).execute()
        if not mat.data:
            return {"ok": False, "motivo": "materia no encontrada"}
        materia_id = mat.data[0]["id"]
        storage_path = f"{slug_materia}_u{numero}.pdf"
        sb.storage.from_("modulos").upload(
            storage_path, contenido_pdf,
            {"content-type": "application/pdf", "upsert": "true"},
        )
        sb.table("unidades").upsert({
            "materia_id": materia_id, "numero": str(numero),
            "nombre": nombre_unidad, "storage_path": storage_path,
        }, on_conflict="materia_id,numero").execute()
        return {"ok": True, "storage_path": storage_path}
    except Exception as e:
        return {"ok": False, "motivo": str(e)}


def listar_unidades() -> list:
    sb = get_supabase()
    if sb is None:
        return []
    try:
        res = sb.table("unidades").select("numero,nombre,materias!inner(nombre)").execute()
        return res.data or []
    except Exception:
        return []


def descargar_modulo(storage_path: str) -> bytes | None:
    sb = get_supabase()
    if sb is None:
        return None
    try:
        return sb.storage.from_("modulos").download(storage_path)
    except Exception:
        return None


def eliminar_materia(slug_materia: str) -> dict:
    """Borra unidades, archivos del bucket y la materia."""
    sb = get_supabase()
    if sb is None:
        return {"ok": False, "motivo": "supabase-no-configurado"}
    try:
        mat = sb.table("materias").select("id").eq("slug", slug_materia).execute()
        if mat.data:
            materia_id = mat.data[0]["id"]
            sb.table("unidades").delete().eq("materia_id", materia_id).execute()
            sb.table("materias").delete().eq("id", materia_id).execute()
        try:
            archivos = sb.storage.from_("modulos").list()
            borrar = [f["name"] for f in (archivos or [])
                      if f.get("name", "").startswith(slug_materia + "_")]
            if borrar:
                sb.storage.from_("modulos").remove(borrar)
        except Exception:
            pass
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "motivo": str(e)}


def eliminar_unidad(slug_materia: str, numero: str) -> dict:
    sb = get_supabase()
    if sb is None:
        return {"ok": False, "motivo": "supabase-no-configurado"}
    try:
        mat = sb.table("materias").select("id").eq("slug", slug_materia).execute()
        if mat.data:
            sb.table("unidades").delete()\
                .eq("materia_id", mat.data[0]["id"]).eq("numero", str(numero)).execute()
        try:
            sb.storage.from_("modulos").remove([f"{slug_materia}_u{numero}.pdf"])
        except Exception:
            pass
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "motivo": str(e)}

"""
Persistencia en MongoDB (base `colsubsidio`, colecciones sessions /
audit_log / solicitudes).

Reemplaza el backend SQLite original (var/clara.db) manteniendo EXACTAMENTE
la misma API pública: save_session, load_session, append_audit,
purge_old_sessions, upsert_solicitud, list_solicitudes,
set_estado_solicitud, stats. Los callers (app/main.py, app/agent.py) no
requieren cambios.

Decisiones de esquema (documentadas):
- `sessions` y `solicitudes` usan `_id` = id propio (clave natural única:
  el id de sesión y la referencia SOL-...). No hace falta un índice extra.
- `snapshot` y `payload` se guardan como JSON string, igual que en SQLite,
  para preservar byte a byte el formato de los snapshots existentes.
- Las fechas se guardan como strings ISO con el mismo `_now()` de siempre
  (isoformat con segundos), así los datos migrados y los nuevos comparan
  lexicográficamente sin conversión.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from typing import Any

from pymongo import ASCENDING, DESCENDING
from pymongo.database import Database
from pymongo.errors import PyMongoError

from .config import settings
from .mongo import get_db

logger = logging.getLogger("clara.store")

_indexes_ok = False


def _db() -> Database:
    """Base de datos con los índices asegurados (una sola vez por proceso)."""
    global _indexes_ok
    db = get_db()
    if not _indexes_ok:
        try:
            db["audit_log"].create_index([("session_id", ASCENDING)])
            db["sessions"].create_index([("updated_at", ASCENDING)])
            db["solicitudes"].create_index([("estado", ASCENDING)])
            db["perfiles"].create_index([("updated_at", DESCENDING)])
            db["ofertas"].create_index([("updated_at", DESCENDING)])
            _indexes_ok = True
        except PyMongoError:
            # Sin Mongo disponible los índices se reintentan en el próximo
            # acceso; la operación que sigue fallará con su propio error.
            logger.warning("No se pudieron asegurar los índices de Mongo")
    return db


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def save_session(session_id: str, canal: str, estado: str, snapshot: dict[str, Any]) -> None:
    payload = json.dumps(snapshot, ensure_ascii=False, default=str)
    now = _now()
    _db()["sessions"].update_one(
        {"_id": session_id},
        {
            "$set": {"estado": estado, "snapshot": payload, "updated_at": now},
            "$setOnInsert": {"id": session_id, "canal": canal, "created_at": now},
        },
        upsert=True,
    )


def load_session(session_id: str) -> dict[str, Any] | None:
    doc = _db()["sessions"].find_one({"_id": session_id}, {"snapshot": 1})
    if not doc:
        return None
    try:
        return json.loads(doc["snapshot"])
    except (json.JSONDecodeError, KeyError, TypeError):
        logger.error("Snapshot corrupto para la sesión %s", session_id)
        return None


def append_audit(session_id: str, events: list[dict[str, str]]) -> None:
    if not events:
        return
    now = _now()
    _db()["audit_log"].insert_many([
        {"session_id": session_id, "kind": e.get("kind", ""), "tag": e.get("tag", ""),
         "descripcion": e.get("desc", ""), "at": now}
        for e in events
    ])


def purge_old_sessions(ttl_hours: int | None = None) -> int:
    """Elimina sesiones sin actividad más antiguas que el TTL. Devuelve cuántas."""
    ttl = ttl_hours or settings.SESSION_TTL_HOURS
    limit = (dt.datetime.now() - dt.timedelta(hours=ttl)).isoformat(timespec="seconds")
    result = _db()["sessions"].delete_many({"updated_at": {"$lt": limit}})
    if result.deleted_count:
        logger.info("Sesiones purgadas por TTL: %d", result.deleted_count)
    return result.deleted_count


# --------------------------------------------------------------------------
# Solicitudes: la bandeja del asesor / aseguradora.
# Colsubsidio no emite pólizas: Clara empaqueta cada vinculación y la
# transmite aquí para que el asesor la gestione con la aseguradora.
# --------------------------------------------------------------------------
def upsert_solicitud(solicitud_id: str, session_id: str, tipo: str, producto: str | None,
                     estado: str, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False, default=str)
    now = _now()
    _db()["solicitudes"].update_one(
        {"_id": solicitud_id},
        {
            "$set": {"estado": estado, "payload": body, "updated_at": now},
            "$setOnInsert": {"id": solicitud_id, "session_id": session_id,
                             "tipo": tipo, "producto": producto, "created_at": now},
        },
        upsert=True,
    )


def list_solicitudes() -> list[dict[str, Any]]:
    out = []
    for doc in _db()["solicitudes"].find({}).sort("updated_at", DESCENDING):
        try:
            payload = json.loads(doc.get("payload") or "{}")
        except json.JSONDecodeError:
            payload = {}
        out.append({
            "id": doc["_id"], "session_id": doc.get("session_id"),
            "tipo": doc.get("tipo"), "producto": doc.get("producto"),
            "estado": doc.get("estado"), "payload": payload,
            "created_at": doc.get("created_at"), "updated_at": doc.get("updated_at"),
        })
    return out


def set_estado_solicitud(solicitud_id: str, estado: str) -> bool:
    result = _db()["solicitudes"].update_one(
        {"_id": solicitud_id},
        {"$set": {"estado": estado, "updated_at": _now()}},
    )
    return result.matched_count > 0


# --------------------------------------------------------------------------
# Perfil vivo: la base que se enriquece con cada interacción.
# --------------------------------------------------------------------------
def get_perfil(perfil_id: str) -> dict[str, Any] | None:
    doc = _db()["perfiles"].find_one({"_id": perfil_id})
    if not doc:
        return None
    try:
        perfil = json.loads(doc.get("perfil") or "{}")
    except json.JSONDecodeError:
        perfil = {}
    return {"id": doc["_id"], "es_afiliado": bool(doc.get("es_afiliado")),
            "identificador": doc.get("identificador"), "perfil": perfil,
            "interacciones": doc.get("interacciones", 0),
            "created_at": doc.get("created_at"), "updated_at": doc.get("updated_at")}


def upsert_perfil(perfil_id: str, es_afiliado: bool, identificador: str | None,
                  perfil: dict[str, Any], bump: bool = True) -> None:
    body = json.dumps(perfil, ensure_ascii=False, default=str)
    now = _now()
    set_fields = {"es_afiliado": bool(es_afiliado), "perfil": body, "updated_at": now}
    # identificador: solo se sobrescribe si viene uno nuevo (COALESCE del SQL).
    if identificador is not None:
        set_fields["identificador"] = identificador
    _db()["perfiles"].update_one(
        {"_id": perfil_id},
        {
            "$set": set_fields,
            "$setOnInsert": {"id": perfil_id, "created_at": now},
            "$inc": {"interacciones": 1 if bump else 0},
        },
        upsert=True,
    )


def list_perfiles(limit: int = 100) -> list[dict[str, Any]]:
    out = []
    for doc in _db()["perfiles"].find({}).sort("updated_at", DESCENDING).limit(limit):
        try:
            perfil = json.loads(doc.get("perfil") or "{}")
        except json.JSONDecodeError:
            perfil = {}
        out.append({"id": doc["_id"], "es_afiliado": bool(doc.get("es_afiliado")),
                    "identificador": doc.get("identificador"), "perfil": perfil,
                    "interacciones": doc.get("interacciones", 0),
                    "updated_at": doc.get("updated_at")})
    return out


# --------------------------------------------------------------------------
# Bandeja del agente de ofertas (segundo agente, saliente).
# --------------------------------------------------------------------------
def insert_oferta(oferta_id: str, perfil_id: str | None, evento: str, tipo: str,
                  producto: str | None, canal: str | None, estado: str,
                  payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False, default=str)
    now = _now()
    _db()["ofertas"].update_one(
        {"_id": oferta_id},
        {
            "$set": {"estado": estado, "payload": body, "updated_at": now},
            "$setOnInsert": {"id": oferta_id, "perfil_id": perfil_id, "evento": evento,
                             "tipo": tipo, "producto": producto, "canal": canal,
                             "created_at": now},
        },
        upsert=True,
    )


def list_ofertas(limit: int = 100) -> list[dict[str, Any]]:
    out = []
    for doc in _db()["ofertas"].find({}).sort("updated_at", DESCENDING).limit(limit):
        try:
            payload = json.loads(doc.get("payload") or "{}")
        except json.JSONDecodeError:
            payload = {}
        out.append({"id": doc["_id"], "perfil_id": doc.get("perfil_id"),
                    "evento": doc.get("evento"), "tipo": doc.get("tipo"),
                    "producto": doc.get("producto"), "canal": doc.get("canal"),
                    "estado": doc.get("estado"), "payload": payload,
                    "created_at": doc.get("created_at"), "updated_at": doc.get("updated_at")})
    return out


def set_estado_oferta(oferta_id: str, estado: str) -> bool:
    result = _db()["ofertas"].update_one(
        {"_id": oferta_id},
        {"$set": {"estado": estado, "updated_at": _now()}},
    )
    return result.matched_count > 0


def oferta_reciente(perfil_id: str, producto_id: str, dias: int = 15) -> bool:
    """True si ya se generó una oferta del mismo producto para el mismo perfil
    dentro de los últimos `dias` (para no repetir/spamear al cliente)."""
    if not perfil_id or not producto_id:
        return False
    limite = (dt.datetime.now() - dt.timedelta(days=dias)).isoformat(timespec="seconds")
    return _db()["ofertas"].count_documents({
        "perfil_id": perfil_id, "producto": producto_id,
        "created_at": {"$gte": limite},
    }) > 0


def stats() -> dict[str, int]:
    db = _db()
    return {
        "sesiones": db["sessions"].count_documents({}),
        "eventos_auditoria": db["audit_log"].count_documents({}),
        "solicitudes_asesor": db["solicitudes"].count_documents({}),
        "perfiles_vivos": db["perfiles"].count_documents({}),
        "ofertas_salientes": db["ofertas"].count_documents({}),
    }

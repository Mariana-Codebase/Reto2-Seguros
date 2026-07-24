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
            _indexes_ok = True
        except PyMongoError:
            # Sin Mongo disponible los índices se reintentan en el próximo
            # acceso; la operación que sigue fallará con su propio error.
            logger.warning("No se pudieron asegurar los índices de Mongo")
    return db


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def save_session(session_id: str, canal: str, estado: str, snapshot: dict[str, Any]) -> None:
    payload = json.dumps(snapshot, ensure_ascii=False)
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
    body = json.dumps(payload, ensure_ascii=False)
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


def stats() -> dict[str, int]:
    db = _db()
    return {
        "sesiones": db["sessions"].count_documents({}),
        "eventos_auditoria": db["audit_log"].count_documents({}),
        "solicitudes_asesor": db["solicitudes"].count_documents({}),
    }

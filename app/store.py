"""
Persistencia en SQLite (var/clara.db).

Guarda un snapshot JSON de cada sesión tras cada turno y un registro de
auditoría append-only. Así las sesiones sobreviven a reinicios del servidor
y toda decisión queda trazada fuera de la memoria del proceso.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import sqlite3
import threading
from typing import Any

from .config import settings

logger = logging.getLogger("clara.store")

_lock = threading.Lock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id          TEXT PRIMARY KEY,
    canal       TEXT NOT NULL,
    estado      TEXT NOT NULL,
    snapshot    TEXT NOT NULL,          -- JSON completo de la sesión
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    kind        TEXT NOT NULL,
    tag         TEXT NOT NULL,
    descripcion TEXT NOT NULL,
    at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_session ON audit_log(session_id);
CREATE TABLE IF NOT EXISTS solicitudes (
    id          TEXT PRIMARY KEY,        -- SOL-... (misma referencia del contrato)
    session_id  TEXT NOT NULL,
    tipo        TEXT NOT NULL,           -- vinculacion | escalamiento
    producto    TEXT,
    estado      TEXT NOT NULL,           -- pendiente_pago | pagada | enviada_aseguradora | emitida_aseguradora | cerrada
    payload     TEXT NOT NULL,           -- JSON: perfil, propension, datos, contrato, pago, vinculacion
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
-- Perfil VIVO: la base semilla se enriquece con cada interacción. Es lo que
-- convierte a Colsubsidio en dueño de un perfil claro y creciente por persona.
CREATE TABLE IF NOT EXISTS perfiles (
    id           TEXT PRIMARY KEY,       -- SERIE del afiliado, o NA-xxxx si no afiliado
    es_afiliado  INTEGER NOT NULL,       -- 1 / 0
    identificador TEXT,                  -- lo que la persona entregó (documento/serie)
    perfil       TEXT NOT NULL,          -- JSON: base + conversacional + intereses + eventos + propension
    interacciones INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
-- Bandeja del AGENTE DE OFERTAS (segundo agente, proactivo/saliente).
CREATE TABLE IF NOT EXISTS ofertas (
    id          TEXT PRIMARY KEY,
    perfil_id   TEXT,
    evento      TEXT NOT NULL,           -- disparador (credito_vivienda, sin_interaccion_30d, ...)
    tipo        TEXT NOT NULL,           -- seguro | credito
    producto    TEXT,
    canal       TEXT,
    estado      TEXT NOT NULL,           -- generada | enviada | aceptada | descartada
    payload     TEXT NOT NULL,           -- JSON de la oferta (mensaje, razon, url, ...)
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


_conn = _connect()
with _lock:
    _conn.executescript(_SCHEMA)
    _conn.commit()


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def save_session(session_id: str, canal: str, estado: str, snapshot: dict[str, Any]) -> None:
    payload = json.dumps(snapshot, ensure_ascii=False)
    with _lock:
        _conn.execute(
            """INSERT INTO sessions (id, canal, estado, snapshot, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 estado = excluded.estado,
                 snapshot = excluded.snapshot,
                 updated_at = excluded.updated_at""",
            (session_id, canal, estado, payload, _now(), _now()),
        )
        _conn.commit()


def load_session(session_id: str) -> dict[str, Any] | None:
    with _lock:
        row = _conn.execute(
            "SELECT snapshot FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
    if not row:
        return None
    try:
        return json.loads(row[0])
    except json.JSONDecodeError:
        logger.error("Snapshot corrupto para la sesión %s", session_id)
        return None


def append_audit(session_id: str, events: list[dict[str, str]]) -> None:
    if not events:
        return
    with _lock:
        _conn.executemany(
            "INSERT INTO audit_log (session_id, kind, tag, descripcion, at) VALUES (?, ?, ?, ?, ?)",
            [(session_id, e.get("kind", ""), e.get("tag", ""), e.get("desc", ""), _now())
             for e in events],
        )
        _conn.commit()


def purge_old_sessions(ttl_hours: int | None = None) -> int:
    """Elimina sesiones sin actividad más antiguas que el TTL. Devuelve cuántas."""
    ttl = ttl_hours or settings.SESSION_TTL_HOURS
    limit = (dt.datetime.now() - dt.timedelta(hours=ttl)).isoformat(timespec="seconds")
    with _lock:
        cur = _conn.execute("DELETE FROM sessions WHERE updated_at < ?", (limit,))
        _conn.commit()
    if cur.rowcount:
        logger.info("Sesiones purgadas por TTL: %d", cur.rowcount)
    return cur.rowcount


# --------------------------------------------------------------------------
# Solicitudes: la bandeja del asesor / aseguradora.
# Colsubsidio no emite pólizas: Clara empaqueta cada vinculación y la
# transmite aquí para que el asesor la gestione con la aseguradora.
# --------------------------------------------------------------------------
def upsert_solicitud(solicitud_id: str, session_id: str, tipo: str, producto: str | None,
                     estado: str, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False)
    with _lock:
        _conn.execute(
            """INSERT INTO solicitudes (id, session_id, tipo, producto, estado, payload, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 estado = excluded.estado,
                 payload = excluded.payload,
                 updated_at = excluded.updated_at""",
            (solicitud_id, session_id, tipo, producto, estado, body, _now(), _now()),
        )
        _conn.commit()


def list_solicitudes() -> list[dict[str, Any]]:
    with _lock:
        rows = _conn.execute(
            "SELECT id, session_id, tipo, producto, estado, payload, created_at, updated_at "
            "FROM solicitudes ORDER BY updated_at DESC"
        ).fetchall()
    out = []
    for r in rows:
        try:
            payload = json.loads(r[5])
        except json.JSONDecodeError:
            payload = {}
        out.append({"id": r[0], "session_id": r[1], "tipo": r[2], "producto": r[3],
                    "estado": r[4], "payload": payload, "created_at": r[6], "updated_at": r[7]})
    return out


def set_estado_solicitud(solicitud_id: str, estado: str) -> bool:
    with _lock:
        cur = _conn.execute(
            "UPDATE solicitudes SET estado = ?, updated_at = ? WHERE id = ?",
            (estado, _now(), solicitud_id),
        )
        _conn.commit()
    return cur.rowcount > 0


# --------------------------------------------------------------------------
# Perfil vivo: la base que se enriquece con cada interacción.
# --------------------------------------------------------------------------
def get_perfil(perfil_id: str) -> dict[str, Any] | None:
    with _lock:
        row = _conn.execute(
            "SELECT id, es_afiliado, identificador, perfil, interacciones, created_at, updated_at "
            "FROM perfiles WHERE id = ?", (perfil_id,)
        ).fetchone()
    if not row:
        return None
    try:
        perfil = json.loads(row[3])
    except json.JSONDecodeError:
        perfil = {}
    return {"id": row[0], "es_afiliado": bool(row[1]), "identificador": row[2],
            "perfil": perfil, "interacciones": row[4], "created_at": row[5], "updated_at": row[6]}


def upsert_perfil(perfil_id: str, es_afiliado: bool, identificador: str | None,
                  perfil: dict[str, Any], bump: bool = True) -> None:
    body = json.dumps(perfil, ensure_ascii=False)
    inc = 1 if bump else 0
    with _lock:
        _conn.execute(
            """INSERT INTO perfiles (id, es_afiliado, identificador, perfil, interacciones, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 es_afiliado = excluded.es_afiliado,
                 identificador = COALESCE(excluded.identificador, perfiles.identificador),
                 perfil = excluded.perfil,
                 interacciones = perfiles.interacciones + ?,
                 updated_at = excluded.updated_at""",
            (perfil_id, 1 if es_afiliado else 0, identificador, body, inc, _now(), _now(), inc),
        )
        _conn.commit()


def list_perfiles(limit: int = 100) -> list[dict[str, Any]]:
    with _lock:
        rows = _conn.execute(
            "SELECT id, es_afiliado, identificador, perfil, interacciones, updated_at "
            "FROM perfiles ORDER BY updated_at DESC LIMIT ?", (limit,)
        ).fetchall()
    out = []
    for r in rows:
        try:
            perfil = json.loads(r[3])
        except json.JSONDecodeError:
            perfil = {}
        out.append({"id": r[0], "es_afiliado": bool(r[1]), "identificador": r[2],
                    "perfil": perfil, "interacciones": r[4], "updated_at": r[5]})
    return out


# --------------------------------------------------------------------------
# Bandeja del agente de ofertas (segundo agente, saliente).
# --------------------------------------------------------------------------
def insert_oferta(oferta_id: str, perfil_id: str | None, evento: str, tipo: str,
                  producto: str | None, canal: str | None, estado: str,
                  payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False)
    with _lock:
        _conn.execute(
            """INSERT INTO ofertas (id, perfil_id, evento, tipo, producto, canal, estado, payload, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 estado = excluded.estado, payload = excluded.payload, updated_at = excluded.updated_at""",
            (oferta_id, perfil_id, evento, tipo, producto, canal, estado, body, _now(), _now()),
        )
        _conn.commit()


def list_ofertas(limit: int = 100) -> list[dict[str, Any]]:
    with _lock:
        rows = _conn.execute(
            "SELECT id, perfil_id, evento, tipo, producto, canal, estado, payload, created_at, updated_at "
            "FROM ofertas ORDER BY updated_at DESC LIMIT ?", (limit,)
        ).fetchall()
    out = []
    for r in rows:
        try:
            payload = json.loads(r[7])
        except json.JSONDecodeError:
            payload = {}
        out.append({"id": r[0], "perfil_id": r[1], "evento": r[2], "tipo": r[3], "producto": r[4],
                    "canal": r[5], "estado": r[6], "payload": payload, "created_at": r[8], "updated_at": r[9]})
    return out


def set_estado_oferta(oferta_id: str, estado: str) -> bool:
    with _lock:
        cur = _conn.execute(
            "UPDATE ofertas SET estado = ?, updated_at = ? WHERE id = ?", (estado, _now(), oferta_id))
        _conn.commit()
    return cur.rowcount > 0


def stats() -> dict[str, int]:
    with _lock:
        sesiones = _conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        eventos = _conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
        solicitudes = _conn.execute("SELECT COUNT(*) FROM solicitudes").fetchone()[0]
        perfiles = _conn.execute("SELECT COUNT(*) FROM perfiles").fetchone()[0]
        ofertas = _conn.execute("SELECT COUNT(*) FROM ofertas").fetchone()[0]
    return {"sesiones": sesiones, "eventos_auditoria": eventos, "solicitudes_asesor": solicitudes,
            "perfiles_vivos": perfiles, "ofertas_salientes": ofertas}

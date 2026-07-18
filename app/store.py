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


def stats() -> dict[str, int]:
    with _lock:
        sesiones = _conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        eventos = _conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    return {"sesiones": sesiones, "eventos_auditoria": eventos}

"""
Migración one-shot de la persistencia SQLite (var/clara.db) a MongoDB.

Copia sessions, audit_log y solicitudes a las colecciones equivalentes de la
base `colsubsidio`, con el mismo esquema que escribe app/store.py (snapshot y
payload como JSON string, _id = id propio, fechas ISO string).

Idempotente: se puede correr varias veces sin duplicar.
- sessions y solicitudes: upsert por id.
- audit_log: si Mongo ya tiene registros de una sesión, esa sesión se salta.

Uso:  python scripts/migrar_sqlite_mongo.py
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.mongo import get_db  # noqa: E402


def migrar() -> None:
    db_path = settings.DB_PATH
    if not db_path.exists():
        print(f"No hay nada que migrar: {db_path} no existe.")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    mongo = get_db()

    # --- sessions: upsert por id ---
    sesiones = 0
    for r in conn.execute("SELECT * FROM sessions"):
        mongo["sessions"].update_one(
            {"_id": r["id"]},
            {"$set": {"id": r["id"], "canal": r["canal"], "estado": r["estado"],
                      "snapshot": r["snapshot"], "created_at": r["created_at"],
                      "updated_at": r["updated_at"]}},
            upsert=True,
        )
        sesiones += 1

    # --- audit_log: solo sesiones que aún no tienen registros en Mongo ---
    auditoria = 0
    saltadas = 0
    session_ids = [r[0] for r in conn.execute(
        "SELECT DISTINCT session_id FROM audit_log")]
    for sid in session_ids:
        if mongo["audit_log"].count_documents({"session_id": sid}, limit=1):
            saltadas += 1
            continue
        docs = [
            {"session_id": r["session_id"], "kind": r["kind"], "tag": r["tag"],
             "descripcion": r["descripcion"], "at": r["at"]}
            for r in conn.execute(
                "SELECT * FROM audit_log WHERE session_id = ? ORDER BY id", (sid,))
        ]
        if docs:
            mongo["audit_log"].insert_many(docs)
            auditoria += len(docs)

    # --- solicitudes: upsert por id ---
    solicitudes = 0
    for r in conn.execute("SELECT * FROM solicitudes"):
        mongo["solicitudes"].update_one(
            {"_id": r["id"]},
            {"$set": {"id": r["id"], "session_id": r["session_id"], "tipo": r["tipo"],
                      "producto": r["producto"], "estado": r["estado"],
                      "payload": r["payload"], "created_at": r["created_at"],
                      "updated_at": r["updated_at"]}},
            upsert=True,
        )
        solicitudes += 1

    conn.close()
    print(f"Migración completada desde {db_path}:")
    print(f"  sessions:    {sesiones} upserts")
    print(f"  audit_log:   {auditoria} eventos insertados "
          f"({saltadas} sesiones ya migradas, saltadas)")
    print(f"  solicitudes: {solicitudes} upserts")


if __name__ == "__main__":
    migrar()

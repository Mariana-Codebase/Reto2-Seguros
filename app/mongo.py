"""
Cliente MongoDB compartido.

Un único `MongoClient` por proceso, creado de forma perezosa la primera vez
que se llama `get_db()`. Lo comparten app/afiliados_db.py y app/store.py.
"""

from __future__ import annotations

from pymongo import MongoClient
from pymongo.database import Database

from .config import settings

_client: MongoClient | None = None


def get_client() -> MongoClient:
    """Devuelve el MongoClient del proceso, creándolo la primera vez."""
    global _client
    if _client is None:
        _client = MongoClient(
            settings.MONGODB_URI,
            serverSelectionTimeoutMS=5000,
        )
    return _client


def get_db() -> Database:
    """Base de datos de la aplicación (settings.MONGODB_DB)."""
    return get_client()[settings.MONGODB_DB]

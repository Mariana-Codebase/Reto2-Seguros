"""
base_afiliados.py
-----------------
Acceso de LECTURA a la base de afiliados Colsubsidio (identificada por SERIE,
sin cédulas ni nombres). Responde una pregunta clave del flujo:

    ¿esta persona es afiliada? → si lo es, cargamos su perfil de la base.

La base real (500k) no se versiona; en la demo la búsqueda opera sobre la
muestra `data/afiliados_demo.json`. En producción, `buscar()` consultaría el
mismo índice contra la base completa (o un servicio de datos de Colsubsidio):
el resto del sistema no cambia.

El perfil VIVO (lo que Clara aprende y enriquece en cada interacción) NO vive
aquí: vive en la tabla `perfiles` de store.py. Este módulo solo lee el registro
semilla de la base.
"""

from __future__ import annotations

from typing import Any

from . import propension

# Índice serie -> registro, construido perezosamente desde la muestra demo.
_index: dict[str, dict[str, Any]] | None = None


def _build_index() -> dict[str, dict[str, Any]]:
    idx: dict[str, dict[str, Any]] = {}
    for a in propension.cargar_demo():
        serie = str(a.get("serie") or "").strip()
        if serie:
            # guardamos solo los campos de la base (sin la propensión precalculada)
            idx[serie] = {k: v for k, v in a.items()
                          if k not in ("propension", "arquetipo", "arquetipo_desc")}
    return idx


def _get_index() -> dict[str, dict[str, Any]]:
    global _index
    if _index is None:
        _index = _build_index()
    return _index


def buscar(identificador: str) -> dict[str, Any] | None:
    """Busca un afiliado por su número (SERIE). Devuelve el registro de la base
    o None si no está (persona no afiliada o no encontrada)."""
    key = str(identificador or "").strip().lstrip("0") or str(identificador or "").strip()
    idx = _get_index()
    # match exacto y tolerante a ceros a la izquierda
    return idx.get(str(identificador or "").strip()) or idx.get(key)


def existe(identificador: str) -> bool:
    return buscar(identificador) is not None


def resumen_base(a: dict[str, Any]) -> dict[str, Any]:
    """Vista compacta y legible del registro de la base para el perfil vivo y el
    panel del asesor (traduce las etiquetas anonimizadas cuando hay mapeo)."""
    if not a:
        return {}
    return {
        "serie": a.get("serie"),
        "genero": a.get("genero"),
        "rango_edad": a.get("rango_edad"),
        "rango_salarial": a.get("rango_salarial"),
        "ciudad": a.get("ciudad"),
        "marcas_consumo": [k for k, v in (a.get("marcas") or {}).items() if v],
        "segmentos": propension.describir_segmentos(a),
    }

"""
Capa de acceso a las colecciones de negocio en MongoDB (base `colsubsidio`).

Colecciones (creadas y pobladas por scripts/cargar_mongo.py, relacionadas
por el campo `serie`, int):

- `afiliados`: registro normalizado del afiliado (campos en minúsculas al
  estilo de parse_afiliado() de app/propension.py + campos de gestión:
  afiliado_activo, origen, created_at, updated_at, segmentos_interpretados).
- `viviendas`:  serie, tipo, modalidad, valor_estimado, ciudad,
  fecha_adquisicion, estado.
- `creditos`:   serie, tipo, monto, cuota_mensual, estado (al_dia/en_mora),
  fecha_desembolso.
- `eventos`:    bitácora append-only (serie, coleccion, accion, detalle, at).

Todas las funciones devuelven documentos SIN el `_id` interno de Mongo
(proyección {"_id": 0}) para que sean serializables a JSON directamente.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from pymongo import DESCENDING
from pymongo.errors import DuplicateKeyError, PyMongoError

from . import knowledge as kb
from . import propension
from .mongo import get_db

logger = logging.getLogger("clara.afiliados_db")

_SIN_ID = {"_id": 0}

# Campos que la conversación con Lara puede modificar sobre un afiliado.
CAMPOS_EDITABLES = {
    "genero", "rango_edad", "rango_salarial", "categoria",
    "segmento_familiar", "segmento_poblacional", "piramide",
    "empresa", "ciudad", "marcas", "afiliado_activo",
}

# Campos del registro normalizado (mismo esquema de parse_afiliado()).
_CAMPOS_BASE = [
    "genero", "rango_edad", "rango_salarial", "categoria",
    "segmento_familiar", "segmento_poblacional", "piramide",
    "empresa", "ciudad",
]
_MARCAS = ["hoteles", "piscilago", "drogueria", "agencias", "vivienda"]


_indexes_ok = False


def _ensure_indexes() -> None:
    """Índices de las colecciones de negocio (idempotente; los mismos que
    crea scripts/cargar_mongo.py). El único en `serie` es el que sostiene el
    reintento de asignación de serie en crear_afiliado()."""
    global _indexes_ok
    if _indexes_ok:
        return
    try:
        db = get_db()
        db["afiliados"].create_index("serie", unique=True)
        db["viviendas"].create_index("serie")
        db["creditos"].create_index("serie")
        db["eventos"].create_index("serie")
        db["eventos"].create_index("at")
        _indexes_ok = True
    except PyMongoError:
        logger.warning("No se pudieron asegurar los índices de negocio en Mongo")


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def _serie_int(serie: Any) -> int | None:
    """Normaliza la serie a int (en la conversación puede llegar como str)."""
    try:
        return int(str(serie).strip())
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------
# Bitácora de eventos
# --------------------------------------------------------------------------
def registrar_evento(serie: int, coleccion: str, accion: str,
                     detalle: dict[str, Any] | str) -> None:
    """Registra un evento append-only en la bitácora `eventos`."""
    s = _serie_int(serie)
    try:
        get_db()["eventos"].insert_one({
            "serie": s, "coleccion": coleccion, "accion": accion,
            "detalle": detalle, "at": _now(),
        })
    except PyMongoError:
        # La bitácora nunca debe tumbar la operación de negocio.
        logger.exception("No se pudo registrar el evento %s/%s para la serie %s",
                         coleccion, accion, s)


# --------------------------------------------------------------------------
# Consultas
# --------------------------------------------------------------------------
def existe_afiliado(serie: Any) -> dict[str, Any] | None:
    """Documento del afiliado (sin _id) o None si la serie no existe."""
    s = _serie_int(serie)
    if s is None:
        return None
    return get_db()["afiliados"].find_one({"serie": s}, _SIN_ID)


def muestra_series(n: int = 8) -> list[int]:
    """Muestra aleatoria de SERIES de la base real (para el barrido autónomo del
    agente de ofertas). Usa $sample de Mongo; si falla, cae a las primeras N."""
    n = max(1, min(int(n or 8), 100))
    db = get_db()
    try:
        cur = db["afiliados"].aggregate([
            {"$sample": {"size": n}},
            {"$project": {"_id": 0, "serie": 1}},
        ])
        series = [d["serie"] for d in cur if d.get("serie") is not None]
        if series:
            return series
    except PyMongoError:
        logger.warning("No se pudo tomar la muestra aleatoria; se usan las primeras series")
    return [d["serie"] for d in db["afiliados"].find({}, {"_id": 0, "serie": 1}).limit(n)
            if d.get("serie") is not None]


def perfil_360(serie: Any) -> dict[str, Any] | None:
    """Vista completa del afiliado: datos + viviendas + créditos + eventos
    recientes. None si la serie no existe."""
    afiliado = existe_afiliado(serie)
    if afiliado is None:
        return None
    s = _serie_int(serie)
    db = get_db()
    return {
        "afiliado": afiliado,
        "viviendas": list(db["viviendas"].find({"serie": s}, _SIN_ID)),
        "creditos": list(db["creditos"].find({"serie": s}, _SIN_ID)),
        "eventos_recientes": list(
            db["eventos"].find({"serie": s}, _SIN_ID)
            .sort("at", DESCENDING).limit(10)
        ),
    }


# --------------------------------------------------------------------------
# Escritura
# --------------------------------------------------------------------------
def _nueva_serie(db: Any) -> int:
    doc = db["afiliados"].find_one(sort=[("serie", DESCENDING)], projection={"serie": 1})
    return (doc["serie"] + 1) if doc else 1


def crear_afiliado(datos: dict[str, Any]) -> dict[str, Any]:
    """Crea un afiliado nuevo con serie asignada (max serie + 1).

    `datos` trae los campos que Lara recogió en la conversación (minúsculas,
    mismo esquema de parse_afiliado). Si incluye `vivienda` y/o `credito`
    (dicts), crea también esos registros. Registra el evento "creado" y
    devuelve el documento creado (sin _id)."""
    _ensure_indexes()
    db = get_db()
    now = _now()

    doc: dict[str, Any] = {campo: datos.get(campo, "") for campo in _CAMPOS_BASE}
    marcas = datos.get("marcas") or {}
    doc["marcas"] = {m: bool(marcas.get(m, False)) for m in _MARCAS}
    doc.update({
        "afiliado_activo": bool(datos.get("afiliado_activo", True)),
        "origen": datos.get("origen", "clara_conversacion"),
        "created_at": now,
        "updated_at": now,
    })

    vivienda = datos.get("vivienda")
    credito = datos.get("credito")
    if vivienda:
        doc["marcas"]["vivienda"] = True
    doc["segmentos_interpretados"] = propension.describir_segmentos(doc)

    # Asignación de serie con reintentos: si dos procesos calculan el mismo
    # max+1, el índice único en `serie` rechaza al segundo y se reintenta.
    for intento in range(5):
        doc["serie"] = _nueva_serie(db)
        try:
            db["afiliados"].insert_one(dict(doc))
            break
        except DuplicateKeyError:
            logger.warning("Colisión de serie %s al crear afiliado (intento %d)",
                           doc["serie"], intento + 1)
    else:
        raise RuntimeError("No fue posible asignar una serie nueva tras 5 intentos")

    serie = doc["serie"]
    if isinstance(vivienda, dict):
        db["viviendas"].insert_one({
            "serie": serie,
            "tipo": vivienda.get("tipo", ""),
            "modalidad": vivienda.get("modalidad", ""),
            "valor_estimado": vivienda.get("valor_estimado"),
            "ciudad": vivienda.get("ciudad", doc.get("ciudad", "")),
            "fecha_adquisicion": vivienda.get("fecha_adquisicion", now[:10]),
            "estado": vivienda.get("estado", "activa"),
        })
        registrar_evento(serie, "viviendas", "creado", {"tipo": vivienda.get("tipo", "")})
    if isinstance(credito, dict):
        db["creditos"].insert_one({
            "serie": serie,
            "tipo": credito.get("tipo", ""),
            "monto": credito.get("monto"),
            "cuota_mensual": credito.get("cuota_mensual"),
            "estado": credito.get("estado", "al_dia"),
            "fecha_desembolso": credito.get("fecha_desembolso", now[:10]),
        })
        registrar_evento(serie, "creditos", "creado", {"tipo": credito.get("tipo", "")})

    registrar_evento(serie, "afiliados", "creado", {"origen": doc["origen"]})
    logger.info("Afiliado creado con serie %s", serie)
    doc.pop("_id", None)  # insert_one muta el dict agregando _id
    return doc


def actualizar_afiliado(serie: Any, campos: dict[str, Any]) -> dict[str, Any] | None:
    """Update parcial del afiliado: solo campos de CAMPOS_EDITABLES.

    Registra el evento "actualizado" con el detalle de cambios y devuelve el
    documento actualizado (sin _id), o None si la serie no existe."""
    s = _serie_int(serie)
    actual = existe_afiliado(s)
    if actual is None:
        return None

    permitidos = {k: v for k, v in campos.items() if k in CAMPOS_EDITABLES}
    ignorados = sorted(set(campos) - set(permitidos))
    if ignorados:
        logger.warning("Campos no editables ignorados para la serie %s: %s", s, ignorados)

    cambios = {k: v for k, v in permitidos.items() if actual.get(k) != v}
    if not cambios:
        return actual

    cambios["updated_at"] = _now()
    get_db()["afiliados"].update_one({"serie": s}, {"$set": cambios})
    registrar_evento(s, "afiliados", "actualizado", {
        k: {"antes": actual.get(k), "ahora": v}
        for k, v in cambios.items() if k != "updated_at"
    })
    return existe_afiliado(s)


# --------------------------------------------------------------------------
# Ofertas y alertas explicables sobre el perfil 360
# --------------------------------------------------------------------------
def _oferta(producto_id: str, razon: str, fuente: str) -> dict[str, str]:
    return {
        "producto_id": producto_id,
        "titulo": kb.CATALOG[producto_id]["nombre"],
        "razon": razon,
        "fuente": fuente,
    }


def ofertas_para(serie: Any) -> list[dict[str, str]]:
    """Ofertas explicables según el perfil 360 del afiliado.

    Reglas (documentadas, no caja negra):
    - Tiene vivienda registrada       → promo Seguro de Hogar (+ asistencias).
    - Tiene crédito al día            → Seguro de Vida (protección deudor).
    - Crédito en mora                 → SIN oferta comercial (solo alerta,
                                        ver alertas_pendientes).
    - Sin vivienda y salario >= 4 SMLV → promo Vida y Ahorro (meta vivienda).
    """
    perfil = perfil_360(serie)
    if perfil is None:
        return []

    afiliado = perfil["afiliado"]
    viviendas = perfil["viviendas"]
    creditos = perfil["creditos"]
    ofertas: list[dict[str, str]] = []

    if viviendas:
        v = viviendas[0]
        desc = " ".join(str(x) for x in (v.get("tipo"), "en", v.get("ciudad")) if x)
        ofertas.append(_oferta(
            "hogar",
            f"Tiene una vivienda registrada ({desc.strip() or 'vivienda propia'}): "
            "un patrimonio real que proteger contra incendio, robo y daños.",
            "viviendas",
        ))
        ofertas.append(_oferta(
            "asistencia_multiple",
            "Con vivienda a su nombre, las asistencias de plomería, cerrajería y "
            "electricidad de emergencia resuelven imprevistos del hogar a un llamado.",
            "viviendas",
        ))

    al_dia = [c for c in creditos if c.get("estado") == "al_dia"]
    en_mora = [c for c in creditos if c.get("estado") == "en_mora"]
    if al_dia:
        c = al_dia[0]
        ofertas.append(_oferta(
            "vida",
            f"Tiene un crédito {c.get('tipo') or 'vigente'} al día: un seguro de "
            "vida deudor evita que la deuda pase a su familia si el ingreso falta.",
            "creditos",
        ))
    if en_mora:
        # Con mora activa no se empuja oferta comercial: la mora se reporta
        # como alerta en alertas_pendientes().
        logger.info("Serie %s con crédito en mora: se omiten ofertas de crédito",
                    _serie_int(serie))

    salario = afiliado.get("rango_salarial") or ""
    # "Entre 4 y 6 SMLV" es el índice 6 en la escala ordinal de propension.
    if not viviendas and propension._nivel_salarial(salario) >= 6:
        ofertas.append(_oferta(
            "vida_ahorro",
            f"No tiene vivienda registrada y su rango salarial ({salario}) permite "
            "combinar protección con ahorro programado para una meta de vivienda.",
            "afiliados",
        ))

    return ofertas


def alertas_pendientes(serie: Any) -> list[dict[str, Any]]:
    """Alertas derivadas (créditos en mora) + eventos recientes de la serie."""
    s = _serie_int(serie)
    if s is None:
        return []
    db = get_db()
    alertas: list[dict[str, Any]] = []

    for c in db["creditos"].find({"serie": s, "estado": "en_mora"}, _SIN_ID):
        alertas.append({
            "tipo": "mora",
            "mensaje": (f"Crédito {c.get('tipo') or ''} en mora "
                        f"(cuota mensual {c.get('cuota_mensual')}): priorizar "
                        "normalización antes de cualquier oferta comercial.").strip(),
            "fuente": "creditos",
            "detalle": c,
        })

    for e in (db["eventos"].find({"serie": s}, _SIN_ID)
              .sort("at", DESCENDING).limit(5)):
        alertas.append({
            "tipo": "evento",
            "mensaje": f"{e.get('coleccion')}: {e.get('accion')}",
            "fuente": "eventos",
            "detalle": e,
        })

    return alertas

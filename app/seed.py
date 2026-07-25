"""
seed.py — Siembra de una MUESTRA de afiliados SIMULADOS.

Si la colección `afiliados` está vacía, genera N afiliados sintéticos con sus
viviendas y créditos (algunos en mora), para que la demo del agente de ofertas
(barrido autónomo, mora→normalización, propensión) y verificar_afiliado
funcionen automáticamente SIN cargar el Excel real (que no va en la imagen).

Datos ILUSTRATIVOS y deterministas (semilla fija): sirven para el reto/demo, no
son datos reales de Colsubsidio.
"""

from __future__ import annotations

import datetime as dt
import logging
import random

from pymongo import ASCENDING
from pymongo.errors import PyMongoError

from . import propension
from .mongo import get_db

logger = logging.getLogger("clara.seed")

_GENERO = ["F", "M"]
_EDAD = ["20 a 35 años", "36 a 45 años", "46 a 55 años", "Mayor de 55 años", "Menor de 19 años"]
_SALARIO = propension._SALARIOS[:9]     # hasta ~8-10 SMLV (valores plausibles)
_CIUDAD = ["BOGOTA D.C.", "MEDELLIN", "CALI", "BARRANQUILLA", "BUCARAMANGA",
           "PEREIRA", "MANIZALES", "CARTAGENA", "IBAGUE"]
_CATEGORIA = ["ALFA", "BETA", "GAMMA", "DELTA", "SIGMA", "ZETA"]
_SEG_FAM = ["LAMBDA", "RHO", "OMEGA", "THETA"]
_SEG_POB = ["PI", "MU", "NU"]
_PIRAMIDE = ["XI", "DELTA", "OMICRON"]

_SMLV = 1_423_500
_SMLV_MEDIO = {
    "Menor al SMLV": 0.8, "Entre 1 y 1.5 SMLV": 1.25, "Entre 1.5 y 2 SMLV": 1.75,
    "Entre 2 y 2.5 SMLV": 2.25, "Entre 2.5 y 3 SMLV": 2.75, "Entre 3 y 4 SMLV": 3.5,
    "Entre 4 y 6 SMLV": 5.0, "Entre 6 y 8 SMLV": 7.0, "Entre 8 y 10 SMLV": 9.0,
}


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def _fecha_pasada(rng: random.Random, max_dias: int) -> str:
    return (dt.datetime.now() - dt.timedelta(days=rng.randint(30, max_dias))).isoformat(timespec="seconds")


def _afiliado(serie: int, rng: random.Random) -> dict:
    return {
        "serie": serie,
        "genero": rng.choice(_GENERO),
        "rango_edad": rng.choice(_EDAD),
        "rango_salarial": rng.choice(_SALARIO),
        "categoria": rng.choice(_CATEGORIA),
        "segmento_familiar": rng.choice(_SEG_FAM),
        "segmento_poblacional": rng.choice(_SEG_POB),
        "piramide": rng.choice(_PIRAMIDE),
        "empresa": f"EMP_{rng.randint(1, 900):06d}",
        "ciudad": rng.choice(_CIUDAD),
        "marcas": {
            "hoteles": rng.random() < 0.15,
            "piscilago": rng.random() < 0.20,
            "drogueria": rng.random() < 0.50,
            "agencias": rng.random() < 0.10,
            "vivienda": rng.random() < 0.30,
        },
    }


def _vivienda(serie: int, a: dict, rng: random.Random, now: str) -> dict:
    nivel = propension._nivel_salarial(a["rango_salarial"])
    tipo = rng.choice(["VIS", "apartamento", "casa"]) if nivel > 3 else rng.choice(["VIS", "apartamento"])
    modalidad = rng.choices(["subsidio_colsubsidio", "credito_hipotecario", "contado"], [40, 45, 15])[0]
    salario = _SMLV * _SMLV_MEDIO.get(a["rango_salarial"], 1.5)
    valor = int(round(max(salario * rng.uniform(45, 75), 60_000_000), -6))
    return {"serie": serie, "tipo": tipo, "modalidad": modalidad, "valor_estimado": valor,
            "ciudad": a["ciudad"], "fecha_adquisicion": _fecha_pasada(rng, 5 * 365),
            "estado": "activa", "origen": "seed_demo", "created_at": now, "updated_at": now}


def _creditos(serie: int, a: dict, vivienda: dict | None, rng: random.Random, now: str) -> list[dict]:
    creditos: list[dict] = []
    salario = _SMLV * _SMLV_MEDIO.get(a["rango_salarial"], 1.5)

    def base(tipo: str, monto: float) -> dict:
        return {"serie": serie, "tipo": tipo, "monto": int(round(monto, -5)),
                "cuota_mensual": int(round(monto / 48, -3)),
                "estado": "en_mora" if rng.random() < 0.15 else "al_dia",
                "fecha_desembolso": _fecha_pasada(rng, 4 * 365), "origen": "seed_demo",
                "created_at": now, "updated_at": now}

    if vivienda and vivienda["modalidad"] == "credito_hipotecario":
        creditos.append(base("hipotecario", vivienda["valor_estimado"] * rng.uniform(0.55, 0.80)))
    if rng.random() < 0.35:
        creditos.append(base("libre_inversion", salario * rng.uniform(2, 8)))
    return creditos


def sembrar_muestra(n: int = 250, semilla: int = 42) -> dict[str, int]:
    """Genera y carga N afiliados sintéticos + sus viviendas/créditos."""
    db = get_db()
    rng = random.Random(semilla)
    now = _now()
    afs: list[dict] = []
    vis: list[dict] = []
    crs: list[dict] = []
    for serie in range(1, n + 1):
        a = _afiliado(serie, rng)
        doc = dict(a)
        doc["segmentos_interpretados"] = propension.describir_segmentos(a)
        doc["afiliado_activo"] = rng.random() < 0.92
        doc["origen"] = "seed_demo"
        doc["created_at"] = now
        doc["updated_at"] = now
        afs.append(doc)
        v = _vivienda(serie, a, rng, now) if a["marcas"]["vivienda"] else None
        if v:
            vis.append(v)
        crs.extend(_creditos(serie, a, v, rng, now))

    db["afiliados"].create_index([("serie", ASCENDING)], unique=True)
    db["viviendas"].create_index([("serie", ASCENDING)])
    db["creditos"].create_index([("serie", ASCENDING)])
    db["afiliados"].insert_many(afs, ordered=False)
    if vis:
        db["viviendas"].insert_many(vis, ordered=False)
    if crs:
        db["creditos"].insert_many(crs, ordered=False)
    resumen = {"afiliados": len(afs), "viviendas": len(vis), "creditos": len(crs)}
    logger.info("Seed demo cargado: %s", resumen)
    return resumen


def sembrar_si_vacia(n: int = 250) -> dict[str, int] | None:
    """Siembra la muestra solo si la base de afiliados está vacía. Idempotente:
    si ya hay afiliados (seed o Excel real), no hace nada."""
    try:
        db = get_db()
        if db["afiliados"].estimated_document_count() > 0:
            return None
        logger.info("Base de afiliados vacía: sembrando muestra demo de %d afiliados…", n)
        return sembrar_muestra(n)
    except PyMongoError as e:  # noqa: BLE001
        logger.warning("No se pudo sembrar la muestra demo: %s", e)
        return None

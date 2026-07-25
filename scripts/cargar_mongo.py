"""
cargar_mongo.py
---------------
ETL de la base real de afiliados (`Usos_Productos_Afiliados_SIN_ID.xlsx`,
500.000 filas, hoja 'in') hacia MongoDB (base `colsubsidio`):

  afiliados   Excel limpio: SERIE a int (deduplicada, clave única), marcas
              SI/NO a booleanos, ciudad normalizada, etiquetas anonimizadas
              tal cual + `segmentos_interpretados` (describir_segmentos),
              campos de gestión (afiliado_activo, origen, created_at...).
  viviendas   Simulación coherente y DETERMINÍSTICA (random.Random(serie)):
              todo afiliado con VIVIENDA=SI recibe un registro con tipo,
              modalidad y valor_estimado escalados por su RANGO_SALARIAL.
  creditos    Simulación determinística: hipotecario correlacionado con la
              vivienda a crédito, libre inversión según salario, educativo
              en jóvenes; ~10% en mora.
  eventos     Bitácora append-only: se crea vacía con sus índices.

Idempotente: cada corrida hace drop de afiliados/viviendas/creditos y las
recarga. `eventos` NO se borra por defecto (es bitácora de la aplicación);
usar --reset para borrarla también.

Uso:
  python scripts/cargar_mongo.py "C:/ruta/Usos_Productos_Afiliados_SIN_ID.xlsx" [--reset]
"""

from __future__ import annotations

import pathlib
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from pymongo import ASCENDING, DESCENDING  # noqa: E402

from app import propension  # noqa: E402
from app.mongo import get_db  # noqa: E402
from scripts.perfilar_base import leer_filas  # noqa: E402

LOTE = 5_000
SMLV = 1_423_500  # salario mínimo mensual legal vigente (COP)

# Punto medio (en SMLV) de cada rango salarial de la base, para escalar
# valores simulados. Los rangos abiertos usan un valor conservador.
_SMLV_MEDIO = {
    "Menor al SMLV": 0.8, "Entre 1 y 1.5 SMLV": 1.25, "Entre 1.5 y 2 SMLV": 1.75,
    "Entre 2 y 2.5 SMLV": 2.25, "Entre 2.5 y 3 SMLV": 2.75, "Entre 3 y 4 SMLV": 3.5,
    "Entre 4 y 6 SMLV": 5.0, "Entre 6 y 8 SMLV": 7.0, "Entre 8 y 10 SMLV": 9.0,
    "Entre 10 y 20 SMLV": 15.0, "Entre 20 y 30 SMLV": 25.0, "Mayor a 30 SMLV": 35.0,
}


def _salario_medio(rango: str) -> float:
    """Salario mensual estimado (COP) según el rango de la base."""
    return SMLV * _SMLV_MEDIO.get(rango, 1.5)


def _fecha_pasada(rng: random.Random, max_dias: int) -> datetime:
    """Fecha determinística dentro de los últimos `max_dias` días."""
    base = datetime(2026, 7, 1, tzinfo=timezone.utc)
    return base - timedelta(days=rng.randint(30, max_dias))


# ---------------------------------------------------------------------------
# Simulación de vivienda (solo afiliados con marca VIVIENDA=SI)
# ---------------------------------------------------------------------------
def simular_vivienda(serie: int, a: dict[str, Any], ciudad: str | None,
                     now: datetime) -> dict[str, Any]:
    rng = random.Random(serie)  # semilla = serie → reproducible
    nivel = propension._nivel_salarial(a["rango_salarial"])  # -1..11

    if nivel <= 2:        # hasta 2.5 SMLV → predomina VIS con subsidio
        tipo = rng.choices(["VIS", "apartamento", "casa"], [70, 20, 10])[0]
        modalidad = rng.choices(
            ["subsidio_colsubsidio", "credito_hipotecario", "contado"], [65, 30, 5])[0]
    elif nivel <= 5:      # 2.5 a 4 SMLV
        tipo = rng.choices(["VIS", "apartamento", "casa"], [35, 40, 25])[0]
        modalidad = rng.choices(
            ["subsidio_colsubsidio", "credito_hipotecario", "contado"], [30, 60, 10])[0]
    else:                 # más de 4 SMLV
        tipo = rng.choices(["VIS", "apartamento", "casa"], [5, 50, 45])[0]
        modalidad = rng.choices(
            ["subsidio_colsubsidio", "credito_hipotecario", "contado"], [5, 70, 25])[0]

    # Valor estimado: ~45-75 salarios mensuales, con piso por tipo de vivienda
    salario = _salario_medio(a["rango_salarial"])
    valor = salario * rng.uniform(45, 75)
    piso = {"VIS": 60_000_000, "apartamento": 90_000_000, "casa": 110_000_000}[tipo]
    valor_estimado = int(round(max(valor, piso), -6))  # redondeo a millones

    return {
        "serie": serie,
        "tipo": tipo,
        "modalidad": modalidad,
        "valor_estimado": valor_estimado,
        "ciudad": ciudad,
        "fecha_adquisicion": _fecha_pasada(rng, 5 * 365),
        "estado": rng.choices(["activa", "en_proceso"], [85, 15])[0],
        "origen": "simulacion_etl",
        "created_at": now,
        "updated_at": now,
    }


# ---------------------------------------------------------------------------
# Simulación de créditos (probabilidad y tipo según salario/segmento)
# ---------------------------------------------------------------------------
def _cuota_mensual(monto: float, tasa_mensual: float, plazo_meses: int) -> int:
    """Cuota de amortización francesa, redondeada a miles."""
    i = tasa_mensual
    cuota = monto * i / (1 - (1 + i) ** -plazo_meses)
    return int(round(cuota, -3))


def simular_creditos(serie: int, a: dict[str, Any],
                     vivienda: dict[str, Any] | None,
                     now: datetime) -> list[dict[str, Any]]:
    # Semilla distinta a la de vivienda para no repetir la misma secuencia
    rng = random.Random(serie * 31 + 7)
    nivel = propension._nivel_salarial(a["rango_salarial"])
    salario = _salario_medio(a["rango_salarial"])
    creditos: list[dict[str, Any]] = []

    def base(tipo: str, monto: float, tasa: float, plazo: int) -> dict[str, Any]:
        return {
            "serie": serie,
            "tipo": tipo,
            "monto": int(round(monto, -5)),
            "plazo_meses": plazo,
            "cuota_mensual": _cuota_mensual(monto, tasa, plazo),
            "estado": "en_mora" if rng.random() < 0.10 else "al_dia",
            "fecha_desembolso": _fecha_pasada(rng, 4 * 365),
            "origen": "simulacion_etl",
            "created_at": now,
            "updated_at": now,
        }

    # Hipotecario: correlacionado con la vivienda financiada a crédito
    if vivienda is not None and vivienda["modalidad"] == "credito_hipotecario":
        monto = vivienda["valor_estimado"] * rng.uniform(0.55, 0.80)
        cred = base("hipotecario", monto, 0.010, rng.choice([120, 180, 240]))
        cred["fecha_desembolso"] = vivienda["fecha_adquisicion"]
        creditos.append(cred)

    # Libre inversión: probabilidad crece con el salario (12% a ~40%)
    p_libre = min(0.12 + 0.025 * max(nivel, 0), 0.40)
    if rng.random() < p_libre:
        monto = salario * rng.uniform(2, 8)
        creditos.append(base("libre_inversion", monto, 0.016, rng.choice([12, 24, 36, 48])))

    # Educativo: jóvenes (segmento poblacional o edad 20-35), prob. 8%
    es_joven = (propension._sentido("SEGMENTO_POBLACIONAL", a["segmento_poblacional"]) == "joven"
                or a["rango_edad"] == "20 a 35 años")
    if es_joven and rng.random() < 0.08:
        monto = salario * rng.uniform(3, 10)
        creditos.append(base("educativo", monto, 0.011, rng.choice([24, 36, 48, 60])))

    return creditos


# ---------------------------------------------------------------------------
# Limpieza y transformación de una fila
# ---------------------------------------------------------------------------
def transformar(row: dict[str, Any], now: datetime,
                stats: dict[str, int]) -> tuple[dict, dict | None, list[dict]] | None:
    """Fila cruda → (afiliado, vivienda|None, [creditos]). None si SERIE inválida."""
    a = propension.parse_afiliado(row)

    try:
        serie = int(float(a["serie"]))
    except (ValueError, TypeError):
        stats["serie_invalida"] += 1
        return None

    # CIUDAD_AFILIADO: nulos → None explícito + normalización trim/mayúsculas
    ciudad_cruda = row.get("CIUDAD_AFILIADO")
    ciudad = str(ciudad_cruda).strip().upper() if ciudad_cruda is not None else None
    if not ciudad or ciudad in ("NONE", "NULL", "NAN"):
        ciudad = None
        stats["ciudad_nula"] += 1
    if not a["genero"]:
        stats["genero_invalido"] += 1

    afiliado = {
        "serie": serie,
        "genero": a["genero"] or None,
        "rango_edad": a["rango_edad"] or None,
        "rango_salarial": a["rango_salarial"] or None,
        # etiquetas anonimizadas tal cual vienen en la base
        "categoria": a["categoria"] or None,
        "segmento_familiar": a["segmento_familiar"] or None,
        "segmento_poblacional": a["segmento_poblacional"] or None,
        "piramide": a["piramide"] or None,
        "empresa": a["empresa"] or None,
        "ciudad": ciudad,
        "marcas": a["marcas"],  # SI/NO → booleanos (parse_afiliado)
        "segmentos_interpretados": propension.describir_segmentos(a),
        "afiliado_activo": True,
        "origen": "base_excel",
        "created_at": now,
        "updated_at": now,
    }

    vivienda = simular_vivienda(serie, a, ciudad, now) if a["marcas"]["vivienda"] else None
    creditos = simular_creditos(serie, a, vivienda, now)
    return afiliado, vivienda, creditos


# ---------------------------------------------------------------------------
# Carga
# ---------------------------------------------------------------------------
def main(path: str, reset_eventos: bool = False, limite: int | None = None) -> None:
    t0 = time.time()
    db = get_db()
    now = datetime.now(timezone.utc)

    print("Recreando colecciones de negocio (drop + índices)...")
    for col in ("afiliados", "viviendas", "creditos"):
        db.drop_collection(col)
    if reset_eventos:
        db.drop_collection("eventos")

    db.afiliados.create_index([("serie", ASCENDING)], unique=True)
    db.viviendas.create_index([("serie", ASCENDING)])
    db.creditos.create_index([("serie", ASCENDING)])
    # eventos: bitácora append-only; se crea vacía con sus índices
    db.eventos.create_index([("serie", ASCENDING), ("at", DESCENDING)])
    db.eventos.create_index([("at", DESCENDING)])

    stats = {"filas": 0, "serie_invalida": 0, "serie_duplicada": 0,
             "ciudad_nula": 0, "genero_invalido": 0}
    series_vistas: set[int] = set()
    buf_af: list[dict] = []
    buf_vi: list[dict] = []
    buf_cr: list[dict] = []

    def flush() -> None:
        if buf_af:
            db.afiliados.insert_many(buf_af, ordered=False)
            buf_af.clear()
        if buf_vi:
            db.viviendas.insert_many(buf_vi, ordered=False)
            buf_vi.clear()
        if buf_cr:
            db.creditos.insert_many(buf_cr, ordered=False)
            buf_cr.clear()

    print(f"Leyendo {path} ...")
    for row in leer_filas(path):
        stats["filas"] += 1
        res = transformar(row, now, stats)
        if res is None:
            continue
        afiliado, vivienda, creditos = res
        if afiliado["serie"] in series_vistas:
            stats["serie_duplicada"] += 1
            continue
        series_vistas.add(afiliado["serie"])
        buf_af.append(afiliado)
        if vivienda:
            buf_vi.append(vivienda)
        buf_cr.extend(creditos)
        if len(buf_af) >= LOTE:
            flush()
        if stats["filas"] % 100_000 == 0:
            print(f"  ... {stats['filas']:,} filas ({time.time() - t0:.0f}s)")
        # --limit N: muestra menor (carga rápida para demo).
        if limite and len(series_vistas) >= limite:
            print(f"  Límite alcanzado: {limite:,} afiliados (muestra menor).")
            break
    flush()

    # ------------------------------------------------------------------
    # Reporte
    # ------------------------------------------------------------------
    dt = time.time() - t0
    print(f"\nCarga terminada en {dt:.0f}s ({dt / 60:.1f} min)")
    print("\nLimpieza:")
    for k, v in stats.items():
        print(f"  {k}: {v:,}")

    print("\nConteos por colección:")
    for col in ("afiliados", "viviendas", "creditos", "eventos"):
        print(f"  {col}: {db[col].estimated_document_count():,}")

    print("\nMuestra: afiliado con vivienda y su relación por serie")
    viv = db.viviendas.find_one({}, sort=[("serie", ASCENDING)])
    if viv:
        serie = viv["serie"]
        af = db.afiliados.find_one({"serie": serie}, {"_id": 0})
        creds = list(db.creditos.find({"serie": serie}, {"_id": 0}))
        viv.pop("_id", None)
        print(f"  afiliado {serie}: {af}")
        print(f"  vivienda: {viv}")
        print(f"  creditos ({len(creds)}): {creds}")

    cred = db.creditos.find_one({"estado": "en_mora"}, {"_id": 0})
    print(f"\nMuestra: crédito en mora → {cred}")


if __name__ == "__main__":
    _limite = None
    for _a in sys.argv[1:]:
        if _a.startswith("--limit="):
            _limite = int(_a.split("=", 1)[1])
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit("Uso: python scripts/cargar_mongo.py <ruta al .xlsx> [--reset]")
    main(args[0], reset_eventos="--reset" in sys.argv, limite=_limite)

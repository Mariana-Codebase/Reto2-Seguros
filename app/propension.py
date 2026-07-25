"""
propension.py
-------------
Motor de propensión sobre la base real de afiliados Colsubsidio
(`Usos_Productos_Afiliados_SIN_ID.xlsx`, 500.000 registros, identificados
por número de SERIE — sin nombres ni cédulas).

Responde la pregunta del jurado: «¿por qué a esta persona le mostraste
este seguro y no otro?» — con reglas 100% explicables, NO caja negra:

- Cada regla es una fila de la tabla REGLAS: condición sobre una variable
  real de la base → producto → puntos → razón en lenguaje natural.
- El puntaje de un producto es la suma de las reglas que aplican; el
  desglose completo (variable, valor observado, puntos, razón) acompaña
  cada recomendación y se muestra en la interfaz y en la auditoría.
- El motor solo afirma lo que los datos respaldan. Lo que la base no
  contiene (mascotas, vehículo...) no se infiere aquí: lo descubre Lara
  conversando y se suma después.

ETIQUETAS ANONIMIZADAS. Colsubsidio entregó las clasificaciones internas
(categoría, segmento familiar, segmento poblacional, pirámide) anonimizadas
con letras griegas (SIGMA, LAMBDA, RHO...). La correspondencia con su
significado vive en `data/mapa_segmentos.json`: un archivo EDITABLE que
documenta, para cada etiqueta, la interpretación asignada, la evidencia
(participación en la base + validación cruzada por edad/salario/consumo)
y el nivel de confianza. Las reglas de mayor peso usan variables legibles
de la base (rango salarial, edad, marcas de consumo); las reglas basadas
en el mapa lo citan explícitamente. Si Colsubsidio entrega el diccionario
oficial, basta editar ese archivo — el motor no cambia.

También deriva el "momento y canal" de contacto sugerido a partir de las
marcas de consumo (timing estratégico del reto).
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from typing import Any, Callable

from . import knowledge as kb
from .config import settings

logger = logging.getLogger("clara.propension")

# --------------------------------------------------------------------------
# Mapa de segmentos (etiquetas anonimizadas -> significado documentado)
# --------------------------------------------------------------------------
_MAPA_PATH = settings.DATA_DIR / "mapa_segmentos.json"
_mapa_cache: dict[str, Any] | None = None


def mapa_segmentos() -> dict[str, Any]:
    global _mapa_cache
    if _mapa_cache is None:
        if _MAPA_PATH.exists():
            _mapa_cache = json.loads(_MAPA_PATH.read_text(encoding="utf-8"))
        else:
            logger.warning("data/mapa_segmentos.json no existe: las reglas por segmento no aplicarán.")
            _mapa_cache = {}
    return _mapa_cache


def _sentido(dimension: str, etiqueta: str) -> str:
    """Traduce una etiqueta anonimizada (p. ej. 'RHO') a su clave canónica
    (p. ej. 'monoparental') según el mapa documentado. '' si no hay mapeo."""
    m = mapa_segmentos().get(dimension, {}).get("etiquetas", {})
    return (m.get(etiqueta) or {}).get("clave", "")


# --------------------------------------------------------------------------
# Normalización del registro crudo de la base
# --------------------------------------------------------------------------
# Cabeceras reales del archivo (hoja 'in'):
# SERIE, GENERO, RANGO_EDAD, RANGO_SALARIAL, CATEGORIA,
# SEGMENTO_GRUPO_FAMILIAR, SEGMENTO_POBLACIONAL, PIRAMIDE_NUEVA,
# EMPRESA_FOCO (id EMP_xxxxxx), CIUDAD_AFILIADO,
# HOTELES, PISCILAGO, DROGUERIA, AGENCIAS, VIVIENDA (SI/NO)

_RANGO_EDAD_COTIZADOR = {
    "Menor de 19 años": "18-30",
    "20 a 35 años": "18-30",
    "36 a 45 años": "31-45",
    "46 a 55 años": "46-60",
    "Mayor de 55 años": "60+",
}

_MARCAS = ["HOTELES", "PISCILAGO", "DROGUERIA", "AGENCIAS", "VIVIENDA"]

# Orden de los rangos salariales de la base, para comparaciones "mayor que".
_SALARIOS = [
    "Menor al SMLV", "Entre 1 y 1.5 SMLV", "Entre 1.5 y 2 SMLV",
    "Entre 2 y 2.5 SMLV", "Entre 2.5 y 3 SMLV", "Entre 3 y 4 SMLV",
    "Entre 4 y 6 SMLV", "Entre 6 y 8 SMLV", "Entre 8 y 10 SMLV",
    "Entre 10 y 20 SMLV", "Entre 20 y 30 SMLV", "Mayor a 30 SMLV",
]
_SAL_IDX = {s: i for i, s in enumerate(_SALARIOS)}


def _nivel_salarial(rango: str) -> int:
    """Índice ordinal del rango salarial (-1 si no hay dato)."""
    return _SAL_IDX.get(rango, -1)


def parse_afiliado(row: dict[str, Any]) -> dict[str, Any]:
    """Convierte una fila cruda de la base en el registro normalizado del motor.
    El afiliado se identifica solo por SERIE (la base no trae nombres)."""
    def s(k: str) -> str:
        v = row.get(k)
        return str(v).strip() if v is not None else ""

    g = s("GENERO").upper()
    return {
        "serie": s("SERIE"),
        "genero": g if g in ("F", "M") else "",
        "rango_edad": s("RANGO_EDAD"),
        "rango_salarial": s("RANGO_SALARIAL"),
        "categoria": s("CATEGORIA").upper(),                    # etiqueta anonimizada
        "segmento_familiar": s("SEGMENTO_GRUPO_FAMILIAR").upper(),
        "segmento_poblacional": s("SEGMENTO_POBLACIONAL").upper(),
        "piramide": s("PIRAMIDE_NUEVA").upper(),
        "empresa": s("EMPRESA_FOCO"),                           # id EMP_xxxxxx
        "ciudad": s("CIUDAD_AFILIADO").title(),
        "marcas": {m.lower(): s(m).upper() == "SI" for m in _MARCAS},
    }


def rango_edad_cotizador(a: dict[str, Any]) -> str | None:
    return _RANGO_EDAD_COTIZADOR.get(a.get("rango_edad") or "")


# --------------------------------------------------------------------------
# Tabla de reglas (la "lógica documentada" del reto)
# --------------------------------------------------------------------------
# Cada regla: (id, variable, condición legible, test, producto, puntos, razón).
# La razón está escrita para mostrarse tal cual al jurado y al asesor.
# Las reglas S* usan el mapa de segmentos (etiquetas anonimizadas → significado
# documentado en data/mapa_segmentos.json); el resto usa variables legibles.

def _fam(a: dict[str, Any]) -> str:
    return _sentido("SEGMENTO_GRUPO_FAMILIAR", a["segmento_familiar"])


def _pir(a: dict[str, Any]) -> str:
    return _sentido("PIRAMIDE_NUEVA", a["piramide"])


def _pob(a: dict[str, Any]) -> str:
    return _sentido("SEGMENTO_POBLACIONAL", a["segmento_poblacional"])


def es_empresa_foco(a: dict[str, Any]) -> bool:
    return _sentido("EMPRESA_FOCO", a.get("empresa") or "") == "foco"


Regla = tuple[str, str, str, Callable[[dict[str, Any]], bool], str, int, str]

REGLAS: list[Regla] = [
    # --- Segmento del grupo familiar (vía mapa documentado) ---
    ("S1", "segmento_familiar", "familia monoparental",
     lambda a: _fam(a) in ("monoparental", "monoparental_ampliada"),
     "vida", 30, "Su segmento familiar corresponde a hogares de un solo sostén: si ese ingreso falta, los hijos quedan desprotegidos."),
    ("S2", "segmento_familiar", "familia monoparental",
     lambda a: _fam(a) in ("monoparental", "monoparental_ampliada"),
     "asistencia_familiar", 15, "En hogares a cargo de una sola persona, el médico a domicilio y la orientación 24/7 resuelven urgencias sin desplazarse."),
    ("S3", "segmento_familiar", "familia monoparental",
     lambda a: _fam(a) in ("monoparental", "monoparental_ampliada"),
     "exequial", 10, "En una familia de un solo sostén, un evento exequial sin cobertura golpea directamente el presupuesto del hogar."),
    ("S4", "segmento_familiar", "familia nuclear (con hijos)",
     lambda a: _fam(a) in ("nuclear", "nuclear_ampliada"),
     "vida", 25, "Su segmento familiar corresponde a familias con hijos que dependen de los ingresos del hogar."),
    ("S5", "segmento_familiar", "familia nuclear (con hijos)",
     lambda a: _fam(a) in ("nuclear", "nuclear_ampliada"),
     "salud", 15, "Con hijos en casa, un plan complementario agiliza consultas y especialistas para toda la familia."),
    ("S6", "segmento_familiar", "pareja conyugal",
     lambda a: _fam(a) == "pareja",
     "vida", 15, "Su segmento corresponde a parejas que comparten gastos y proyectos que dependen de ambos ingresos."),
    ("S7", "segmento_familiar", "pareja conyugal",
     lambda a: _fam(a) == "pareja",
     "vida_ahorro", 12, "Una pareja en etapa de construcción patrimonial aprovecha proteger y ahorrar en un mismo producto."),
    ("S8", "segmento_familiar", "afiliado sin grupo familiar",
     lambda a: _fam(a) == "sin_grupo",
     "accidentes", 18, "Sin beneficiarios registrados a cargo, su mayor riesgo económico es su propia incapacidad: un accidente detiene su ingreso."),
    ("S9", "segmento_familiar", "afiliado sin grupo familiar",
     lambda a: _fam(a) == "sin_grupo",
     "vida_ahorro", 10, "Sin cargas familiares registradas es el mejor momento para crear un ahorro protegido a mediano plazo."),

    # --- Rango de edad (variable legible de la base) ---
    ("E1", "rango_edad", "hasta 35 años",
     lambda a: a["rango_edad"] in ("20 a 35 años", "Menor de 19 años"),
     "accidentes", 8, "En el rango de edad más activo, los accidentes son el riesgo más frecuente."),
    ("E2", "rango_edad", "20 a 35 años",
     lambda a: a["rango_edad"] == "20 a 35 años",
     "vida_ahorro", 8, "Empezar el ahorro protegido antes de los 35 multiplica el beneficio a largo plazo."),
    ("E3", "rango_edad", "36 a 45 años",
     lambda a: a["rango_edad"] == "36 a 45 años",
     "vida", 10, "Entre los 36 y 45 años suele estar en su etapa de mayores responsabilidades económicas."),
    ("E4", "rango_edad", "46 a 55 años",
     lambda a: a["rango_edad"] == "46 a 55 años",
     "salud", 12, "A partir de los 46 años crece la frecuencia de consultas y exámenes: un complementario reduce esperas."),
    ("E5", "rango_edad", "mayor de 55 años",
     lambda a: a["rango_edad"] == "Mayor de 55 años",
     "exequial", 20, "Después de los 55, anticipar la protección exequial evita a la familia una carga en el peor momento."),
    ("E6", "rango_edad", "mayor de 55 años",
     lambda a: a["rango_edad"] == "Mayor de 55 años",
     "salud", 10, "Con la edad aumenta el uso de servicios médicos; el plan complementario agiliza la atención."),

    # --- Rango salarial (variable legible; reemplaza el proxy de categoría) ---
    ("R1", "rango_salarial", "hasta 1.5 SMLV",
     lambda a: 0 <= _nivel_salarial(a["rango_salarial"]) <= 1,
     "exequial", 8, "Con ingresos de hasta 1.5 SMLV conviene priorizar coberturas de prima baja y alto impacto familiar."),
    ("R2", "rango_salarial", "hasta 1.5 SMLV",
     lambda a: 0 <= _nivel_salarial(a["rango_salarial"]) <= 1,
     "accidentes", 6, "El seguro de accidentes protege el ingreso con una de las primas más bajas del portafolio."),
    ("R3", "rango_salarial", "entre 1.5 y 4 SMLV",
     lambda a: 2 <= _nivel_salarial(a["rango_salarial"]) <= 5,
     "salud", 8, "Su nivel de ingresos permite complementar la EPS con atención más ágil sin desbalancear el presupuesto."),
    ("R4", "rango_salarial", "más de 4 SMLV",
     lambda a: _nivel_salarial(a["rango_salarial"]) >= 6,
     "vida_ahorro", 10, "Con ingresos superiores a 4 SMLV tiene capacidad real de combinar protección con ahorro rentable."),
    ("R5", "rango_salarial", "más de 4 SMLV",
     lambda a: _nivel_salarial(a["rango_salarial"]) >= 6,
     "hogar", 8, "A mayor ingreso, mayor patrimonio en el hogar que proteger."),
    ("R6", "rango_salarial", "más de 6 SMLV",
     lambda a: _nivel_salarial(a["rango_salarial"]) >= 7,
     "vida", 8, "Un ingreso alto sostiene el nivel de vida del hogar: asegurarlo protege ese estándar."),

    # --- Pirámide / tipo de vinculación (vía mapa documentado) ---
    ("P1", "piramide", "pensionado",
     lambda a: _pir(a) == "pensionado",
     "exequial", 12, "Su segmento corresponde a pensionados: la protección exequial familiar es la más consultada en ese grupo."),
    ("P2", "piramide", "pensionado",
     lambda a: _pir(a) == "pensionado",
     "salud", 8, "Los pensionados concentran el mayor uso de servicios de salud."),
    ("P3", "piramide", "independiente",
     lambda a: _pir(a) == "independiente",
     "accidentes", 10, "Su segmento corresponde a independientes, sin el respaldo de una ARL de empleador: un accidente frena su ingreso."),
    ("P4", "piramide", "independiente",
     lambda a: _pir(a) == "independiente",
     "juridica", 6, "Quien trabaja por cuenta propia firma contratos y trámites sin un área legal que lo respalde."),

    # --- Segmento poblacional (vía mapa documentado) ---
    ("B1", "segmento_poblacional", "joven",
     lambda a: _pob(a) == "joven",
     "vida_ahorro", 6, "Su segmento poblacional agrupa a los afiliados jóvenes: el ahorro protegido rinde más cuanto antes empiece."),
    ("B2", "segmento_poblacional", "medio/alto",
     lambda a: _pob(a) in ("medio", "alto"),
     "salud", 5, "Su segmento poblacional (construido con ingresos, edad y compensación) sugiere capacidad para complementar su EPS."),

    # --- Marcas de consumo 2026 (hábitos observados, la señal más directa) ---
    # El comportamiento reciente pesa MÁS que la demografía: una marca activa
    # es evidencia directa de la necesidad, no una inferencia. Además son
    # señales escasas en la base (<0.1% salvo droguería), así que cuando
    # aparecen deben mandar sobre las reglas de segmento.
    ("M1", "marca AGENCIAS", "compró en agencias de viajes Colsubsidio",
     lambda a: a["marcas"]["agencias"],
     "viajes", 35, "Ya compra viajes con Colsubsidio: la asistencia en viaje protege lo que ya hace."),
    ("M2", "marca HOTELES", "se hospedó en hoteles Colsubsidio",
     lambda a: a["marcas"]["hoteles"],
     "viajes", 30, "Se hospeda en hoteles Colsubsidio: viaja, y un imprevisto médico en viaje es un gasto no planeado."),
    ("M3", "marca PISCILAGO", "visitó Piscilago / recreación",
     lambda a: a["marcas"]["piscilago"],
     "accidentes", 10, "Su recreación activa (Piscilago) hace tangible el valor de una cobertura de accidentes."),
    ("M4", "marca DROGUERIA", "compra en droguerías Colsubsidio",
     lambda a: a["marcas"]["drogueria"],
     "salud", 15, "Su gasto recurrente en droguería revela una necesidad de salud activa que el plan complementario alivia."),
    ("M5", "marca DROGUERIA", "compra en droguerías Colsubsidio",
     lambda a: a["marcas"]["drogueria"],
     "asistencia_familiar", 10, "Quien compra medicamentos con frecuencia aprovecha médico a domicilio y orientación 24/7."),
    ("M6", "marca VIVIENDA", "usó el servicio de vivienda Colsubsidio",
     lambda a: a["marcas"]["vivienda"],
     "hogar", 40, "Acaba de usar el servicio de vivienda: quien estrena o mejora casa tiene un patrimonio nuevo que proteger."),
    ("M7", "marca VIVIENDA", "usó el servicio de vivienda Colsubsidio",
     lambda a: a["marcas"]["vivienda"],
     "asistencia_multiple", 10, "Un hogar recién estrenado necesita plomería, cerrajería y electricidad de emergencia a un llamado."),
]


# --------------------------------------------------------------------------
# Momento y canal sugerido (timing estratégico)
# --------------------------------------------------------------------------
def momento_canal(a: dict[str, Any]) -> dict[str, str]:
    m = a["marcas"]
    if m["vivienda"]:
        return {"momento": "Al momento del desembolso o entrega del servicio de vivienda",
                "canal": "Notificación en la app + correo del proceso de vivienda",
                "porque": "El evento de vida 'casa nueva' es la mayor ventana de receptividad para el seguro de hogar."}
    if m["agencias"] or m["hoteles"]:
        return {"momento": "Al confirmar una reserva de viaje u hotel",
                "canal": "Correo de confirmación de la reserva + WhatsApp",
                "porque": "La necesidad de asistencia en viaje es evidente justo cuando la persona está comprando el viaje."}
    if m["drogueria"]:
        return {"momento": "Tras una compra en droguería (recibo digital)",
                "canal": "WhatsApp con el recibo + app Colsubsidio",
                "porque": "El gasto en salud está fresco: es el momento en que un plan complementario se percibe como alivio, no como venta."}
    if m["piscilago"]:
        return {"momento": "Al comprar el pasaporte o boleta de Piscilago",
                "canal": "Oferta en el flujo de compra de la boleta",
                "porque": "La recreación activa hace tangible el valor de una cobertura de accidentes familiar."}
    if _pir(a) == "pensionado":
        return {"momento": "Con el comprobante mensual de la mesada pensional",
                "canal": "Correo + llamada de bienestar del programa de pensionados",
                "porque": "Es el contacto recurrente de mayor confianza con el afiliado pensionado."}
    if es_empresa_foco(a):
        return {"momento": "Jornada de bienestar en su empresa aportante (empresa foco)",
                "canal": "Correo corporativo + stand digital en la jornada",
                "porque": "El canal empresa concentra afiliados con empleador activo y alta confianza institucional."}
    return {"momento": "Campaña de bienestar según su segmento",
            "canal": "WhatsApp (canal de mayor apertura en afiliados)",
            "porque": "Sin marcas de consumo recientes, el mejor disparador es la comunicación segmentada de la caja."}


# --------------------------------------------------------------------------
# Motor: puntuar y explicar
# --------------------------------------------------------------------------
def perfilar(a: dict[str, Any], top: int = 4) -> dict[str, Any]:
    """Aplica la tabla de reglas al afiliado normalizado y devuelve el ranking
    de productos con su puntaje y el desglose de razones (explicable)."""
    scores: dict[str, float] = defaultdict(float)
    razones: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for rid, variable, condicion, test, producto, puntos, razon in REGLAS:
        try:
            aplica = test(a)
        except Exception:  # noqa: BLE001 — un dato sucio no debe tumbar el motor
            aplica = False
        if aplica:
            scores[producto] += puntos
            razones[producto].append({
                "regla": rid, "variable": variable, "condicion": condicion,
                "puntos": puntos, "razon": razon,
            })

    ranking = sorted(scores.items(), key=lambda kv: -kv[1])[:top]
    productos = [{
        "producto_id": pid,
        "nombre": kb.CATALOG[pid]["nombre"],
        "score": round(score, 1),
        "afinidad": round(100 * score / max(s for _, s in ranking), 0),
        "razones": razones[pid],
    } for pid, score in ranking]

    return {
        "serie": a.get("serie"),
        "productos": productos,
        "momento_canal": momento_canal(a),
        "rango_edad_cotizador": rango_edad_cotizador(a),
    }


def reglas_documentadas() -> list[dict[str, Any]]:
    """La tabla de reglas en formato legible: la 'lógica documentada' que pide
    el reto, servida por la API y mostrada en la interfaz."""
    return [{"regla": rid, "variable": var, "si": cond, "producto": prod,
             "puntos": pts, "porque": razon}
            for rid, var, cond, _, prod, pts, razon in REGLAS]


def describir_segmentos(a: dict[str, Any]) -> dict[str, str]:
    """Descripción legible de las etiquetas anonimizadas de un afiliado según
    el mapa documentado (para el contexto de Lara y el panel del asesor)."""
    out = {}
    for dim, campo in [("SEGMENTO_GRUPO_FAMILIAR", "segmento_familiar"),
                       ("SEGMENTO_POBLACIONAL", "segmento_poblacional"),
                       ("PIRAMIDE_NUEVA", "piramide"),
                       ("CATEGORIA", "categoria")]:
        etiqueta = a.get(campo) or ""
        info = mapa_segmentos().get(dim, {}).get("etiquetas", {}).get(etiqueta)
        if info:
            out[campo] = f"{etiqueta} → {info.get('significado', '?')} (confianza {info.get('confianza', '?')})"
        elif etiqueta:
            out[campo] = f"{etiqueta} (sin mapeo documentado)"
    return out


# --------------------------------------------------------------------------
# Perfiles demo y estadísticas (precalculados desde la base real)
# --------------------------------------------------------------------------
_DEMO_PATH = settings.DATA_DIR / "afiliados_demo.json"
_STATS_PATH = settings.DATA_DIR / "propension_stats.json"


def cargar_demo() -> list[dict[str, Any]]:
    if _DEMO_PATH.exists():
        return json.loads(_DEMO_PATH.read_text(encoding="utf-8"))
    return []


def cargar_stats() -> dict[str, Any]:
    if _STATS_PATH.exists():
        return json.loads(_STATS_PATH.read_text(encoding="utf-8"))
    return {}


def buscar_demo(serie: str) -> dict[str, Any] | None:
    for a in cargar_demo():
        if str(a.get("serie")) == str(serie):
            return a
    return None

"""
ofertas.py — El AGENTE DE OFERTAS (segundo agente, proactivo/saliente)
======================================================================

Mientras Clara (agente 1) conversa con quien llega, este agente actúa por su
cuenta: escucha EVENTOS de las bases de Colsubsidio (un crédito desembolsado, un
alza de ingreso, un cumpleaños, inactividad…) y, para cada uno, decide la
oferta más pertinente y por qué canal enviarla. Cruza dos mundos:

  · Seguros  (portafolio de app/knowledge.py)
  · Créditos (portafolio de Colsubsidio: colsubsidio.com/creditos)

Regla de oro (igual que Clara): nada aleatorio. Cada oferta sale de una regla
evento→producto con una razón explicable. El disparo lo puede hacer n8n (u otro
orquestador) llamando POST /api/eventos; la inteligencia vive aquí, versionada
y testeable.

Ejemplo insignia del reto: otra base marca que el afiliado adquirió un crédito
de vivienda → este agente le ofrece el seguro de hogar (protege el patrimonio
que acaba de financiar), citando el evento como motivo.
"""

from __future__ import annotations

import uuid
from typing import Any

from . import knowledge as kb, propension

CREDITOS_URL = "https://www.colsubsidio.com/creditos"

# --------------------------------------------------------------------------
# Portafolio de crédito Colsubsidio (líneas reales; detalle comercial en la web)
# --------------------------------------------------------------------------
CREDITOS: dict[str, dict[str, str]] = {
    "vivienda": {
        "nombre": "Crédito de Vivienda",
        "desc": "Financia la compra de vivienda nueva o usada, o el leasing habitacional.",
        "url": CREDITOS_URL + "/vivienda",
    },
    "libre_inversion": {
        "nombre": "Crédito de Libre Inversión",
        "desc": "Dinero libre para remodelar, viajar, consolidar gastos o lo que necesites.",
        "url": CREDITOS_URL + "/libre-inversion",
    },
    "educativo": {
        "nombre": "Crédito Educativo",
        "desc": "Financia matrículas y estudios tuyos o de tu familia.",
        "url": CREDITOS_URL + "/educativo",
    },
    "vehiculo": {
        "nombre": "Crédito de Vehículo",
        "desc": "Financia la compra de carro o moto, nuevo o usado.",
        "url": CREDITOS_URL + "/vehiculo",
    },
    "compra_cartera": {
        "nombre": "Compra de Cartera",
        "desc": "Unifica tus deudas en una sola cuota y busca una mejor tasa.",
        "url": CREDITOS_URL + "/compra-de-cartera",
    },
    "rotativo": {
        "nombre": "Cupo Rotativo",
        "desc": "Un cupo de crédito disponible para usar cuando lo necesites.",
        "url": CREDITOS_URL + "/rotativo",
    },
}


def _seguro(pid: str) -> dict[str, str]:
    p = kb.CATALOG[pid]
    return {"nombre": p["nombre"], "desc": kb._REASONS.get(pid, ""),
            "aseguradora": kb.aseguradora(pid)}


# --------------------------------------------------------------------------
# Reglas evento → oferta (la "lógica documentada" del agente de ofertas)
# --------------------------------------------------------------------------
# Cada entrada: evento -> (tipo, producto_id, razon). El tipo dice si el
# producto es de 'seguro' o de 'credito'. La razón se envía y se audita.
EVENTO_REGLAS: dict[str, dict[str, Any]] = {
    "credito_vivienda_desembolsado": {
        "tipo": "seguro", "producto": "hogar",
        "razon": "Acabas de financiar tu vivienda con Colsubsidio: el seguro de hogar protege ese patrimonio nuevo.",
        "cross": ("seguro", "vida", "Un seguro de vida cubre el saldo del crédito si algo te llega a pasar."),
    },
    "credito_vehiculo_desembolsado": {
        "tipo": "seguro", "producto": "autos",
        "razon": "Financiaste tu vehículo con Colsubsidio: el seguro de autos lo cubre ante daños y hurto.",
    },
    "credito_libre_inversion_desembolsado": {
        "tipo": "seguro", "producto": "vida",
        "razon": "Tomaste un crédito de libre inversión: un seguro de vida protege a tu familia del saldo pendiente.",
    },
    "credito_educativo_desembolsado": {
        "tipo": "seguro", "producto": "accidentes",
        "razon": "Con un crédito educativo en marcha, un seguro de accidentes protege al estudiante y su continuidad.",
    },
    "nacimiento_hijo": {
        "tipo": "seguro", "producto": "vida",
        "razon": "Un nuevo integrante en la familia hace del seguro de vida la protección más importante.",
        "cross": ("seguro", "salud", "El plan complementario de salud agiliza la atención pediátrica y familiar."),
    },
    "cumple_55": {
        "tipo": "seguro", "producto": "exequial",
        "razon": "Al llegar a esta etapa, anticipar la protección exequial evita cargas a tu familia.",
    },
    "alza_ingreso": {
        "tipo": "credito", "producto": "libre_inversion",
        "razon": "Tu capacidad de pago mejoró: un crédito de libre inversión te da margen para tus proyectos.",
        "cross": ("seguro", "vida_ahorro", "Con más ingreso, el seguro de vida y ahorro combina protección y rentabilidad."),
    },
    "consulta_vivienda": {
        "tipo": "credito", "producto": "vivienda",
        "razon": "Estuviste consultando vivienda: el crédito de vivienda Colsubsidio puede hacerla posible.",
        "cross": ("seguro", "hogar", "Y el seguro de hogar protege ese patrimonio desde el primer día."),
    },
    # P2 · Cuando hay mora, NO se empuja oferta comercial: se ofrece normalización.
    "en_mora_normalizacion": {
        "tipo": "credito", "producto": "compra_cartera",
        "razon": ("Vimos una cuota en mora. Antes de nuevas ofertas, la compra de cartera "
                  "puede unificar tus deudas en una sola cuota más manejable."),
    },
}

# Canal por defecto según lo que se sepa de la persona.
def _canal(perfil: dict[str, Any]) -> str:
    contacto = (perfil or {}).get("contacto") or {}
    if contacto.get("canal"):
        return contacto["canal"]
    return "whatsapp"


def _oferta_producto(tipo: str, pid: str) -> dict[str, Any]:
    if tipo == "credito":
        c = CREDITOS.get(pid, {})
        return {"tipo": "credito", "producto_id": pid, "nombre": c.get("nombre", pid),
                "desc": c.get("desc", ""), "url": c.get("url", CREDITOS_URL)}
    s = _seguro(pid)
    return {"tipo": "seguro", "producto_id": pid, "nombre": s["nombre"], "desc": s["desc"],
            "aseguradora": s.get("aseguradora"), "url": "https://www.colsubsidio.com/seguros"}


def _mensaje(nombre: str | None, prod: dict[str, Any], razon: str) -> str:
    saludo = f"Hola{(' ' + nombre) if nombre else ''}, soy Colsubsidio. "
    return (saludo + razon + f" Conoce {prod['nombre']}: {prod['desc']} {prod['url']}").strip()


def _mejor_por_propension(perfil: dict[str, Any]) -> dict[str, Any] | None:
    prop = (perfil or {}).get("propension") or {}
    prods = prop.get("productos") or []
    if not prods:
        return None
    top = prods[0]
    razon = (top.get("razones") or [{}])[0].get("razon", "")
    return {"tipo": "seguro", "producto": top["producto_id"], "razon": razon}


def generar_oferta(perfil: dict[str, Any], evento: str, datos: dict[str, Any] | None = None) -> dict[str, Any]:
    """Decide la oferta para un evento y un perfil. Devuelve la oferta principal
    (y una secundaria de cross-sell si aplica), con su razón explicable."""
    evento = (evento or "").strip().lower()
    nombre = ((perfil or {}).get("contacto") or {}).get("nombre") or \
             (perfil or {}).get("nombre")

    regla = EVENTO_REGLAS.get(evento)
    if regla is None and evento in ("interes_sin_cierre", "sin_cierre"):
        # P4 · Interés abandonado: la persona pidió un seguro con Clara y no cerró.
        pid = (perfil or {}).get("seguro_solicitado")
        if pid and pid in kb.CATALOG:
            regla = {"tipo": "seguro", "producto": pid,
                     "razon": (f"Nos quedó pendiente tu {kb.CATALOG[pid]['nombre'].lower()}: "
                               "si quieres, retomamos justo donde lo dejamos.")}
    if regla is None:
        # Evento no mapeado o genérico (re-enganche): usa la propensión del perfil.
        base = _mejor_por_propension(perfil)
        if base is None:
            return {"evento": evento, "oferta": None,
                    "motivo": "Sin regla para el evento y sin propensión calculada; nada que ofrecer."}
        regla = {"tipo": base["tipo"], "producto": base["producto"], "razon": base["razon"]}

    prod = _oferta_producto(regla["tipo"], regla["producto"])
    oferta = {
        "id": "OF-" + uuid.uuid4().hex[:8].upper(),
        "evento": evento,
        "tipo": prod["tipo"],
        "producto_id": prod["producto_id"],
        "nombre": prod["nombre"],
        "aseguradora": prod.get("aseguradora"),
        "razon": regla["razon"],
        "url": prod["url"],
        "canal": _canal(perfil),
        "mensaje": _mensaje(nombre, prod, regla["razon"]),
    }
    cross = regla.get("cross")
    if cross:
        c_prod = _oferta_producto(cross[0], cross[1])
        oferta["cross"] = {"tipo": c_prod["tipo"], "producto_id": c_prod["producto_id"],
                           "nombre": c_prod["nombre"], "razon": cross[2], "url": c_prod["url"]}
    return {"evento": evento, "oferta": oferta}


def eventos_soportados() -> list[dict[str, str]]:
    """Catálogo de eventos que el agente de ofertas sabe atender (para docs/UI/n8n)."""
    out = []
    for ev, r in EVENTO_REGLAS.items():
        prod = _oferta_producto(r["tipo"], r["producto"])
        out.append({"evento": ev, "ofrece": prod["nombre"], "tipo": r["tipo"], "razon": r["razon"]})
    out.append({"evento": "interes_sin_cierre", "ofrece": "El seguro que pidió y no cerró",
                "tipo": "seguro", "razon": "Re-enganche por interés abandonado (usa lo que Clara detectó)."})
    out.append({"evento": "(cualquier otro)", "ofrece": "Mejor seguro por propensión",
                "tipo": "seguro", "razon": "Re-enganche basado en el perfil del afiliado."})
    return out

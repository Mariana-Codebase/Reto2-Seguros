"""
ofertas.py — El AGENTE DE OFERTAS (segundo agente, proactivo/saliente)
======================================================================

Mientras Lara (agente 1) conversa con quien llega, este agente actúa por su
cuenta y está enfocado EXCLUSIVAMENTE en SEGUROS: escucha EVENTOS (un crédito
desembolsado en otra base, un alza de ingreso, un nacimiento, inactividad, o el
interés que quedó sin cerrar en una charla con Lara) y, para cada uno, decide el
SEGURO más pertinente del portafolio (app/knowledge.py) y por qué canal enviarlo.

Regla de oro (igual que Lara): nada aleatorio. Cada oferta sale de una regla
evento→seguro con una razón explicable. El disparo lo puede hacer n8n (u otro
orquestador) llamando POST /api/eventos; la inteligencia vive aquí, versionada
y testeable.

Ejemplo insignia del reto: otra base marca que el afiliado adquirió un crédito
de vivienda → este agente le ofrece el SEGURO DE HOGAR (protege el patrimonio
que acaba de financiar), citando el evento como motivo. El agente NO gestiona
créditos ni mora: se dedica a ser el mejor agente de seguros.
"""

from __future__ import annotations

import uuid
from typing import Any

from . import knowledge as kb, propension


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
        "tipo": "seguro", "producto": "vida_ahorro",
        "razon": "Tu ingreso mejoró: el seguro de vida y ahorro combina protección con un ahorro para tus metas.",
    },
    "consulta_vivienda": {
        "tipo": "seguro", "producto": "hogar",
        "razon": "Estuviste mirando temas de vivienda: el seguro de hogar protege ese patrimonio desde el primer día.",
    },
}

# Canal por defecto según lo que se sepa de la persona.
def _canal(perfil: dict[str, Any]) -> str:
    contacto = (perfil or {}).get("contacto") or {}
    if contacto.get("canal"):
        return contacto["canal"]
    return "whatsapp"


def _oferta_producto(tipo: str, pid: str) -> dict[str, Any]:
    # El agente es 100% de seguros: cualquier oferta es un seguro del portafolio.
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
    if regla is None and evento in ("interes_sin_cierre", "sin_cierre", "abandono_con_contacto"):
        # Unión de los dos agentes · La persona habló con Lara, dejó su contacto y
        # no cerró. El agente de ofertas la re-engancha con SU seguro: el que pidió,
        # si no su interés, si no el mejor por propensión.
        pid = (perfil or {}).get("seguro_solicitado")
        if not (pid and pid in kb.CATALOG):
            intereses = (perfil or {}).get("intereses_productos") or []
            pid = next((i for i in intereses if i in kb.CATALOG), None)
            if not pid:
                base = _mejor_por_propension(perfil)
                pid = base["producto"] if base else None
        if pid and pid in kb.CATALOG:
            regla = {"tipo": "seguro", "producto": pid,
                     "razon": (f"Quedó pendiente tu {kb.CATALOG[pid]['nombre'].lower()}. "
                               "Aún puedes gestionarlo cuando quieras; te dejo el recordatorio para retomarlo.")}
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
                "tipo": "seguro", "razon": "Re-enganche por interés abandonado (usa lo que Lara detectó)."})
    out.append({"evento": "(cualquier otro)", "ofrece": "Mejor seguro por propensión",
                "tipo": "seguro", "razon": "Re-enganche basado en el perfil del afiliado."})
    return out

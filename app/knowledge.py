"""
knowledge.py
------------
Motor determinístico de la solución:

- Catálogo de productos con sus condiciones (base de conocimiento / "RAG").
- Recuperación de fragmentos (consultar_coberturas) con cita de fuente.
- Motor de cotización por reglas (cotizar). El precio NUNCA lo calcula el LLM.
- Recomendador que rankea por ajuste al perfil, no por precio.

Todo esto es la "fuente de verdad" del agente: el modelo conversa, pero las
coberturas salen de aquí y los precios de reglas auditables.
"""

from __future__ import annotations
from typing import Any

# --------------------------------------------------------------------------
# Catálogo + base de conocimiento (equivale al RAG sobre pólizas reales)
# --------------------------------------------------------------------------
CATALOG: dict[str, dict[str, Any]] = {
    "vida": {
        "nombre": "Seguro de Vida",
        "base": 18900,
        "amparo": [
            "Fallecimiento por cualquier causa",
            "Incapacidad total y permanente",
            "Auxilio funerario para la familia",
        ],
        "exclusion": [
            "Preexistencias no declaradas al momento de la afiliación",
            "Actos derivados de guerra o terrorismo",
        ],
        "condicion": [
            "Puedes cancelarlo en cualquier momento sin penalidad.",
            "La cobertura inicia tras un periodo de carencia de 60 días.",
            "Cubre el fallecimiento por enfermedad una vez superada la carencia.",
        ],
        "fuente": "Condiciones Generales Seguro de Vida Colsubsidio, cláusula 4.2",
    },
    "hogar": {
        "nombre": "Seguro de Hogar",
        "base": 16500,
        "amparo": [
            "Incendio y daños por agua",
            "Hurto de contenidos del hogar",
            "Responsabilidad civil familiar",
        ],
        "exclusion": [
            "Daños preexistentes a la contratación",
            "Joyas y dinero en efectivo sin declaración previa",
        ],
        "condicion": [
            "Aplica para vivienda propia o en arriendo.",
            "En arriendo cubre el contenido, no la estructura del inmueble.",
        ],
        "fuente": "Condiciones Generales Seguro de Hogar Colsubsidio, cláusula 3.1",
    },
    "autos": {
        "nombre": "Seguro de Autos",
        "base": 52000,
        "amparo": [
            "Pérdida total y parcial por daños",
            "Hurto del vehículo",
            "Responsabilidad civil extracontractual",
        ],
        "exclusion": [
            "Uso comercial cuando se declaró uso particular",
            "Conducción bajo efectos de alcohol o sustancias",
        ],
        "condicion": [
            "El uso declarado debe coincidir con el uso real del vehículo.",
            "Requiere inspección previa para vehículos con más de 10 años.",
        ],
        "fuente": "Condiciones Generales Seguro de Autos Colsubsidio, cláusula 5.4",
    },
    "salud": {
        "nombre": "Plan Complementario de Salud",
        "base": 32000,
        "amparo": [
            "Consultas médicas y especialistas",
            "Exámenes de diagnóstico",
            "Orientación médica telefónica 24/7",
        ],
        "exclusion": [
            "Tratamientos estéticos",
            "Preexistencias sin periodo de carencia cumplido",
        ],
        "condicion": [
            "Complementa tu EPS, no la reemplaza.",
            "Algunos servicios aplican carencia de 30 a 90 días.",
        ],
        "fuente": "Condiciones Generales Plan Complementario de Salud Colsubsidio, cláusula 2.3",
    },
    "mascotas": {
        "nombre": "Seguro de Mascotas",
        "base": 24000,
        "amparo": [
            "Atención veterinaria por accidente o enfermedad",
            "Cirugías y hospitalización de tu mascota",
            "Responsabilidad civil por daños de tu mascota a terceros",
            "Gastos de sacrificio humanitario y sepelio",
        ],
        "exclusion": [
            "Enfermedades preexistentes no declaradas al contratar",
            "Procedimientos estéticos, reproducción, partos y cría",
        ],
        "condicion": [
            "Aplica para perros y gatos desde los 3 meses hasta los 9 años.",
            "Algunos servicios tienen un periodo de carencia de 30 días.",
            "Requiere carné de vacunación al día del animal.",
        ],
        "fuente": "Condiciones Generales Seguro de Mascotas Colsubsidio, cláusula 6.1",
    },
    "moto": {
        "nombre": "Seguro de Moto",
        "base": 29000,
        "amparo": [
            "Pérdida total y parcial por daños",
            "Hurto de la motocicleta",
            "Responsabilidad civil extracontractual",
            "Asistencia en vía, grúa y auxilio mecánico",
        ],
        "exclusion": [
            "Uso en competencias, piques o acrobacias",
            "Conducción sin licencia vigente o bajo efectos de alcohol o sustancias",
        ],
        "condicion": [
            "El uso declarado debe coincidir con el uso real de la moto.",
            "Requiere inspección previa para motos con más de 8 años.",
        ],
        "fuente": "Condiciones Generales Seguro de Moto Colsubsidio, cláusula 5.9",
    },
    # --- Portafolio real de Colsubsidio (colsubsidio.com/seguros/familiares) ---
    "juridica": {
        "nombre": "Asesorías Jurídicas",
        "base": 12900,
        "amparo": [
            "Consultas jurídicas ilimitadas con abogados",
            "Acompañamiento en trámites y gestiones legales",
            "Elaboración y revisión de documentos legales básicos",
        ],
        "exclusion": [
            "Representación en procesos judiciales iniciados antes de la afiliación",
            "Casos penales de alta complejidad",
        ],
        "condicion": [
            "Atención telefónica y virtual con expertos en horario hábil.",
            "Cubre al afiliado y su núcleo familiar declarado.",
        ],
        "fuente": "Portafolio Asesorías Jurídicas Colsubsidio (colsubsidio.com/seguros/familiares)",
    },
    "accidentes": {
        "nombre": "Seguro de Accidentes Personales",
        "base": 15900,
        "amparo": [
            "Indemnización por muerte accidental",
            "Incapacidad total o parcial por accidente",
            "Gastos médicos derivados de un accidente",
        ],
        "exclusion": [
            "Lesiones por deportes de alto riesgo no declarados",
            "Accidentes bajo efectos de alcohol o sustancias",
        ],
        "condicion": [
            "Cobertura 24/7 en Colombia y el exterior.",
            "Aplica para afiliados desde los 18 años.",
        ],
        "fuente": "Condiciones Seguro de Accidentes Personales Colsubsidio",
    },
    "asistencia_multiple": {
        "nombre": "Asistencias Múltiples",
        "base": 21900,
        "amparo": [
            "Asistencia para salud, hogar, vehículo y mascotas 24/7",
            "Plomería, cerrajería y electricidad de emergencia",
            "Grúa y asistencia en vía",
            "Orientación veterinaria telefónica",
        ],
        "exclusion": [
            "Reparaciones estructurales mayores",
            "Eventos preexistentes a la contratación",
        ],
        "condicion": [
            "Servicio disponible 24 horas, todos los días.",
            "Número limitado de eventos al año según el plan.",
        ],
        "fuente": "Portafolio Asistencias Múltiples Colsubsidio",
    },
    "exequial": {
        "nombre": "Seguro Exequial",
        "base": 13900,
        "amparo": [
            "Servicio funerario completo para el afiliado y su familia",
            "Traslados y trámites del proceso exequial",
            "Acompañamiento durante todo el proceso",
        ],
        "exclusion": [
            "Servicios no coordinados con la red autorizada",
            "Beneficiarios no registrados en la póliza",
        ],
        "condicion": [
            "Cubre al grupo familiar declarado.",
            "Periodo de carencia de 90 días para muerte natural.",
        ],
        "fuente": "Condiciones Seguro Exequial Colsubsidio",
    },
    "accidentes_exequial": {
        "nombre": "Accidentes Personales y Servicio Exequial",
        "base": 19900,
        "amparo": [
            "Cobertura por accidentes personales",
            "Servicio y gastos exequiales",
            "Apoyo financiero inmediato a la familia",
        ],
        "exclusion": [
            "Muerte por causas excluidas del amparo de accidentes",
            "Servicios exequiales fuera de la red autorizada",
        ],
        "condicion": [
            "Combina el amparo de accidentes con el servicio exequial.",
            "Carencia de 90 días para el componente exequial por causa natural.",
        ],
        "fuente": "Condiciones Accidentes Personales y Servicio Exequial Colsubsidio",
    },
    "vida_ahorro": {
        "nombre": "Seguro de Vida y Ahorro",
        "base": 45000,
        "amparo": [
            "Amparo de vida por fallecimiento o incapacidad",
            "Componente de ahorro programado",
            "Rentabilidad sobre el ahorro acumulado",
        ],
        "exclusion": [
            "Retiros del ahorro antes del plazo pactado (con penalidad)",
            "Preexistencias no declaradas al contratar",
        ],
        "condicion": [
            "Combina protección de vida con ahorro a mediano y largo plazo.",
            "El ahorro es rescatable según las condiciones del plan.",
        ],
        "fuente": "Condiciones Seguro de Vida y Ahorro Colsubsidio",
    },
    "asistencia_familiar": {
        "nombre": "Asistencias Médicas Familiares",
        "base": 26000,
        "amparo": [
            "Médico a domicilio",
            "Consultas médicas telefónicas 24/7",
            "Urgencias odontológicas",
            "Orientación médica y psicológica",
        ],
        "exclusion": [
            "Hospitalización y cirugías",
            "Tratamientos de enfermedades crónicas",
        ],
        "condicion": [
            "Complementa tu EPS, no la reemplaza.",
            "Cubre al grupo familiar declarado.",
        ],
        "fuente": "Portafolio Asistencias Médicas Familiares Colsubsidio",
    },
    "viajes": {
        "nombre": "Asistencia Médica en Viajes",
        "base": 18000,
        "amparo": [
            "Emergencias médicas durante el viaje",
            "Consultas telefónicas y medicamentos",
            "Urgencias dentales durante el viaje",
            "Asistencia por pérdida de equipaje o documentos",
        ],
        "exclusion": [
            "Enfermedades preexistentes no declaradas",
            "Actividades de alto riesgo no aseguradas",
        ],
        "condicion": [
            "Cobertura durante la vigencia del viaje declarado.",
            "Debe contratarse antes de iniciar el viaje.",
        ],
        "fuente": "Condiciones Asistencia Médica en Viajes Colsubsidio",
    },
}

PRODUCTOS_VALIDOS = list(CATALOG.keys())

# Factores del motor de reglas (auditable, versionable en YAML en producción)
EDAD_FACTOR = {"18-30": 0.90, "31-45": 1.00, "46-60": 1.25, "60+": 1.60}


# --------------------------------------------------------------------------
# consultar_coberturas  (RAG simulado, con cita de fuente)
# --------------------------------------------------------------------------
def consultar_coberturas(producto: str, tipo: str = "amparo") -> dict[str, Any]:
    producto = (producto or "").lower().strip()
    tipo = (tipo or "amparo").lower().strip()
    if producto not in CATALOG:
        return {"error": f"Producto '{producto}' no existe. Válidos: {PRODUCTOS_VALIDOS}"}
    if tipo not in ("amparo", "exclusion", "condicion"):
        tipo = "amparo"
    p = CATALOG[producto]
    return {
        "producto": p["nombre"],
        "tipo": tipo,
        "chunks": p[tipo],
        "fuente": p["fuente"],
    }


# --------------------------------------------------------------------------
# cotizar  (motor de reglas determinístico)
# --------------------------------------------------------------------------
def cotizar(producto: str, rango_edad: str | None = None, dependientes: int = 0) -> dict[str, Any]:
    producto = (producto or "").lower().strip()
    if producto not in CATALOG:
        return {"error": f"Producto '{producto}' no existe. Válidos: {PRODUCTOS_VALIDOS}"}
    p = CATALOG[producto]
    factor = EDAD_FACTOR.get(rango_edad or "31-45", 1.0)
    try:
        dependientes = int(dependientes or 0)
    except (TypeError, ValueError):
        dependientes = 0

    precio = p["base"]
    desglose = [f"Prima base: {precio:,}".replace(",", ".")]
    if producto == "vida":
        extra = dependientes * 2600
        precio += extra
        if extra:
            desglose.append(f"Dependientes ({dependientes}): +{extra:,}".replace(",", "."))
    elif producto == "salud":
        extra = dependientes * 3400
        precio += extra
        if extra:
            desglose.append(f"Dependientes ({dependientes}): +{extra:,}".replace(",", "."))
    precio = round(precio * factor)
    desglose.append(f"Factor edad ({rango_edad or '31-45'}): x{factor}")
    precio = round(precio / 100) * 100

    return {
        "producto": p["nombre"],
        "producto_id": producto,
        "precio_mensual": precio,
        "precio_formateado": format_cop(precio),
        "moneda": "COP",
        "desglose": desglose,
        "vigencia": "anual renovable",
    }


def format_cop(n: int) -> str:
    return "$" + f"{int(n):,}".replace(",", ".")


# --------------------------------------------------------------------------
# recomendar  (rankea por ajuste al perfil)
# --------------------------------------------------------------------------
_REASONS = {
    "vida": "Protege el ingreso de tu familia si a ti te pasa algo.",
    "hogar": "Protege tu hogar y su contenido, útil cuando vives en arriendo.",
    "autos": "Cubre tu vehículo particular ante daños y hurto.",
    "salud": "Complementa la atención médica tuya y de tu familia.",
    "mascotas": "Cuida la salud de tu mascota y cubre imprevistos veterinarios.",
    "moto": "Protege tu moto ante daños, hurto y responsabilidad civil.",
    "juridica": "Te da respaldo legal y acompañamiento en trámites cuando lo necesitas.",
    "accidentes": "Te protege económicamente ante un accidente inesperado.",
    "asistencia_multiple": "Resuelve emergencias de hogar, vehículo, salud y mascotas 24/7.",
    "exequial": "Acompaña a tu familia en los momentos más sensibles sin cargas económicas.",
    "accidentes_exequial": "Une el amparo por accidentes con el servicio exequial para tu familia.",
    "vida_ahorro": "Protege tu vida mientras construyes un ahorro para el futuro.",
    "asistencia_familiar": "Atención médica en casa y orientación 24/7 para tu familia.",
    "viajes": "Viaja tranquilo con asistencia médica y respaldo ante imprevistos.",
}

# Palabras clave -> producto, para detectar intereses o peticiones directas.
_KEYWORDS: dict[str, list[str]] = {
    "mascotas": ["gato", "perro", "mascota", "felino", "canino", "cachorro", "minino", "michi", "perrito", "gatito"],
    "moto": ["moto", "motocicleta", "scooter", "scoote"],
    "autos": ["carro", "auto", "vehículo particular", "vehiculo particular", "camioneta"],
    "viajes": ["viaje", "viajar", "viajo", "turismo", "vacaciones", "exterior", "extranjero", "vuelo"],
    "juridica": ["jurídic", "juridic", "legal", "abogad", "demanda", "trámite legal", "tramite legal"],
    "accidentes": ["accidente", "accidentes personales"],
    "exequial": ["exequial", "funerari", "sepelio", "entierro"],
    "vida_ahorro": ["ahorro", "ahorrar", "vida y ahorro"],
    "salud": ["salud", "eps", "médic", "medic", "clínica", "clinica", "especialista"],
    "hogar": ["hogar", "casa", "apartamento", "arriendo", "vivienda"],
    "vida": ["seguro de vida", "fallecimiento"],
    "asistencia_multiple": ["asistencia múltiple", "asistencia multiple", "asistencias múltiples"],
    "asistencia_familiar": ["médico a domicilio", "medico a domicilio", "asistencia médica familiar", "asistencia medica familiar"],
}


def detectar_productos(texto: str) -> list[str]:
    """Devuelve los productos mencionados en un texto libre (peticiones directas
    o intereses), preservando el orden de aparición y sin duplicar."""
    low = (texto or "").lower()
    encontrados: list[str] = []
    for prod, kws in _KEYWORDS.items():
        if any(k in low for k in kws) and prod not in encontrados:
            encontrados.append(prod)
    return encontrados


def bienes_desde_notas(perfil: dict[str, Any]) -> list[str]:
    """Detecta productos extra a partir de detalles libres del perfil
    (mascotas, moto, viaje, etc.) para no ignorar lo que contó la persona."""
    notas = " ".join(perfil.get("notas", []) or [])
    return detectar_productos(notas)


_PRIORIDAD_MAP: dict[str, list[str]] = {
    "hogar": ["hogar", "asistencia_multiple", "vida"],
    "salud": ["salud", "asistencia_familiar", "vida"],
    "mascotas": ["mascotas", "asistencia_multiple", "salud"],
    "viajes": ["viajes", "salud", "accidentes"],
    "exequial": ["exequial", "accidentes_exequial", "vida"],
    "ahorro": ["vida_ahorro", "vida", "salud"],
    "accidentes": ["accidentes", "asistencia_familiar", "vida"],
    "juridica": ["juridica", "hogar", "vida"],
}


def recomendar(perfil: dict[str, Any], productos: list[str] | None = None,
               propension: dict[str, Any] | None = None) -> dict[str, Any]:
    # Prioridad de señales (de más a menos fuerte):
    #   1. Producto pedido explícitamente en la conversación.
    #   2. Prioridad expresada por la persona durante el diagnóstico.
    #   3. Ranking del motor de propensión (variables reales de la base).
    #   4. Portafolio por defecto.
    # Lo que la persona dice SIEMPRE le gana a lo que la base sugiere.
    ids: list[str] = [p for p in (productos or []) if p in CATALOG]

    if not ids:
        prioridad = perfil.get("prioridad")
        vehiculo = perfil.get("vehiculo")
        hogar = perfil.get("hogar")
        veh_prod = "moto" if vehiculo == "moto" else "autos"
        tiene_veh = vehiculo in ("particular", "comercial", "moto")

        if prioridad == "ingreso":
            ids = ["vida", veh_prod if tiene_veh else ("hogar" if hogar != "solo" else "salud"), "salud"]
        elif prioridad == "vehiculo":
            ids = [veh_prod, "asistencia_multiple", "vida"]
        elif prioridad in _PRIORIDAD_MAP:
            ids = list(_PRIORIDAD_MAP[prioridad])
        elif propension and propension.get("productos"):
            ids = [p["producto_id"] for p in propension["productos"] if p["producto_id"] in CATALOG]
        else:
            ids = ["vida", "salud", "hogar"]

    # Suma productos detectados en la conversación (mascotas, moto, viaje...).
    ids += bienes_desde_notas(perfil)

    # dedup preservando orden
    seen: set[str] = set()
    ids = [x for x in ids if not (x in seen or seen.add(x))][:4]

    dependientes = perfil.get("dependientes", 0) or 0
    rango_edad = perfil.get("rango_edad")

    # Razones del motor de propensión por producto (si la sesión está anclada
    # a un afiliado de la base): alimentan el "por qué" explicable de la oferta.
    razones_base: dict[str, Any] = {}
    if propension:
        for p in propension.get("productos", []):
            razones_base[p["producto_id"]] = {
                "afinidad": p.get("afinidad"),
                "razones": [r["razon"] for r in p.get("razones", [])],
            }

    opciones = []
    for i in ids:
        q = cotizar(i, rango_edad, dependientes)
        p = CATALOG[i]
        opciones.append({
            "producto_id": i,
            "nombre": p["nombre"],
            "por_que": _REASONS[i],
            "propension": razones_base.get(i),
            "cubre": p["amparo"][:3],
            "no_cubre": p["exclusion"],
            "precio_mensual": q["precio_mensual"],
            "precio_formateado": q["precio_formateado"],
            "fuente": p["fuente"],
        })
    return {"opciones": opciones}

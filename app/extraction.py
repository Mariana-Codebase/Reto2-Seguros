"""
Captura de datos de la conversación, en dos capas complementarias:

1. Determinística (regex): correo, celular, placa, cédula. No depende del
   modelo y nunca falla en silencio.
2. Estructurada (Gemini con responseSchema): perfil de necesidades y datos
   de contratación. La salida queda restringida a un esquema JSON, por lo
   que no hay que "parsear texto con suerte".

El agente igual puede llamar sus herramientas registrar_perfil /
registrar_datos; esto garantiza que nada de lo que diga el afiliado se pierda.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from . import llm

logger = logging.getLogger("clara.extraction")

# --------------------------------------------------------------------------
# Capa 1 · Regex determinísticos
# --------------------------------------------------------------------------
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"(?:\+?57[\s-]?)?(3\d{2}[\s-]?\d{3}[\s-]?\d{4})\b")
PLACA_CARRO_RE = re.compile(r"\b([A-Z]{3}[\s-]?\d{3})\b", re.IGNORECASE)
PLACA_MOTO_RE = re.compile(r"\b([A-Z]{3}[\s-]?\d{2}[A-Z])\b", re.IGNORECASE)
CEDULA_RE = re.compile(r"\b(?:c[eé]dula|cc|documento)\D{0,12}(\d{6,10})\b", re.IGNORECASE)


def extract_contact_deterministic(text: str, existentes: dict[str, str]) -> dict[str, str]:
    """Correo, celular, placa y documento por regex. Solo campos aún vacíos."""
    out: dict[str, str] = {}
    m = EMAIL_RE.search(text)
    if m and not existentes.get("correo"):
        out["correo"] = m.group(0).strip(".,;")
    m = PHONE_RE.search(text)
    if m and not existentes.get("telefono"):
        out["telefono"] = re.sub(r"[\s-]", "", m.group(1))
    m = PLACA_MOTO_RE.search(text) or PLACA_CARRO_RE.search(text)
    if m and not existentes.get("placa"):
        out["placa"] = re.sub(r"[\s-]", "", m.group(1)).upper()
    m = CEDULA_RE.search(text)
    if m and not existentes.get("documento"):
        out["documento"] = m.group(1)
    return out


# --------------------------------------------------------------------------
# Capa 2 · Extracción estructurada con Gemini (responseSchema)
# --------------------------------------------------------------------------
_PERFIL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "hogar": {"type": "string", "enum": ["solo", "pareja", "pareja_hijos", "familia"]},
        "vehiculo": {"type": "string", "enum": ["no", "particular", "comercial", "moto"]},
        "dependientes": {"type": "integer"},
        "ocupacion": {"type": "string", "enum": ["empleado", "independiente", "pensionado", "otro"]},
        "rango_edad": {"type": "string", "enum": ["18-30", "31-45", "46-60", "60+"]},
        "prioridad": {"type": "string", "enum": [
            "ingreso", "hogar", "vehiculo", "salud", "mascotas", "viajes",
            "exequial", "ahorro", "accidentes", "juridica",
        ]},
        "notas": {"type": "array", "items": {"type": "string"}},
    },
}

_PERFIL_SYS = """Eres un extractor de datos para una aseguradora. Del mensaje del afiliado, extrae SOLO los datos dichos de forma EXPLÍCITA y devuélvelos en el JSON del esquema. Omite todo campo que la persona no haya mencionado.

Reglas:
- FIDELIDAD ABSOLUTA: nunca inventes, infieras ni cambies cantidades. "un gato" => nota "Tiene un gato" (jamás "dos").
- "vivo con mi pareja" -> hogar=pareja; "pareja e hijos" -> pareja_hijos; "solo/a" -> solo.
- "tengo moto" -> vehiculo=moto; "carro particular" -> particular; "carro de trabajo" -> comercial.
- Si pide o le interesa un seguro concreto mapea prioridad: viaje->viajes, exequial/funeraria->exequial, ahorro->ahorro, accidentes->accidentes, legal->juridica, salud->salud, mascota->mascotas, casa->hogar, carro/moto->vehiculo, "proteger a mi familia si falto"->ingreso.
- Mascotas, familiares a cargo, negocios, viajes o riesgos van SIEMPRE también en "notas" como frases cortas ("Tiene un gato", "Viaja pronto a Europa").
- Si el mensaje no aporta datos, devuelve un objeto vacío {}."""

_DATOS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "nombre": {"type": "string", "description": "Nombre completo del afiliado"},
        "correo": {"type": "string"},
        "telefono": {"type": "string"},
        "documento": {"type": "string"},
        "direccion": {"type": "string"},
        "marca": {"type": "string"},
        "modelo": {"type": "string"},
        "anio": {"type": "string"},
        "placa": {"type": "string"},
        "cilindraje": {"type": "string"},
        "mascota_nombre": {"type": "string"},
        "mascota_especie": {"type": "string"},
        "mascota_raza": {"type": "string"},
        "mascota_edad": {"type": "string"},
        "viaje_destino": {"type": "string"},
        "viaje_inicio": {"type": "string"},
        "viaje_fin": {"type": "string"},
    },
}

_DATOS_SYS = """Eres un extractor de datos de contratación para una aseguradora. Del mensaje del afiliado extrae SOLO los datos presentes de forma explícita (nombre completo, contacto, datos del carro/moto/mascota/viaje) según el esquema. Nunca inventes valores; si un dato no aparece, omítelo. "nombre" solo si la persona dice su nombre (ej. "soy Ana Pérez", "me llamo ..."). Si no hay nada, devuelve {}."""


def extract_perfil(user_text: str) -> dict[str, Any]:
    """Perfil de necesidades del último mensaje. Nunca lanza: si Gemini falla,
    devuelve {} y la conversación sigue."""
    try:
        data = llm.extract_json(_PERFIL_SYS, user_text, _PERFIL_SCHEMA)
    except Exception as e:  # noqa: BLE001
        logger.warning("extract_perfil falló: %s", e)
        return {}
    return {k: v for k, v in data.items() if v not in (None, "", [], 0) or (k == "dependientes" and v == 0)}


def extract_datos(user_text: str) -> dict[str, Any]:
    """Datos de contratación (contacto y bien asegurado) del último mensaje."""
    try:
        data = llm.extract_json(_DATOS_SYS, user_text, _DATOS_SCHEMA)
    except Exception as e:  # noqa: BLE001
        logger.warning("extract_datos falló: %s", e)
        return {}
    return {k: str(v).strip() for k, v in data.items() if v not in (None, "")}

"""
Capa de acceso al modelo de lenguaje: Google Gemini (API REST v1beta).

Expone dos operaciones:
  - chat(messages, tools)  -> mensaje normalizado {"role","content","tool_calls"}
  - extract_json(...)      -> extracción con salida JSON garantizada (responseSchema)

El historial interno es neutro:
  {"role": "system"|"user"|"assistant"|"tool", "content": str,
   "tool_calls": [{"name", "arguments"}], "name": str}
y aquí se convierte al formato de Gemini (contents / parts / functionCall).
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import requests

from .config import settings

logger = logging.getLogger("clara.llm")

_RETRYABLE = {429, 500, 502, 503, 504}


class LLMError(RuntimeError):
    """Error definitivo del proveedor de LLM (tras reintentos)."""


def _is_vertex_key() -> bool:
    """Las claves 'AQ....' son de Vertex AI en modo Express y usan el endpoint
    aiplatform.googleapis.com; las 'AIza...' (AI Studio) usan
    generativelanguage.googleapis.com."""
    return settings.GEMINI_API_KEY.startswith("AQ.")


def _endpoint_url() -> str:
    model = settings.GEMINI_MODEL
    if _is_vertex_key():
        return f"https://aiplatform.googleapis.com/v1/publishers/google/models/{model}:generateContent"
    return f"{settings.GEMINI_BASE_URL}/models/{model}:generateContent"


def health() -> dict[str, Any]:
    return {
        "provider": "gemini (vertex express)" if _is_vertex_key() else "gemini (ai studio)",
        "model": settings.GEMINI_MODEL,
        "ready": bool(settings.GEMINI_API_KEY),
    }


# --------------------------------------------------------------------------
# Llamada base a generateContent con reintentos
# --------------------------------------------------------------------------
def _generate(payload: dict[str, Any]) -> dict[str, Any]:
    if not settings.GEMINI_API_KEY:
        raise LLMError("Falta GEMINI_API_KEY en el entorno (.env).")
    url = _endpoint_url()
    last_error: str = ""
    for attempt in range(settings.LLM_MAX_RETRIES + 1):
        try:
            r = requests.post(
                url,
                params={"key": settings.GEMINI_API_KEY},
                json=payload,
                timeout=settings.LLM_TIMEOUT,
            )
        except requests.RequestException as e:
            last_error = f"error de red: {e}"
            logger.warning("Gemini intento %d falló: %s", attempt + 1, last_error)
            time.sleep(1.5 * (attempt + 1))
            continue
        if r.status_code in _RETRYABLE:
            last_error = f"HTTP {r.status_code}: {r.text[:300]}"
            logger.warning("Gemini intento %d falló: %s", attempt + 1, last_error)
            time.sleep(1.5 * (attempt + 1))
            continue
        if not r.ok:
            raise LLMError(f"Gemini rechazó la petición (HTTP {r.status_code}): {r.text[:300]}")
        return r.json()
    raise LLMError(f"Gemini no respondió tras {settings.LLM_MAX_RETRIES + 1} intentos ({last_error}).")


# --------------------------------------------------------------------------
# chat con herramientas
# --------------------------------------------------------------------------
def chat(messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    system, contents = _to_gemini_contents(messages)
    payload: dict[str, Any] = {
        "contents": contents,
        "generationConfig": {"temperature": settings.LLM_TEMPERATURE},
    }
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}
    if tools:
        payload["tools"] = [{"functionDeclarations": [_to_declaration(t) for t in tools]}]

    data = _generate(payload)
    return _parse_candidate(data)


def _parse_candidate(data: dict[str, Any]) -> dict[str, Any]:
    candidates = data.get("candidates") or []
    if not candidates:
        block = (data.get("promptFeedback") or {}).get("blockReason", "sin candidatos")
        raise LLMError(f"Gemini no devolvió respuesta ({block}).")
    parts = (candidates[0].get("content") or {}).get("parts") or []
    text_chunks: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    for p in parts:
        if "text" in p:
            text_chunks.append(p["text"])
        elif "functionCall" in p:
            fc = p["functionCall"]
            args = fc.get("args") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            tool_calls.append({"name": fc.get("name", ""), "arguments": args})
    return {
        "role": "assistant",
        "content": "".join(text_chunks).strip(),
        "tool_calls": tool_calls,
    }


# --------------------------------------------------------------------------
# Extracción estructurada (JSON garantizado por responseSchema)
# --------------------------------------------------------------------------
def extract_json(system: str, user_text: str, schema: dict[str, Any] | None = None) -> dict[str, Any]:
    """Pide a Gemini un objeto JSON. Con `schema` la salida queda restringida
    al esquema (modo JSON nativo del modelo): mucho más fiable que parsear texto."""
    gen: dict[str, Any] = {"temperature": 0.0, "responseMimeType": "application/json"}
    if schema:
        gen["responseSchema"] = _to_gemini_schema(schema)
    payload = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user_text}]}],
        "generationConfig": gen,
    }
    data = _generate(payload)
    msg = _parse_candidate(data)
    try:
        out = json.loads(msg["content"] or "{}")
        return out if isinstance(out, dict) else {}
    except json.JSONDecodeError:
        logger.warning("extract_json: respuesta no era JSON válido: %r", msg["content"][:200])
        return {}


# --------------------------------------------------------------------------
# Conversión de formatos
# --------------------------------------------------------------------------
def _to_gemini_contents(messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """Separa el system prompt y convierte el historial neutro a contents."""
    system = ""
    contents: list[dict[str, Any]] = []
    for m in messages:
        role = m.get("role")
        if role == "system":
            system = m.get("content", "")
        elif role == "user":
            contents.append({"role": "user", "parts": [{"text": m.get("content", "") or " "}]})
        elif role == "assistant":
            parts: list[dict[str, Any]] = []
            if m.get("content"):
                parts.append({"text": m["content"]})
            for tc in m.get("tool_calls") or []:
                parts.append({"functionCall": {"name": tc.get("name", ""), "args": tc.get("arguments") or {}}})
            if parts:
                contents.append({"role": "model", "parts": parts})
        elif role == "tool":
            result: Any = m.get("content", "")
            if isinstance(result, str):
                try:
                    result = json.loads(result)
                except json.JSONDecodeError:
                    result = {"resultado": result}
            if not isinstance(result, dict):
                result = {"resultado": result}
            contents.append({
                "role": "user",
                "parts": [{"functionResponse": {"name": m.get("name", ""), "response": result}}],
            })
    return system, contents


def _to_declaration(tool: dict[str, Any]) -> dict[str, Any]:
    """Convierte una tool estilo OpenAI ({'type':'function','function':{...}})
    a una functionDeclaration de Gemini."""
    fn = tool.get("function", tool)
    decl = {"name": fn.get("name", ""), "description": fn.get("description", "")}
    params = fn.get("parameters")
    if params and params.get("properties"):
        decl["parameters"] = _to_gemini_schema(params)
    return decl


_TYPE_MAP = {
    "object": "OBJECT", "string": "STRING", "integer": "INTEGER",
    "number": "NUMBER", "boolean": "BOOLEAN", "array": "ARRAY",
}


def _to_gemini_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Adapta un JSON Schema al subconjunto OpenAPI que espera Gemini."""
    out: dict[str, Any] = {}
    t = schema.get("type")
    if isinstance(t, str):
        out["type"] = _TYPE_MAP.get(t.lower(), t.upper())
    for key in ("description", "enum", "required", "nullable"):
        if key in schema:
            out[key] = schema[key]
    if "properties" in schema:
        out["properties"] = {k: _to_gemini_schema(v) for k, v in schema["properties"].items()}
    if "items" in schema:
        out["items"] = _to_gemini_schema(schema["items"])
    return out

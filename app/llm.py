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


def _provider() -> str:
    return settings.llm_provider


def health() -> dict[str, Any]:
    labels = {
        "anthropic": "claude (anthropic)",
        "vertex": "gemini (vertex express)",
        "aistudio": "gemini (ai studio)",
    }
    if _provider() == "ollama":
        remoto = "huggingface" in settings.OLLAMA_BASE_URL
        return {
            "provider": "modelo remoto (hugging face)" if remoto else "modelo local (ollama)",
            "model": settings.llm_model,
            "ready": bool(settings.HF_TOKEN) if remoto else True,
        }
    return {
        "provider": labels.get(_provider(), _provider()),
        "model": settings.llm_model,
        "ready": bool(settings.GEMINI_API_KEY),
    }


# --------------------------------------------------------------------------
# POST genérico con reintentos (compartido por Gemini y Anthropic)
# --------------------------------------------------------------------------
def _post(url: str, *, headers: dict[str, str] | None = None,
          params: dict[str, str] | None = None, payload: dict[str, Any],
          label: str) -> dict[str, Any]:
    if settings.llm_needs_key and not settings.GEMINI_API_KEY:
        raise LLMError("Falta la clave del modelo (GEMINI_API_KEY) en el entorno (.env).")
    last_error: str = ""
    for attempt in range(settings.LLM_MAX_RETRIES + 1):
        try:
            r = requests.post(url, headers=headers, params=params, json=payload,
                              timeout=settings.LLM_TIMEOUT)
        except requests.RequestException as e:
            last_error = f"error de red: {e}"
            logger.warning("%s intento %d falló: %s", label, attempt + 1, last_error)
            time.sleep(1.5 * (attempt + 1))
            continue
        if r.status_code in _RETRYABLE:
            last_error = f"HTTP {r.status_code}: {r.text[:300]}"
            logger.warning("%s intento %d falló: %s", label, attempt + 1, last_error)
            time.sleep(1.5 * (attempt + 1))
            continue
        if not r.ok:
            raise LLMError(f"{label} rechazó la petición (HTTP {r.status_code}): {r.text[:300]}")
        return r.json()
    raise LLMError(f"{label} no respondió tras {settings.LLM_MAX_RETRIES + 1} intentos ({last_error}).")


def _generate(payload: dict[str, Any]) -> dict[str, Any]:
    """Llamada base a Gemini generateContent."""
    return _post(_endpoint_url(), params={"key": settings.GEMINI_API_KEY},
                 payload=payload, label="Gemini")


# --------------------------------------------------------------------------
# chat con herramientas
# --------------------------------------------------------------------------
def chat(messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    if _provider() == "ollama":
        return _openai_chat(messages, tools)
    if _provider() == "anthropic":
        return _anthropic_chat(messages, tools)
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
    """Pide al modelo un objeto JSON. Con `schema` la salida queda restringida
    al esquema: mucho más fiable que parsear texto."""
    if _provider() == "ollama":
        return _openai_extract(system, user_text, schema)
    if _provider() == "anthropic":
        return _anthropic_extract(system, user_text, schema)
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
# Backend compatible con OpenAI (Ollama local / router de Hugging Face)
#
# Ambos exponen /chat/completions con el mismo contrato, así que un solo
# backend cubre los dos despliegues: solo cambia OLLAMA_BASE_URL (y el token).
# Ventaja: las tools de agent.py ya vienen en formato OpenAI y pasan sin
# conversión — a diferencia de Gemini y Anthropic, que sí requieren adaptador.
# --------------------------------------------------------------------------
_THINK_OPEN = "<think>"
_THINK_CLOSE = "</think>"


def _strip_think(text: str) -> str:
    """Elimina los bloques de razonamiento interno (<think>...</think>) que
    emiten modelos como Qwen3. Sin esto se filtrarían al chat del afiliado."""
    while True:
        start = text.find(_THINK_OPEN)
        if start == -1:
            break
        end = text.find(_THINK_CLOSE, start)
        if end == -1:
            # Bloque sin cerrar: se descarta desde la apertura.
            text = text[:start]
            break
        text = text[:start] + text[end + len(_THINK_CLOSE):]
    return text.strip()


def _openai_headers() -> dict[str, str]:
    headers = {"content-type": "application/json"}
    if settings.HF_TOKEN:
        headers["authorization"] = f"Bearer {settings.HF_TOKEN}"
    return headers


def _openai_url(path: str) -> str:
    return f"{settings.OLLAMA_BASE_URL.rstrip('/')}/{path.lstrip('/')}"


def _openai_chat(messages: list[dict[str, Any]],
                 tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": settings.OLLAMA_MODEL,
        "messages": _to_openai_messages(messages),
        "temperature": settings.LLM_TEMPERATURE,
        "max_tokens": settings.LLM_MAX_TOKENS,
        "stream": False,
    }
    if tools:
        # Las tools ya están en formato OpenAI; solo se envuelven las que
        # vengan "planas" (sin la clave 'function').
        payload["tools"] = [
            t if "function" in t else {"type": "function", "function": t} for t in tools
        ]
    data = _post(_openai_url("chat/completions"), headers=_openai_headers(),
                 payload=payload, label="Modelo")
    return _parse_openai(data)


def _openai_extract(system: str, user_text: str,
                    schema: dict[str, Any] | None) -> dict[str, Any]:
    """Extracción JSON. Con esquema se usa forced tool-use, que es lo que mejor
    soportan tanto Ollama como los proveedores del router de HF."""
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_text},
    ]
    payload: dict[str, Any] = {
        "model": settings.OLLAMA_MODEL,
        "messages": messages,
        "temperature": 0.0,
        "max_tokens": settings.LLM_MAX_TOKENS,
        "stream": False,
    }
    if schema:
        payload["tools"] = [{
            "type": "function",
            "function": {"name": "emitir", "description": "Devuelve los datos extraídos.",
                         "parameters": _clean_schema(schema)},
        }]
        payload["tool_choice"] = {"type": "function", "function": {"name": "emitir"}}
    else:
        payload["response_format"] = {"type": "json_object"}

    data = _post(_openai_url("chat/completions"), headers=_openai_headers(),
                 payload=payload, label="Modelo")
    msg = _parse_openai(data)
    for call in msg["tool_calls"]:
        if call["name"] == "emitir":
            return call["arguments"] if isinstance(call["arguments"], dict) else {}
    try:
        out = json.loads(msg["content"] or "{}")
        return out if isinstance(out, dict) else {}
    except json.JSONDecodeError:
        logger.warning("extract_json: respuesta no era JSON válido: %r", msg["content"][:200])
        return {}


def _parse_openai(data: dict[str, Any]) -> dict[str, Any]:
    choices = data.get("choices") or []
    if not choices:
        detail = data.get("error") or data
        raise LLMError(f"El modelo no devolvió respuesta ({str(detail)[:200]}).")
    msg = choices[0].get("message") or {}
    tool_calls: list[dict[str, Any]] = []
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function") or {}
        args = fn.get("arguments")
        # OpenAI entrega los argumentos como string JSON; Ollama a veces como dict.
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                logger.warning("tool_call con argumentos no parseables: %r", args[:200])
                args = {}
        tool_calls.append({"name": fn.get("name", ""), "arguments": args or {}})
    return {
        "role": "assistant",
        "content": _strip_think(msg.get("content") or ""),
        "tool_calls": tool_calls,
    }


def _to_openai_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convierte el historial neutro al formato de /chat/completions.
    El historial no guarda ids de tool_call, así que se sintetizan y se
    emparejan por orden con sus resultados (misma estrategia que Anthropic)."""
    out: list[dict[str, Any]] = []
    id_queue: list[str] = []
    counter = 0

    for m in messages:
        role = m.get("role")
        if role == "system":
            out.append({"role": "system", "content": m.get("content", "")})
        elif role == "user":
            out.append({"role": "user", "content": m.get("content") or " "})
        elif role == "assistant":
            msg: dict[str, Any] = {"role": "assistant", "content": m.get("content") or ""}
            calls = []
            for tc in m.get("tool_calls") or []:
                tid = f"call_{counter}"
                counter += 1
                id_queue.append(tid)
                calls.append({
                    "id": tid,
                    "type": "function",
                    "function": {
                        "name": tc.get("name", ""),
                        "arguments": json.dumps(tc.get("arguments") or {}, ensure_ascii=False),
                    },
                })
            if calls:
                msg["tool_calls"] = calls
            out.append(msg)
        elif role == "tool":
            tid = id_queue.pop(0) if id_queue else f"call_{counter}"
            result = m.get("content", "")
            if not isinstance(result, str):
                result = json.dumps(result, ensure_ascii=False)
            out.append({"role": "tool", "tool_call_id": tid,
                        "name": m.get("name", ""), "content": result})
    return out


# --------------------------------------------------------------------------
# Backend Anthropic / Claude (Messages API)
# --------------------------------------------------------------------------
def _anthropic_generate(system: str, messages: list[dict[str, Any]],
                        tools: list[dict[str, Any]] | None = None,
                        tool_choice: dict[str, Any] | None = None,
                        temperature: float | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": settings.ANTHROPIC_MODEL,
        "max_tokens": settings.LLM_MAX_TOKENS,
        "messages": messages,
    }
    # Modelos recientes (p. ej. Opus 4.8) deprecaron `temperature`; solo se envía
    # si está explícitamente habilitado por entorno para modelos que lo aceptan.
    if settings.ANTHROPIC_SEND_TEMPERATURE:
        payload["temperature"] = settings.LLM_TEMPERATURE if temperature is None else temperature
    if system:
        payload["system"] = system
    if tools:
        payload["tools"] = tools
    if tool_choice:
        payload["tool_choice"] = tool_choice
    headers = {
        "x-api-key": settings.GEMINI_API_KEY,
        "anthropic-version": settings.ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    base = settings.ANTHROPIC_BASE_URL.rstrip("/")
    if not base.endswith("/v1"):
        base += "/v1"   # robusto ante ANTHROPIC_BASE_URL con o sin sufijo de versión
    return _post(f"{base}/messages", headers=headers, payload=payload, label="Claude")


def _anthropic_chat(messages: list[dict[str, Any]],
                    tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    system, msgs = _to_anthropic_messages(messages)
    anth_tools = [_to_anthropic_tool(t) for t in tools] if tools else None
    data = _anthropic_generate(system, msgs, anth_tools)
    return _parse_anthropic(data)


def _anthropic_extract(system: str, user_text: str,
                       schema: dict[str, Any] | None) -> dict[str, Any]:
    """Extracción JSON garantizada vía forced tool-use: se define una única
    herramienta con el esquema como input_schema y se obliga al modelo a llamarla."""
    if not schema:
        data = _anthropic_generate(system, [{"role": "user", "content": user_text}], temperature=0.0)
        msg = _parse_anthropic(data)
        try:
            out = json.loads(msg["content"] or "{}")
            return out if isinstance(out, dict) else {}
        except json.JSONDecodeError:
            return {}
    tool = {"name": "emitir", "description": "Devuelve los datos extraídos.",
            "input_schema": _clean_schema(schema)}
    data = _anthropic_generate(system, [{"role": "user", "content": user_text}],
                               tools=[tool], tool_choice={"type": "tool", "name": "emitir"},
                               temperature=0.0)
    for block in (data.get("content") or []):
        if block.get("type") == "tool_use" and block.get("name") == "emitir":
            inp = block.get("input")
            return inp if isinstance(inp, dict) else {}
    return {}


def _parse_anthropic(data: dict[str, Any]) -> dict[str, Any]:
    if data.get("type") == "error" or "content" not in data:
        raise LLMError(f"Claude no devolvió respuesta ({data.get('error', data)}).")
    text_chunks: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    for block in data.get("content") or []:
        btype = block.get("type")
        if btype == "text":
            text_chunks.append(block.get("text", ""))
        elif btype == "tool_use":
            tool_calls.append({"name": block.get("name", ""), "arguments": block.get("input") or {}})
    return {"role": "assistant", "content": "".join(text_chunks).strip(), "tool_calls": tool_calls}


def _to_anthropic_tool(tool: dict[str, Any]) -> dict[str, Any]:
    fn = tool.get("function", tool)
    params = fn.get("parameters") or {"type": "object", "properties": {}}
    return {"name": fn.get("name", ""), "description": fn.get("description", ""),
            "input_schema": _clean_schema(params)}


def _clean_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """JSON Schema estándar (Anthropic acepta JSON Schema directamente)."""
    out: dict[str, Any] = {}
    for key in ("type", "description", "enum", "required", "items", "properties"):
        if key in schema:
            if key == "properties":
                out[key] = {k: _clean_schema(v) for k, v in schema[key].items()}
            elif key == "items":
                out[key] = _clean_schema(schema[key])
            else:
                out[key] = schema[key]
    out.setdefault("type", "object")
    return out


def _to_anthropic_messages(messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """Convierte el historial neutro al formato de la Messages API de Anthropic.
    Sintetiza ids de tool_use (el historial no los guarda), agrupa resultados de
    herramientas consecutivos en un solo mensaje de usuario y descarta el saludo
    inicial del asistente (Anthropic exige empezar por 'user')."""
    system = ""
    out: list[dict[str, Any]] = []
    id_queue: list[str] = []
    pending_results: list[dict[str, Any]] = []
    counter = 0

    def flush():
        nonlocal pending_results
        if pending_results:
            out.append({"role": "user", "content": pending_results})
            pending_results = []

    for m in messages:
        role = m.get("role")
        if role == "system":
            system = m.get("content", "") or system
        elif role == "user":
            flush()
            out.append({"role": "user", "content": [{"type": "text", "text": m.get("content") or " "}]})
        elif role == "assistant":
            flush()
            content: list[dict[str, Any]] = []
            if m.get("content"):
                content.append({"type": "text", "text": m["content"]})
            for tc in m.get("tool_calls") or []:
                tid = f"call_{counter}"
                counter += 1
                id_queue.append(tid)
                content.append({"type": "tool_use", "id": tid,
                                "name": tc.get("name", ""), "input": tc.get("arguments") or {}})
            # Anthropic no admite un mensaje de asistente antes del primer 'user'.
            if not out and not content:
                continue
            if not out:
                # Saludo inicial: se omite; el system prompt ya indica que Clara saludó.
                continue
            if not content:
                content = [{"type": "text", "text": " "}]
            out.append({"role": "assistant", "content": content})
        elif role == "tool":
            tid = id_queue.pop(0) if id_queue else f"call_{counter}"
            result = m.get("content", "")
            if not isinstance(result, str):
                result = json.dumps(result, ensure_ascii=False)
            pending_results.append({"type": "tool_result", "tool_use_id": tid, "content": result})
    flush()
    # Garantía dura: el primer mensaje debe ser de 'user'.
    while out and out[0]["role"] != "user":
        out.pop(0)
    return system, out


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

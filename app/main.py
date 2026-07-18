"""
API de Clara (FastAPI) + entrega de la interfaz.

Endpoints:
  GET  /                          -> interfaz (static/index.html)
  GET  /api/health                -> estado del servicio y del proveedor LLM
  POST /api/session               -> crea una sesión y devuelve el saludo inicial
  POST /api/chat                  -> turno de conversación con el agente
  POST /api/firmar-contrato       -> firma electrónica + enlace de pago
  GET  /docs/{archivo}            -> PDF generado (resumen / contrato / póliza)
  GET  /pay/{session}/{token}     -> checkout de pago simulado (estilo Wompi)
  POST /pay/{session}/{token}     -> procesa la tarjeta (sandbox) y dispara el webhook
  GET  /api/pago-estado/{session} -> estado de pagos (polling del frontend)
  POST /api/confirmar-pago        -> emite la póliza y Clara confirma en el chat

Ejecuta:  python server.py   (o uvicorn app.main:app)
"""

from __future__ import annotations

import logging
import pathlib

from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__, agent, knowledge as kb, llm, payments, store
from .config import settings

logger = logging.getLogger("clara.api")

app = FastAPI(
    title="Clara · Venta automatizada de seguros",
    version=__version__,
    docs_url=None if settings.is_production else "/api/docs",
    redoc_url=None,
    openapi_url=None if settings.is_production else "/openapi.json",
)

SESSIONS: dict[str, agent.Session] = {}

app.mount("/static", StaticFiles(directory=str(settings.STATIC_DIR)), name="static")

SALUDO = (
    "Hola, soy Clara, la asesora digital de seguros de Colsubsidio. "
    "Antes de empezar: tus datos se tratan conforme a la Política de Tratamiento de Datos "
    "Personales de Colsubsidio (Ley 1581 de 2012) y puedes solicitar su eliminación cuando quieras. "
    "Para empezar, cuéntame: ¿ya sabes qué seguro buscas o prefieres que te ayude a encontrar "
    "la mejor opción para ti?"
)


class SessionReq(BaseModel):
    canal: str = "WhatsApp"


class ChatReq(BaseModel):
    session_id: str
    text: str = Field(min_length=1, max_length=2000)


class ConfirmarReq(BaseModel):
    session_id: str
    token: str


class FirmaReq(BaseModel):
    session_id: str
    producto: str


@app.on_event("startup")
def _startup():
    purged = store.purge_old_sessions()
    logger.info(
        "Clara v%s lista · entorno=%s · modelo=%s · sesiones purgadas=%d",
        __version__, settings.ENV, settings.GEMINI_MODEL, purged,
    )


def _get_session(sid: str) -> agent.Session:
    s = SESSIONS.get(sid)
    if s is None:
        # Recuperación tras reinicio: la sesión pudo quedar persistida en SQLite.
        snap = store.load_session(sid)
        if snap:
            s = agent.Session.from_snapshot(snap)
            SESSIONS[sid] = s
            logger.info("Sesión %s restaurada desde SQLite", sid)
    if s is None:
        raise HTTPException(status_code=404, detail="Sesión no encontrada. Reinicia la demo.")
    return s


# --------------------------------------------------------------------------
# Interfaz y estáticos
# --------------------------------------------------------------------------
@app.get("/", include_in_schema=False)
def index():
    return FileResponse(settings.INDEX_HTML)


@app.get("/docs/{archivo}")
def documento(archivo: str):
    safe = pathlib.Path(archivo).name  # evita path traversal
    ruta = settings.DOCS_DIR / safe
    if not ruta.exists():
        raise HTTPException(status_code=404, detail="Documento no encontrado.")
    return FileResponse(ruta, media_type="application/pdf")


@app.get("/api/health")
def health():
    return {"ok": True, "version": __version__, "env": settings.ENV,
            "llm": llm.health(), "store": store.stats()}


# --------------------------------------------------------------------------
# Conversación
# --------------------------------------------------------------------------
@app.post("/api/session")
def crear_sesion(req: SessionReq):
    s = agent.Session(canal=req.canal)
    SESSIONS[s.id] = s
    s._log("db", "SESSIONS", "INSERT sessions · estado DIAGNOSTICO, perfil vacío")
    s.messages.append({"role": "assistant", "content": SALUDO})
    s.persist()
    return {"session_id": s.id, "reply": SALUDO, "estado": s.estado,
            "perfil": s.perfil, "audit": s.audit, "canal": s.canal}


@app.post("/api/chat")
def chat(req: ChatReq):
    s = _get_session(req.session_id)
    try:
        out = agent.run_turn(s, req.text)
    except llm.LLMError as e:
        logger.error("Turno fallido en sesión %s: %s", s.id, e)
        raise HTTPException(status_code=503, detail=str(e))
    return JSONResponse(out)


# --------------------------------------------------------------------------
# Firma del contrato: registra consentimiento y crea el enlace de pago
# --------------------------------------------------------------------------
@app.post("/api/firmar-contrato")
def firmar_contrato(req: FirmaReq):
    s = _get_session(req.session_id)
    producto = (req.producto or "").lower()
    if producto not in kb.CATALOG:
        raise HTTPException(status_code=400, detail="Producto inválido.")
    s.audit = []
    s.actions = []
    try:
        res = s.firmar_contrato(producto)
    except Exception as e:  # noqa: BLE001
        logger.exception("Fallo firmando contrato en sesión %s", s.id)
        raise HTTPException(status_code=500, detail=f"No se pudo firmar el contrato: {e}")
    s.persist()
    contrato = res["contrato"]
    pago = res["pago"]
    nombre = (s.datos.get("nombre") or "").split(" ")[0] or "listo"
    reply = (
        f"Perfecto, {nombre}. Quedó firmado tu contrato del {contrato['producto']} "
        f"(solicitud {contrato['solicitud']}). Te dejé el enlace de pago seguro por "
        f"{kb.format_cop(pago['precio'])} al mes; tu referencia de pago es {pago['referencia']}. "
        f"En cuanto completes el pago, emito tu póliza al instante."
    )
    return JSONResponse({
        "reply": reply, "estado": s.estado, "perfil": s.perfil,
        "audit": s.audit, "actions": s.actions, "verified": True,
    })


# --------------------------------------------------------------------------
# Pago (checkout sandbox con tarjeta + webhook + confirmación del agente)
# --------------------------------------------------------------------------
@app.get("/pay/{session_id}/{token}", response_class=HTMLResponse, include_in_schema=False)
def checkout(session_id: str, token: str):
    try:
        s = _get_session(session_id)
    except HTTPException:
        return HTMLResponse("<h3>Enlace de pago no válido o expirado.</h3>", status_code=404)
    pago = s.payments.get(token)
    if not pago:
        return HTMLResponse("<h3>Enlace de pago no válido o expirado.</h3>", status_code=404)
    prod = kb.CATALOG.get(pago["producto"], {})
    return HTMLResponse(payments.checkout_html(
        session_id, token, prod.get("nombre", pago["producto"]),
        payments.format_precio(pago), pago.get("referencia", ""), pago,
    ))


@app.post("/pay/{session_id}/{token}", response_class=HTMLResponse, include_in_schema=False)
def procesar_pago(session_id: str, token: str,
                  card: str = Form(""), exp: str = Form(""), cvc: str = Form("")):
    try:
        s = _get_session(session_id)
    except HTTPException:
        return HTMLResponse("<h3>Pago no encontrado.</h3>", status_code=404)
    pago = s.payments.get(token)
    if not pago:
        return HTMLResponse("<h3>Pago no encontrado.</h3>", status_code=404)
    if pago["estado"] == "aprobado":
        prod = kb.CATALOG.get(pago["producto"], {})
        return HTMLResponse(payments.result_html(True, prod.get("nombre", ""),
                                                 payments.format_precio(pago),
                                                 pago.get("referencia", ""), pago, ya_estaba=True))

    resultado = payments.process_card(pago, card, exp, cvc)
    if resultado["estado"] == "aprobado":
        s._log("db", "WOMPI", f"Webhook APPROVED · trx {resultado['trx']} · "
                              f"referencia {pago.get('referencia', '—')} · tarjeta ****{pago.get('ultimos4')}")
    else:
        s._log("db", "WOMPI", f"Webhook DECLINED · trx {resultado['trx']} · {resultado['detalle']}")
    s.persist()
    store.append_audit(s.id, s.audit)

    prod = kb.CATALOG.get(pago["producto"], {})
    if resultado["estado"] == "aprobado":
        return HTMLResponse(payments.result_html(True, prod.get("nombre", ""),
                                                 payments.format_precio(pago),
                                                 pago.get("referencia", ""), pago))
    # Rechazado: volver a mostrar el checkout con el motivo para reintentar.
    return HTMLResponse(payments.checkout_html(
        session_id, token, prod.get("nombre", pago["producto"]),
        payments.format_precio(pago), pago.get("referencia", ""), pago,
    ))


@app.get("/api/pago-estado/{session_id}")
def pago_estado(session_id: str):
    s = _get_session(session_id)
    return {"payments": {t: {"producto": p["producto"], "estado": p["estado"],
                             "confirmado": p.get("confirmado", False),
                             "intentos": p.get("intentos", 0)}
                         for t, p in s.payments.items()}}


@app.post("/api/confirmar-pago")
def confirmar_pago(req: ConfirmarReq):
    """Tras el pago aprobado: emite la póliza (determinístico) y deja que Clara
    confirme en lenguaje natural."""
    s = _get_session(req.session_id)
    pago = s.payments.get(req.token)
    if not pago:
        raise HTTPException(status_code=404, detail="Pago no encontrado.")
    if pago["estado"] != "aprobado":
        raise HTTPException(status_code=400, detail="El pago aún no está aprobado.")
    if pago.get("confirmado"):
        raise HTTPException(status_code=409, detail="Este pago ya fue confirmado.")

    producto = pago["producto"]
    s.audit = []
    s.actions = []
    poliza = s.emitir_poliza(producto, pago.get("referencia"))
    pre_audit = list(s.audit)
    poliza_action = next((a for a in s.actions if a["type"] == "poliza"),
                         {"type": "poliza", "data": s.poliza})
    pago["confirmado"] = True

    evento = (
        f"El pago fue APROBADO (referencia {pago.get('referencia', '—')}, transacción {pago.get('trx', '—')}) "
        f"y la póliza N.º {poliza['numero']} del {poliza['producto']} quedó emitida y activa. Ya enviamos la "
        f"carátula al canal del afiliado. Confírmale con calidez que ya quedó asegurado, menciona su número de "
        f"póliza y la referencia de pago, explica en máximo 3 líneas cómo usar la póliza (línea 018000 94 7900, "
        f"qué hacer ante un siniestro) y ofrécele una encuesta de satisfacción del 1 al 5."
    )
    try:
        out = agent.run_turn(s, user_text=None, system_event=evento)
    except llm.LLMError:
        logger.warning("Emisión confirmada pero el modelo no respondió; usando texto de respaldo.")
        out = {"reply": f"Ya quedaste asegurado. Tu póliza N.º {poliza['numero']} está activa.",
               "estado": s.estado, "perfil": s.perfil, "audit": [], "actions": [], "verified": False}
        s.persist()
    out["audit"] = pre_audit + out.get("audit", [])
    if not any(a["type"] == "poliza" for a in out.get("actions", [])):
        out.setdefault("actions", []).append(poliza_action)
    return JSONResponse(out)

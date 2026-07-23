"""
API de Clara (FastAPI) + entrega de la interfaz.

Endpoints:
  GET  /                          -> interfaz (static/index.html)
  GET  /api/health                -> estado del servicio y del proveedor LLM
  POST /api/session               -> crea una sesión y devuelve el saludo inicial
  POST /api/chat                  -> turno de conversación con el agente
  POST /api/firmar-contrato       -> firma electrónica + enlace de pago
  GET  /docs/{archivo}            -> PDF generado (resumen / contrato / vinculación)
  GET  /pay/{session}/{token}     -> checkout de pago simulado (estilo Wompi)
  POST /pay/{session}/{token}     -> procesa la tarjeta (sandbox) y dispara el webhook
  GET  /api/pago-estado/{session} -> estado de pagos (polling del frontend)
  POST /api/confirmar-pago        -> confirma la vinculación (la aseguradora emite la póliza)

Ejecuta:  python server.py   (o uvicorn app.main:app)
"""

from __future__ import annotations

import logging
import pathlib

from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__, agent, knowledge as kb, llm, payments, propension, store
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


# Gancho del saludo personalizado, en segunda persona, según el producto de
# mayor propensión. La razón técnica completa vive en el panel "Propensión".
_GANCHOS = {
    "vida": "cómo proteger el ingreso del que depende tu familia",
    "hogar": "cómo proteger ese hogar que estás estrenando o mejorando",
    "salud": "cómo agilizar la atención en salud tuya y de los tuyos",
    "mascotas": "cómo cuidar la salud de tu mascota",
    "moto": "cómo proteger tu moto",
    "autos": "cómo proteger tu vehículo",
    "juridica": "cómo tener respaldo legal cuando lo necesites",
    "accidentes": "cómo proteger tu ingreso si un accidente te detiene",
    "asistencia_multiple": "cómo resolver emergencias del día a día con una sola asistencia",
    "exequial": "cómo darle tranquilidad a tu familia en los momentos más difíciles",
    "accidentes_exequial": "cómo proteger a tu familia ante un accidente y sus consecuencias",
    "vida_ahorro": "cómo protegerte mientras construyes un ahorro",
    "asistencia_familiar": "cómo tener atención médica en casa para tu familia",
    "viajes": "cómo viajar con la tranquilidad de estar cubierto",
}


class SessionReq(BaseModel):
    canal: str = "WhatsApp"
    serie: str | None = None  # afiliado de la base (muestra demo) para arrancar personalizado


class EstadoSolicitudReq(BaseModel):
    estado: str = Field(pattern="^(nueva|pendiente_pago|pagada|enviada_aseguradora|emitida_aseguradora|cerrada)$")


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
        "Clara v%s lista · entorno=%s · proveedor=%s · modelo=%s · sesiones purgadas=%d",
        __version__, settings.ENV, settings.llm_provider, settings.llm_model, purged,
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

    saludo = SALUDO
    if req.serie:
        af = propension.buscar_demo(req.serie)
        if af is None:
            raise HTTPException(status_code=404, detail=f"Afiliado SERIE {req.serie} no está en la muestra demo.")
        s.set_afiliado(af)
        top = s.propension["productos"][0] if s.propension.get("productos") else None
        gancho = ""
        if top:
            hook = _GANCHOS.get(top["producto_id"], "")
            if hook:
                gancho = f" Por lo que Colsubsidio ya conoce de ti, creo que lo primero que deberíamos mirar juntos es {hook}."
        saludo = (
            "Hola, soy Clara, la asesora digital de seguros de Colsubsidio. "
            "Tus datos se tratan conforme a la Política de Tratamiento de Datos Personales "
            "(Ley 1581 de 2012) y puedes pedir su eliminación cuando quieras. "
            f"Veo que eres parte de la familia Colsubsidio.{gancho} "
            "¿Quieres que te muestre la protección que mejor encaja contigo, o prefieres contarme tú qué buscas?"
        )

    s.messages.append({"role": "assistant", "content": saludo})
    s.persist()
    return {"session_id": s.id, "reply": saludo, "estado": s.estado,
            "perfil": s.perfil, "audit": s.audit, "canal": s.canal,
            "afiliado": s.afiliado, "propension": s.propension}


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
# Propensión: perfiles demo de la base, reglas documentadas y estadísticas
# --------------------------------------------------------------------------
@app.get("/api/afiliados-demo")
def afiliados_demo():
    """Muestra anonimizada de la base real (solo SERIE + variables, sin nombres),
    con la propensión ya explicada para que el jurado compare ofertas por perfil."""
    out = []
    for a in propension.cargar_demo():
        p = a.get("propension") or propension.perfilar(a)
        out.append({**a, "propension": p})
    return {"afiliados": out}


@app.get("/api/propension/reglas")
def propension_reglas():
    """La lógica documentada del reto: cada regla del motor con su condición,
    producto, puntos y razón. Nada de caja negra."""
    return {"reglas": propension.reglas_documentadas(), "stats": propension.cargar_stats()}


# --------------------------------------------------------------------------
# Panel del asesor: Colsubsidio distribuye, no emite. Clara transmite cada
# vinculación empaquetada y el asesor la gestiona con la aseguradora.
# --------------------------------------------------------------------------
@app.get("/asesor", include_in_schema=False)
def asesor_panel():
    return FileResponse(settings.STATIC_DIR / "asesor.html")


@app.get("/api/asesor/solicitudes")
def asesor_solicitudes():
    return {"solicitudes": store.list_solicitudes()}


_ESTADO_AVISO = {
    "enviada_aseguradora": "El asesor envió la solicitud {sol} a la aseguradora para su emisión oficial.",
    "emitida_aseguradora": "La aseguradora emitió oficialmente la póliza de la solicitud {sol}. El proceso quedó completo.",
    "cerrada": "La solicitud {sol} fue cerrada por el asesor.",
}


@app.post("/api/asesor/solicitudes/{solicitud_id}/estado")
def asesor_cambiar_estado(solicitud_id: str, req: EstadoSolicitudReq):
    if not store.set_estado_solicitud(solicitud_id, req.estado):
        raise HTTPException(status_code=404, detail="Solicitud no encontrada.")
    # Lazo de vuelta al afiliado: la sesión queda enterada del avance para que
    # Clara pueda informarlo si el afiliado pregunta por su solicitud.
    aviso = _ESTADO_AVISO.get(req.estado)
    sol = next((x for x in store.list_solicitudes() if x["id"] == solicitud_id), None)
    if aviso and sol:
        try:
            s = _get_session(sol["session_id"])
            s.audit = []
            s._log("db", "ASESOR", f"Solicitud {solicitud_id} → {req.estado} (gestión del asesor)")
            s.messages.append({"role": "system",
                               "content": "[EVENTO DEL SISTEMA] " + aviso.format(sol=solicitud_id)})
            s.persist()
        except HTTPException:
            pass  # sesión expirada: el estado queda igualmente en la bandeja
    return {"ok": True, "id": solicitud_id, "estado": req.estado}


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
        f"En cuanto completes el pago, confirmo tu vinculación al instante."
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
    """Tras el pago aprobado: confirma y radica la vinculación (Colsubsidio
    distribuye, no emite pólizas) y deja que Clara confirme en lenguaje natural.
    La póliza la emitirá la aseguradora desde el panel del asesor."""
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
    vinc = s.confirmar_vinculacion(producto, pago.get("referencia"))
    pre_audit = list(s.audit)
    vinc_action = next((a for a in s.actions if a["type"] == "vinculacion"),
                       {"type": "vinculacion", "data": s.vinculacion})
    pago["confirmado"] = True

    evento = (
        f"El pago fue APROBADO (referencia {pago.get('referencia', '—')}, transacción {pago.get('trx', '—')}) "
        f"y la vinculación al {vinc['producto']} quedó CONFIRMADA y RADICADA con el número {vinc['radicado']}. "
        f"RECUERDA: Colsubsidio distribuye, NO emite pólizas; la aseguradora emitirá la póliza y se la hará llegar. "
        f"Confírmale con calidez que su vinculación quedó lista, menciona su número de radicado y la referencia de "
        f"pago, aclara que la aseguradora expedirá la póliza, dile la línea de servicio 018000 94 7900 y ofrécele "
        f"una encuesta de satisfacción del 1 al 5. No inventes número de póliza."
    )
    try:
        out = agent.run_turn(s, user_text=None, system_event=evento)
    except llm.LLMError:
        logger.warning("Vinculación confirmada pero el modelo no respondió; usando texto de respaldo.")
        out = {"reply": (f"Tu vinculación quedó confirmada y radicada con el número {vinc['radicado']}. "
                         f"La aseguradora emitirá tu póliza y te la hará llegar."),
               "estado": s.estado, "perfil": s.perfil, "audit": [], "actions": [], "verified": False}
        s.persist()
    out["audit"] = pre_audit + out.get("audit", [])
    if not any(a["type"] == "vinculacion" for a in out.get("actions", [])):
        out.setdefault("actions", []).append(vinc_action)
    return JSONResponse(out)

"""
API de Lara (FastAPI) + entrega de la interfaz.

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

import datetime as dt
import logging
import pathlib

from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import (__version__, afiliados_db, agent, base_afiliados, knowledge as kb,
               llm, notify, ofertas, payments, propension, seed, store)
from .config import settings

logger = logging.getLogger("clara.api")

app = FastAPI(
    title="Lara · Venta automatizada de seguros",
    version=__version__,
    docs_url=None if settings.is_production else "/api/docs",
    redoc_url=None,
    openapi_url=None if settings.is_production else "/openapi.json",
)

SESSIONS: dict[str, agent.Session] = {}

app.mount("/static", StaticFiles(directory=str(settings.STATIC_DIR)), name="static")

SALUDO = (
    "Hola, soy Lara, la asesora digital de seguros de Colsubsidio. "
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


class IdentificarReq(BaseModel):
    session_id: str
    documento: str = ""   # número de afiliado / documento; vacío = no afiliado


class EventoReq(BaseModel):
    """Entrada de Cody. La dispara n8n (u otra base de Colsubsidio)."""
    serie: str | None = None          # id del afiliado en la base
    perfil_id: str | None = None      # o el id del perfil vivo (NA-...)
    evento: str                       # p. ej. credito_vivienda_desembolsado
    datos: dict | None = None
    enviar: bool = True               # simular envío por el canal del perfil
    source: str = "api"
    trace_id: str | None = None


class EstadoOfertaReq(BaseModel):
    estado: str = Field(pattern="^(generada|enviada|aceptada|descartada)$")


class BarridoReq(BaseModel):
    """Barrido autónomo del agente de ofertas sobre una muestra de la base real."""
    muestra: int | None = 8           # cuántos afiliados de la base recorrer


class ReengancheReq(BaseModel):
    """Re-enganche de abandonos: minutos de inactividad tras los cuales se
    considera abandonada una conversación con contacto dejado."""
    minutos: int | None = 30


class ChatReq(BaseModel):
    session_id: str
    text: str = Field(min_length=1, max_length=2000)


class ConfirmarReq(BaseModel):
    session_id: str
    token: str


class FirmaReq(BaseModel):
    session_id: str
    producto: str


class AfiliadoCrearReq(BaseModel):
    """Datos con los que Lara (o el equipo) registra un afiliado nuevo. Todos
    opcionales salvo lo mínimo para personalizar; la SERIE la asigna la base."""
    genero: str | None = Field(default=None, pattern="^[FM]$")
    rango_edad: str | None = None
    rango_salarial: str | None = None
    categoria: str | None = None
    segmento_familiar: str | None = None
    segmento_poblacional: str | None = None
    piramide: str | None = None
    empresa: str | None = None
    ciudad: str | None = None
    marcas: dict[str, bool] | None = None
    vivienda: dict[str, object] | None = None
    credito: dict[str, object] | None = None


class AfiliadoActualizarReq(BaseModel):
    """Actualización parcial: solo se aplican los campos editables presentes."""
    genero: str | None = Field(default=None, pattern="^[FM]$")
    rango_edad: str | None = None
    rango_salarial: str | None = None
    categoria: str | None = None
    segmento_familiar: str | None = None
    segmento_poblacional: str | None = None
    piramide: str | None = None
    empresa: str | None = None
    ciudad: str | None = None
    marcas: dict[str, bool] | None = None
    afiliado_activo: bool | None = None


@app.on_event("startup")
def _startup():
    purged = store.purge_old_sessions()
    # Siembra la muestra demo si la base de afiliados está vacía (no bloquea el
    # arranque si Mongo no está listo: sembrar_si_vacia captura sus errores).
    if settings.SEED_MUESTRA > 0:
        sembrado = seed.sembrar_si_vacia(settings.SEED_MUESTRA)
        if sembrado:
            logger.info("Muestra demo sembrada: %s", sembrado)
        try:
            seed.sembrar_abandonos_demo()      # perfiles de abandono para la demo de re-enganche
            seed.sembrar_solicitudes_demo()    # solicitudes con conversación para el panel del asesor
        except Exception as e:  # noqa: BLE001
            logger.warning("No se pudieron sembrar los datos demo: %s", e)
    logger.info(
        "Lara v%s lista · entorno=%s · proveedor=%s · modelo=%s · sesiones purgadas=%d",
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
        # Primero la base real (500k afiliados en Mongo); si no está, se cae al
        # comportamiento demo anterior (muestra precalculada en data/).
        af = afiliados_db.existe_afiliado(req.serie)
        if af is None:
            af = propension.buscar_demo(req.serie)
        if af is None:
            raise HTTPException(status_code=404,
                                detail=f"Afiliado SERIE {req.serie} no está en la base ni en la muestra demo.")
        s.set_afiliado(af)
        top = s.propension["productos"][0] if s.propension.get("productos") else None
        gancho = ""
        if top:
            hook = _GANCHOS.get(top["producto_id"], "")
            if hook:
                gancho = f" Por lo que Colsubsidio ya conoce de ti, creo que lo primero que deberíamos mirar juntos es {hook}."
        saludo = (
            "Hola, soy Lara, la asesora digital de seguros de Colsubsidio. "
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


@app.get("/api/session/{session_id}")
def estado_sesion(session_id: str):
    """Restaura la misma conversación al volver desde Cody o el asesor."""
    s = _get_session(session_id)
    return {
        "session_id": s.id,
        "estado": s.estado,
        "perfil": s.perfil,
        "datos": s.datos,
        "contacto": s.contacto,
        "afiliado": s.afiliado,
        "propension": s.propension,
        "messages": s._transcripcion(limite=100),
    }


@app.post("/api/chat")
def chat(req: ChatReq):
    s = _get_session(req.session_id)
    try:
        out = agent.run_turn(s, req.text)
    except llm.LLMError as e:
        logger.error("Turno fallido en sesión %s: %s", s.id, e)
        raise HTTPException(status_code=503, detail=str(e))
    return JSONResponse(out)


@app.post("/api/identificar")
def identificar(req: IdentificarReq):
    """Identifica a la persona: busca su número en la base. Si es afiliada,
    carga su perfil y propensión; si no, sigue como no afiliada. En ambos casos
    queda un perfil vivo que la conversación seguirá enriqueciendo."""
    s = _get_session(req.session_id)
    res = s.identificar(req.documento)
    s.persist()
    return {"es_afiliado": res["es_afiliado"], "perfil_id": res["perfil_id"],
            "afiliado": s.afiliado, "propension": s.propension}


# --------------------------------------------------------------------------
# Afiliados (base real en Mongo): perfil 360, alta, actualización y ofertas.
# Sirven para validar el flujo y para el uso del equipo.
# --------------------------------------------------------------------------
@app.get("/api/afiliados/{serie}")
def afiliado_perfil(serie: str):
    perfil = afiliados_db.perfil_360(serie)
    if perfil is None:
        raise HTTPException(status_code=404, detail=f"Afiliado SERIE {serie} no encontrado.")
    return perfil


@app.post("/api/afiliados")
def afiliado_crear(req: AfiliadoCrearReq):
    datos = req.model_dump(exclude_none=True)
    doc = afiliados_db.crear_afiliado(datos)
    return {"ok": True, "afiliado": doc}


@app.patch("/api/afiliados/{serie}")
def afiliado_actualizar(serie: str, req: AfiliadoActualizarReq):
    campos = req.model_dump(exclude_none=True)
    if not campos:
        raise HTTPException(status_code=400, detail="No se indicó ningún campo para actualizar.")
    doc = afiliados_db.actualizar_afiliado(serie, campos)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Afiliado SERIE {serie} no encontrado.")
    return {"ok": True, "afiliado": doc}


@app.get("/api/afiliados/{serie}/ofertas")
def afiliado_ofertas(serie: str):
    if afiliados_db.existe_afiliado(serie) is None:
        raise HTTPException(status_code=404, detail=f"Afiliado SERIE {serie} no encontrado.")
    return {"serie": serie,
            "ofertas": afiliados_db.ofertas_para(serie),
            "alertas": afiliados_db.alertas_pendientes(serie)}


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
# Panel del asesor: Colsubsidio distribuye, no emite. Lara transmite cada
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
    # Lara pueda informarlo si el afiliado pregunta por su solicitud.
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


@app.post("/api/asesor/solicitudes/{solicitud_id}/eliminar")
def asesor_eliminar(solicitud_id: str):
    """El asesor descarta una solicitud de la bandeja."""
    if not store.eliminar_solicitud(solicitud_id):
        raise HTTPException(status_code=404, detail="Solicitud no encontrada.")
    return {"ok": True, "id": solicitud_id}


@app.post("/api/asesor/solicitudes/{solicitud_id}/continuar")
def asesor_continuar(solicitud_id: str):
    """Simula que el asesor retoma la conversación: envía la póliza y el link de
    pago al cliente, y el cliente responde. Deja el intercambio en la solicitud y
    avanza el estado (demo del cierre del lado del asesor)."""
    sol = store.get_solicitud(solicitud_id)
    if sol is None:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada.")
    p = sol["payload"]
    ss = p.get("seguro_solicitado") or {}
    datos = p.get("datos_contratante") or {}
    nombre = (datos.get("nombre") or "").split(" ")[0] or "hola"
    aseg = ss.get("aseguradora_elegida") or ss.get("aseguradora") or "la aseguradora"
    prod = ss.get("nombre") or "tu seguro"
    ref = "PAGO-" + solicitud_id.split("-")[-1]
    conv = list(p.get("conversacion") or [])
    conv.append({"de": "asesor",
                 "texto": (f"Hola {nombre}, soy tu asesor de Colsubsidio. Confirmé {prod} con {aseg}. "
                           f"Te comparto tu póliza y el link de pago (referencia {ref}); cuando lo completes "
                           "queda todo listo. Cualquier duda, con gusto te ayudo.")})
    conv.append({"de": "cliente",
                 "texto": "¡Perfecto, muchas gracias! Reviso la póliza y hago el pago ahora mismo."})
    p["conversacion"] = conv
    store.actualizar_payload_solicitud(solicitud_id, p)
    store.set_estado_solicitud(solicitud_id, "enviada_aseguradora")
    logger.info("Asesor continuó la solicitud %s (simulado) → enviada_aseguradora", solicitud_id)
    return {"ok": True, "id": solicitud_id, "estado": "enviada_aseguradora"}


# --------------------------------------------------------------------------
# Perfil vivo: la base que se enriquece con cada interacción.
# --------------------------------------------------------------------------
@app.get("/api/perfil/{perfil_id}")
def perfil_vivo(perfil_id: str):
    p = store.get_perfil(perfil_id)
    if p is None:
        raise HTTPException(status_code=404, detail="Perfil no encontrado.")
    return p


@app.get("/api/perfiles")
def perfiles():
    return {"perfiles": store.list_perfiles()}


# --------------------------------------------------------------------------
# AGENTE DE OFERTAS (segundo agente). Lo dispara n8n u otra base de Colsubsidio
# vía POST /api/eventos. La inteligencia (evento -> oferta) vive en ofertas.py.
# --------------------------------------------------------------------------
@app.get("/ofertas", include_in_schema=False)
def ofertas_panel():
    return FileResponse(settings.STATIC_DIR / "ofertas.html")


@app.get("/api/ofertas/catalogo")
def ofertas_catalogo():
    """Eventos que el agente de seguros sabe atender (para UI/n8n)."""
    return {"eventos": ofertas.eventos_soportados(), "creditos": {}}


@app.get("/api/ofertas/salientes")
def ofertas_salientes():
    return {"ofertas": store.list_ofertas()}


@app.post("/api/ofertas/reset")
def ofertas_reset():
    """Vacía la bandeja de ofertas salientes para reiniciar la demo en limpio."""
    n = store.limpiar_ofertas()
    seed.resembrar_abandonos_demo()  # deja los abandonos listos para re-enganchar de nuevo
    logger.info("Ofertas salientes reiniciadas (%d eliminadas)", n)
    return {"ok": True, "eliminadas": n}


@app.post("/api/ofertas/demo/reset-abandonos")
def ofertas_reset_abandonos():
    """Reinicia los abandonos demo para que el re-enganche vuelva a mostrar
    resultados (útil para repetir la demostración ante el jurado)."""
    n = seed.resembrar_abandonos_demo()
    return {"ok": True, "abandonos": n}


@app.post("/api/ofertas/{oferta_id}/estado")
def ofertas_estado(oferta_id: str, req: EstadoOfertaReq):
    if not store.set_estado_oferta(oferta_id, req.estado):
        raise HTTPException(status_code=404, detail="Oferta no encontrada.")
    return {"ok": True, "id": oferta_id, "estado": req.estado}


def _perfil_para_ofertas(serie: str | None, perfil_id: str | None) -> tuple[str, dict]:
    """Consigue el perfil vivo para el agente de ofertas. Si la persona nunca
    chateó pero está en la base (evento desde otra base), lo construye al vuelo."""
    pid = perfil_id or serie
    guardado = store.get_perfil(pid) if pid else None
    if guardado:
        return guardado["id"], guardado["perfil"]
    if serie:
        # Canal simulado para que el envío del agente saliente se refleje en la
        # demo (afiliado de la base sin contacto conversacional aún).
        contacto = {"canal": "whatsapp", "destino": f"+57·demo·{serie}"}
        # 1) Base REAL en Mongo (500k): la fuente principal del agente de ofertas.
        doc = afiliados_db.existe_afiliado(serie)
        if doc is not None:
            perfil = {"id": str(doc.get("serie")), "es_afiliado": True,
                      "base": base_afiliados.resumen_base(doc),
                      "propension": propension.perfilar(doc),
                      "contacto": contacto, "eventos_vida": []}
            return str(doc.get("serie")), perfil
        # 2) Muestra demo (fallback para series que no están en Mongo).
        af = base_afiliados.buscar(serie)
        if af:
            perfil = {"id": str(serie), "es_afiliado": True,
                      "base": base_afiliados.resumen_base(af),
                      "propension": propension.perfilar(af),
                      "contacto": contacto, "eventos_vida": []}
            return str(serie), perfil
    # Perfil mínimo desconocido.
    return (pid or "NA-DESCONOCIDO"), {"id": pid, "es_afiliado": False, "eventos_vida": []}


def _procesar_evento(serie, perfil_id, evento, datos, enviar) -> dict:
    """Núcleo del agente de ofertas (100% seguros): enriquece el perfil, aplica
    dedup (anti-spam), decide el SEGURO más pertinente y lo registra/envía."""
    pid, perfil = _perfil_para_ofertas(serie, perfil_id)

    # 1) El evento enriquece el perfil vivo (la base sigue creciendo).
    perfil.setdefault("eventos_vida", []).append(
        {"tipo": evento, "fuente": "base_externa", "datos": datos or {}})
    store.upsert_perfil(pid, bool(perfil.get("es_afiliado")), None, perfil, bump=True)

    # 2) El agente decide el seguro (regla evento -> seguro, explicable).
    res = ofertas.generar_oferta(perfil, evento, datos)
    oferta = res.get("oferta")
    if not oferta:
        return {"ok": True, "perfil_id": pid, "oferta": None, "motivo": res.get("motivo")}

    # Anti-spam: no repetir el mismo seguro al perfil en 15 días.
    if store.oferta_reciente(pid, oferta["producto_id"], dias=15):
        return {"ok": True, "perfil_id": pid, "oferta": None, "suprimida": True,
                "motivo": f"Ya se ofreció {oferta['nombre']} a este perfil hace poco (anti-spam, 15 días)."}

    # 3) Se registra y (si aplica) se envía por el canal del perfil.
    estado = "generada"
    entrega = {"simulado": True, "detalle": "no enviada"}
    contacto = (perfil.get("contacto") or {})
    destino = contacto.get("destino") or contacto.get("correo") or contacto.get("telefono")
    if enviar and destino:
        if oferta["canal"] == "correo":
            entrega = notify.send_email(destino, "Una recomendación de Colsubsidio para ti", oferta["mensaje"])
        else:
            entrega = notify.send_whatsapp(destino, oferta["mensaje"])
        estado = "enviada"
    store.insert_oferta(oferta["id"], pid, evento, oferta["tipo"], oferta["producto_id"],
                        oferta["canal"], estado, {**oferta, "entrega": entrega})
    logger.info("Agente de ofertas · evento=%s perfil=%s -> %s (%s)",
                evento, pid, oferta["nombre"], estado)
    return {"ok": True, "perfil_id": pid, "estado": estado, "oferta": oferta, "entrega": entrega}


@app.post("/api/eventos")
def recibir_evento(req: EventoReq):
    """Webhook del agente de ofertas. Un evento (crédito desembolsado en otra
    base, alza de ingreso, nacimiento, inactividad…) entra aquí: enriquece el
    perfil, decide el mejor SEGURO y lo deja listo. Ej.: crédito de vivienda ->
    seguro de hogar."""
    resultado = _procesar_evento(req.serie, req.perfil_id, req.evento, req.datos, req.enviar)
    resultado["orquestacion"] = {
        "source": req.source,
        "trace_id": req.trace_id,
        "agente": "Cody",
    }
    return resultado


@app.post("/api/ofertas/barrido")
def ofertas_barrido(req: BarridoReq):
    """Barrido AUTÓNOMO: el agente no espera al cliente. Toma una muestra de la
    base real (Mongo) y para cada afiliado decide y radica un SEGURO por
    propensión, sin repetir (anti-spam). Es lo que el cron de n8n dispara."""
    n = max(1, min(int(req.muestra or 8), 40))
    series = afiliados_db.muestra_series(n)
    generadas, suprimidas, resultados = 0, 0, []
    for serie in series:
        r = _procesar_evento(serie, None, "sin_interaccion_30d", {}, enviar=True)
        item = {"serie": serie}
        if r.get("oferta"):
            generadas += 1
            item.update({"oferta": r["oferta"]["nombre"], "tipo": r["oferta"]["tipo"],
                         "razon": r["oferta"]["razon"]})
        else:
            suprimidas += 1
            item["motivo"] = r.get("motivo")
        resultados.append(item)
    logger.info("Barrido autónomo · muestra=%d generadas=%d suprimidas=%d",
                len(series), generadas, suprimidas)
    return {"ok": True, "muestra": len(series), "generadas": generadas,
            "suprimidas": suprimidas, "resultados": resultados}


@app.post("/api/ofertas/reenganche")
def ofertas_reenganche(req: ReengancheReq):
    """UNIÓN DE LOS DOS AGENTES · Re-enganche de abandonos. Busca perfiles vivos
    de gente que habló con Lara, dejó su contacto (celular/correo) y NO cerró la
    compra; y para cada uno el agente de ofertas envía un RECORDATORIO de su
    seguro ("aún puedes gestionarlo"). Es lo que el cron de n8n dispara."""
    minutos = max(0, int(req.minutos if req.minutos is not None else 30))
    corte = (dt.datetime.now() - dt.timedelta(minutes=minutos)).isoformat(timespec="seconds")
    reenganchados, resultados = 0, []
    for p in store.list_perfiles(limit=500):
        perfil = p.get("perfil") or {}
        contacto = perfil.get("contacto") or {}
        datos = perfil.get("datos_contratacion") or {}
        tiene_contacto = bool(contacto.get("destino") or datos.get("correo") or datos.get("telefono"))
        interes = perfil.get("seguro_solicitado") or (perfil.get("intereses_productos") or [])
        cerro = perfil.get("estado_conversacion") in ("CIERRE",) or perfil.get("vinculado")
        # Elegible: dejó contacto, mostró interés, no cerró y está inactivo.
        if not tiene_contacto or not interes or cerro:
            continue
        if (p.get("updated_at") or "") >= corte:
            continue  # aún activo: darle tiempo
        r = _procesar_evento(None, p["id"], "abandono_con_contacto", {}, enviar=True)
        item = {"perfil_id": p["id"], "nombre": datos.get("nombre")}
        if r.get("oferta"):
            reenganchados += 1
            item.update({"oferta": r["oferta"]["nombre"], "razon": r["oferta"]["razon"]})
        else:
            item["motivo"] = r.get("motivo")
        resultados.append(item)
    logger.info("Re-enganche de abandonos · reenganchados=%d de %d revisados",
                reenganchados, len(resultados))
    return {"ok": True, "reenganchados": reenganchados, "revisados": len(resultados),
            "resultados": resultados}


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
    distribuye, no emite pólizas) y deja que Lara confirme en lenguaje natural.
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

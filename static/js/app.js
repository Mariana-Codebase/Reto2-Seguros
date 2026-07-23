/* =========================================================================
   Clara — Frontend (conectado al backend FastAPI + Gemini)
   El agente vive en el servidor; aquí solo se renderiza la conversación,
   el perfil extraído, la auditoría y los documentos.
========================================================================= */
"use strict";

const API = ""; // mismo origen

/* ---------- Estado global ---------- */
let started = false;
let sessionId = null;
let busy = false;
let pollTimer = null;
let afiliadosDemo = [];   // muestra anonimizada de la base (por SERIE)

/* ---------- Navegación entre vistas ---------- */
const views = document.querySelectorAll(".view");

function showView(id) {
  views.forEach(v => v.classList.toggle("active", v.id === id));
  document.querySelectorAll(".nav-links button")
    .forEach(b => b.classList.toggle("active", b.dataset.view === id));
  window.scrollTo({ top: 0 });
  try { history.replaceState(null, "", "#" + id); } catch (e) { /* noop */ }
  if (id === "demo" && !started) startDemo();
}

document.querySelectorAll("[data-view]").forEach(b => {
  b.addEventListener("click", () => showView(b.dataset.view));
});

(function initViewFromHash() {
  const id = (location.hash || "").replace("#", "");
  if (id && document.getElementById(id)) showView(id);
})();

/* ---------- Etiquetas legibles del perfil ---------- */
const PF_LABELS = {
  hogar: { solo: "Vive solo/a", pareja: "Con pareja", pareja_hijos: "Pareja e hijos", familia: "Con familia" },
  vehiculo: { no: "Sin vehículo", particular: "Particular", comercial: "Comercial", moto: "Motocicleta" },
  ocupacion: { empleado: "Empleado/a", independiente: "Independiente", pensionado: "Pensionado/a", otro: "Otro" },
  prioridad: {
    ingreso: "Proteger ingreso familiar", hogar: "Proteger el hogar", vehiculo: "Proteger el vehículo",
    salud: "Cubrir salud", mascotas: "Proteger a su mascota", viajes: "Viajar tranquilo",
    exequial: "Cubrir gastos exequiales", ahorro: "Proteger ingreso y ahorrar",
    accidentes: "Protegerse ante accidentes", juridica: "Respaldo jurídico"
  }
};

/* ---------- Referencias DOM ---------- */
const chat = document.getElementById("chat");
const chips = document.getElementById("chips");
const input = document.getElementById("userInput");
const sendBtn = document.getElementById("sendBtn");
const audit = document.getElementById("audit");

/* ---------- Utilidades de chat ---------- */
const scrollChat = () => { chat.scrollTop = chat.scrollHeight; };
const clearChips = () => { chips.innerHTML = ""; };

function setChips(items) {
  clearChips();
  items.forEach(it => {
    const b = document.createElement("button");
    b.className = "chip" + (it.style ? " " + it.style : "");
    b.textContent = it.label;
    b.onclick = it.action;
    chips.appendChild(b);
  });
}

function addUser(text) {
  const m = document.createElement("div");
  m.className = "msg user";
  m.innerHTML = '<div class="body"></div>';
  m.querySelector(".body").textContent = text;
  chat.appendChild(m);
  scrollChat();
}

function addBot(text, opts = {}) {
  const m = document.createElement("div");
  m.className = "msg bot";
  const safe = (text || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/\n/g, "<br>");
  let inner = '<div class="body">' + safe;
  if (opts.verified) {
    inner += '<div class="verified">✓ Respaldado en documentos · Guardrail: aprobado</div>';
  }
  inner += "</div>";
  m.innerHTML = inner;
  if (opts.extra) m.querySelector(".body").appendChild(opts.extra);
  chat.appendChild(m);
  scrollChat();
  return m;
}

function addSystem(text) {
  const m = document.createElement("div");
  m.className = "msg system";
  m.innerHTML = '<div class="body"></div>';
  m.querySelector(".body").textContent = text;
  chat.appendChild(m);
  scrollChat();
}

function showTyping() {
  const t = document.createElement("div");
  t.className = "typing";
  t.id = "typing";
  t.innerHTML = "<i></i><i></i><i></i>";
  chat.appendChild(t);
  scrollChat();
}
const hideTyping = () => { const t = document.getElementById("typing"); if (t) t.remove(); };

/* ---------- Paneles laterales ---------- */
const STATE_ORDER = ["DIAGNOSTICO", "RECOMENDACION", "DUDAS", "CIERRE", "EMITIDA", "CERRADA"];

function setState(estado) {
  const at = STATE_ORDER.indexOf(estado);
  document.querySelectorAll("#stateTrack .st").forEach(el => {
    const i = STATE_ORDER.indexOf(el.dataset.state);
    el.classList.toggle("active", i === at);
    el.classList.toggle("done", i < at);
    el.querySelector(".dot").textContent = i < at ? "✓" : String(i + 1);
  });
}

function updateProfile(perfil) {
  const map = { hogar: "hogar", vehiculo: "vehiculo", dependientes: "dependientes",
                ocupacion: "ocupacion", rango_edad: "edad", prioridad: "prioridad" };
  Object.keys(map).forEach(k => {
    const el = document.querySelector('[data-pf="' + map[k] + '"]');
    if (!el) return;
    const v = perfil[k];
    if (v === undefined || v === null || v === "") return;
    let disp = v;
    if (PF_LABELS[k]) disp = PF_LABELS[k][v] || v;
    else if (k === "dependientes") disp = (v == 0 ? "Ninguno" : v + (v == 1 ? " persona" : " personas"));
    else if (k === "rango_edad") disp = v + " años";
    el.textContent = disp;
    el.classList.remove("empty");
  });
  const notasEl = document.querySelector('[data-pf="notas"]');
  if (notasEl && Array.isArray(perfil.notas) && perfil.notas.length) {
    notasEl.textContent = perfil.notas.join(" · ");
    notasEl.classList.remove("empty");
  }
}

function pushAudit(events) {
  if (!events || !events.length) return;
  const empty = audit.querySelector(".audit-empty");
  if (empty) empty.remove();
  events.forEach(e => {
    const div = document.createElement("div");
    div.className = "ae " + (e.kind || "state");
    const desc = (e.desc || "").replace(/&/g, "&amp;").replace(/</g, "&lt;");
    div.innerHTML = '<span class="tag">' + e.tag + '</span><div class="desc">' + desc + "</div>";
    audit.appendChild(div);
  });
  audit.scrollTop = audit.scrollHeight;
}

/* ---------- API helpers ---------- */
async function apiPost(path, body) {
  return fetch(API + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
}

/* ---------- Afiliados demo (la oferta cambia según el perfil) ---------- */
const afiliadoSel = document.getElementById("afiliadoSel");

async function loadAfiliados() {
  if (afiliadosDemo.length || !afiliadoSel) return;
  try {
    const r = await fetch(API + "/api/afiliados-demo");
    const d = await r.json();
    afiliadosDemo = d.afiliados || [];
    afiliadosDemo.forEach(a => {
      const o = document.createElement("option");
      o.value = a.serie;
      const top = a.propension && a.propension.productos && a.propension.productos[0];
      o.textContent = "SERIE " + a.serie + " · " + a.arquetipo_desc + (top ? " → " + top.nombre : "");
      afiliadoSel.appendChild(o);
    });
  } catch (e) { /* la demo funciona igual como visitante anónimo */ }
}

if (afiliadoSel) afiliadoSel.addEventListener("change", () => resetDemo());

function renderPropension(prop) {
  const panel = document.getElementById("propensionPanel");
  const list = document.getElementById("propensionList");
  const mc = document.getElementById("propensionMC");
  if (!panel || !list) return;
  if (!prop || !prop.productos || !prop.productos.length) {
    panel.style.display = "none";
    list.innerHTML = "";
    if (mc) mc.innerHTML = "";
    return;
  }
  panel.style.display = "";
  list.innerHTML = "";
  prop.productos.forEach(p => {
    const div = document.createElement("div");
    div.className = "prop-item";
    const razones = (p.razones || []).map(r => r.razon);
    div.innerHTML =
      '<div class="prop-head"><b>' + p.nombre + '</b>' +
      '<span class="prop-aff">' + Math.round(p.afinidad) + '%</span></div>' +
      '<div class="prop-bar"><i style="width:' + Math.round(p.afinidad) + '%"></i></div>' +
      '<ul class="prop-reasons">' + razones.map(r => "<li></li>").join("") + "</ul>";
    div.querySelectorAll(".prop-reasons li").forEach((li, i) => { li.textContent = razones[i]; });
    list.appendChild(div);
  });
  if (mc && prop.momento_canal) {
    mc.innerHTML = "";
    const b = document.createElement("div");
    b.className = "prop-mc-box";
    b.innerHTML = "<b>Momento y canal sugerido</b><p></p><small></small>";
    b.querySelector("p").textContent = prop.momento_canal.momento + " · " + prop.momento_canal.canal;
    b.querySelector("small").textContent = prop.momento_canal.porque;
    mc.appendChild(b);
  }
}

/* ---------- Inicio de la demo ---------- */
async function startDemo() {
  started = true;
  busy = true;
  showTyping();
  await loadAfiliados();
  try {
    const serie = afiliadoSel && afiliadoSel.value ? afiliadoSel.value : null;
    const body = { canal: "WhatsApp" };
    if (serie) body.serie = serie;
    const r = await apiPost("/api/session", body);
    const d = await r.json();
    sessionId = d.session_id;
    hideTyping();
    setState(d.estado || "DIAGNOSTICO");
    pushAudit(d.audit);
    renderPropension(d.propension);
    if (d.perfil) updateProfile(d.perfil);
    addBot(d.reply);
    starterChips(!!serie);
  } catch (err) {
    hideTyping();
    addBot("No pude iniciar la sesión. Verifica que el servidor esté corriendo (python server.py) y que la clave de Gemini esté configurada.");
  } finally {
    busy = false;
  }
}

function starterChips(conPerfil) {
  if (conPerfil) {
    setChips([
      { label: "Muéstrame mi mejor opción", style: "primary", action: () => quickSend("Sí, muéstrame la protección que mejor encaja conmigo") },
      { label: "Prefiero contarte qué busco", action: () => quickSend("Prefiero contarte yo qué estoy buscando") },
      { label: "¿Por qué me recomiendas eso?", action: () => quickSend("¿Por qué me recomiendas eso a mí?") }
    ]);
    return;
  }
  setChips([
    { label: "Ayúdame a encontrar mi mejor opción", action: () => quickSend("La verdad no estoy seguro, ayúdame a encontrar la mejor opción para mí") },
    { label: "Ya sé qué busco", action: () => quickSend("Ya sé qué busco") },
    { label: "Solo quiero un seguro de viaje", action: () => quickSend("Solo quiero un seguro de viaje, viajo pronto al exterior") },
    { label: "Tengo un gato y una moto", action: () => quickSend("Tengo un gato y una moto, me gustaría protegerlos") }
  ]);
}

function quickSend(t) {
  input.value = t;
  handleSend();
}

/* ---------- Envío de mensajes ---------- */
async function handleSend() {
  const text = input.value.trim();
  if (!text || busy || !sessionId) return;
  input.value = "";
  addUser(text);
  clearChips();
  busy = true;
  showTyping();
  try {
    let r = await apiPost("/api/chat", { session_id: sessionId, text });
    // La sesión pudo perderse (reinicio + TTL): recrear y reintentar una vez.
    if (r.status === 404) {
      const body = { canal: "WhatsApp" };
      if (afiliadoSel && afiliadoSel.value) body.serie = afiliadoSel.value;
      const rs = await apiPost("/api/session", body);
      const ds = await rs.json();
      sessionId = ds.session_id;
      addSystem("La sesión anterior expiró; inicié una nueva y sigo contigo.");
      r = await apiPost("/api/chat", { session_id: sessionId, text });
    }
    if (!r.ok) {
      const e = await r.json().catch(() => ({}));
      hideTyping();
      addBot("Tuve un problema para responder" + (e.detail ? ": " + e.detail : ". Revisa la configuración del modelo."));
      return;
    }
    const d = await r.json();
    hideTyping();
    render(d);
  } catch (err) {
    hideTyping();
    addBot("No pude conectar con el servidor. ¿Está corriendo el backend?");
  } finally {
    busy = false;
  }
}

sendBtn.addEventListener("click", handleSend);
input.addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    handleSend();
  }
});

/* ---------- Render de la respuesta del agente ---------- */
function render(d) {
  if (d.estado) setState(d.estado);
  if (d.perfil) updateProfile(d.perfil);
  pushAudit(d.audit);

  if (d.reply) addBot(d.reply, { verified: d.verified });

  const actionChips = [];
  (d.actions || []).forEach(a => {
    if (a.type === "recomendacion") {
      addBot("", { extra: buildOptionCards(a.data.opciones) });
    } else if (a.type === "documento") {
      const ent = a.data.entrega || {};
      addSystem("Resumen en PDF · " + (ent.detalle || "generado"));
      actionChips.push({ label: "Ver el resumen (PDF)", action: () => window.open(a.data.url, "_blank") });
    } else if (a.type === "contrato") {
      const ent = a.data.entrega || {};
      if (a.data.firmado) addSystem("Contrato firmado " + a.data.solicitud + " · " + (ent.detalle || "entregado"));
      addBot("", { extra: buildContratoCard(a.data) });
    } else if (a.type === "pago") {
      const ref = a.data.referencia ? " · Ref " + a.data.referencia : "";
      addSystem("Enlace de pago seguro generado" + ref);
      actionChips.push({ label: "Abrir enlace de pago", style: "primary", action: () => window.open(a.data.link, "_blank") });
      startPaymentPolling(a.data.token);
    } else if (a.type === "poliza") {
      const ent = a.data.entrega || {};
      const ref = a.data.referencia ? " · Ref " + a.data.referencia : "";
      addSystem("Carátula de póliza " + a.data.numero + " (PDF)" + ref + " · " + (ent.detalle || "generada"));
      actionChips.push({ label: "Ver mi póliza (PDF)", action: () => window.open(a.data.url, "_blank") });
    }
  });
  if (actionChips.length) setChips(actionChips);
}

function buildOptionCards(opciones) {
  const cont = document.createElement("div");
  cont.className = "opt-cards";
  (opciones || []).forEach((o, i) => {
    const card = document.createElement("div");
    card.className = "opt-card";
    let propHtml = "";
    if (o.propension && o.propension.razones && o.propension.razones.length) {
      propHtml = '<div class="oc-row cov"><span class="lab">Por qué para ti</span><span>' +
        o.propension.razones.slice(0, 2).map(r => String(r).replace(/&/g, "&amp;").replace(/</g, "&lt;")).join(" · ") +
        "</span></div>";
    }
    card.innerHTML =
      '<div class="oc-top"><h4>Opción ' + (i + 1) + " — " + o.nombre + "</h4>" +
      '<div class="price">' + o.precio_formateado + "<small>/mes</small></div></div>" +
      '<div class="why">' + o.por_que + "</div>" +
      propHtml +
      '<div class="oc-row cov"><span class="lab">Cubre</span><span>' + o.cubre.join(" · ") + "</span></div>" +
      '<div class="oc-row exc"><span class="lab">No cubre</span><span>' + o.no_cubre.join(" · ") + "</span></div>";
    cont.appendChild(card);
  });
  return cont;
}

/* ---------- Contrato: tarjeta con firma electrónica ---------- */
function buildContratoCard(c) {
  const cont = document.createElement("div");
  cont.className = "opt-cards";
  const card = document.createElement("div");
  card.className = "opt-card";
  let bienHtml = "";
  if (c.bien && c.bien.items && c.bien.items.length) {
    bienHtml = '<div class="oc-row cov"><span class="lab">' + c.bien.titulo + '</span><span>' +
      c.bien.items.map(it => it[0] + ": " + it[1]).join(" · ") + "</span></div>";
  }
  const faltan = (c.faltan && c.faltan.length)
    ? '<div class="oc-row exc"><span class="lab">Faltan datos</span><span>' + c.faltan.join(" · ") + "</span></div>"
    : "";
  card.innerHTML =
    '<div class="oc-top"><h4>Contrato · ' + c.producto + "</h4>" +
    '<div class="price">' + c.precio_formateado + "<small>/mes</small></div></div>" +
    '<div class="why">Solicitud ' + c.solicitud + " · Vigencia " + c.vigencia +
    (c.firmado ? ' · <b style="color:var(--primary-d)">Firmado</b>' : " · Pendiente de firma") + "</div>" +
    '<div class="oc-row"><span class="lab">Tomador</span><span>' + ((c.tomador && c.tomador.nombre) || "—") + "</span></div>" +
    bienHtml + faltan;

  const actions = document.createElement("div");
  actions.style.cssText = "display:flex;gap:8px;flex-wrap:wrap;margin-top:11px";
  const verBtn = document.createElement("button");
  verBtn.className = "chip";
  verBtn.textContent = "Ver contrato (PDF)";
  verBtn.onclick = () => window.open(c.url, "_blank");
  actions.appendChild(verBtn);
  if (!c.firmado) {
    const firmarBtn = document.createElement("button");
    firmarBtn.className = "chip consent";
    firmarBtn.textContent = "Firmar y aceptar condiciones";
    firmarBtn.onclick = () => firmarContrato(c.producto_id, firmarBtn);
    actions.appendChild(firmarBtn);
  }
  card.appendChild(actions);
  cont.appendChild(card);
  return cont;
}

async function firmarContrato(producto, btn) {
  if (busy || !sessionId) return;
  busy = true;
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Firmando...";
  }
  clearChips();
  addSystem("Firmando el contrato electrónicamente");
  showTyping();
  try {
    const r = await apiPost("/api/firmar-contrato", { session_id: sessionId, producto });
    if (!r.ok) {
      const e = await r.json().catch(() => ({}));
      hideTyping();
      addBot("No pude firmar el contrato" + (e.detail ? ": " + e.detail : "."));
      return;
    }
    const d = await r.json();
    hideTyping();
    render(d);
  } catch (err) {
    hideTyping();
    addBot("No pude conectar para firmar el contrato.");
  } finally {
    busy = false;
  }
}

/* ---------- Pago: polling del checkout + confirmación del agente ---------- */
function startPaymentPolling(token) {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    try {
      const r = await fetch(API + "/api/pago-estado/" + sessionId);
      const d = await r.json();
      const p = d.payments && d.payments[token];
      if (p && p.estado === "aprobado" && !p.confirmado) {
        clearInterval(pollTimer);
        pollTimer = null;
        confirmarPago(token);
      }
    } catch (e) { /* reintenta en el próximo tick */ }
  }, 2500);
}

async function confirmarPago(token) {
  if (busy) return;
  busy = true;
  clearChips();
  addSystem("Pago aprobado en Wompi (sandbox)");
  showTyping();
  try {
    const r = await apiPost("/api/confirmar-pago", { session_id: sessionId, token });
    const d = await r.json();
    hideTyping();
    render(d);
  } catch (err) {
    hideTyping();
    addBot("El pago fue aprobado, pero no pude confirmar la emisión automáticamente.");
  } finally {
    busy = false;
  }
}

/* ---------- Reiniciar ---------- */
async function resetDemo() {
  chat.innerHTML = "";
  clearChips();
  audit.innerHTML = '<div class="audit-empty">Aún no hay eventos registrados.</div>';
  document.querySelectorAll("[data-pf]").forEach(el => {
    el.textContent = "Sin datos";
    el.classList.add("empty");
  });
  document.querySelectorAll("#stateTrack .st").forEach((el, i) => {
    el.classList.remove("active", "done");
    el.querySelector(".dot").textContent = String(i + 1);
  });
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  renderPropension(null);
  started = false;
  sessionId = null;
  await startDemo();
}
document.getElementById("resetDemo").addEventListener("click", resetDemo);

/* ---------- Tema (claro / oscuro) ---------- */
const THEME_KEY = "clara-theme";
document.getElementById("themeToggle").addEventListener("click", () => {
  const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  try { localStorage.setItem(THEME_KEY, next); } catch (e) { /* noop */ }
});

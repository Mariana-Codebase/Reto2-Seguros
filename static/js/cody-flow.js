/**
 * Cody · Agent Flow — cerebro animado del agente de ofertas (hero).
 * Solo UI explicativa (sin backend). Estructura distinta a Clara:
 * Evento → Afiliado → Cody → Regla → Envía → Actualiza
 */
(function () {
  "use strict";

  const ROOT_ID = "codyFlow";
  const RESUME_MS = 5000;
  const CYCLE_PAUSE_MS = 2200;
  const HOLD_MS = 2600;

  const NODES = {
    evento: {
      name: "Evento",
      hint: "Algo cambió en su vida",
      detail: "Cuando Colsubsidio registra un hecho importante —por ejemplo, un crédito de vivienda aprobado— esa señal activa a Cody. No hace falta que la persona inicie un chat.",
      bullets: ["Crédito, ingreso, familia…", "Señal automática", "Sin esperar al afiliado"],
    },
    afiliado: {
      name: "Afiliado",
      hint: "Lee su información",
      detail: "Cody consulta la base de datos de Colsubsidio, ubica a esa persona y entiende su contexto: qué acaba de ocurrir y qué protección tiene sentido ofrecerle.",
      bullets: ["Consulta la base", "Identifica a la persona", "Entiende el momento"],
    },
    cody: {
      name: "Cody",
      hint: "Agente automático",
      detail: "Un agente independiente que trabaja solo: recibe el evento, piensa la mejor oferta de seguro y actúa. Automatización inteligente al servicio del afiliado.",
      bullets: ["Independiente de Clara", "Piensa y actúa solo", "Enfocado en seguros"],
    },
    regla: {
      name: "Criterio",
      hint: "Elige qué ofrecer",
      detail: "Con pensamiento claro y reglas transparentes: si hubo un crédito de vivienda, propone el seguro que protege ese patrimonio. Siempre con una razón que se puede explicar.",
      bullets: ["Evento → oferta justa", "Razón fácil de entender", "Sin decisiones al azar"],
    },
    envio: {
      name: "Envía",
      hint: "Llega a la persona",
      detail: "Cody manda la oferta de seguro por el canal del afiliado. El mensaje llega en el momento oportuno: cuando el evento recién ocurrió.",
      bullets: ["Oferta de seguro", "En el momento justo", "Canal del afiliado"],
    },
    actualiza: {
      name: "Actualiza",
      hint: "Deja constancia",
      detail: "Guarda el evento y la oferta en el perfil de esa persona. La información queda al día para futuras interacciones con Colsubsidio o con Clara.",
      bullets: ["Perfil actualizado", "Historial del evento", "Listo para el siguiente contacto"],
    },
  };

  /** Pipeline horizontal: distinto al hub de Clara. */
  const EDGES = [
    { id: "e-ev-af", from: "evento", to: "afiliado", d: "M8 50 C14 50, 18 50, 23 50" },
    { id: "e-af-cody", from: "afiliado", to: "cody", d: "M23 50 C29 50, 34 50, 40 50" },
    { id: "e-cody-regla", from: "cody", to: "regla", d: "M40 50 C48 50, 52 50, 58 50" },
    { id: "e-regla-envio", from: "regla", to: "envio", d: "M58 50 C65 50, 70 50, 75 50" },
    { id: "e-envio-act", from: "envio", to: "actualiza", d: "M75 50 C82 50, 86 50, 92 50" },
  ];

  const ICONS = {
    evento: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>',
    afiliado: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>',
    cody: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a4 4 0 0 1 4 4v1h1a3 3 0 0 1 0 6h-.5"/><path d="M8 7V6a4 4 0 0 1 4-4"/><path d="M7.5 13H7a3 3 0 0 1 0-6h1"/><circle cx="9" cy="10" r="1"/><circle cx="15" cy="10" r="1"/><path d="M9 16c.8 1.2 2 2 3 2s2.2-.8 3-2"/><path d="M12 18v3"/><path d="M9 21h6"/></svg>',
    regla: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M8 13h8"/><path d="M8 17h8"/><path d="M8 9h2"/></svg>',
    envio: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 2 11 13"/><path d="M22 2l-7 20-4-9-9-4 20-7z"/></svg>',
    actualiza: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/><path d="M16 16h5v5"/></svg>',
  };

  function reduceMotion() {
    return !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }

  function wait(ms, ctl) {
    return new Promise((resolve) => {
      const t = setTimeout(resolve, ms);
      ctl.timeouts.add(t);
      const prev = ctl._clearWait;
      ctl._clearWait = () => {
        clearTimeout(t);
        ctl.timeouts.delete(t);
        if (prev) prev();
      };
    });
  }

  function clearTimers(ctl) {
    ctl.timeouts.forEach((t) => clearTimeout(t));
    ctl.timeouts.clear();
    ctl.intervals.forEach((i) => clearInterval(i));
    ctl.intervals.clear();
    if (ctl._clearWait) { ctl._clearWait(); ctl._clearWait = null; }
    if (ctl.resumeTimer) { clearTimeout(ctl.resumeTimer); ctl.resumeTimer = null; }
    cancelAnimationFrame(ctl.raf);
    ctl.raf = 0;
  }

  function build(root) {
    root.innerHTML = "";
    root.setAttribute("role", "img");
    root.setAttribute("aria-label", "Cerebro de Cody: evento, afiliado, regla, envío y actualización");

    const label = document.createElement("div");
    label.className = "af-label";
    label.innerHTML = '<span class="af-live" aria-hidden="true"></span> Cerebro Cody · ofertas automáticas';
    root.appendChild(label);

    const stage = document.createElement("div");
    stage.className = "af-stage";
    root.appendChild(stage);

    const svgNS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(svgNS, "svg");
    svg.classList.add("af-wires");
    svg.setAttribute("viewBox", "0 0 100 100");
    svg.setAttribute("preserveAspectRatio", "none");
    svg.setAttribute("aria-hidden", "true");

    const edgeEls = {};
    EDGES.forEach((e) => {
      const path = document.createElementNS(svgNS, "path");
      path.setAttribute("d", e.d);
      path.setAttribute("id", e.id);
      path.classList.add("af-edge", "is-cody-edge");
      svg.appendChild(path);
      edgeEls[e.id] = path;
    });

    const particles = [];
    for (let i = 0; i < 3; i++) {
      const c = document.createElementNS(svgNS, "circle");
      c.setAttribute("r", "0.85");
      c.classList.add("af-particle", "is-cody-particle");
      c.style.display = "none";
      svg.appendChild(c);
      particles.push(c);
    }
    stage.appendChild(svg);

    const nodeEls = {};
    Object.keys(NODES).forEach((id) => {
      const meta = NODES[id];
      const el = document.createElement("button");
      el.type = "button";
      el.className = "af-node" + (id === "cody" ? " is-cody" : "");
      el.dataset.id = id;
      el.setAttribute("aria-label", meta.name + ": " + meta.hint);
      el.innerHTML =
        '<span class="af-status" data-st></span>' +
        '<span class="af-ico" aria-hidden="true">' + ICONS[id] + "</span>" +
        '<span class="af-name">' + meta.name + "</span>" +
        '<span class="af-hint">' + meta.hint + "</span>" +
        (id === "cody"
          ? '<span class="af-think-dots" aria-hidden="true"><i></i><i></i><i></i></span>'
          : "");
      stage.appendChild(el);
      nodeEls[id] = el;
    });

    const detail = document.createElement("div");
    detail.className = "af-detail af-detail-cody";
    detail.setAttribute("aria-hidden", "true");
    document.body.appendChild(detail);

    return { stage, svg, edgeEls, particles, nodeEls, detail };
  }

  function setNodeState(nodeEls, id, state) {
    const el = nodeEls[id];
    if (!el) return;
    el.classList.remove("is-active", "is-next", "is-done", "is-thinking", "is-pulse", "is-dim");
    const st = el.querySelector("[data-st]");
    if (state === "active") {
      el.classList.add("is-active", "is-pulse");
      if (st) st.textContent = "Activo";
    } else if (state === "thinking") {
      el.classList.add("is-active", "is-thinking");
      if (st) st.textContent = "Decidiendo";
    } else if (state === "next") {
      el.classList.add("is-next");
      if (st) st.textContent = "";
    } else if (state === "done") {
      el.classList.add("is-done");
      if (st) st.textContent = "";
    } else if (st) {
      st.textContent = "";
    }
  }

  function resetVisual(ui) {
    Object.keys(ui.nodeEls).forEach((id) => setNodeState(ui.nodeEls, id, "idle"));
    Object.values(ui.edgeEls).forEach((p) => p.classList.remove("is-lit"));
    ui.particles.forEach((c) => {
      c.classList.remove("is-on");
      c.style.display = "none";
    });
    Object.values(ui.nodeEls).forEach((n) => n.classList.remove("is-hover"));
    hideDetail(ui);
  }

  function pointOnPath(pathEl, t) {
    const len = pathEl.getTotalLength();
    return pathEl.getPointAtLength(Math.max(0, Math.min(1, t)) * len);
  }

  function animateParticle(ctl, ui, edgeId, opts) {
    const path = ui.edgeEls[edgeId];
    const particle = ui.particles[opts.slot || 0];
    if (!path || !particle || reduceMotion()) return Promise.resolve();
    return new Promise((resolve) => {
      const dur = opts.duration || 900;
      path.classList.add("is-lit");
      particle.classList.add("is-on");
      particle.style.display = "";
      let elapsed = 0;
      let last = performance.now();
      function frame(now) {
        if (ctl.destroyed) {
          particle.classList.remove("is-on");
          particle.style.display = "none";
          resolve();
          return;
        }
        if (ctl.paused) {
          last = now;
          ctl.raf = requestAnimationFrame(frame);
          return;
        }
        elapsed += now - last;
        last = now;
        const t = Math.min(1, elapsed / dur);
        const ease = 1 - Math.pow(1 - t, 2.4);
        const pt = pointOnPath(path, ease);
        particle.setAttribute("cx", pt.x);
        particle.setAttribute("cy", pt.y);
        if (t < 1) ctl.raf = requestAnimationFrame(frame);
        else {
          particle.classList.remove("is-on");
          particle.style.display = "none";
          resolve();
        }
      }
      ctl.raf = requestAnimationFrame(frame);
    });
  }

  async function runCycle(ctl, ui) {
    const N = ui.nodeEls;
    const sleep = (ms) => wait(ms, ctl);

    async function gate() {
      while (ctl.paused && !ctl.destroyed) await sleep(120);
      return !ctl.destroyed && ctl.running;
    }

    async function clearSpotlight() {
      Object.values(N).forEach((n) => n.classList.remove("is-hover"));
      hideDetail(ui, ctl);
      ctl.root.classList.remove("is-auto-focus");
      ctl.autoSpotlight = null;
    }

    async function spotlight(id, state) {
      const el = N[id];
      if (!el || !(await gate())) return false;
      await clearSpotlight();
      setNodeState(N, id, state || "active");
      el.classList.add("is-hover");
      ctl.root.classList.add("is-auto-focus");
      ctl.autoSpotlight = id;
      showDetail(ctl, ui, id, el);
      await sleep(HOLD_MS);
      if (!(await gate())) return false;
      el.classList.remove("is-hover");
      hideDetail(ui, ctl);
      ctl.root.classList.remove("is-auto-focus");
      ctl.autoSpotlight = null;
      setNodeState(N, id, "done");
      return true;
    }

    resetVisual(ui);
    await clearSpotlight();
    if (!(await gate())) return;

    const steps = [
      ["evento", "e-ev-af", "afiliado"],
      ["afiliado", "e-af-cody", "cody"],
      ["cody", "e-cody-regla", "regla", "thinking"],
      ["regla", "e-regla-envio", "envio"],
      ["envio", "e-envio-act", "actualiza"],
      ["actualiza", null, null],
    ];

    for (let i = 0; i < steps.length; i++) {
      const [id, edge, next, state] = steps[i];
      if (next) setNodeState(N, next, "next");
      if (!(await spotlight(id, state || "active"))) return;
      if (!(await gate())) return;
      if (edge) {
        await animateParticle(ctl, ui, edge, { duration: 750, slot: 0 });
        if (!(await gate())) return;
      }
    }

    await sleep(CYCLE_PAUSE_MS);
  }

  function showDetail(ctl, ui, id, nodeEl) {
    const meta = NODES[id];
    if (!meta) return;
    ctl.detailId = id;
    ctl.detailNode = nodeEl;
    ui.detail.innerHTML =
      "<h4><span>" + ICONS[id] + "</span>" + meta.name + "</h4>" +
      "<p>" + meta.detail + "</p>" +
      "<ul>" + meta.bullets.map((b) => "<li>" + b + "</li>").join("") + "</ul>";

    const nodeRect = nodeEl.getBoundingClientRect();
    const maxW = Math.min(240, window.innerWidth * 0.42);
    ui.detail.style.width = maxW + "px";
    ui.detail.style.position = "fixed";

    let left = nodeRect.left + nodeRect.width / 2;
    const half = maxW / 2;
    left = Math.max(half + 8, Math.min(window.innerWidth - half - 8, left));
    ui.detail.classList.remove("is-above");
    ui.detail.style.transformOrigin = "top center";
    ui.detail.style.left = left + "px";
    ui.detail.style.top = nodeRect.bottom + 12 + "px";
    ui.detail.classList.add("is-open");
    ui.detail.setAttribute("aria-hidden", "false");
    ctl.root.classList.add("is-detail-open");
  }

  function hideDetail(ui, ctl) {
    ui.detail.classList.remove("is-open", "is-above");
    ui.detail.setAttribute("aria-hidden", "true");
    if (ctl) {
      ctl.detailId = null;
      ctl.detailNode = null;
      if (ctl.root) ctl.root.classList.remove("is-detail-open");
    } else {
      const root = document.getElementById(ROOT_ID);
      if (root) root.classList.remove("is-detail-open");
    }
  }

  function syncDetailOnScroll(ctl, ui) {
    if (!ui.detail.classList.contains("is-open") || !ctl.detailNode) return;
    const rect = ctl.detailNode.getBoundingClientRect();
    const visible = rect.bottom > 40 && rect.top < window.innerHeight - 40;
    if (!visible) {
      Object.values(ui.nodeEls).forEach((n) => n.classList.remove("is-hover"));
      hideDetail(ui, ctl);
      ctl.root.classList.remove("is-auto-focus");
      if (ctl.hoverId) {
        ctl.hoverId = null;
        scheduleResume(ctl, ui);
      }
      return;
    }
    const maxW = parseFloat(ui.detail.style.width) || Math.min(240, window.innerWidth * 0.42);
    let left = rect.left + rect.width / 2;
    const half = maxW / 2;
    left = Math.max(half + 8, Math.min(window.innerWidth - half - 8, left));
    ui.detail.style.left = left + "px";
    ui.detail.style.top = rect.bottom + 12 + "px";
  }

  function pause(ctl) {
    ctl.paused = true;
    ctl.root.classList.add("is-paused");
    ctl.root.classList.remove("is-auto-focus");
    if (ctl.resumeTimer) { clearTimeout(ctl.resumeTimer); ctl.resumeTimer = null; }
  }

  function scheduleResume(ctl, ui) {
    if (ctl.resumeTimer) clearTimeout(ctl.resumeTimer);
    ctl.resumeTimer = setTimeout(() => {
      if (ctl.destroyed || ctl.hoverId) return;
      ctl.paused = false;
      ctl.root.classList.remove("is-paused");
      Object.values(ui.nodeEls).forEach((el) => el.classList.remove("is-hover"));
      hideDetail(ui, ctl);
      if (!ctl.loopActive) startLoop(ctl, ui);
    }, RESUME_MS);
  }

  async function startLoop(ctl, ui) {
    if (ctl.loopActive || ctl.destroyed) return;
    ctl.loopActive = true;
    ctl.running = true;
    while (ctl.running && !ctl.destroyed) {
      if (ctl.paused) {
        await wait(150, ctl);
        continue;
      }
      try { await runCycle(ctl, ui); } catch (e) { /* noop */ }
      if (reduceMotion()) {
        Object.keys(ui.nodeEls).forEach((id) => setNodeState(ui.nodeEls, id, "done"));
        break;
      }
    }
    ctl.loopActive = false;
  }

  function bind(ctl, ui) {
    Object.entries(ui.nodeEls).forEach(([id, el]) => {
      el.addEventListener("pointerenter", () => {
        ctl.hoverId = id;
        pause(ctl);
        Object.values(ui.nodeEls).forEach((n) => n.classList.remove("is-hover"));
        el.classList.add("is-hover");
        const st = el.querySelector("[data-st]");
        if (st) st.textContent = "Activo";
        showDetail(ctl, ui, id, el);
      });
      el.addEventListener("pointerleave", () => {
        if (ctl.hoverId === id) ctl.hoverId = null;
        el.classList.remove("is-hover");
        if (!el.classList.contains("is-active") && !el.classList.contains("is-thinking")) {
          const st = el.querySelector("[data-st]");
          if (st) st.textContent = "";
        }
        hideDetail(ui, ctl);
        scheduleResume(ctl, ui);
      });
    });

    const inicio = document.getElementById("inicio");
    if (inicio && "MutationObserver" in window) {
      ctl.viewObs = new MutationObserver(() => {
        const active = inicio.classList.contains("active");
        if (!active) {
          ctl.running = false;
          pause(ctl);
          clearTimers(ctl);
        } else if (!ctl.loopActive) {
          ctl.paused = false;
          ctl.root.classList.remove("is-paused");
          startLoop(ctl, ui);
        }
      });
      ctl.viewObs.observe(inicio, { attributes: true, attributeFilter: ["class"] });
    }

    ctl.onScroll = function () { syncDetailOnScroll(ctl, ui); };
    window.addEventListener("scroll", ctl.onScroll, { passive: true, capture: true });
  }

  function init() {
    const root = document.getElementById(ROOT_ID);
    if (!root) return;

    const ctl = {
      root,
      paused: false,
      running: false,
      loopActive: false,
      destroyed: false,
      hoverId: null,
      detailId: null,
      detailNode: null,
      onScroll: null,
      timeouts: new Set(),
      intervals: new Set(),
      resumeTimer: null,
      raf: 0,
      viewObs: null,
      _clearWait: null,
    };

    const ui = build(root);
    bind(ctl, ui);

    if ("IntersectionObserver" in window) {
      const io = new IntersectionObserver((entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            if (!ctl.loopActive && !ctl.paused) startLoop(ctl, ui);
          } else {
            ctl.running = false;
            clearTimers(ctl);
            ctl.loopActive = false;
          }
        });
      }, { threshold: 0.2 });
      io.observe(root);
      ctl.io = io;
    } else {
      startLoop(ctl, ui);
    }

    if (reduceMotion()) {
      Object.keys(ui.nodeEls).forEach((id) => setNodeState(ui.nodeEls, id, "done"));
      Object.values(ui.edgeEls).forEach((p) => p.classList.add("is-lit"));
    }

    window.__claraCodyFlow = {
      destroy() {
        ctl.destroyed = true;
        ctl.running = false;
        clearTimers(ctl);
        if (ctl.onScroll) window.removeEventListener("scroll", ctl.onScroll, { capture: true });
        if (ctl.viewObs) ctl.viewObs.disconnect();
        if (ctl.io) ctl.io.disconnect();
        if (ui.detail && ui.detail.parentNode) ui.detail.parentNode.removeChild(ui.detail);
      },
    };
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();

/**
 * Clara · Agent Flow — cerebro animado (hero).
 * Vanilla SVG + CSS. Sin librerías externas.
 * Flujo real: Afiliado → Identifica → Mongo → Clara → [Perfil 360 · Ofertas · Alertas] → Recomienda / escala
 */
(function () {
  "use strict";

  const ROOT_ID = "agentFlow";
  const RESUME_MS = 5000;
  const CYCLE_PAUSE_MS = 2200;
  const HOLD_MS = 2800;

  const NODES = {
    user: {
      name: "Afiliado",
      hint: "Llega al chat",
      detail: "Clara pregunta si es afiliado Colsubsidio y abre la conversación por web o WhatsApp.",
      bullets: ["Canal WhatsApp o web", "Lenguaje natural", "Sin formularios previos"],
    },
    query: {
      name: "Identifica",
      hint: "SERIE o datos",
      detail: "Pide la SERIE o datos básicos para ubicar (o crear) al afiliado antes de recomendar.",
      bullets: ["SERIE Colsubsidio", "Datos básicos", "Primer filtro"],
    },
    agent: {
      name: "Clara",
      hint: "Orquesta el cerebro",
      detail: "Verifica en Mongo, arma el contexto y recomienda.",
      bullets: ["Verifica el usuario", "Elige herramientas", "Guarda la información."],
    },
    perfil: {
      name: "Perfil 360",
      hint: "Quién es y qué necesita",
      detail: "Clara arma una vista completa de su situación —hogar, vivienda y créditos— y calcula qué seguro encaja mejor, con el porqué.",
      bullets: ["Vista completa del afiliado", "Vivienda, crédito y hogar", "Oferta con explicación clara"],
    },
    ofertas: {
      name: "Ofertas",
      hint: "Vivienda · crédito",
      detail: "Consulta ofertas según vivienda/crédito del afiliado en las bases de Colsubsidio.",
      bullets: ["Vivienda y crédito", "Oferta pertinente", "Cruce con seguros"],
    },
    alertas: {
      name: "Alertas",
      hint: "Mora · novedades",
      detail: "Consulta alertas de mora y novedades para no recomendar a ciegas.",
      bullets: ["Mora", "Novedades", "Contexto real"],
    },
    respuesta: {
      name: "Recomienda",
      hint: "O escala al asesor",
      detail: "Clara conversa y recomienda seguros. Actualiza al afiliado y escala a un asesor.",
      bullets: ["Recomendación clara", "Actualiza + sesión Mongo", "Escala si hay cierre"],
    },
  };

  /** Paths L→R in viewBox 0 0 100 100 (node centers) */
  const EDGES = [
    { id: "e-user-query", from: "user", to: "query", d: "M8 50 C14 50, 18 50, 23 50" },
    { id: "e-query-agent", from: "query", to: "agent", d: "M23 50 C29 50, 34 50, 40 50" },
    { id: "e-agent-perfil", from: "agent", to: "perfil", d: "M40 50 C48 32, 54 20, 62 18" },
    { id: "e-agent-ofertas", from: "agent", to: "ofertas", d: "M40 50 C48 50, 54 50, 62 50" },
    { id: "e-agent-alertas", from: "agent", to: "alertas", d: "M40 50 C48 68, 54 80, 62 82" },
    { id: "e-perfil-agent", from: "perfil", to: "agent", d: "M62 18 C54 20, 48 32, 40 50", ret: true },
    { id: "e-ofertas-agent", from: "ofertas", to: "agent", d: "M62 50 C54 50, 48 50, 40 50", ret: true },
    { id: "e-alertas-agent", from: "alertas", to: "agent", d: "M62 82 C54 80, 48 68, 40 50", ret: true },
    { id: "e-agent-resp", from: "agent", to: "respuesta", d: "M40 50 C55 92, 75 92, 90 50" },
  ];

  const ICONS = {
    user: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>',
    query: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>',
    agent: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a4 4 0 0 1 4 4v1h1a3 3 0 0 1 0 6h-.5"/><path d="M8 7V6a4 4 0 0 1 4-4"/><path d="M7.5 13H7a3 3 0 0 1 0-6h1"/><circle cx="9" cy="10" r="1"/><circle cx="15" cy="10" r="1"/><path d="M9 16c.8 1.2 2 2 3 2s2.2-.8 3-2"/><path d="M12 18v3"/><path d="M9 21h6"/></svg>',
    perfil: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>',
    ofertas: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>',
    alertas: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>',
    respuesta: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>',
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
    root.setAttribute("aria-label", "Cerebro de Clara: identifica, verifica en Mongo, recomienda y escala");

    const label = document.createElement("div");
    label.className = "af-label";
    label.innerHTML = '<span class="af-live" aria-hidden="true"></span> Cerebro Clara';
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
      path.classList.add("af-edge");
      if (e.ret) path.classList.add("is-return");
      svg.appendChild(path);
      edgeEls[e.id] = path;
    });

    const particles = [];
    for (let i = 0; i < 4; i++) {
      const c = document.createElementNS(svgNS, "circle");
      c.setAttribute("r", "0.85");
      c.classList.add("af-particle");
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
      el.className = "af-node" + (id === "agent" ? " is-agent" : "");
      el.dataset.id = id;
      el.setAttribute("aria-label", meta.name + ": " + meta.hint);
      el.innerHTML =
        '<span class="af-status" data-st></span>' +
        '<span class="af-ico" aria-hidden="true">' + ICONS[id] + "</span>" +
        '<span class="af-name">' + meta.name + "</span>" +
        '<span class="af-hint">' + meta.hint + "</span>" +
        (id === "agent"
          ? '<span class="af-think-dots" aria-hidden="true"><i></i><i></i><i></i></span>'
          : "");
      stage.appendChild(el);
      nodeEls[id] = el;
    });

    const detail = document.createElement("div");
    detail.className = "af-detail";
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
      if (st) st.textContent = "Analizando";
    } else if (state === "next") {
      el.classList.add("is-next");
      if (st) st.textContent = "";
    } else if (state === "done") {
      el.classList.add("is-done");
      if (st) st.textContent = "";
    } else if (state === "dim") {
      el.classList.add("is-dim");
      if (st) st.textContent = "";
    } else if (st) {
      st.textContent = "";
    }
  }

  function resetVisual(ui) {
    Object.keys(ui.nodeEls).forEach((id) => setNodeState(ui.nodeEls, id, "idle"));
    Object.values(ui.edgeEls).forEach((p) => p.classList.remove("is-lit"));
    ui.particles.forEach((c) => {
      c.classList.remove("is-on", "is-return");
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
    if (!path || !particle || reduceMotion()) {
      return Promise.resolve();
    }
    return new Promise((resolve) => {
      const dur = opts.duration || 900;
      const ret = !!opts.ret;
      path.classList.add("is-lit");
      particle.classList.toggle("is-return", ret);
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
        if (t < 1) {
          ctl.raf = requestAnimationFrame(frame);
        } else {
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

    /** Activa un nodo, muestra su hover/detalle 3s y luego lo cierra. */
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

    // 1. Afiliado
    setNodeState(N, "query", "next");
    if (!(await spotlight("user", "active"))) return;
    if (!(await gate())) return;
    await animateParticle(ctl, ui, "e-user-query", { duration: 700, slot: 0 });
    if (!(await gate())) return;

    // 2. Identifica (SERIE / datos)
    setNodeState(N, "agent", "next");
    if (!(await spotlight("query", "active"))) return;
    if (!(await gate())) return;
    await animateParticle(ctl, ui, "e-query-agent", { duration: 750, slot: 0 });
    if (!(await gate())) return;

    // 3. Clara orquesta (Mongo + herramientas)
    setNodeState(N, "perfil", "next");
    setNodeState(N, "ofertas", "next");
    setNodeState(N, "alertas", "next");
    if (!(await spotlight("agent", "thinking"))) return;
    if (!(await gate())) return;

    // 4. Contexto en paralelo conceptual: perfil → ofertas → alertas
    await animateParticle(ctl, ui, "e-agent-perfil", { duration: 800, slot: 0 });
    if (!(await gate())) return;
    if (!(await spotlight("perfil", "active"))) return;

    await animateParticle(ctl, ui, "e-agent-ofertas", { duration: 800, slot: 1 });
    if (!(await gate())) return;
    if (!(await spotlight("ofertas", "active"))) return;

    await animateParticle(ctl, ui, "e-agent-alertas", { duration: 800, slot: 2 });
    if (!(await gate())) return;
    if (!(await spotlight("alertas", "active"))) return;

    // 5. Retorno y decisión
    if (!(await gate())) return;
    await Promise.all([
      animateParticle(ctl, ui, "e-perfil-agent", { duration: 700, slot: 0, ret: true }),
      (async () => {
        await sleep(80);
        await animateParticle(ctl, ui, "e-ofertas-agent", { duration: 700, slot: 1, ret: true });
      })(),
      (async () => {
        await sleep(160);
        await animateParticle(ctl, ui, "e-alertas-agent", { duration: 700, slot: 2, ret: true });
      })(),
    ]);
    if (!(await gate())) return;

    setNodeState(N, "respuesta", "next");
    if (!(await spotlight("agent", "active"))) return;
    const st = N.agent.querySelector("[data-st]");
    if (st) st.textContent = "";

    if (!(await gate())) return;
    await animateParticle(ctl, ui, "e-agent-resp", { duration: 850, slot: 0 });
    if (!(await gate())) return;

    // 6. Recomienda / escala (sin pago ni póliza)
    if (!(await spotlight("respuesta", "active"))) return;

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
    const maxW = Math.min(220, window.innerWidth * 0.42);
    ui.detail.style.width = maxW + "px";
    ui.detail.style.position = "fixed";

    let left = nodeRect.left + nodeRect.width / 2;
    const half = maxW / 2;
    left = Math.max(half + 8, Math.min(window.innerWidth - half - 8, left));

    // Siempre debajo del nodo, por encima del resto de la página
    const top = nodeRect.bottom + 12;
    ui.detail.classList.remove("is-above");
    ui.detail.style.transformOrigin = "top center";
    ui.detail.style.left = left + "px";
    ui.detail.style.top = top + "px";
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

  /** Evita que el popup fijo quede flotando al hacer scroll. */
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
    const maxW = parseFloat(ui.detail.style.width) || Math.min(220, window.innerWidth * 0.42);
    let left = rect.left + rect.width / 2;
    const half = maxW / 2;
    left = Math.max(half + 8, Math.min(window.innerWidth - half - 8, left));
    ui.detail.style.left = left + "px";
    ui.detail.style.top = rect.bottom + 12 + "px";
  }

  function setHoverBadge(el, on) {
    const st = el && el.querySelector("[data-st]");
    if (!st) return;
    if (on) {
      // No pisar "Analizando" si ya está en thinking
      if (!el.classList.contains("is-thinking") || !st.textContent) {
        if (!st.textContent) st.textContent = "Activo";
      }
    } else if (!el.classList.contains("is-active") && !el.classList.contains("is-thinking")) {
      st.textContent = "";
    }
  }

  function pause(ctl, ui) {
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
      try {
        await runCycle(ctl, ui);
      } catch (e) {
        /* noop */
      }
      if (reduceMotion()) {
        // Static showcase once then stop loop churn
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
        pause(ctl, ui);
        Object.values(ui.nodeEls).forEach((n) => {
          n.classList.remove("is-hover");
          setHoverBadge(n, false);
        });
        el.classList.add("is-hover");
        const st = el.querySelector("[data-st]");
        if (st) st.textContent = "Activo";
        showDetail(ctl, ui, id, el);
      });
      el.addEventListener("pointerleave", () => {
        if (ctl.hoverId === id) ctl.hoverId = null;
        el.classList.remove("is-hover");
        setHoverBadge(el, false);
        if (!el.classList.contains("is-active") && !el.classList.contains("is-thinking")) {
          const st = el.querySelector("[data-st]");
          if (st) st.textContent = "";
        }
        hideDetail(ui, ctl);
        scheduleResume(ctl, ui);
      });
      el.addEventListener("focus", () => {
        ctl.hoverId = id;
        pause(ctl, ui);
        el.classList.add("is-hover");
        const st = el.querySelector("[data-st]");
        if (st) st.textContent = "Activo";
        showDetail(ctl, ui, id, el);
      });
      el.addEventListener("blur", () => {
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

    // Pause when hero view hidden
    const inicio = document.getElementById("inicio");
    if (inicio && "MutationObserver" in window) {
      ctl.viewObs = new MutationObserver(() => {
        const active = inicio.classList.contains("active");
        if (!active) {
          ctl.running = false;
          pause(ctl, ui);
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

    // Start when visible
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
      }, { threshold: 0.25 });
      io.observe(root);
      ctl.io = io;
    } else {
      startLoop(ctl, ui);
    }

    // Reduced motion: show completed snapshot
    if (reduceMotion()) {
      Object.keys(ui.nodeEls).forEach((id) => setNodeState(ui.nodeEls, id, "done"));
      Object.values(ui.edgeEls).forEach((p) => p.classList.add("is-lit"));
    }

    window.__claraAgentFlow = {
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

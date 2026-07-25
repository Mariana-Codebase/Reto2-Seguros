/* Flujo integrado Lara + Sol 5.6 + n8n + Cody. Sin overlays fuera del canvas. */
"use strict";

(function () {
  const flow = document.getElementById("systemFlow");
  const detail = document.getElementById("systemFlowDetail");
  if (!flow || !detail) return;

  const steps = [
    {
      title: "El afiliado inicia con una necesidad real.",
      body: "El flujo comienza con lenguaje natural; no obliga a elegir un producto antes de entender la situación.",
      tags: ["entrada conversacional", "consentimiento"]
    },
    {
      title: "Lara escucha y convierte la conversación en contexto.",
      body: "Identifica intención, datos explícitos y señales de protección. Mantiene un perfil vivo para que la persona no tenga que repetir su historia.",
      tags: ["diagnóstico natural", "perfil vivo", "memoria de sesión"]
    },
    {
      title: "Sol 5.6 razona y selecciona la herramienta correcta.",
      body: "El modelo interpreta la intención; Mongo consulta el perfil, RAG recupera coberturas verificadas y el motor de reglas calcula la recomendación y el precio.",
      tags: ["Sol 5.6", "MongoDB", "RAG", "reglas auditables"]
    },
    {
      title: "n8n entrega el contexto completo, no una tarea aislada.",
      body: "Normaliza eventos y transporta perfil, intención, trazabilidad y estado de la conversación entre Lara, Cody y los sistemas de Colsubsidio.",
      tags: ["webhook", "contexto", "trazabilidad"]
    },
    {
      title: "Cody detecta el momento y activa la siguiente mejor acción.",
      body: "Reacciona a eventos o abandonos, evita mensajes repetidos y retoma la oportunidad con la misma necesidad que Lara ya entendió.",
      tags: ["eventos", "propensión", "anti-spam", "reenganche"]
    },
    {
      title: "El asesor completa el cierre regulado.",
      body: "Recibe la solicitud empaquetada y continúa con el envío de la póliza y la generación de la información de pago, sin pedir los datos de nuevo.",
      tags: ["panel asesor", "póliza", "información de pago"]
    }
  ];

  const nodes = Array.from(flow.querySelectorAll("[data-sf-step]"));
  const reducedMotion = window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let active = 0;
  let timer = null;
  let resumeTimer = null;
  let visible = true;

  function renderDetail(index) {
    const step = steps[index];
    detail.classList.add("is-changing");
    window.setTimeout(function () {
      detail.innerHTML =
        '<span class="sf-detail-index">' + String(index + 1).padStart(2, "0") + "</span>" +
        "<div><strong>" + step.title + "</strong><p>" + step.body + "</p></div>" +
        '<div class="sf-detail-tags">' +
        step.tags.map(function (tag) { return "<span>" + tag + "</span>"; }).join("") +
        "</div>";
      detail.classList.remove("is-changing");
    }, reducedMotion ? 0 : 140);
  }

  function setActive(index) {
    active = (index + nodes.length) % nodes.length;
    flow.style.setProperty("--sf-progress", String(active));
    nodes.forEach(function (node, i) {
      const selected = i === active;
      node.classList.toggle("is-active", selected);
      node.setAttribute("aria-pressed", String(selected));
    });
    renderDetail(active);
  }

  function stop() {
    if (timer) window.clearInterval(timer);
    timer = null;
  }

  function start() {
    stop();
    if (reducedMotion || !visible) return;
    timer = window.setInterval(function () {
      setActive(active + 1);
    }, 3200);
  }

  nodes.forEach(function (node, index) {
    node.addEventListener("click", function () {
      setActive(index);
      stop();
      if (resumeTimer) window.clearTimeout(resumeTimer);
      resumeTimer = window.setTimeout(start, 6500);
    });
  });

  if ("IntersectionObserver" in window) {
    const observer = new IntersectionObserver(function (entries) {
      visible = entries.some(function (entry) { return entry.isIntersecting; });
      if (visible) start();
      else stop();
    }, { threshold: 0.25 });
    observer.observe(flow);
  }

  const home = document.getElementById("inicio");
  if (home && "MutationObserver" in window) {
    new MutationObserver(function () {
      visible = home.classList.contains("active");
      if (visible) start();
      else stop();
    }).observe(home, { attributes: true, attributeFilter: ["class"] });
  }

  setActive(0);
  start();
})();

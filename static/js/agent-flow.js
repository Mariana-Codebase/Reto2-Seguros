/* Dos animaciones paralelas y una sola interacción condicional de abandono. */
"use strict";

(function () {
  const root = document.getElementById("systemFlow");
  const detail = document.getElementById("systemFlowDetail");
  if (!root || !detail) return;

  const copy = {
    afiliado: ["El afiliado inicia la conversación.", "Expresa una necesidad o una preocupación en lenguaje natural.", ["chat", "intención"]],
    consulta: ["La consulta entra al sistema.", "Lara recibe el mensaje y mantiene la sesión para conservar el contexto.", ["sesión", "trazabilidad"]],
    lara: ["Lara entiende y coordina la atención.", "Conversa, pide solo los datos necesarios y decide qué herramienta consultar.", ["agente conversacional", "una pregunta por turno"]],
    perfil: ["El perfil aporta contexto real.", "Consulta la información disponible y guarda únicamente los datos que la persona entrega.", ["perfil vivo", "MongoDB"]],
    coberturas: ["Las coberturas salen de documentos.", "RAG recupera información verificable de las pólizas; Lara no inventa beneficios.", ["RAG", "fuente documental"]],
    cotizar: ["El precio lo calcula un motor de reglas.", "La cotización es determinística y auditable; no la genera el modelo.", ["reglas", "precio trazable"]],
    respuesta: ["Lara entrega información clara.", "Explica la opción, sus coberturas y el precio referencial para que la persona decida.", ["recomendación", "explicabilidad"]],
    asesor: ["El asesor entra únicamente si la persona quiere continuar.", "Recibe el caso de Lara para enviar la póliza y generar la información de pago.", ["solo ruta Lara", "cierre regulado"]],
    n8n: ["n8n ejecuta la ruta independiente de Cody.", "El workflow se activa por un evento o por un abandono válido con datos de contacto.", ["workflow n8n", "trigger"]],
    contexto: ["Cody recibe contexto solo cuando es utilizable.", "En un abandono se requiere interés identificado y un correo u otro dato de contacto disponible.", ["abandono", "contacto disponible"]],
    cody: ["Cody funciona de forma independiente dentro de n8n.", "No conversa con el asesor ni participa en el cierre de Lara; evalúa si corresponde retomar la oportunidad.", ["independiente", "solo n8n"]],
    criterio: ["Los guardrails protegen la experiencia.", "Las reglas validan pertinencia, deduplicación y frecuencia antes de enviar cualquier mensaje.", ["anti-spam", "deduplicación"]],
    mensaje: ["Cody recuerda la conversación y envía la oferta.", "Retoma el interés por el canal disponible sin pedirle a la persona que empiece de cero.", ["recordatorio", "oferta pertinente"]]
  };

  const laraNodes = Array.from(root.querySelectorAll(".sf-lane-lara [data-flow-node]"));
  const codyNodes = Array.from(root.querySelectorAll(".sf-lane-cody [data-flow-node]"));
  const reducedMotion = window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let laraIndex = 0;
  let codyIndex = 0;
  let laraTimer = null;
  let codyTimer = null;

  function setLaneActive(nodes, index) {
    nodes.forEach(function (node, i) {
      const active = i === index;
      node.classList.toggle("is-active", active);
      node.setAttribute("aria-pressed", String(active));
    });
  }

  function showDetail(id) {
    const item = copy[id];
    if (!item) return;
    detail.classList.add("is-changing");
    window.setTimeout(function () {
      detail.innerHTML =
        '<span class="sf-detail-index">' + (id === "cody" ? "C" : id === "lara" ? "L" : "•") + "</span>" +
        "<div><strong>" + item[0] + "</strong><p>" + item[1] + "</p></div>" +
        '<div class="sf-detail-tags">' +
        item[2].map(function (tag) { return "<span>" + tag + "</span>"; }).join("") +
        "</div>";
      detail.classList.remove("is-changing");
    }, reducedMotion ? 0 : 120);
  }

  function stop() {
    if (laraTimer) window.clearInterval(laraTimer);
    if (codyTimer) window.clearInterval(codyTimer);
    laraTimer = null;
    codyTimer = null;
  }

  function start() {
    stop();
    if (reducedMotion) return;
    laraTimer = window.setInterval(function () {
      laraIndex = (laraIndex + 1) % laraNodes.length;
      setLaneActive(laraNodes, laraIndex);
    }, 1800);
    codyTimer = window.setInterval(function () {
      codyIndex = (codyIndex + 1) % codyNodes.length;
      setLaneActive(codyNodes, codyIndex);
    }, 2300);
  }

  root.querySelectorAll("[data-flow-node]").forEach(function (node) {
    node.addEventListener("click", function () {
      showDetail(node.dataset.flowNode);
    });
  });

  if ("IntersectionObserver" in window) {
    const observer = new IntersectionObserver(function (entries) {
      if (entries.some(function (entry) { return entry.isIntersecting; })) start();
      else stop();
    }, { threshold: 0.2 });
    observer.observe(root);
  } else {
    start();
  }

  setLaneActive(laraNodes, 0);
  setLaneActive(codyNodes, 0);
})();

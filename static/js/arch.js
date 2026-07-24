/* =========================================================================
   Clara · Arquitectura — deck de capas + pipeline/tools
========================================================================= */
"use strict";

(function initArch() {
  const view = document.getElementById("arquitectura");
  const deck = document.getElementById("archDeck");
  if (!view) return;

  const GROW_MS = 400;
  const W_REST = 0.25;
  const W_OPEN = 0.34;
  const W_SIDE = 0.22;
  const STEP_MS = 420;
  const HOT_MS = 900;

  let timers = [];
  let pipeHotTimer = null;
  let toolHotTimer = null;

  function prefersReduce() {
    return !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }

  function later(ms, fn) {
    const id = setTimeout(fn, ms);
    timers.push(id);
    return id;
  }

  function clearTimers() {
    timers.forEach(clearTimeout);
    timers = [];
    if (pipeHotTimer) {
      clearInterval(pipeHotTimer);
      pipeHotTimer = null;
    }
    if (toolHotTimer) {
      clearInterval(toolHotTimer);
      toolHotTimer = null;
    }
  }

  if (deck) {
    const row = deck.querySelector(".deck-row");
    const cards = Array.prototype.slice.call(deck.querySelectorAll(".deck-card"));
    const touchy = window.matchMedia && window.matchMedia("(hover: none)").matches;
    const runs = new Map();

    function usableWidth() {
      if (!row) return 0;
      const gap = 12;
      const cs = getComputedStyle(row);
      const pad = (parseFloat(cs.paddingLeft) || 0) + (parseFloat(cs.paddingRight) || 0);
      return row.clientWidth - pad - gap * (cards.length - 1);
    }

    function pxFor(share) {
      return usableWidth() * share;
    }

    function cancelRun(card) {
      const run = runs.get(card);
      if (!run) return;
      if (run.timer) clearInterval(run.timer);
      runs.delete(card);
    }

    function animateWidth(card, targetShare) {
      cancelRun(card);
      const to = pxFor(targetShare);
      const from = card.getBoundingClientRect().width;
      card.style.flex = "0 0 auto";

      if (Math.abs(from - to) < 0.5) {
        card.style.width = to + "px";
        return;
      }

      const start = performance.now();
      const timer = setInterval(function () {
        const t = Math.min(1, (performance.now() - start) / GROW_MS);
        const w = from + (to - from) * t;
        card.style.width = w + "px";
        if (t >= 1) {
          clearInterval(timer);
          runs.delete(card);
          card.style.width = to + "px";
        }
      }, 40);
      runs.set(card, { timer: timer });
    }

    function layout(openIndex) {
      if (window.innerWidth <= 900) {
        cards.forEach(function (c) {
          cancelRun(c);
          c.style.width = "";
        });
        return;
      }
      cards.forEach(function (card, i) {
        const share = openIndex == null ? W_REST : (i === openIndex ? W_OPEN : W_SIDE);
        animateWidth(card, share);
      });
    }

    function openCard(card) {
      const idx = cards.indexOf(card);
      cards.forEach(function (c) { c.classList.toggle("is-open", c === card); });
      layout(idx);
    }

    function closeAll() {
      cards.forEach(function (c) { c.classList.remove("is-open"); });
      layout(null);
    }

    if (!touchy) {
      cards.forEach(function (card) {
        card.addEventListener("mouseenter", function () {
          if (window.innerWidth <= 900) return;
          openCard(card);
        });
      });
      if (row) {
        row.addEventListener("mouseleave", function () {
          if (window.innerWidth <= 900) return;
          closeAll();
        });
      }
    }

    cards.forEach(function (card) {
      card.addEventListener("click", function () {
        if (touchy || window.innerWidth <= 900) openCard(card);
      });
      card.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          openCard(card);
        }
      });
    });

    window.addEventListener("resize", function () {
      const open = cards.findIndex(function (c) { return c.classList.contains("is-open"); });
      layout(open >= 0 ? open : null);
    });

    later(30, function () { layout(touchy && cards[0] ? 0 : null); });
    if (touchy && cards[0]) cards[0].classList.add("is-open");
  }

  function setTrackProgress(pct) {
    const fill = document.getElementById("pipeTrackFill");
    const signal = document.getElementById("pipeSignal");
    const p = Math.max(0, Math.min(100, pct));
    if (fill) fill.style.height = p + "%";
    if (signal) signal.style.top = p + "%";
  }

  function bindToolTilt() {
    const stage = document.getElementById("toolStage");
    const rack = document.getElementById("toolRack");
    if (!stage || !rack || prefersReduce()) return;
    if (stage.dataset.tiltBound === "1") return;
    if (window.matchMedia && window.matchMedia("(hover: none)").matches) return;
    if (window.matchMedia && window.matchMedia("(max-width: 900px)").matches) return;

    stage.dataset.tiltBound = "1";
    let raf = 0;
    let nx = 0;
    let ny = 0;

    function apply() {
      raf = 0;
      rack.style.setProperty("--px", (nx * 10).toFixed(2) + "deg");
      rack.style.setProperty("--py", (-ny * 7).toFixed(2) + "deg");
    }

    stage.addEventListener("pointermove", function (e) {
      const r = stage.getBoundingClientRect();
      if (!r.width || !r.height) return;
      nx = (e.clientX - r.left) / r.width - 0.5;
      ny = (e.clientY - r.top) / r.height - 0.5;
      if (!raf) raf = requestAnimationFrame(apply);
    });

    stage.addEventListener("pointerleave", function () {
      nx = 0;
      ny = 0;
      if (!raf) raf = requestAnimationFrame(apply);
    });
  }

  function revealRest() {
    const stage = document.getElementById("pipeStage");
    const toolsSec = document.getElementById("archTools");
    const steps = Array.prototype.slice.call(view.querySelectorAll(".pipe-step"));
    const tools = Array.prototype.slice.call(view.querySelectorAll(".tool-card"));

    if (stage) stage.classList.remove("is-running");
    if (toolsSec) toolsSec.classList.remove("is-live");
    steps.forEach(function (el) { el.classList.remove("on", "lit", "hot"); });
    tools.forEach(function (el) { el.classList.remove("on", "is-hot"); });
    setTrackProgress(0);

    if (prefersReduce()) {
      steps.forEach(function (el) { el.classList.add("on", "lit"); });
      tools.forEach(function (el) { el.classList.add("on"); });
      if (toolsSec) toolsSec.classList.add("is-live");
      setTrackProgress(100);
      return;
    }

    if (stage) stage.classList.add("is-running");

    steps.forEach(function (step, i) {
      later(180 + i * STEP_MS, function () {
        step.classList.add("on");
        later(160, function () {
          step.classList.add("lit");
          setTrackProgress(((i + 1) / steps.length) * 100);

          steps.forEach(function (s) { s.classList.remove("hot"); });
          step.classList.add("hot");
          later(HOT_MS, function () { step.classList.remove("hot"); });
        });
      });
    });

    const afterPipe = 180 + steps.length * STEP_MS + 500;

    later(afterPipe, function () {
      let hi = 0;
      pipeHotTimer = setInterval(function () {
        if (!view.classList.contains("active")) return;
        steps.forEach(function (s) { s.classList.remove("hot"); });
        steps[hi].classList.add("hot");
        setTrackProgress(((hi + 1) / steps.length) * 100);
        hi = (hi + 1) % steps.length;
      }, 1600);
    });

    // Tools: cascada + hint + spotlight rotativo
    later(afterPipe - 200, function () {
      if (toolsSec) toolsSec.classList.add("is-live");
    });

    tools.forEach(function (card, i) {
      later(afterPipe + i * 110, function () {
        card.classList.add("on");
      });
    });

    later(afterPipe + tools.length * 110 + 400, function () {
      let ti = 0;
      toolHotTimer = setInterval(function () {
        if (!view.classList.contains("active")) return;
        tools.forEach(function (t) { t.classList.remove("is-hot"); });
        if (tools[ti]) tools[ti].classList.add("is-hot");
        ti = (ti + 1) % tools.length;
      }, 1400);
    });
  }

  function start() {
    if (!view.classList.contains("active")) return;
    clearTimers();
    bindToolTilt();
    revealRest();
  }

  function stop() {
    clearTimers();
    const stage = document.getElementById("pipeStage");
    const toolsSec = document.getElementById("archTools");
    if (stage) stage.classList.remove("is-running");
    if (toolsSec) toolsSec.classList.remove("is-live");
    view.querySelectorAll(".pipe-step").forEach(function (el) {
      el.classList.remove("hot");
    });
    view.querySelectorAll(".tool-card").forEach(function (el) {
      el.classList.remove("is-hot");
    });
  }

  if (view.classList.contains("active")) later(60, start);

  new MutationObserver(function () {
    if (view.classList.contains("active")) start();
    else stop();
  }).observe(view, { attributes: true, attributeFilter: ["class"] });
})();

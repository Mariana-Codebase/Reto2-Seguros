/* =========================================================================
   Lara · Hero live chat — bucle lento y muy visible
========================================================================= */
"use strict";

(function () {
  function boot() {
    const body = document.getElementById("heroLiveChat");
    const statusEl = document.getElementById("heroLiveStatus");
    if (!body) {
      console.warn("[Lara] #heroLiveChat no encontrado");
      return;
    }

    const lines = [
      { role: "bot", text: "Hola, soy Lara. Para recomendarte lo adecuado, primero quiero entender tu situación." },
      { role: "user", text: "Vivo en arriendo con mi pareja e hijo." },
      {
        role: "bot",
        text: "Con base en tu perfil te propongo el Seguro de Vida: protege el ingreso de tu familia.",
        stamp: "✓ respaldado · $28.900/mes"
      },
      { role: "user", text: "Me interesa. ¿Me lo envías por escrito?" },
      { role: "bot", text: "Te envié el resumen a tu correo y aquí tienes tu enlace de pago seguro." }
    ];

    let gen = 0;
    const pending = [];

    function after(ms, fn) {
      const id = setTimeout(fn, ms);
      pending.push(id);
      return id;
    }

    function kill() {
      while (pending.length) clearTimeout(pending.pop());
    }

    function status(t) {
      if (statusEl) statusEl.textContent = t;
    }

    function scrollToBottom() {
      // Baja al último mensaje sin barra visible
      body.scrollTop = body.scrollHeight;
    }

    function addBubble(item) {
      const el = document.createElement("div");
      el.className = "mini " + item.role;
      el.appendChild(document.createTextNode(item.text));
      if (item.stamp) {
        el.appendChild(document.createElement("br"));
        const s = document.createElement("span");
        s.className = "stamp";
        s.textContent = item.stamp;
        el.appendChild(s);
      }
      body.appendChild(el);
      requestAnimationFrame(function () {
        requestAnimationFrame(function () {
          el.classList.add("in");
          scrollToBottom();
        });
      });
      scrollToBottom();
    }

    function addTyping() {
      hideTyping();
      const t = document.createElement("div");
      t.className = "typing";
      t.id = "heroTyping";
      t.innerHTML = "<i></i><i></i><i></i>";
      body.appendChild(t);
      requestAnimationFrame(function () {
        requestAnimationFrame(function () {
          t.classList.add("in");
          scrollToBottom();
        });
      });
      scrollToBottom();
    }

    function hideTyping() {
      const t = document.getElementById("heroTyping");
      if (t) t.remove();
    }

    // Encadena pasos en serie (más fiable que programar todos los timeouts al inicio)
    function play(myGen) {
      if (myGen !== gen) return;
      body.innerHTML = "";
      status("En línea · responde al instante");

      let i = 0;

      function next() {
        if (myGen !== gen) return;
        if (i >= lines.length) {
          status("En línea · responde al instante");
          after(1200, function () {
            if (myGen !== gen) return;
            body.style.opacity = "0.25";
            after(350, function () {
              if (myGen !== gen) return;
              body.style.opacity = "1";
              play(myGen);
            });
          });
          return;
        }

        const item = lines[i++];

        if (item.role === "bot") {
          status("escribiendo…");
          addTyping();
          after(1100, function () {
            if (myGen !== gen) return;
            hideTyping();
            addBubble(item);
            status("En línea · responde al instante");
            after(item.stamp ? 1400 : 1100, next);
          });
        } else {
          after(650, function () {
            if (myGen !== gen) return;
            addBubble(item);
            after(900, next);
          });
        }
      }

      after(200, next);
    }

    function start() {
      kill();
      gen += 1;
      body.style.transition = "opacity .35s ease";
      body.style.opacity = "1";
      console.info("[Lara] hero live chat started");
      play(gen);
    }

    function stop() {
      kill();
      gen += 1;
      hideTyping();
    }

    start();

    const home = document.getElementById("inicio");
    if (home) {
      new MutationObserver(function () {
        if (home.classList.contains("active")) start();
        else stop();
      }).observe(home, { attributes: true, attributeFilter: ["class"] });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();

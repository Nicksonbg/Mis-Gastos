/* Reportar un problema: captura la pantalla actual, DIFUMINA todo texto con cifras
   (lado seguro: tapa de más, nunca de menos) y lo envía con un mensaje. */
(function () {
  if (!window.PB_API_MSG) return;
  var L = (window.PB_LANG || "es").slice(0, 2);
  var TX = ({
    es: { btn: "Problema", title: "Reportar un problema", ph: "Cuéntanos qué ha pasado…", note: "Adjuntamos una captura de esta pantalla con las cifras difuminadas por tu seguridad.", keep: "Enviar con captura", drop: "Enviar sin captura", send: "Enviar", cancel: "Cancelar", sending: "Enviando…", prep: "Preparando captura…", ok: "¡Gracias! Lo hemos recibido.", err: "No se pudo enviar. Inténtalo de nuevo.", empty: "Escribe primero el problema.", aiwarn: "La IA ha visto cantidades en la captura; ya van difuminadas.", nocap: "No se pudo hacer la captura; se envía solo el texto." },
    en: { btn: "Problem", title: "Report a problem", ph: "Tell us what happened…", note: "We attach a screenshot of this screen with the amounts blurred for your safety.", keep: "Send with screenshot", drop: "Send without screenshot", send: "Send", cancel: "Cancel", sending: "Sending…", prep: "Preparing screenshot…", ok: "Thanks! We got it.", err: "Could not send. Try again.", empty: "Write the problem first.", aiwarn: "The AI spotted amounts in the screenshot; they are already blurred.", nocap: "Could not take the screenshot; sending text only." },
    bg: { btn: "Проблем", title: "Съобщи проблем", ph: "Кажи ни какво стана…", note: "Прилагаме снимка на този екран със замъглени суми за твоята сигурност.", keep: "Изпрати със снимка", drop: "Изпрати без снимка", send: "Изпрати", cancel: "Отказ", sending: "Изпраща…", prep: "Подготвя снимка…", ok: "Благодарим! Получихме го.", err: "Неуспешно. Опитай пак.", empty: "Първо напиши проблема.", aiwarn: "ИИ видя суми в снимката; те вече са замъглени.", nocap: "Снимката не успя; изпраща се само текст." }
  })[L] || null;
  if (!TX) TX = { btn: "Problem", title: "Report a problem", ph: "…", note: "", keep: "Send with screenshot", drop: "Send without screenshot", send: "Send", cancel: "Cancel", sending: "…", prep: "…", ok: "OK", err: "Error", empty: "Write first.", aiwarn: "", nocap: "" };

  // Envía JSON con auth flexible: por token Bearer (app, window.PB_TOKEN()) o por cookie (web).
  function postJSON(url, obj) {
    return Promise.resolve(typeof window.PB_TOKEN === "function" ? window.PB_TOKEN() : null).then(function (tok) {
      var h = { "Content-Type": "application/json" };
      if (tok) h["Authorization"] = "Bearer " + tok;
      var opt = { method: "POST", headers: h, body: JSON.stringify(obj) };
      if (!tok) opt.credentials = "same-origin";
      return fetch(url, opt);
    });
  }

  function loadH2C() {
    return new Promise(function (res, rej) {
      if (window.html2canvas) return res(window.html2canvas);
      var s = document.createElement("script");
      s.src = window.PB_H2C; s.onload = function () { res(window.html2canvas); }; s.onerror = rej;
      document.head.appendChild(s);
    });
  }

  // Captura <main> y difumina los rectángulos de todo texto con dígitos. Devuelve dataURL o null.
  function capture() {
    var area = document.querySelector("main") || document.body;
    var base = area.getBoundingClientRect();
    // 1) Rectángulos de texto con cifras + inputs con valor numérico.
    var rects = [];
    try {
      var walk = document.createTreeWalker(area, NodeFilter.SHOW_TEXT, {
        acceptNode: function (n) {
          if (!/\d/.test(n.nodeValue || "")) return NodeFilter.FILTER_REJECT;
          var p = n.parentElement; if (!p) return NodeFilter.FILTER_REJECT;
          var st = getComputedStyle(p);
          if (st.visibility === "hidden" || st.display === "none" || +st.opacity === 0) return NodeFilter.FILTER_REJECT;
          return NodeFilter.FILTER_ACCEPT;
        }
      });
      var node;
      while ((node = walk.nextNode())) {
        var r = document.createRange(); r.selectNodeContents(node);
        var list = r.getClientRects();
        for (var i = 0; i < list.length; i++) if (list[i].width > 0 && list[i].height > 0) rects.push(list[i]);
      }
      area.querySelectorAll("input,textarea").forEach(function (el) {
        if (/\d/.test(el.value || "")) { var rc = el.getBoundingClientRect(); if (rc.width > 0 && rc.height > 0) rects.push(rc); }
      });
    } catch (e) { }
    return loadH2C().then(function (h2c) {
      return h2c(area, { backgroundColor: getComputedStyle(document.body).backgroundColor || "#000", logging: false, useCORS: true });
    }).then(function (canvas) {
      var scale = canvas.width / base.width;
      var ctx = canvas.getContext("2d");
      ctx.setTransform(1, 0, 0, 1, 0, 0); // html2canvas deja una escala activa; la reseteamos
      var copy = document.createElement("canvas"); copy.width = canvas.width; copy.height = canvas.height;
      copy.getContext("2d").drawImage(canvas, 0, 0);
      rects.forEach(function (rc) {
        var pad = 7;
        var bx = (rc.left - base.left - pad) * scale, by = (rc.top - base.top - pad) * scale;
        var bw = (rc.width + pad * 2) * scale, bh = (rc.height + pad * 2) * scale;
        // Desenfoque proporcional al tamaño del texto (las cifras grandes necesitan más).
        var br = Math.max(10, Math.round(bh * 0.5)), m = br + 6;
        // Región origen=destino 1:1, recortada al lienzo (evita bordes transparentes).
        var sx = Math.max(0, bx - m), sy = Math.max(0, by - m);
        var ex = Math.min(canvas.width, bx + bw + m), ey = Math.min(canvas.height, by + bh + m);
        ctx.save();
        ctx.beginPath(); ctx.rect(bx, by, bw, bh); ctx.clip();
        ctx.filter = "blur(" + br + "px)";
        ctx.drawImage(copy, sx, sy, ex - sx, ey - sy, sx, sy, ex - sx, ey - sy);     // original -> difuminado
        ctx.drawImage(canvas, sx, sy, ex - sx, ey - sy, sx, sy, ex - sx, ey - sy);   // acumula
        ctx.drawImage(canvas, sx, sy, ex - sx, ey - sy, sx, sy, ex - sx, ey - sy);   // acumula
        ctx.restore();
      });
      ctx.filter = "none";
      return canvas.toDataURL("image/jpeg", 0.8);
    }).catch(function () { return null; });
  }

  var dlg, foto = null;
  function buildUI() {
    var st = document.createElement("style");
    st.textContent =
      "#pb-rep-btn{position:fixed;right:14px;bottom:calc(env(safe-area-inset-bottom,0px) + 78px);z-index:50;" +
      "background:var(--card,#1b1b1f);color:var(--text,#fff);border:1px solid var(--line,#333);border-radius:999px;" +
      "padding:9px 14px;font:inherit;font-size:13px;cursor:pointer;box-shadow:0 4px 14px rgba(0,0,0,.35);opacity:.92}" +
      "#pb-rep-btn:hover{opacity:1}" +
      "#pb-rep-dlg{border:none;border-radius:16px;padding:18px;max-width:460px;width:92vw;background:var(--card,#1b1b1f);color:var(--text,#fff)}" +
      "#pb-rep-dlg::backdrop{background:rgba(0,0,0,.5)}";
    document.head.appendChild(st);
    var btn = document.createElement("button");
    btn.id = "pb-rep-btn"; btn.type = "button"; btn.textContent = "🛟 " + TX.btn;
    btn.setAttribute("aria-label", TX.title);
    document.body.appendChild(btn);

    dlg = document.createElement("dialog"); dlg.id = "pb-rep-dlg";
    dlg.innerHTML =
      '<form method="dialog"><h3 style="margin:0 0 10px">' + TX.title + '</h3>' +
      '<textarea id="pb-rep-txt" rows="4" placeholder="' + TX.ph.replace(/"/g, "&quot;") + '" maxlength="3000" style="width:100%;padding:10px;border:1px solid var(--line);border-radius:10px;background:var(--bg);color:var(--text);font:inherit;resize:vertical"></textarea>' +
      '<div id="pb-rep-cap" style="margin-top:10px"></div>' +
      '<p class="muted small" id="pb-rep-note" style="margin:8px 0 0"></p>' +
      '<div class="row" style="gap:8px;margin-top:12px;flex-wrap:wrap"><span class="spacer"></span>' +
      '<button type="button" class="btn ghost" id="pb-rep-x">' + TX.cancel + '</button>' +
      '<button type="button" class="btn" id="pb-rep-send">' + TX.send + '</button></div></form>';
    document.body.appendChild(dlg);

    btn.addEventListener("click", open);
    dlg.querySelector("#pb-rep-x").addEventListener("click", function () { dlg.close(); });
    dlg.querySelector("#pb-rep-send").addEventListener("click", send);
  }

  function open() {
    foto = null;
    dlg.querySelector("#pb-rep-txt").value = "";
    var cap = dlg.querySelector("#pb-rep-cap"), note = dlg.querySelector("#pb-rep-note");
    cap.innerHTML = '<p class="muted small">' + TX.prep + "</p>"; note.textContent = "";
    dlg.showModal();
    capture().then(function (dataURL) {
      foto = dataURL;
      if (!dataURL) { cap.innerHTML = '<p class="muted small">' + TX.nocap + "</p>"; return; }
      cap.innerHTML = '<img src="' + dataURL + '" alt="" style="max-width:100%;max-height:300px;border-radius:10px;border:1px solid var(--line)">' +
        '<label style="display:flex;align-items:center;gap:8px;margin-top:8px" class="small"><input type="checkbox" id="pb-rep-keep" checked> ' + TX.keep + "</label>";
      note.textContent = TX.note;
      // Aviso de la IA (best-effort): si detecta cantidades, lo decimos; ya van difuminadas.
      if (window.PB_API_MSG_REV) {
        postJSON(window.PB_API_MSG_REV, { foto: dataURL })
          .then(function (r) { return r.json(); }).then(function (j) { if (j && j.hay) note.textContent = TX.aiwarn + " " + TX.note; }).catch(function () { });
      }
    });
  }

  function send() {
    var txt = dlg.querySelector("#pb-rep-txt").value.trim();
    var note = dlg.querySelector("#pb-rep-note");
    if (!txt) { note.textContent = TX.empty; return; }
    var keep = dlg.querySelector("#pb-rep-keep");
    var payload = { texto: txt, lang: L, plat: window.PB_PLAT || "web", version: window.PB_VER || "" };
    if (foto && (!keep || keep.checked)) payload.foto = foto;
    var sb = dlg.querySelector("#pb-rep-send"); sb.disabled = true; note.textContent = TX.sending;
    postJSON(window.PB_API_MSG, payload)
      .then(function (r) { if (!r.ok) throw 0; return r.json(); })
      .then(function () { dlg.close(); alert(TX.ok); })
      .catch(function () { note.textContent = TX.err; })
      .then(function () { sb.disabled = false; });
  }

  if (document.readyState !== "loading") buildUI();
  else document.addEventListener("DOMContentLoaded", buildUI);
})();

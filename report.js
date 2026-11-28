/* Reportar un problema: mensaje de texto + captura OPCIONAL de la pantalla visible
   (la hace el usuario con un botón), con las cifras difuminadas de forma suave.
   El difuminado se hace reduciendo+ampliando cada cifra (sin ctx.filter, que iOS
   Safari no soporta en canvas antes de 18.4). */
(function () {
  if (!window.PB_API_MSG) return;
  var L = (window.PB_LANG || "es").slice(0, 2);
  var TX = ({
    es: { btn: "Problema", title: "Reportar un problema", ph: "Cuéntanos qué ha pasado…", shot: "📸 Capturar pantalla", reshot: "Repetir captura", remove: "Quitar captura", note: "La captura es opcional y solo coge lo que se ve. Tapamos las cifras por tu seguridad.", send: "Enviar", cancel: "Cancelar", sending: "Enviando…", shooting: "Capturando…", ok: "¡Gracias! Lo hemos recibido.", err: "No se pudo enviar. Inténtalo de nuevo.", empty: "Escribe primero el problema.", nocap: "No se pudo capturar la pantalla.", zoom: "Toca la imagen para verla a tamaño real." },
    en: { btn: "Problem", title: "Report a problem", ph: "Tell us what happened…", shot: "📸 Capture screen", reshot: "Retake", remove: "Remove screenshot", note: "The screenshot is optional and only takes what's visible. We blur the amounts for your safety.", send: "Send", cancel: "Cancel", sending: "Sending…", shooting: "Capturing…", ok: "Thanks! We got it.", err: "Could not send. Try again.", empty: "Write the problem first.", nocap: "Could not capture the screen.", zoom: "Tap the image to view it full size." },
    bg: { btn: "Проблем", title: "Съобщи проблем", ph: "Кажи ни какво стана…", shot: "📸 Снимка на екрана", reshot: "Отново", remove: "Премахни снимката", note: "Снимката е по избор и взема само видимото. Замъгляваме сумите за сигурност.", send: "Изпрати", cancel: "Отказ", sending: "Изпраща…", shooting: "Прави снимка…", ok: "Благодарим! Получихме го.", err: "Неуспешно. Опитай пак.", empty: "Първо напиши проблема.", nocap: "Екранът не можа да се заснеме.", zoom: "Докосни за реален размер." }
  })[L] || { btn: "Problem", title: "Report a problem", ph: "…", shot: "Capture", reshot: "Retake", remove: "Remove", note: "", send: "Send", cancel: "Cancel", sending: "…", shooting: "…", ok: "OK", err: "Error", empty: "Write first.", nocap: "Error", zoom: "" };

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

  function loadShot() {
    return new Promise(function (res, rej) {
      if (window.modernScreenshot) return res(window.modernScreenshot);
      var s = document.createElement("script");
      s.src = window.PB_H2C; s.onload = function () { res(window.modernScreenshot); }; s.onerror = rej;
      document.head.appendChild(s);
    });
  }

  // Rectángulos (coords de viewport) de SOLO las cantidades de dinero visibles:
  // importes con decimales de coma (34,19) o con miles de punto (1.287). Así no se
  // difuminan fechas, "18 meses", "2026", porcentajes ni la UI: solo tus importes.
  var MONEY = /\d[\d.]*,\d{2}|\d{1,3}(?:\.\d{3})+/g;
  function digitRects() {
    var W = window.innerWidth, H = window.innerHeight, rects = [];
    function inView(rc) { return rc.width > 0 && rc.height > 0 && rc.bottom > 0 && rc.top < H && rc.right > 0 && rc.left < W; }
    try {
      var walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
        acceptNode: function (n) {
          MONEY.lastIndex = 0;
          if (!MONEY.test(n.nodeValue || "")) return NodeFilter.FILTER_REJECT;
          var p = n.parentElement; if (!p) return NodeFilter.FILTER_REJECT;
          if (p.closest("#pb-rep-dlg,#pb-rep-btn")) return NodeFilter.FILTER_REJECT;
          var st = getComputedStyle(p);
          if (st.visibility === "hidden" || st.display === "none" || +st.opacity === 0) return NodeFilter.FILTER_REJECT;
          return NodeFilter.FILTER_ACCEPT;
        }
      });
      var node;
      while ((node = walk.nextNode())) {
        var v = node.nodeValue || "", m; MONEY.lastIndex = 0;
        while ((m = MONEY.exec(v))) {
          try {
            var r = document.createRange();
            r.setStart(node, m.index); r.setEnd(node, m.index + m[0].length);
            var list = r.getClientRects();
            for (var i = 0; i < list.length; i++) { if (inView(list[i])) rects.push(list[i]); }
          } catch (e) { }
        }
      }
      document.body.querySelectorAll("input,textarea").forEach(function (el) {
        if (el.closest("#pb-rep-dlg")) return;
        MONEY.lastIndex = 0;
        if (MONEY.test(el.value || "")) { var rc = el.getBoundingClientRect(); if (inView(rc)) rects.push(rc); }
      });
    } catch (e) { }
    return rects;
  }

  // Difumina una zona del canvas reduciéndola a 'th' px de alto y volviéndola a ampliar.
  // Sin ctx.filter (iOS Safari no lo soporta en canvas antes de 18.4).
  function blurRegion(ctx, src, tmp, tctx, bx, by, bw, bh, th) {
    th = Math.max(2, Math.round(th)); var tw = Math.max(2, Math.round(bw * (th / bh)));
    tmp.width = tw; tmp.height = th; tctx.imageSmoothingEnabled = true;
    tctx.clearRect(0, 0, tw, th);
    tctx.drawImage(src, bx, by, bw, bh, 0, 0, tw, th);
    ctx.drawImage(tmp, 0, 0, tw, th, bx, by, bw, bh);
  }

  // Captura SOLO lo visible (viewport) y difumina las cifras. Devuelve dataURL o null.
  // Nunca se queda colgada: tope de tiempo + el botón se restaura pase lo que pase.
  function capture() {
    var W = window.innerWidth, H = window.innerHeight, SX = window.scrollX || 0, SY = window.scrollY || 0;
    var rects = digitRects();
    var btn = document.getElementById("pb-rep-btn"); var prev = btn ? btn.style.display : "";
    if (btn) btn.style.display = "none";
    function restore() { if (btn) btn.style.display = prev; }
    // font:false evita que la librería descargue e incruste las Google Fonts (eso se colgaba).
    // filter: quita la UI del propio reporte y los nodos que inyectan las extensiones del
    //   navegador (Grammarly, LastPass…), cuyas imágenes chrome-extension:// no se pueden
    //   incrustar y "ensucian" el lienzo (toDataURL fallaba → "No se pudo capturar").
    // placeholderImage + timeout: si una imagen no carga, se sustituye en vez de ensuciar.
    var PH = "data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==";
    var work = loadShot().then(function (ms) {
      return ms.domToCanvas(document.body, {
        width: W, height: H, scale: 2, font: false, timeout: 6000, placeholderImage: PH,
        filter: function (node) {
          if (!node || node.nodeType !== 1) return true;
          var id = node.id || "";
          if (id === "pb-rep-dlg" || id === "pb-rep-ov" || id === "pb-rep-btn") return false;
          var nn = (node.nodeName || "").toLowerCase();
          if (nn.indexOf("grammarly") >= 0 || nn.indexOf("-extension") >= 0 || nn.indexOf("lastpass") >= 0) return false;
          var cn = typeof node.className === "string" ? node.className : "";
          if (/grammarly|lastpass|gramm/i.test(id + " " + cn)) return false;
          return true;
        },
        style: { transform: "translate(" + (-SX) + "px," + (-SY) + "px)", transformOrigin: "top left" },
        backgroundColor: getComputedStyle(document.body).backgroundColor || "#000"
      });
    }).then(function (canvas) {
      var scale = canvas.width / W;
      var ctx = canvas.getContext("2d"); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.imageSmoothingEnabled = true;
      var copy = document.createElement("canvas"); copy.width = canvas.width; copy.height = canvas.height;
      copy.getContext("2d").drawImage(canvas, 0, 0);
      var tmp = document.createElement("canvas"), tctx = tmp.getContext("2d");
      // ¿Se puede usar blur gaussiano? (escritorio, iOS 18.4+). Si sí, lo usamos para
      // suavizar el reescalado y que no se vean bloques.
      var useFilter = (function () { try { ctx.filter = "blur(2px)"; var ok = ctx.filter === "blur(2px)"; ctx.filter = "none"; return ok; } catch (e) { return false; } })();
      rects.forEach(function (rc) {
        var pad = 3;
        var bx = Math.max(0, Math.round((rc.left - pad) * scale));
        var by = Math.max(0, Math.round((rc.top - pad) * scale));
        var bw = Math.round(Math.min((rc.width + pad * 2) * scale, canvas.width - bx));
        var bh = Math.round(Math.min((rc.height + pad * 2) * scale, canvas.height - by));
        if (bw < 2 || bh < 2) return;
        // 1) Reducir la zona a muy pocos píxeles: destruye por completo la legibilidad.
        var th = Math.max(3, Math.min(Math.round(bh * 0.12), 6)), tw = Math.max(3, Math.round(bw * (th / bh)));
        tmp.width = tw; tmp.height = th; tctx.imageSmoothingEnabled = true; tctx.clearRect(0, 0, tw, th);
        tctx.drawImage(copy, bx, by, bw, bh, 0, 0, tw, th);
        // 2) Volver a ampliar con suavizado (y blur gaussiano si se puede): queda suave,
        //    sin bloques, pero ilegible porque el detalle ya se perdió al reducir.
        ctx.save();
        ctx.beginPath(); ctx.rect(bx, by, bw, bh); ctx.clip();
        ctx.imageSmoothingEnabled = true;
        if (useFilter) ctx.filter = "blur(" + Math.max(3, Math.round(bh * 0.13)) + "px)";
        ctx.drawImage(tmp, 0, 0, tw, th, bx, by, bw, bh);
        ctx.restore();
      });
      return canvas.toDataURL("image/jpeg", 0.92);
    });
    var timed = new Promise(function (res) { setTimeout(function () { res("__timeout__"); }, 10000); });
    return Promise.race([work, timed]).then(function (r) {
      restore();
      return (typeof r === "string" && r.indexOf("data:") === 0) ? r : null;
    }).catch(function () { restore(); return null; });
  }

  var dlg, ov, foto = null;
  function buildUI() {
    var st = document.createElement("style");
    st.textContent =
      "#pb-rep-btn{position:fixed;left:14px;bottom:calc(env(safe-area-inset-bottom,0px) + 78px);z-index:50;" +
      "background:var(--card,#1b1b1f);color:var(--text,#fff);border:1px solid var(--line,#333);border-radius:999px;" +
      "padding:9px 14px;font:inherit;font-size:13px;cursor:pointer;box-shadow:0 4px 14px rgba(0,0,0,.35);opacity:.92}" +
      "#pb-rep-btn:hover{opacity:1}" +
      "#pb-rep-dlg{border:none;border-radius:16px;padding:18px;max-width:460px;width:92vw;background:var(--card,#1b1b1f);color:var(--text,#fff)}" +
      "#pb-rep-dlg::backdrop{background:rgba(0,0,0,.5)}" +
      "#pb-rep-ov{display:none;position:fixed;inset:0;z-index:100;background:rgba(8,10,14,.98);overflow:auto;padding:16px;text-align:center;-webkit-overflow-scrolling:touch}" +
      "#pb-rep-ov img{display:block;margin:12px auto;max-width:100%;height:auto;background:#fff;border-radius:6px;box-shadow:0 0 0 2px rgba(255,255,255,.2);cursor:zoom-in}" +
      "#pb-rep-ov img.zoomed{max-width:none;margin:12px 0;cursor:zoom-out}" +
      "#pb-rep-ovx{position:fixed;top:12px;right:14px;z-index:101;background:#fff;color:#000;border:none;border-radius:999px;width:42px;height:42px;font-size:20px;line-height:42px;cursor:pointer}";
    document.head.appendChild(st);

    var btn = document.createElement("button");
    btn.id = "pb-rep-btn"; btn.type = "button"; btn.textContent = "🛟 " + TX.btn;
    btn.setAttribute("aria-label", TX.title);
    document.body.appendChild(btn);

    dlg = document.createElement("dialog"); dlg.id = "pb-rep-dlg";
    dlg.innerHTML =
      '<form method="dialog"><h3 style="margin:0 0 10px">' + TX.title + '</h3>' +
      '<textarea id="pb-rep-txt" rows="4" placeholder="' + TX.ph.replace(/"/g, "&quot;") + '" maxlength="3000" style="width:100%;padding:10px;border:1px solid var(--line);border-radius:10px;background:var(--bg);color:var(--text);font:inherit;resize:vertical"></textarea>' +
      '<div style="margin-top:10px"><button type="button" class="btn ghost" id="pb-rep-shot"></button></div>' +
      '<div id="pb-rep-cap" style="margin-top:10px"></div>' +
      '<p class="muted small" id="pb-rep-note" style="margin:8px 0 0"></p>' +
      '<div class="row" style="gap:8px;margin-top:12px;flex-wrap:wrap"><span class="spacer"></span>' +
      '<button type="button" class="btn ghost" id="pb-rep-x">' + TX.cancel + '</button>' +
      '<button type="button" class="btn" id="pb-rep-send">' + TX.send + '</button></div></form>';
    document.body.appendChild(dlg);

    ov = document.createElement("div"); ov.id = "pb-rep-ov";
    ov.innerHTML = '<button type="button" id="pb-rep-ovx" aria-label="Cerrar">✕</button><img alt="">';
    document.body.appendChild(ov);
    var ovImg = ov.querySelector("img");
    function cerrarOv() { ov.style.display = "none"; ovImg.classList.remove("zoomed"); ovImg.style.width = ""; }
    ov.addEventListener("click", function (e) { if (e.target === ov || e.target.id === "pb-rep-ovx") cerrarOv(); });
    ovImg.addEventListener("click", function (e) {
      e.stopPropagation();
      if (ovImg.classList.toggle("zoomed")) ovImg.style.width = Math.max(320, Math.round(ovImg.naturalWidth / 2)) + "px";
      else ovImg.style.width = "";
    });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape" && ov.style.display === "block") cerrarOv(); });

    btn.addEventListener("click", open);
    dlg.querySelector("#pb-rep-x").addEventListener("click", function () { dlg.close(); });
    dlg.querySelector("#pb-rep-send").addEventListener("click", send);
    dlg.querySelector("#pb-rep-shot").addEventListener("click", doShot);
  }

  function setShotBtn(label, disabled) {
    var b = dlg.querySelector("#pb-rep-shot"); b.textContent = label; b.disabled = !!disabled;
  }

  function open() {
    foto = null;
    dlg.querySelector("#pb-rep-txt").value = "";
    dlg.querySelector("#pb-rep-cap").innerHTML = "";
    dlg.querySelector("#pb-rep-note").textContent = TX.note;
    setShotBtn(TX.shot, false);
    dlg.showModal();
  }

  // Cierra el diálogo un instante para capturar la pantalla real, y lo reabre con la vista previa.
  function doShot() {
    var note = dlg.querySelector("#pb-rep-note");
    var saved = dlg.querySelector("#pb-rep-txt").value;
    setShotBtn(TX.shooting, true);
    dlg.close();
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        capture().then(function (dataURL) {
          dlg.showModal();
          dlg.querySelector("#pb-rep-txt").value = saved;
          if (!dataURL) { setShotBtn(TX.shot, false); note.textContent = TX.nocap; return; }
          foto = dataURL;
          showPreview(dataURL);
          setShotBtn(TX.reshot, false);
          note.textContent = TX.note;
        });
      });
    });
  }

  function showPreview(dataURL) {
    var cap = dlg.querySelector("#pb-rep-cap");
    cap.innerHTML = '<div style="background:#eceff3;border:1px solid var(--line);border-radius:12px;padding:6px;display:inline-block;max-width:100%">' +
      '<img id="pb-rep-img" src="' + dataURL + '" alt="" style="display:block;max-width:100%;max-height:360px;border-radius:7px;cursor:zoom-in"></div>' +
      '<div class="muted small" style="margin-top:6px">👆 ' + TX.zoom + '</div>' +
      '<button type="button" class="btn ghost sm" id="pb-rep-rm" style="margin-top:6px">' + TX.remove + '</button>';
    cap.querySelector("#pb-rep-img").addEventListener("click", function () {
      var oi = ov.querySelector("img");
      oi.classList.remove("zoomed"); oi.style.width = "";
      oi.src = dataURL; ov.scrollTop = 0; ov.scrollLeft = 0; ov.style.display = "block";
    });
    cap.querySelector("#pb-rep-rm").addEventListener("click", function () {
      foto = null; cap.innerHTML = ""; setShotBtn(TX.shot, false);
    });
  }

  function send() {
    var txt = dlg.querySelector("#pb-rep-txt").value.trim();
    var note = dlg.querySelector("#pb-rep-note");
    if (!txt) { note.textContent = TX.empty; return; }
    var payload = { texto: txt, lang: L, plat: window.PB_PLAT || "web", version: window.PB_VER || "" };
    if (foto) payload.foto = foto;
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

// Escáner de tickets y facturas — compartido por la web y la app.
// 1) Cámara o galería · 2) detección de bordes con esquinas ajustables, enderezado y contraste · 3) lectura con IA.
// La página define window.PB_SCAN = { api, getToken: async () => token|null, open: datos => abre el formulario relleno }
// El último resultado queda en window.pbLastScan (para guardar las líneas con el gasto).
(() => {
  if (window.pbScan) return;
  const L = (document.documentElement.lang || 'es').slice(0, 2), I = { es: 0, en: 1, bg: 2 }[L] ?? 0;
  const TX = {
    camera: ['📷 Hacer foto', '📷 Take photo', '📷 Направи снимка'],
    gallery: ['🖼️ Elegir de la galería', '🖼️ Choose from gallery', '🖼️ Избери от галерията'],
    cancel: ['Cancelar', 'Cancel', 'Отказ'],
    adjust: ['Ajusta las esquinas al borde del ticket', 'Drag the corners to the edges of the receipt', 'Нагласи ъглите по ръба на бележката'],
    retake: ['Repetir', 'Retake', 'Отново'], whole: ['Toda la foto', 'Whole photo', 'Цялата снимка'], go: ['Escanear ✓', 'Scan ✓', 'Сканирай ✓'],
    reading: ['Leyendo el ticket…', 'Reading the receipt…', 'Чета касовата бележка…'],
    check: ['Revisa los datos antes de guardar.', 'Check the details before saving.', 'Провери данните преди да запазиш.'],
    sum: ['Ojo: las líneas suman {s} y el total leído es {t}. Comprueba el importe.', 'Note: the lines add up to {s} and the total read is {t}. Check the amount.', 'Внимание: редовете са {s}, а прочетената сума е {t}. Провери сумата.'],
    sumok: ['Las {n} líneas suman exactamente el total ✓', 'The {n} lines add up exactly to the total ✓', '{n} реда дават точно общата сума ✓'],
    date: ['No se leía la fecha: he puesto la de hoy.', 'The date was not readable: I used today.', 'Датата не се чете: сложих днешната.'],
    cur: ['El ticket está en {m}: pon el importe en euros.', 'The receipt is in {m}: enter the amount in euros.', 'Бележката е в {m}: въведи сумата в евро.'],
    lines: ['Ver las {n} líneas del ticket', 'See the {n} receipt lines', 'Виж {n} реда от бележката'],
    bad: ['No he podido leer el ticket. Prueba con más luz y con el ticket entero en la foto.', 'I could not read the receipt. Try with more light and the whole receipt in the photo.', 'Не успях да прочета бележката. Опитай с повече светлина и цялата бележка в снимката.'],
    nokey: ['El escáner no está activado (falta la clave de la IA en el servidor).', 'The scanner is not enabled (the AI key is missing on the server).', 'Скенерът не е активиран (липсва ключът за ИИ на сървъра).'],
    busy: ['La IA gratuita está saturada. Inténtalo en unos minutos.', 'The free AI is busy. Try again in a few minutes.', 'Безплатният ИИ е претоварен. Опитай след малко.'],
    limit: ['Has llegado al límite de usos de IA de hoy.', 'You have reached today\'s AI limit.', 'Достигна дневния лимит за ИИ.'],
    err: ['No se pudo leer el ticket. Inténtalo de nuevo.', 'Could not read the receipt. Try again.', 'Неуспешно четене. Опитай отново.'],
    tk_total: ['TOTAL', 'TOTAL', 'ОБЩО'], tk_disc: ['Descuentos', 'Discounts', 'Отстъпки'], tk_items: ['{n} artículos', '{n} items', '{n} артикула'],
    tk_pay: ['Pago', 'Payment', 'Плащане'], tk_thanks: ['Ticket electrónico · Personal Balance', 'E-receipt · Personal Balance', 'Електронна бележка · Personal Balance'],
    tk_close: ['Cerrar', 'Close', 'Затвори'], tk_cat: ['Categoría', 'Category', 'Категория'],
  };
  const t = (k, p) => { let s = TX[k][I]; for (const a in (p || {})) s = s.replace('{' + a + '}', p[a]); return s };
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const eur = v => new Intl.NumberFormat({ es: 'es-ES', en: 'en-GB', bg: 'bg-BG' }[L] || 'es-ES', { style: 'currency', currency: 'EUR' }).format(v);

  const css = document.createElement('style');
  css.textContent = `.pbs-ov{position:fixed;inset:0;z-index:70;background:rgba(0,0,0,.6);display:grid;place-items:center;backdrop-filter:blur(4px)}
  .pbs-box{background:var(--card,#161616);color:var(--text,#fff);border:1px solid var(--chip,#262626);border-radius:20px;padding:22px 26px;text-align:center;max-width:320px;font:15px/1.4 Inter,system-ui,sans-serif}
  .pbs-sheet{position:fixed;left:0;right:0;bottom:0;z-index:70;background:var(--card,#161616);border-radius:22px 22px 0 0;padding:16px 16px calc(16px + env(safe-area-inset-bottom,0px));display:grid;gap:10px;box-shadow:0 -10px 40px rgba(0,0,0,.5)}
  .pbs-sheet button,.pbs-bar button{border:0;border-radius:999px;padding:14px 18px;font:600 16px Inter,system-ui,sans-serif;cursor:pointer;background:var(--chip,#262626);color:var(--text,#fff)}
  .pbs-sheet button.main,.pbs-bar button.main{background:var(--text,#fff);color:var(--bg,#000)}
  .pbs-spin{width:34px;height:34px;margin:0 auto 12px;border-radius:50%;border:3px solid var(--chip,#333);border-top-color:var(--accent,#5ad37a);animation:pbs 0.8s linear infinite}
  @keyframes pbs{to{transform:rotate(360deg)}}
  .pbs-crop{position:fixed;inset:0;z-index:71;background:#000;display:flex;flex-direction:column;padding-top:env(safe-area-inset-top,0px)}
  .pbs-crop p{color:#fff;text-align:center;margin:10px 16px;font:500 14px Inter,system-ui,sans-serif}
  .pbs-stage{flex:1;position:relative;touch-action:none;overflow:hidden}
  .pbs-stage canvas{position:absolute;inset:0;width:100%;height:100%}
  .pbs-bar{display:flex;gap:8px;justify-content:center;padding:12px 12px calc(12px + env(safe-area-inset-bottom,0px))}
  .pbs-note{border-radius:12px;padding:10px 12px;margin:0 0 12px;font-size:13px;background:var(--accent-soft,rgba(90,211,122,.14));color:var(--text,#fff)}
  .pbs-note .w{color:var(--warn,#f5a524);display:block;margin-top:4px}.pbs-note .ok{color:var(--ok,#5ad37a);display:block;margin-top:4px}
  .pbs-note details{margin-top:6px}.pbs-note summary{color:var(--muted,#8e8e93);font-weight:500;font-size:13px}
  .pbs-note table{width:100%;margin-top:6px;font-size:12px}.pbs-note td{padding:3px 0;border-bottom:1px solid var(--line,#262626)}
  .pbt-s{margin:10px auto;width:min(320px,100%);filter:drop-shadow(0 6px 16px rgba(0,0,0,.35))}
  .pbt{--zz:conic-gradient(from 135deg at top,#0000,#000 1deg 89deg,#0000 90deg) top/12px 51% repeat-x,conic-gradient(from -45deg at bottom,#0000,#000 1deg 89deg,#0000 90deg) bottom/12px 51% repeat-x;
    -webkit-mask:var(--zz);mask:var(--zz);background:#fbfaf5;color:#1d1d1d;font:13px/1.45 "DM Mono",ui-monospace,"SF Mono",Menlo,Consolas,monospace;padding:26px 18px}
  .pbt .c{text-align:center}.pbt .m{font:800 18px/1.2 Inter,system-ui,sans-serif;letter-spacing:.04em;text-transform:uppercase;margin-bottom:4px}
  .pbt .s{color:#666;font-size:11.5px}.pbt hr{border:0;border-top:1.5px dashed #b9b6ac;margin:10px 0}
  .pbt .r{display:flex;gap:8px;align-items:baseline}.pbt .r span:first-child{flex:1;min-width:0;overflow-wrap:anywhere}.pbt .r span:last-child{white-space:nowrap}
  .pbt .q{color:#777;font-size:11.5px;margin:-2px 0 2px 10px}.pbt .neg{color:#1f7a4d}
  .pbt .tot{font-weight:700;font-size:20px;margin-top:2px}.pbt .bc{display:block;margin:12px auto 4px;height:34px;width:70%}
  .pbt-wrap{max-height:56vh;overflow:auto;padding:6px 2px 14px;margin:0 -6px}
  .pbt-modal{position:fixed;inset:0;z-index:72;background:rgba(0,0,0,.7);backdrop-filter:blur(4px);overflow:auto;padding:max(24px,env(safe-area-inset-top,0px)) 16px 24px;display:flex;flex-direction:column;align-items:center}
  .pbt-modal button{margin-top:18px;border:0;border-radius:999px;padding:12px 22px;font:700 15px Inter,system-ui,sans-serif;background:#fff;color:#000;cursor:pointer}`;
  document.head.appendChild(css);

  const overlay = html => { const o = document.createElement('div'); o.className = 'pbs-ov'; o.innerHTML = `<div class="pbs-box">${html}</div>`; document.body.appendChild(o); return o };
  const toast = msg => { const o = overlay(esc(msg) + '<div style="margin-top:14px"><button class="btn" type="button">OK</button></div>'); o.querySelector('button').onclick = () => o.remove() };

  // ---------- 1. Cámara o galería ----------
  const chooser = () => new Promise(res => {
    const sh = document.createElement('div'); sh.className = 'pbs-sheet';
    sh.innerHTML = `<button class="main" data-k="cam">${t('camera')}</button><button data-k="gal">${t('gallery')}</button><button data-k="no">${t('cancel')}</button>`;
    const bg = document.createElement('div'); bg.className = 'pbs-ov'; bg.style.background = 'rgba(0,0,0,.45)';
    document.body.append(bg, sh);
    const done = v => { sh.remove(); bg.remove(); res(v) };
    bg.onclick = () => done(null);
    sh.onclick = e => { const b = e.target.closest('button'); if (b) done(b.dataset.k === 'no' ? null : b.dataset.k) };
  });
  const pick = camera => new Promise(res => {
    const inp = document.createElement('input'); inp.type = 'file'; inp.accept = 'image/*'; if (camera) inp.setAttribute('capture', 'environment');
    inp.style.display = 'none'; inp.onchange = () => { res(inp.files[0] || null); inp.remove() };
    document.body.appendChild(inp); inp.click();
  });
  const loadImg = file => new Promise((ok, ko) => { const u = URL.createObjectURL(file), i = new Image(); i.onload = () => ok(i); i.onerror = ko; i.src = u });

  // ---------- 2. Detección de bordes ----------
  function detect(img) {
    const k = 360 / Math.max(img.naturalWidth, img.naturalHeight), w = Math.max(8, Math.round(img.naturalWidth * k)), h = Math.max(8, Math.round(img.naturalHeight * k));
    const c = document.createElement('canvas'); c.width = w; c.height = h; const x = c.getContext('2d', { willReadFrequently: true }); x.drawImage(img, 0, 0, w, h);
    const d = x.getImageData(0, 0, w, h).data, g = new Float32Array(w * h), hist = new Array(256).fill(0);
    for (let i = 0; i < w * h; i++) { const v = 0.299 * d[i * 4] + 0.587 * d[i * 4 + 1] + 0.114 * d[i * 4 + 2]; g[i] = v; hist[v | 0]++ }
    // Umbral de Otsu: el papel es la zona clara
    let sum = 0, sumB = 0, wB = 0, best = 0, th = 128; for (let i = 0; i < 256; i++) sum += i * hist[i];
    for (let i = 0; i < 256; i++) { wB += hist[i]; if (!wB) continue; const wF = w * h - wB; if (!wF) break; sumB += i * hist[i]; const mB = sumB / wB, mF = (sum - sumB) / wF, v = wB * wF * (mB - mF) ** 2; if (v > best) { best = v; th = i } }
    const lab = new Int32Array(w * h).fill(-1); let bestLab = -1, bestN = 0, n = 0; const stack = [];
    for (let s = 0; s < w * h; s++) {
      if (lab[s] !== -1 || g[s] <= th) continue; let cnt = 0; stack.push(s); lab[s] = n;
      while (stack.length) { const p = stack.pop(); cnt++; const px = p % w, py = (p / w) | 0;
        for (const q of [px > 0 ? p - 1 : -1, px < w - 1 ? p + 1 : -1, py > 0 ? p - w : -1, py < h - 1 ? p + w : -1]) if (q >= 0 && lab[q] === -1 && g[q] > th) { lab[q] = n; stack.push(q) } }
      if (cnt > bestN) { bestN = cnt; bestLab = n } n++;
    }
    const W = img.naturalWidth, H = img.naturalHeight, inset = [[.05, .05], [.95, .05], [.95, .95], [.05, .95]].map(([a, b]) => [a * W, b * H]);
    if (bestN < w * h * 0.06 || bestN > w * h * 0.97) return inset;
    let tl = [0, 0, 1e9], tr = [0, 0, -1e9], br = [0, 0, -1e9], bl = [0, 0, 1e9];
    for (let p = 0; p < w * h; p++) if (lab[p] === bestLab) { const px = p % w, py = (p / w) | 0;
      if (px + py < tl[2]) tl = [px, py, px + py]; if (px + py > br[2]) br = [px, py, px + py];
      if (px - py > tr[2]) tr = [px, py, px - py]; if (px - py < bl[2]) bl = [px, py, px - py] }
    return [tl, tr, br, bl].map(([a, b]) => [a / k, b / k]);
  }

  // ---------- Editor de esquinas ----------
  function cropUI(img) {
    return new Promise(res => {
      const ui = document.createElement('div'); ui.className = 'pbs-crop';
      ui.innerHTML = `<p>${t('adjust')}</p><div class="pbs-stage"><canvas></canvas></div><div class="pbs-bar"><button data-k="retake">${t('retake')}</button><button data-k="whole">${t('whole')}</button><button class="main" data-k="go">${t('go')}</button></div>`;
      document.body.appendChild(ui);
      const stage = ui.querySelector('.pbs-stage'), cv = ui.querySelector('canvas'), cx = cv.getContext('2d');
      let pts = detect(img), sc = 1, ox = 0, oy = 0, drag = -1;
      const W = img.naturalWidth, H = img.naturalHeight;
      function layout() { const r = stage.getBoundingClientRect(), dpr = window.devicePixelRatio || 1; cv.width = r.width * dpr; cv.height = r.height * dpr;
        sc = Math.min((r.width - 40) / W, (r.height - 40) / H); ox = (r.width - W * sc) / 2; oy = (r.height - H * sc) / 2; cx.setTransform(dpr, 0, 0, dpr, 0, 0); draw() }
      const toS = ([x, y]) => [ox + x * sc, oy + y * sc];
      function draw() { const r = stage.getBoundingClientRect(); cx.clearRect(0, 0, r.width, r.height); cx.drawImage(img, ox, oy, W * sc, H * sc);
        const s = pts.map(toS); cx.fillStyle = 'rgba(0,0,0,.5)'; cx.beginPath(); cx.rect(0, 0, r.width, r.height); cx.moveTo(...s[0]); for (let i = 3; i >= 0; i--) cx.lineTo(...s[i]); cx.closePath(); cx.fill('evenodd');
        cx.strokeStyle = '#5ad37a'; cx.lineWidth = 2.5; cx.beginPath(); cx.moveTo(...s[0]); s.slice(1).forEach(p => cx.lineTo(...p)); cx.closePath(); cx.stroke();
        s.forEach(([a, b]) => { cx.beginPath(); cx.arc(a, b, 13, 0, 7); cx.fillStyle = 'rgba(90,211,122,.35)'; cx.fill(); cx.lineWidth = 3; cx.strokeStyle = '#fff'; cx.stroke() }) }
      const pos = e => { const r = stage.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top] };
      stage.addEventListener('pointerdown', e => { const [a, b] = pos(e); let m = 1e9; pts.forEach((p, i) => { const [x, y] = toS(p), d = Math.hypot(x - a, y - b); if (d < m) { m = d; drag = i } }); if (m > 60) drag = -1; else stage.setPointerCapture(e.pointerId) });
      stage.addEventListener('pointermove', e => { if (drag < 0) return; const [a, b] = pos(e); pts[drag] = [Math.min(W, Math.max(0, (a - ox) / sc)), Math.min(H, Math.max(0, (b - oy) / sc))]; draw() });
      stage.addEventListener('pointerup', () => drag = -1);
      ui.querySelector('.pbs-bar').onclick = e => { const b = e.target.closest('button'); if (!b) return;
        if (b.dataset.k === 'whole') { pts = [[0, 0], [W, 0], [W, H], [0, H]]; draw(); return }
        removeEventListener('resize', layout); ui.remove(); res(b.dataset.k === 'go' ? pts : null) };
      addEventListener('resize', layout); requestAnimationFrame(layout);
    });
  }

  // ---------- Enderezar (perspectiva) y mejorar contraste ----------
  function homography(src, dst) { // matriz que lleva dst -> src
    const A = [], B = [];
    for (let i = 0; i < 4; i++) { const [x, y] = dst[i], [u, v] = src[i];
      A.push([x, y, 1, 0, 0, 0, -u * x, -u * y]); B.push(u); A.push([0, 0, 0, x, y, 1, -v * x, -v * y]); B.push(v) }
    for (let c = 0; c < 8; c++) { let p = c; for (let r = c + 1; r < 8; r++) if (Math.abs(A[r][c]) > Math.abs(A[p][c])) p = r;
      [A[c], A[p]] = [A[p], A[c]]; [B[c], B[p]] = [B[p], B[c]];
      for (let r = 0; r < 8; r++) if (r !== c) { const f = A[r][c] / A[c][c]; for (let k = c; k < 8; k++) A[r][k] -= f * A[c][k]; B[r] -= f * B[c] } }
    return B.map((b, i) => b / A[i][i]).concat(1);
  }
  function warp(img, q) {
    const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
    let ow = Math.max(dist(q[0], q[1]), dist(q[3], q[2])), oh = Math.max(dist(q[0], q[3]), dist(q[1], q[2]));
    const k = Math.min(1, 2000 / Math.max(ow, oh)); ow = Math.max(50, Math.round(ow * k)); oh = Math.max(50, Math.round(oh * k));
    const sc = document.createElement('canvas'); sc.width = img.naturalWidth; sc.height = img.naturalHeight; const sx = sc.getContext('2d', { willReadFrequently: true }); sx.drawImage(img, 0, 0);
    const sd = sx.getImageData(0, 0, sc.width, sc.height).data, SW = sc.width, SH = sc.height;
    const m = homography(q, [[0, 0], [ow, 0], [ow, oh], [0, oh]]);
    const out = document.createElement('canvas'); out.width = ow; out.height = oh; const ox = out.getContext('2d'), od = ox.createImageData(ow, oh), o = od.data;
    const gray = new Uint8ClampedArray(ow * oh), hist = new Array(256).fill(0);
    for (let y = 0; y < oh; y++) for (let x = 0; x < ow; x++) {
      const z = m[6] * x + m[7] * y + m[8], u = Math.min(SW - 1, Math.max(0, Math.round((m[0] * x + m[1] * y + m[2]) / z))), v = Math.min(SH - 1, Math.max(0, Math.round((m[3] * x + m[4] * y + m[5]) / z)));
      const s = (v * SW + u) * 4, gv = (0.299 * sd[s] + 0.587 * sd[s + 1] + 0.114 * sd[s + 2]) | 0; gray[y * ow + x] = gv; hist[gv]++ }
    let lo = 0, hi = 255, acc = 0; const N = ow * oh;
    for (let i = 0; i < 256; i++) { acc += hist[i]; if (acc > N * 0.02) { lo = i; break } } acc = 0;
    for (let i = 255; i >= 0; i--) { acc += hist[i]; if (acc > N * 0.02) { hi = i; break } }
    const span = Math.max(30, hi - lo);
    for (let i = 0; i < N; i++) { const v = Math.max(0, Math.min(255, (gray[i] - lo) * 255 / span)); o[i * 4] = o[i * 4 + 1] = o[i * 4 + 2] = v; o[i * 4 + 3] = 255 }
    ox.putImageData(od, 0, 0);
    return out.toDataURL('image/jpeg', 0.9);
  }

  // ---------- Ticket electrónico ----------
  const fdate = s => { if (!s) return ''; const [y, m, d] = String(s).split('-'); return d && m && y ? `${d}/${m}/${y}` : s };
  function barcode(seed) { let h = 0; for (const ch of String(seed || 'pb')) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
    let x = 0, b = ''; for (let i = 0; i < 46; i++) { h = (h * 1103515245 + 12345) >>> 0; const w = 1 + (h >>> 29) % 3; if (i % 2 === 0) b += `<rect x="${x}" width="${w}" height="34"/>`; x += w } return `<svg class="bc" viewBox="0 0 ${x} 34" preserveAspectRatio="none" fill="#1d1d1d" aria-hidden="true">${b}</svg>` }
  window.pbTicketHTML = d => {
    const tk = d.ticket || d, lin = d.lineas || [], n2 = v => (+v).toLocaleString(L === 'en' ? 'en-GB' : L === 'bg' ? 'bg-BG' : 'es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const disc = lin.filter(x => x.importe < 0).reduce((a, x) => a + x.importe, 0), nItems = lin.filter(x => x.importe >= 0).length;
    let h = `<div class="pbt-s"><div class="pbt"><div class="c m">${esc(tk.comercio || d.concepto || '')}</div>`;
    if (tk.direccion) h += `<div class="c s">${esc(tk.direccion)}</div>`;
    if (tk.nif) h += `<div class="c s">NIF ${esc(tk.nif)}</div>`;
    h += `<hr><div class="r s"><span>${esc(fdate(d.fecha))}${tk.hora ? ' · ' + esc(tk.hora) : ''}</span><span>${tk.num_ticket ? 'Nº ' + esc(tk.num_ticket) : ''}</span></div><hr>`;
    for (const x of lin) {
      const q = +x.cant || 1;
      h += `<div class="r ${x.importe < 0 ? 'neg' : ''}"><span>${esc(x.desc)}</span><span>${n2(x.importe)}</span></div>`;
      if (q !== 1 && x.importe > 0) h += `<div class="q">${String(q).replace('.', L === 'en' ? '.' : ',')} × ${n2(x.importe / q)}</div>`;
    }
    if (lin.length) h += `<hr><div class="r s"><span>${esc(t('tk_items', { n: nItems }))}</span><span></span></div>`;
    if (disc < 0) h += `<div class="r s neg"><span>${esc(t('tk_disc'))}</span><span>${n2(disc)}</span></div>`;
    h += `<div class="r tot"><span>${esc(t('tk_total'))}</span><span>${n2(d.importe)} €</span></div>`;
    if (tk.forma_pago) h += `<div class="r s"><span>${esc(t('tk_pay'))}</span><span>${esc(tk.forma_pago)}</span></div>`;
    if (d.categoria) h += `<div class="r s"><span>${esc(t('tk_cat'))}</span><span>${esc(d.categoria)}</span></div>`;
    h += `<hr>${barcode((tk.comercio || '') + d.fecha + d.importe)}<div class="c s">${esc(t('tk_thanks'))}</div></div></div>`;
    return h;
  };
  window.pbShowTicket = d => {
    const o = document.createElement('div'); o.className = 'pbt-modal'; o.innerHTML = window.pbTicketHTML(d) + `<button type="button">${esc(t('tk_close'))}</button>`;
    o.onclick = e => { if (e.target === o || e.target.tagName === 'BUTTON') o.remove() }; document.body.appendChild(o);
  };

  // ---------- 3. Resultado en el formulario ----------
  function note(d) {
    const f = document.getElementById('f-mov'); if (!f) return;
    f.querySelector('.pbs-note')?.remove();
    let h = `<b>${esc(t('check'))}</b>`;
    if (d.avisos.includes('suma')) h += `<span class="w">⚠️ ${esc(t('sum', { s: eur(d.suma_lineas), t: eur(d.importe) }))}</span>`;
    else if (d.lineas.length) h += `<span class="ok">${esc(t('sumok', { n: d.lineas.length }))}</span>`;
    if (d.avisos.includes('fecha')) h += `<span class="w">⚠️ ${esc(t('date'))}</span>`;
    if (d.avisos.includes('moneda')) h += `<span class="w">⚠️ ${esc(t('cur', { m: d.moneda }))}</span>`;
    h += `<div class="pbt-wrap">${window.pbTicketHTML(d)}</div>`;
    const n = document.createElement('div'); n.className = 'pbs-note'; n.innerHTML = h;
    f.querySelector('h3').after(n);
    f.closest('dialog')?.addEventListener('close', () => { n.remove(); setTimeout(() => { window.pbLastScan = null }, 0) }, { once: true });
  }

  window.pbScan = async () => {
    const C = window.PB_SCAN || {};
    for (;;) {
      const how = await chooser(); if (!how) return;
      const file = await pick(how === 'cam'); if (!file) return;
      let img; try { img = await loadImg(file) } catch (e) { return toast(t('err')) }
      const q = await cropUI(img); URL.revokeObjectURL(img.src);
      if (!q) continue; // Repetir
      const ov = overlay(`<div class="pbs-spin"></div>${esc(t('reading'))}`);
      try {
        const image = warp(img, q);
        const tok = C.getToken ? await C.getToken() : null;
        const r = await fetch(C.api || '/api/scan', { method: 'POST', credentials: 'same-origin',
          headers: Object.assign({ 'Content-Type': 'application/json' }, tok ? { Authorization: 'Bearer ' + tok } : {}),
          body: JSON.stringify({ image, lang: L }) });
        const j = await r.json().catch(() => ({}));
        ov.remove();
        if (!r.ok || j.error) return toast(t({ unreadable: 'bad', no_key: 'nokey', busy: 'busy', limit: 'limit' }[j.error] || 'err') + (j.detail ? ' (' + j.detail + ')' : (!j.error ? ' (HTTP ' + r.status + ')' : '')));
        C.open && C.open(j); window.pbLastScan = j; note(j);
      } catch (e) { ov.remove(); toast(t('err') + ' (' + ((e && e.message) || e) + ')') }
      return;
    }
  };
})();

// Escáner de tickets y facturas — compartido por la web y la app.
// La página define window.PB_SCAN = { api, getToken: async () => token|null, open: datos => abre el formulario relleno }
(() => {
  if (window.pbScan) return;
  const L = (document.documentElement.lang || 'es').slice(0, 2), I = { es: 0, en: 1, bg: 2 }[L] ?? 0;
  const TX = {
    reading: ['Leyendo el ticket…', 'Reading the receipt…', 'Чета касовата бележка…'],
    check: ['Revisa los datos antes de guardar.', 'Check the details before saving.', 'Провери данните преди да запазиш.'],
    sum: ['Ojo: las líneas suman {s} y el total leído es {t}. Comprueba el importe.', 'Note: the lines add up to {s} and the total read is {t}. Check the amount.', 'Внимание: редовете са {s}, а прочетената сума е {t}. Провери сумата.'],
    date: ['No se leía la fecha: he puesto la de hoy.', 'The date was not readable: I used today.', 'Датата не се чете: сложих днешната.'],
    cur: ['El ticket está en {m}: pon el importe en euros.', 'The receipt is in {m}: enter the amount in euros.', 'Бележката е в {m}: въведи сумата в евро.'],
    lines: ['Ver las {n} líneas del ticket', 'See the {n} receipt lines', 'Виж {n} реда от бележката'],
    bad: ['No he podido leer el ticket. Prueba con más luz y con el ticket entero en la foto.', 'I could not read the receipt. Try with more light and the whole receipt in the photo.', 'Не успях да прочета бележката. Опитай с повече светлина и цялата бележка в снимката.'],
    nokey: ['El escáner no está activado (falta la clave de la IA en el servidor).', 'The scanner is not enabled (the AI key is missing on the server).', 'Скенерът не е активиран (липсва ключът за ИИ на сървъра).'],
    busy: ['La IA gratuita está saturada. Inténtalo en unos minutos.', 'The free AI is busy. Try again in a few minutes.', 'Безплатният ИИ е претоварен. Опитай след малко.'],
    limit: ['Has llegado al límite de usos de IA de hoy.', 'You have reached today\'s AI limit.', 'Достигна дневния лимит за ИИ.'],
    err: ['No se pudo leer el ticket. Inténtalo de nuevo.', 'Could not read the receipt. Try again.', 'Неуспешно четене. Опитай отново.'],
  };
  const t = (k, p) => { let s = TX[k][I]; for (const a in (p || {})) s = s.replace('{' + a + '}', p[a]); return s };
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const eur = v => new Intl.NumberFormat({ es: 'es-ES', en: 'en-GB', bg: 'bg-BG' }[L] || 'es-ES', { style: 'currency', currency: 'EUR' }).format(v);

  const css = document.createElement('style');
  css.textContent = `.pbs-ov{position:fixed;inset:0;z-index:70;background:rgba(0,0,0,.6);display:grid;place-items:center;backdrop-filter:blur(4px)}
  .pbs-box{background:var(--card,#161616);color:var(--text,#fff);border:1px solid var(--chip,#262626);border-radius:20px;padding:22px 26px;text-align:center;max-width:320px;font:15px/1.4 Inter,system-ui,sans-serif}
  .pbs-spin{width:34px;height:34px;margin:0 auto 12px;border-radius:50%;border:3px solid var(--chip,#333);border-top-color:var(--accent,#5ad37a);animation:pbs 0.8s linear infinite}
  @keyframes pbs{to{transform:rotate(360deg)}}
  .pbs-note{border-radius:12px;padding:10px 12px;margin:0 0 12px;font-size:13px;background:var(--accent-soft,rgba(90,211,122,.14));color:var(--text,#fff)}
  .pbs-note .w{color:var(--warn,#f5a524);display:block;margin-top:4px}
  .pbs-note details{margin-top:6px}.pbs-note summary{color:var(--muted,#8e8e93);font-weight:500;font-size:13px}
  .pbs-note table{width:100%;margin-top:6px;font-size:12px}.pbs-note td{padding:3px 0;border-bottom:1px solid var(--line,#262626)}`;
  document.head.appendChild(css);

  function overlay(html) { const o = document.createElement('div'); o.className = 'pbs-ov'; o.innerHTML = `<div class="pbs-box">${html}</div>`; document.body.appendChild(o); return o }
  function toast(msg) { const o = overlay(esc(msg) + '<div style="margin-top:14px"><button class="btn" type="button">OK</button></div>'); o.querySelector('button').onclick = () => o.remove() }

  function pick() {
    return new Promise(res => {
      const inp = document.createElement('input'); inp.type = 'file'; inp.accept = 'image/*'; inp.style.display = 'none';
      inp.onchange = () => { res(inp.files[0] || null); inp.remove() };
      document.body.appendChild(inp); inp.click();
    });
  }
  async function shrink(file) {
    const url = URL.createObjectURL(file);
    try {
      const img = await new Promise((ok, ko) => { const i = new Image(); i.onload = () => ok(i); i.onerror = ko; i.src = url });
      const k = Math.min(1, 1800 / Math.max(img.naturalWidth, img.naturalHeight));
      const c = document.createElement('canvas'); c.width = Math.round(img.naturalWidth * k); c.height = Math.round(img.naturalHeight * k);
      c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
      return c.toDataURL('image/jpeg', 0.88);
    } finally { URL.revokeObjectURL(url) }
  }
  function note(d) {
    const f = document.getElementById('f-mov'); if (!f) return;
    f.querySelector('.pbs-note')?.remove();
    let h = `<b>${esc(t('check'))}</b>`;
    if (d.avisos.includes('suma')) h += `<span class="w">⚠️ ${esc(t('sum', { s: eur(d.suma_lineas), t: eur(d.importe) }))}</span>`;
    if (d.avisos.includes('fecha')) h += `<span class="w">⚠️ ${esc(t('date'))}</span>`;
    if (d.avisos.includes('moneda')) h += `<span class="w">⚠️ ${esc(t('cur', { m: d.moneda }))}</span>`;
    if (d.lineas.length) h += `<details><summary>${esc(t('lines', { n: d.lineas.length }))}</summary><table>${d.lineas.map(x => `<tr><td>${esc(x.desc)}</td><td style="text-align:right">${eur(x.importe)}</td></tr>`).join('')}</table></details>`;
    const n = document.createElement('div'); n.className = 'pbs-note'; n.innerHTML = h;
    f.querySelector('h3').after(n);
    const dlg = f.closest('dialog'); dlg?.addEventListener('close', () => n.remove(), { once: true });
  }

  window.pbScan = async () => {
    const C = window.PB_SCAN || {};
    const file = await pick(); if (!file) return;
    const ov = overlay(`<div class="pbs-spin"></div>${esc(t('reading'))}`);
    try {
      const image = await shrink(file);
      const tok = C.getToken ? await C.getToken() : null;
      const r = await fetch(C.api || '/api/scan', { method: 'POST', credentials: 'same-origin',
        headers: Object.assign({ 'Content-Type': 'application/json' }, tok ? { Authorization: 'Bearer ' + tok } : {}),
        body: JSON.stringify({ image, lang: L }) });
      const j = await r.json().catch(() => ({}));
      ov.remove();
      if (!r.ok || j.error) return toast(t({ unreadable: 'bad', no_key: 'nokey', busy: 'busy', limit: 'limit' }[j.error] || 'err'));
      C.open && C.open(j); note(j);
    } catch (e) { ov.remove(); toast(t('err')) }
  };
})();

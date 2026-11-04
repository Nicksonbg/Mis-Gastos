// Inversiones (web): precios en vivo en el navegador, igual que en la app del iPhone.
// Cripto: Binance · Divisas: BCE (con fuentes de respaldo) · Acciones e índices: Finnhub con la clave del usuario.
(() => {
  const D = window.PB_INV; if (!D) return;
  const L = { es: 'es-ES', en: 'en-GB', bg: 'bg-BG' }[D.lang] || 'es-ES';
  const T = (k, p) => { let s = D.tx[k] || k; for (const a in (p || {})) s = s.replace('{' + a + '}', p[a]); return s };
  const eur = new Intl.NumberFormat(L, { style: 'currency', currency: 'EUR', useGrouping: 'always' });
  const money = v => eur.format(+v || 0);
  const pctF = v => new Intl.NumberFormat(L, { maximumFractionDigits: 2 }).format(v) + ' %';
  const qtyF = new Intl.NumberFormat(L, { maximumFractionDigits: 8 });
  const fmtC = (v, c) => { try { return new Intl.NumberFormat(L, { style: 'currency', currency: c }).format(v) } catch (e) { return v.toFixed(2) + ' ' + c } };
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const sgn = (v, f) => v == null ? '<span class="muted">—</span>' : `<span style="color:var(--${v >= 0 ? 'ok' : 'bad'})">${v >= 0 ? '+' : ''}${f(v)}</span>`;
  const ls = { get(k) { try { return JSON.parse(localStorage.getItem(k)) } catch (e) { return null } }, set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)) } catch (e) {} } };
  let PX = ls.get('pbw-precios') || {}, FX = ls.get('pbw-fx') || {}, pxAt = null, pxErr = false, busy = false;
  const pk = i => i.tipo + ':' + String(i.simbolo || '').toUpperCase();

  const jget = async u => { const c = new AbortController(), to = setTimeout(() => c.abort(), 8000); try { const r = await fetch(u, { signal: c.signal }); if (!r.ok) throw new Error('http'); return await r.json() } finally { clearTimeout(to) } };
  async function getFx() {
    if (FX.t && Date.now() - FX.t < 36e5 && FX.r) return; let rates = null;
    const srcs = [['https://api.frankfurter.dev/v1/latest?base=EUR', d => d.rates], ['https://api.frankfurter.app/latest?from=EUR', d => d.rates], ['https://open.er-api.com/v6/latest/EUR', d => d.rates],
      ['https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/eur.json', d => { const o = {}; for (const k in d.eur) o[k.toUpperCase()] = d.eur[k]; return o }]];
    for (const [u, f] of srcs) { try { const r = f(await jget(u)); if (r && r.USD > 0) { rates = r; break } } catch (e) {} }
    if (!rates) throw new Error('fx');
    FX = { t: Date.now(), r: Object.assign({ EUR: 1 }, rates) }; ls.set('pbw-fx', FX);
  }
  const toEur = (x, cur) => cur === 'EUR' ? x : (FX.r && FX.r[cur] ? x / FX.r[cur] : null);
  async function pCripto(sy) {
    try { const d = await jget('https://api.binance.com/api/v3/ticker/24hr?symbol=' + sy + 'EUR'); return { p: +d.lastPrice, ch: +d.priceChangePercent, k: [+d.openPrice, +d.highPrice, +d.lowPrice, +d.lastPrice] } } catch (e) {}
    const d = await jget('https://api.binance.com/api/v3/ticker/24hr?symbol=' + sy + 'USDT'); await getFx();
    return { p: toEur(+d.lastPrice, 'USD'), ch: +d.priceChangePercent, k: [+d.openPrice, +d.highPrice, +d.lowPrice, +d.lastPrice] };
  }
  async function pAccion(sy, cur) {
    if (!D.fh) throw new Error('nokey');
    const d = await jget('https://finnhub.io/api/v1/quote?symbol=' + encodeURIComponent(sy) + '&token=' + encodeURIComponent(D.fh));
    if (!d || !(d.c > 0)) throw new Error('noquote'); if (cur !== 'EUR') await getFx();
    return { p: toEur(d.c, cur), ch: typeof d.dp === 'number' ? d.dp : null, o: cur !== 'EUR' ? d.c : null, cur, k: (d.o > 0 && d.h > 0 && d.l > 0) ? [d.o, d.h, d.l, d.c] : null };
  }
  async function refresh() {
    const all = (D.inv || []).concat((D.watch || []).map(w => ({ ...w, moneda: 'USD' }))); if (!all.length || busy) return; busy = true; let bad = 0;
    try { if (all.some(i => i.tipo === 'divisa' || i.tipo === 'cripto' || ((i.tipo === 'accion' || i.tipo === 'indice') && i.moneda !== 'EUR'))) await getFx() } catch (e) { bad++ }
    const seen = {};
    await Promise.all(all.map(async i => {
      const k = pk(i); if (seen[k]) return; seen[k] = 1; const sy = String(i.simbolo).toUpperCase();
      try {
        let r;
        if (i.tipo === 'cripto') r = await pCripto(sy);
        else if (i.tipo === 'accion' || i.tipo === 'indice') { if (!D.fh) return; r = await pAccion(i.proxy || sy, i.moneda || 'USD') }
        else { await getFx(); const x = FX.r && FX.r[sy]; if (!x) throw new Error('nofx'); r = { p: 1 / x, ch: null } }
        if (r && r.p > 0) PX[k] = { p: r.p, ch: r.ch, t: Date.now(), o: r.o || null, cur: r.cur || null, k: r.k || null }; else bad++;
      } catch (e) { bad++ }
    }));
    pxAt = Date.now(); pxErr = bad > 0; ls.set('pbw-precios', PX); busy = false; render();
  }
  function calc(i) {
    const q = PX[pk(i)]; let p = null, ch = null;
    if (q && q.p > 0) { p = q.p; ch = q.ch } else if (i.tipo === 'accion' && i.precioManual > 0) p = toEur(+i.precioManual, i.moneda || 'USD');
    const val = p != null ? p * i.cantidad : null, cost = i.precioCompra > 0 ? i.precioCompra * i.cantidad : null;
    return { p, ch, val, cost, gp: val != null && cost != null ? val - cost : null, hoy: val != null && ch != null ? val - val / (1 + ch / 100) : null, live: !!(q && q.p > 0) };
  }
  function natPx(i) {
    const q = PX[pk(i)];
    if (i.tipo === 'cripto') { if (!(q && q.p > 0)) return null; const r = FX.r && FX.r.USD; return r ? { v: q.p * r, c: 'USD' } : null }
    if (i.tipo === 'accion' || i.tipo === 'indice') {
      const c = (q && q.cur) || i.moneda || 'USD';
      if (q && q.p > 0) { if (q.o > 0 && q.cur === c) return { v: q.o, c }; const r = FX.r && FX.r[c]; return r ? { v: q.p * r, c } : null }
      if (i.tipo === 'accion' && i.precioManual > 0) return { v: +i.precioManual, c: i.moneda || 'USD' };
    }
    return null;
  }
  const CC = { USD: 'US', EUR: 'EU', GBP: 'GB', CHF: 'CH', JPY: 'JP', BGN: 'BG', CAD: 'CA', AUD: 'AU', NZD: 'NZ', SEK: 'SE', NOK: 'NO', DKK: 'DK', PLN: 'PL', CZK: 'CZ', HUF: 'HU', RON: 'RO', TRY: 'TR', CNY: 'CN', INR: 'IN', BRL: 'BR', MXN: 'MX' };
  function icon(tipo, sy) {
    sy = String(sy || '').toUpperCase(); const ini = esc(sy.replace(/[^A-Z0-9]/g, '').slice(0, 2) || '?');
    if (tipo === 'divisa') { const c = CC[sy]; return c ? String.fromCodePoint(...[...c].map(x => 127397 + x.charCodeAt(0))) : ini }
    if (tipo === 'indice') return '📈';
    const u = tipo === 'cripto' ? 'https://cdn.jsdelivr.net/gh/spothq/cryptocurrency-icons@master/128/color/' + encodeURIComponent(sy.toLowerCase()) + '.png' : 'https://financialmodelingprep.com/image-stock/' + encodeURIComponent(sy) + '.png';
    return `${ini}<img src="${u}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">`;
  }
  function candle(k) {
    const q = PX[k]; if (!q) return ''; const c = q.k, up = (q.ch != null ? q.ch : 0) >= 0, col = up ? 'var(--ok)' : 'var(--bad)';
    const pc = q.ch != null ? `<span class="small" style="color:${col};font-weight:600;margin-left:4px">${up ? '+' : ''}${new Intl.NumberFormat(L, { maximumFractionDigits: 2 }).format(q.ch)} %</span>` : '';
    if (!c || c.length < 4 || !(c[1] > c[2])) return pc;
    const [o, h, l, cl] = c, H = 26, y = v => (2 + (h - v) / (h - l) * (H - 4)).toFixed(1), top = Math.min(y(o), y(cl)), bh = Math.max(Math.abs(y(o) - y(cl)), 1.5);
    return `<svg width="14" height="${H}" viewBox="0 0 14 ${H}" style="vertical-align:middle;margin-left:6px" aria-hidden="true"><line x1="7" x2="7" y1="${y(h)}" y2="${y(l)}" stroke="${col}" stroke-width="1.5"/><rect x="3" width="8" y="${top}" height="${bh}" rx="1" fill="${col}"/></svg>${pc}`;
  }
  const hero = v => { const p = new Intl.NumberFormat(L, { minimumFractionDigits: 2, maximumFractionDigits: 2, useGrouping: 'always' }).format(v), d = L === 'en-GB' ? '.' : ',', i = p.lastIndexOf(d); return `<span class="cur">€</span>${i < 0 ? p : p.slice(0, i)}<span class="dec">${i < 0 ? '' : p.slice(i)}</span>` };

  function render() {
    const body = document.getElementById('inv-body');
    if (body) {
      let V = 0, C = 0, G = 0, H = 0, hasH = false; const byB = {};
      for (const i of D.inv) {
        const tr = body.querySelector(`tr[data-id="${CSS.escape(i.id)}"]`); if (!tr) continue; const c = calc(i);
        if (c.val != null) { V += c.val; const b = i.broker || T('sin_broker'); byB[b] = (byB[b] || 0) + c.val; if (c.cost != null) { C += c.cost; G += c.gp } if (c.hoy != null) { H += c.hoy; hasH = true } }
        const pct = c.gp != null && c.cost > 0 ? c.gp / c.cost * 100 : null, n = natPx(i);
        tr.querySelector('[data-icon]').innerHTML = icon(i.tipo, i.simbolo);
        tr.querySelector('[data-candle]').innerHTML = candle(pk(i)) + (c.live ? ' <span class="pill ok">●</span>' : '');
        tr.querySelector('[data-qty]').textContent = qtyF.format(i.cantidad);
        tr.querySelector('[data-px]').innerHTML = n ? fmtC(n.v, n.c) + (c.p != null ? '<div class="muted small">' + money(c.p) + '</div>' : '') : c.p != null ? money(c.p) : '<span class="muted">' + esc(T('inv_sin_precio')) + '</span>';
        tr.querySelector('[data-val]').innerHTML = c.val != null ? money(c.val) : '<span class="muted">—</span>';
        tr.querySelector('[data-gp]').innerHTML = sgn(c.gp, money) + (pct != null ? '<div class="small">' + sgn(pct, pctF) + '</div>' : '');
        tr.querySelector('[data-ch]').innerHTML = c.ch != null ? sgn(c.ch, pctF) : '<span class="muted">—</span>';
      }
      const gpp = C > 0 ? G / C * 100 : null;
      document.getElementById('inv-total').innerHTML = `<div class="hero-top"><span class="dot"></span>${esc(T('inv_valor'))}</div>
        <div class="hero-val">${V > 0 || !D.inv.length ? hero(V) : '—'}</div>
        <div class="hero-sub">${hasH ? `<span class="${H >= 0 ? 'up' : 'down'}">${H >= 0 ? '↗' : '↘'} ${sgn(H, money)}</span> <span class="muted">${esc(T('inv_hoy'))}</span>` : ''}</div>
        <div class="hero-stats"><div><div class="lbl">${esc(T('inv_invertido'))}</div><div class="v">${C > 0 ? money(C) : '—'}</div></div>
        <div><div class="lbl">${esc(T('inv_gp'))}</div><div class="v">${C > 0 ? sgn(G, money) : '—'}</div>${gpp != null ? '<div class="s">' + sgn(gpp, pctF) + '</div>' : ''}</div></div>`;
      const bs = Object.entries(byB).sort((a, b) => b[1] - a[1]);
      document.getElementById('inv-brokers').innerHTML = `<h2>${esc(T('h_broker'))}</h2>` + (bs.map(([b, v]) => `<div class="row" style="margin:6px 0"><span>${esc(b)}</span><span class="spacer"></span><b>${money(v)}</b><span class="muted small" style="width:52px;text-align:right">${V > 0 ? Math.round(v / V * 100) : 0} %</span></div>`).join('') || '<p class="muted small">—</p>');
      const st = document.getElementById('inv-status');
      if (st && D.inv.length && pxAt) { const h = new Date(pxAt).toLocaleTimeString(L); st.innerHTML = (pxErr ? `<span style="color:var(--bad)">${esc(T('inv_off'))}</span> ` : `<span class="pill ok">● ${esc(T('inv_live'))}</span> `) + `<span class="muted">${esc(T('inv_upd', { h }))}</span>` }
    }
    const wb = document.getElementById('watch-body');
    if (wb) for (const w of D.watch) {
      const row = wb.querySelector(`[data-wid="${CSS.escape(w.id)}"]`); if (!row) continue;
      const q = PX[pk(w)], p = q && q.p > 0 ? q.p : null, n = natPx({ ...w, moneda: 'USD' });
      row.querySelector('[data-icon]').innerHTML = icon(w.tipo, w.proxy || w.simbolo);
      row.querySelector('[data-candle]').innerHTML = candle(pk(w));
      row.querySelector('[data-px]').innerHTML = n ? fmtC(n.v, n.c) + (p != null ? '<div class="muted small">' + money(p) + '</div>' : '') : p != null ? money(p) : '<span class="muted">—</span>';
    }
  }
  // Filtros de la lista de seguimiento
  document.getElementById('wf')?.addEventListener('click', e => {
    const a = e.target.closest('a[data-wf]'); if (!a) return; e.preventDefault();
    document.querySelectorAll('#wf a').forEach(x => x.classList.toggle('on', x === a));
    document.querySelectorAll('#watch-body [data-wid]').forEach(r => { r.style.display = a.dataset.wf === 'all' || r.dataset.tipo === a.dataset.wf ? '' : 'none' });
  });

  // Interactive Brokers (las mismas funciones de Firebase que usa la app)
  const msg = (m, bad) => { const e = document.getElementById('ibkr-msg'); if (e) { e.textContent = m || ''; e.style.color = bad ? 'var(--bad)' : '' } };
  const call = async (n, d) => { if (!window.pbCall) throw new Error('Firebase'); return window.pbCall(n, d) };
  async function pull() {
    const d = await call('ibkrSync'); await getFx().catch(() => {});
    const positions = d.positions.map(p => ({ tipo: p.tipo, simbolo: p.symbol, cantidad: p.qty,
      precioCompra: p.cost != null ? (toEur(p.cost, p.currency) != null ? Math.round(toEur(p.cost, p.currency) * 100) / 100 : null) : null,
      moneda: p.tipo === 'accion' ? p.currency : 'EUR', precioManual: p.tipo === 'accion' ? p.mark : null }));
    if (window.pbFresh) await window.pbFresh();
    const r = await fetch('/api/ibkr-import', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ positions }) });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    msg(T('ibkr_ok', { n: positions.length }) + (d.skipped ? T('ibkr_skip', { k: d.skipped }).replace('..', '.') : ''));
  }
  const run = async f => { msg('…'); try { await f() } catch (e) { msg(T('ibkr_err', { m: (e && e.message) || String(e) }), true) } };
  document.getElementById('ibkr-connect')?.addEventListener('click', () => run(async () => {
    await call('ibkrSave', { token: document.getElementById('ibkr-token').value, queryId: document.getElementById('ibkr-query').value });
    document.getElementById('ibkr-token').value = ''; document.getElementById('ibkr-form').classList.add('hidden'); document.getElementById('ibkr-on').classList.remove('hidden'); await pull();
  }));
  document.getElementById('ibkr-sync')?.addEventListener('click', () => run(pull));
  document.getElementById('ibkr-off')?.addEventListener('click', () => run(async () => {
    await call('ibkrDelete'); document.getElementById('ibkr-form').classList.remove('hidden'); document.getElementById('ibkr-on').classList.add('hidden'); msg(T('ibkr_bye'));
  }));

  render(); refresh();
  setInterval(() => { if (!document.hidden) refresh() }, 15000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh() });
})();

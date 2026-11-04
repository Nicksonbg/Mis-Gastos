// Asistente de IA de Personal Balance — widget compartido por la web y la app.
// La página que lo carga define:
//   window.PB_AGENT = { api: 'https://…/api/agent', getToken: async () => '<idToken>', onChange: () => {} }
(() => {
  if (window.__pbAgent) return; window.__pbAgent = true;
  const CFG = window.PB_AGENT || {};
  const API = CFG.api || '/api/agent';
  const L = (document.documentElement.lang || 'es').slice(0, 2);
  const TX = {
    title: ['Tu asistente personal', 'Your personal assistant', 'Твоят личен асистент'],
    ph: ['Pregunta o pide un cambio…', 'Ask or request a change…', 'Попитай или поискай промяна…'],
    hi: ['Hola 👋 Puedo responder sobre tus gastos y préstamos, y hacer cambios (te pediré confirmación antes).', 'Hi 👋 I can answer about your expenses and loans, and make changes (I will ask you to confirm first).', 'Здравей 👋 Мога да отговарям за разходите и заемите ти и да правя промени (първо ще те попитам).'],
    s1: ['¿Cuánto pago al mes?', 'How much do I pay per month?', 'Колко плащам на месец?'],
    s2: ['¿Qué me queda por pagar este mes?', 'What is left to pay this month?', 'Какво остава да платя този месец?'],
    s3: ['¿Cuándo termino de pagar los préstamos?', 'When do I finish paying my loans?', 'Кога ще изплатя заемите?'],
    s4: ['Apunta 45 € de súper hoy', 'Log €45 of groceries today', 'Запиши 45 € за храна днес'],
    ok: ['Confirmar', 'Confirm', 'Потвърди'], no: ['Cancelar', 'Cancel', 'Отказ'],
    done: ['Hecho ✓', 'Done ✓', 'Готово ✓'], cancelled: ['Cancelado', 'Cancelled', 'Отказано'],
    nokey: ['El asistente aún no está activado: falta la clave de la IA en el servidor.', 'The assistant is not enabled yet: the AI key is missing on the server.', 'Асистентът още не е активиран: липсва ключът за ИИ на сървъра.'],
    busy: ['La IA gratuita está saturada ahora mismo. Inténtalo en unos minutos.', 'The free AI is busy right now. Try again in a few minutes.', 'Безплатният ИИ е претоварен в момента. Опитай след няколко минути.'],
    err: ['No se pudo contactar con el asistente. Inténtalo de nuevo.', 'Could not reach the assistant. Try again.', 'Няма връзка с асистента. Опитай отново.'],
    auth: ['Tu sesión ha caducado. Recarga la página.', 'Your session expired. Reload the page.', 'Сесията изтече. Презареди страницата.'],
    limit: ['Has llegado al límite de mensajes de hoy. Vuelve mañana.', 'You have reached today\'s message limit. Come back tomorrow.', 'Достигна дневния лимит на съобщения. Опитай утре.'],
    clear: ['Nueva conversación', 'New conversation', 'Нов разговор'],
  };
  const t = k => (TX[k] || [k])[{ es: 0, en: 1, bg: 2 }[L] ?? 0];
  const KEY = 'pb-agent-v1';
  let st = { messages: [], view: [], open: false };
  try { st = Object.assign(st, JSON.parse(sessionStorage.getItem(KEY) || '{}')) } catch (e) {}
  const persist = () => { try { sessionStorage.setItem(KEY, JSON.stringify(st)) } catch (e) {} };

  const css = `
  .pba-fab{position:fixed;right:max(16px,env(safe-area-inset-right,0px));bottom:calc(20px + env(safe-area-inset-bottom,0px));z-index:40;width:56px;height:56px;border-radius:50%;border:0;cursor:pointer;background:var(--text,#fff);color:var(--bg,#000);box-shadow:0 8px 28px rgba(0,0,0,.45);display:grid;place-items:center}
  .pba-fab:hover{transform:scale(1.05)}
  .pba{position:fixed;right:max(16px,env(safe-area-inset-right,0px));bottom:calc(20px + env(safe-area-inset-bottom,0px));z-index:41;width:min(420px,calc(100vw - 32px));height:min(640px,calc(100vh - 40px));background:var(--card,#161616);color:var(--text,#fff);border:1px solid var(--chip,#262626);border-radius:22px;box-shadow:0 20px 60px rgba(0,0,0,.55);display:flex;flex-direction:column;overflow:hidden;font:15px/1.45 Inter,system-ui,sans-serif}
  .pba[hidden],.pba-fab[hidden]{display:none}
  .pba-h{display:flex;align-items:center;gap:8px;padding:14px 16px;border-bottom:1px solid var(--line,#262626)}
  .pba-h b{font-size:16px;flex:1;display:flex;align-items:center;gap:8px}
  .pba-h button{background:none;border:0;color:var(--muted,#8e8e93);cursor:pointer;padding:6px;border-radius:8px;font:inherit;font-size:13px}
  .pba-h button:hover{background:var(--chip,#262626);color:var(--text,#fff)}
  .pba-m{flex:1;overflow-y:auto;padding:14px 16px;display:flex;flex-direction:column;gap:10px}
  .pba-b{max-width:88%;padding:10px 13px;border-radius:16px;white-space:pre-wrap;word-wrap:break-word}
  .pba-b.u{align-self:flex-end;background:var(--text,#fff);color:var(--bg,#000);border-bottom-right-radius:6px}
  .pba-b.a{align-self:flex-start;background:var(--card2,#1f1f1f);border-bottom-left-radius:6px}
  .pba-b.e{align-self:flex-start;background:var(--bad-soft,rgba(255,90,78,.14));color:var(--bad,#ff5a4e)}
  .pba-b ul{margin:4px 0;padding-left:18px;white-space:normal}
  .pba-act{align-self:stretch;border:1px solid var(--chip,#262626);border-radius:16px;padding:12px;background:var(--card2,#1f1f1f)}
  .pba-act p{margin:0 0 10px;font-weight:600}
  .pba-act .r{display:flex;gap:8px;justify-content:flex-end}
  .pba-btn{border:0;border-radius:999px;padding:8px 16px;font:inherit;font-weight:700;cursor:pointer;background:var(--text,#fff);color:var(--bg,#000)}
  .pba-btn.g{background:transparent;color:var(--text,#fff);border:1px solid var(--chip,#262626)}
  .pba-note{align-self:center;font-size:12px;color:var(--muted,#8e8e93)}
  .pba-sg{display:flex;flex-wrap:wrap;gap:6px}
  .pba-sg button{border:1px solid var(--chip,#262626);background:transparent;color:var(--text,#fff);border-radius:999px;padding:6px 12px;font:inherit;font-size:13px;cursor:pointer}
  .pba-f{display:flex;gap:8px;padding:12px;border-top:1px solid var(--line,#262626)}
  .pba-f textarea{flex:1;resize:none;max-height:120px;min-height:42px;padding:10px 12px;border-radius:14px;border:1px solid var(--chip,#262626);background:var(--card2,#1f1f1f);color:var(--text,#fff);font:inherit;font-size:16px}
  .pba-f button{width:42px;height:42px;flex:none;border-radius:50%;border:0;background:var(--text,#fff);color:var(--bg,#000);cursor:pointer;display:grid;place-items:center}
  .pba-f button:disabled{opacity:.4;cursor:default}
  .pba-dots span{display:inline-block;width:6px;height:6px;margin:0 2px;border-radius:50%;background:var(--muted,#8e8e93);animation:pbad 1s infinite}
  .pba-dots span:nth-child(2){animation-delay:.15s}.pba-dots span:nth-child(3){animation-delay:.3s}
  @keyframes pbad{0%,80%,100%{opacity:.25}40%{opacity:1}}
  @media (max-width:600px){
    .pba-fab{bottom:calc(98px + env(safe-area-inset-bottom,0px));width:52px;height:52px}
    .pba{inset:0;width:auto;height:auto;border-radius:0;border:0;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}
  }`;
  const SPARK = '<svg viewBox="0 0 24 24" width="24" height="24" fill="currentColor" aria-hidden="true"><path d="M12 2l1.9 5.6L19.5 9.5l-5.6 1.9L12 17l-1.9-5.6L4.5 9.5l5.6-1.9z"/><path d="M19 14l.9 2.6 2.6.9-2.6.9L19 21l-.9-2.6-2.6-.9 2.6-.9z" opacity=".7"/></svg>';
  const SEND = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 19V5M5 12l7-7 7 7"/></svg>';

  const st_ = document.createElement('style'); st_.textContent = css; document.head.appendChild(st_);
  const fab = document.createElement('button'); fab.className = 'pba-fab'; fab.title = fab.ariaLabel = t('title'); fab.innerHTML = SPARK;
  const box = document.createElement('div'); box.className = 'pba'; box.hidden = true; box.setAttribute('role', 'dialog'); box.ariaLabel = t('title');
  box.innerHTML = `<div class="pba-h"><b>${SPARK.replace('width="24" height="24"', 'width="18" height="18"')}${t('title')}</b><button type="button" data-a="clear">${t('clear')}</button><button type="button" data-a="close" aria-label="×" style="font-size:20px;line-height:1">×</button></div>
    <div class="pba-m"></div><form class="pba-f"><textarea rows="1" placeholder="${t('ph')}"></textarea><button type="submit" aria-label="→">${SEND}</button></form>`;
  document.body.append(fab, box);
  const M = box.querySelector('.pba-m'), F = box.querySelector('form'), TA = F.querySelector('textarea'), SB = F.querySelector('button');
  let busy = false;

  const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const md = s => {
    const lines = esc(s).split('\n'); let out = '', inList = false;
    for (const ln of lines) {
      const m = ln.match(/^\s*[-•*]\s+(.*)/);
      if (m) { if (!inList) { out += '<ul>'; inList = true } out += '<li>' + m[1] + '</li>'; continue }
      if (inList) { out += '</ul>'; inList = false }
      out += ln + '\n';
    }
    if (inList) out += '</ul>';
    return out.replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/\n+$/, '');
  };
  function render() {
    let h = '';
    if (!st.view.length) h += `<div class="pba-b a">${esc(t('hi'))}</div><div class="pba-sg">${['s1', 's2', 's3', 's4'].map(k => `<button type="button" data-s="${esc(t(k))}">${esc(t(k))}</button>`).join('')}</div>`;
    for (const v of st.view) {
      if (v.k === 'u') h += `<div class="pba-b u">${esc(v.text)}</div>`;
      else if (v.k === 'a') h += `<div class="pba-b a">${md(v.text)}</div>`;
      else if (v.k === 'e') h += `<div class="pba-b e">${esc(v.text)}</div>`;
      else if (v.k === 'n') h += `<div class="pba-note">${esc(v.text)}</div>`;
      else if (v.k === 'p') h += `<div class="pba-act"><p>${esc(v.summary)}</p>${v.done ? '' : `<div class="r"><button type="button" class="pba-btn g" data-d="no">${t('no')}</button><button type="button" class="pba-btn" data-d="ok">${t('ok')}</button></div>`}</div>`;
    }
    if (busy) h += '<div class="pba-b a pba-dots"><span></span><span></span><span></span></div>';
    M.innerHTML = h; M.scrollTop = M.scrollHeight;
    SB.disabled = busy; TA.disabled = busy || st.view.some(v => v.k === 'p' && !v.done);
  }
  const show = o => { st.open = o; box.hidden = !o; fab.hidden = o; persist(); if (o) { render(); setTimeout(() => TA.focus(), 50) } };

  async function call(body) {
    busy = true; render();
    try {
      const tok = CFG.getToken ? await CFG.getToken() : null;
      const r = await fetch(API, { method: 'POST', headers: Object.assign({ 'Content-Type': 'application/json' }, tok ? { Authorization: 'Bearer ' + tok } : {}), credentials: 'same-origin', body: JSON.stringify(Object.assign({ lang: L, messages: st.messages }, body)) });
      const j = await r.json().catch(() => ({}));
      if (r.status === 401) st.view.push({ k: 'e', text: t('auth') });
      else if (j.error === 'no_key') st.view.push({ k: 'e', text: t('nokey') });
      else if (j.error === 'limit') st.view.push({ k: 'e', text: t('limit') });
      else if (j.error === 'busy') st.view.push({ k: 'e', text: t('busy') });
      else if (!r.ok || j.error) st.view.push({ k: 'e', text: t('err') + (j.detail ? ' (' + j.detail + ')' : '') });
      else {
        st.messages = j.messages || st.messages;
        if (j.reply) st.view.push({ k: 'a', text: j.reply });
        if (j.pending) st.view.push({ k: 'p', id: j.pending.id, summary: j.pending.summary });
        if (j.changed) { st.view.push({ k: 'n', text: t('done') }); try { CFG.onChange && CFG.onChange() } catch (e) {} }
      }
    } catch (e) { st.view.push({ k: 'e', text: t('err') }) }
    busy = false; persist(); render();
  }
  function send(text) {
    text = text.trim(); if (!text || busy) return;
    st.view.push({ k: 'u', text }); st.messages.push({ role: 'user', content: text }); TA.value = ''; call({});
  }
  fab.onclick = () => show(true);
  box.addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.dataset.a === 'close') show(false);
    if (b.dataset.a === 'clear') { st.messages = []; st.view = []; persist(); render() }
    if (b.dataset.s) send(b.dataset.s);
    if (b.dataset.d) {
      const p = [...st.view].reverse().find(v => v.k === 'p' && !v.done); if (!p) return;
      p.done = true; const ok = b.dataset.d === 'ok';
      if (!ok) st.view.push({ k: 'n', text: t('cancelled') });
      call({ decision: { id: p.id, approve: ok } });
    }
  });
  F.onsubmit = e => { e.preventDefault(); send(TA.value) };
  TA.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(TA.value) } });
  TA.addEventListener('input', () => { TA.style.height = 'auto'; TA.style.height = Math.min(TA.scrollHeight, 120) + 'px' });
  window.addEventListener('keydown', e => { if (e.key === 'Escape' && st.open) show(false) });
  if (st.open) show(true);
  window.pbAgentShow = show;
})();

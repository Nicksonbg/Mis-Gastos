// Personal Balance: lectura de posiciones de Interactive Brokers (solo lectura) con el servicio Flex.
// El token Flex se guarda en la coleccion ibkr_secrets/{uid}, que las reglas de Firestore no dejan leer a los clientes.
const { onCall, HttpsError } = require('firebase-functions/v2/https');
const admin = require('firebase-admin');
admin.initializeApp();
const db = admin.firestore();

const BASE = 'https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService';
const opts = { region: 'europe-west1', invoker: 'public', maxInstances: 5, timeoutSeconds: 90, memory: '256MiB' };
const UA = { 'User-Agent': 'PersonalBalance/1.0' };
const get = async u => { try { return await (await fetch(u, { headers: UA })).text(); } catch (e) { throw new HttpsError('unavailable', 'No se pudo contactar con IBKR: ' + (e && e.message || e)); } };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const tag = (x, n) => { const m = x.match(new RegExp('<' + n + '>([^<]*)</' + n + '>')); return m ? m[1] : ''; };
const uidOf = r => { if (!r.auth) throw new HttpsError('unauthenticated', 'Inicia sesión.'); return r.auth.uid; };

exports.ibkrSave = onCall(opts, async r => {
  const uid = uidOf(r);
  const token = String(r.data?.token || '').trim();
  const queryId = String(r.data?.queryId || '').trim();
  if (!/^[A-Za-z0-9]{8,80}$/.test(token) || !/^\d{3,12}$/.test(queryId)) {
    throw new HttpsError('invalid-argument', 'Token o número de consulta no válidos.');
  }
  try { await db.doc('ibkr_secrets/' + uid).set({ token, queryId, saved: Date.now(), last: 0 }); }
  catch (e) { console.error('ibkrSave', e); throw new HttpsError('failed-precondition', 'No se pudo guardar: ' + (e && e.message || e)); }
  return { ok: true };
});

exports.ibkrDelete = onCall(opts, async r => {
  await db.doc('ibkr_secrets/' + uidOf(r)).delete();
  return { ok: true };
});

async function flex(token, q) {
  const a = await get(`${BASE}/SendRequest?t=${encodeURIComponent(token)}&q=${encodeURIComponent(q)}&v=3`);
  if (tag(a, 'Status') !== 'Success') {
    throw new HttpsError('failed-precondition', 'IBKR respondió: ' + (tag(a, 'ErrorMessage') || 'error desconocido'), { code: tag(a, 'ErrorCode') });
  }
  const ref = tag(a, 'ReferenceCode');
  const url = tag(a, 'Url') || `${BASE}/GetStatement`;
  for (let i = 0; i < 8; i++) {
    await sleep(i ? 4000 : 1500);
    const b = await get(`${url}?t=${encodeURIComponent(token)}&q=${encodeURIComponent(ref)}&v=3`);
    if (b.includes('<FlexQueryResponse')) return b;
    const code = tag(b, 'ErrorCode');
    if (code && code !== '1019') {
      throw new HttpsError('failed-precondition', 'IBKR respondió: ' + (tag(b, 'ErrorMessage') || 'error'), { code });
    }
  }
  throw new HttpsError('deadline-exceeded', 'IBKR tarda demasiado en preparar el informe. Inténtalo en un minuto.');
}

function parse(xml) {
  const rows = [];
  for (const m of xml.matchAll(/<OpenPosition\s+([^>]*?)\/?>/g)) {
    const a = {};
    for (const k of m[1].matchAll(/(\w+)="([^"]*)"/g)) a[k[1]] = k[2];
    rows.push(a);
  }
  const hasSummary = rows.some(a => a.levelOfDetail === 'SUMMARY');
  const used = hasSummary ? rows.filter(a => a.levelOfDetail === 'SUMMARY') : rows;
  const by = {};
  let skipped = 0;
  for (const a of used) {
    const qty = parseFloat(a.position ?? a.quantity);
    const tipo = a.assetCategory === 'STK' ? 'accion' : a.assetCategory === 'CRYPTO' ? 'cripto' : null;
    if (!tipo || !(qty > 0) || !a.symbol) { skipped++; continue; }
    const key = tipo + ':' + a.symbol + ':' + a.currency;
    const cost = parseFloat(a.costBasisPrice), mark = parseFloat(a.markPrice);
    const p = by[key] || (by[key] = { tipo, symbol: a.symbol, currency: a.currency || 'USD', qty: 0, costSum: 0, costQty: 0, mark: null });
    p.qty += qty;
    if (cost > 0) { p.costSum += cost * qty; p.costQty += qty; }
    if (mark > 0) p.mark = mark;
  }
  const positions = Object.values(by).map(p => ({
    tipo: p.tipo, symbol: p.symbol, currency: p.currency, qty: p.qty,
    cost: p.costQty ? p.costSum / p.costQty : null, mark: p.mark,
  }));
  return { positions, skipped, asOf: (xml.match(/toDate="([^"]*)"/) || [])[1] || null };
}

exports.ibkrSync = onCall(opts, async r => {
  const uid = uidOf(r);
  const ref = db.doc('ibkr_secrets/' + uid);
  let s; try { s = await ref.get(); } catch (e) { console.error('ibkrSync', e); throw new HttpsError('failed-precondition', 'No se pudo leer: ' + (e && e.message || e)); }
  if (!s.exists) throw new HttpsError('not-found', 'Todavía no has conectado Interactive Brokers.');
  const { token, queryId, last } = s.data();
  if (Date.now() - (last || 0) < 20000) throw new HttpsError('resource-exhausted', 'Espera unos segundos antes de actualizar otra vez.');
  await ref.update({ last: Date.now() });
  return parse(await flex(token, queryId));
});

exports._parse = parse;

"""Notificaciones push de la app del iPhone: recordatorio el día antes de cada pago.

- Las claves VAPID se generan una vez y se guardan en Firestore (server_config/vapid),
  una colección que solo el servidor puede leer.
- Las suscripciones se guardan en push_subs/{id} (también solo servidor).
- Cloud Scheduler llama cada día a /cron/recordatorios con la cabecera X-Cron-Key.
"""
from __future__ import annotations

import base64
import calendar
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone

import calc

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo(os.environ.get("PB_TZ", "Atlantic/Canary"))
except Exception:  # pragma: no cover
    TZ = timezone.utc

CONTACT = "mailto:avisos@personal-balance.app"
TXT = {
    "one": ["Mañana: {c} · {a}", "Tomorrow: {c} · {a}", "Утре: {c} · {a}"],
    "many": ["Mañana tienes {n} pagos · {a}", "Tomorrow you have {n} payments · {a}", "Утре имаш {n} плащания · {a}"],
    "title": ["Pago pendiente", "Payment due", "Предстоящо плащане"],
    "pres_t": ["Presupuesto", "Budget", "Бюджет"],
    "pres_warn": ["{c}: llevas el {p} del presupuesto ({g} de {l}).", "{c}: you have used {p} of the budget ({g} of {l}).", "{c}: използвал си {p} от бюджета ({g} от {l})."],
    "pres_bad": ["{c}: te has pasado del presupuesto ({g} de {l}).", "{c}: you are over budget ({g} of {l}).", "{c}: надвиши бюджета ({g} от {l})."],
    "pago_t": ["¿Añadir este gasto?", "Add this expense?", "Да добавя ли този разход?"],
    "pago_b": ["{c} · {a} — toca para añadirlo a tus gastos", "{c} · {a} — tap to add it to your expenses", "{c} · {a} — докосни, за да го добавиш"],
    "res_t": ["Tu resumen de {m}", "Your {m} summary", "Твоето резюме за {m}"],
    "res_b": ["Has gastado {t} (fijos {f} + día a día {d}).", "You spent {t} (fixed {f} + day to day {d}).", "Похарчи {t} (фиксирани {f} + ежедневни {d})."],
    "res_up": [" {x} más que el mes pasado.", " {x} more than last month.", " С {x} повече от миналия месец."],
    "res_down": [" {x} menos que el mes pasado.", " {x} less than last month.", " С {x} по-малко от миналия месец."],
    "res_top": ["\nLo que más: {c} ({a}).", "\nTop: {c} ({a}).", "\nНай-много: {c} ({a})."],
    "res_pres": ["\nPresupuestos: {ok} de {n} cumplidos.", "\nBudgets: {ok} of {n} kept.", "\nБюджети: спазени {ok} от {n}."],
    "test_t": ["Avisos activados ✓", "Notifications on ✓", "Известията са включени ✓"],
    "test_b": ["Te avisaré el día antes de cada pago.", "I will remind you the day before each payment.", "Ще те напомням ден преди всяко плащане."],
}
IDX = {"es": 0, "en": 1, "bg": 2}


def tx(k, lang, **p):
    s = TXT[k][IDX.get(lang, 0)]
    for a, b in p.items():
        s = s.replace("{" + a + "}", str(b))
    return s


def money(v, lang):
    s = f"{calc.r2(v):,.2f}"
    if lang == "en":
        return "€" + s
    s = s.replace(",", "X").replace(".", ",").replace("X", " " if lang == "bg" else ".")
    return s + " €"


def local_today():
    return datetime.now(TZ).date()


# ---------- Claves VAPID ----------
_vapid_cache = {}


def _b64u(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def vapid(db):
    """Devuelve (clave privada PEM, clave pública para el navegador). Las crea la primera vez."""
    if _vapid_cache:
        return _vapid_cache["priv"], _vapid_cache["pub"]
    ref = db.collection("server_config").document("vapid") if db else None
    d = (ref.get().to_dict() if ref and ref.get().exists else None) or (_vapid_cache.get("local"))
    if not d:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        k = ec.generate_private_key(ec.SECP256R1())
        priv = k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                               serialization.NoEncryption()).decode()
        pub = _b64u(k.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))
        d = {"priv": priv, "pub": pub}
        if ref:
            ref.set(d)
    _vapid_cache.update(priv=d["priv"], pub=d["pub"])
    return d["priv"], d["pub"]


def sub_id(endpoint):
    return hashlib.sha256(endpoint.encode()).hexdigest()[:40]


# ---------- Qué hay que pagar mañana ----------
def due_tomorrow(S, today=None):
    today = today or local_today()
    tm = today + timedelta(days=1)
    tiso = tm.isoformat()
    mk = tiso[:7]
    out = []
    for g in S.get("gastos", []):
        l = g.get("prestamoId") and calc.loan_by_id(S, g["prestamoId"])
        if l:
            for c in l.get("cuotas", []):
                if c.get("fecha") == tiso and c.get("pagada") is not True:
                    out.append((g.get("concepto") or l.get("nombre", ""), float(c.get("cuota") or 0)))
            continue
        if not g.get("dia"):
            continue
        last = calendar.monthrange(tm.year, tm.month)[1]
        if min(int(g["dia"]), last) == tm.day and (g.get("pagos") or {}).get(mk) is not True:
            out.append((g.get("concepto", ""), float(g.get("importe") or 0)))
    # Préstamos sin gasto vinculado
    linked = {g.get("prestamoId") for g in S.get("gastos", []) if g.get("prestamoId")}
    for l in S.get("prestamos", []):
        if l["id"] in linked:
            continue
        for c in l.get("cuotas", []):
            if c.get("fecha") == tiso and c.get("pagada") is not True:
                out.append((l.get("nombre", ""), float(c.get("cuota") or 0)))
    return out


def message(items, lang):
    total = sum(a for _, a in items)
    if len(items) == 1:
        body = tx("one", lang, c=items[0][0], a=money(items[0][1], lang))
    else:
        body = tx("many", lang, n=len(items), a=money(total, lang)) + "\n" + \
            "\n".join(f"• {c}: {money(a, lang)}" for c, a in items[:6])
    return {"title": tx("title", lang), "body": body, "tag": "pb-pagos", "url": "./"}


def send(sub, payload, priv):
    """Envía una notificación. Devuelve False si la suscripción ya no existe."""
    from py_vapid import Vapid01
    from pywebpush import WebPushException, webpush
    try:
        webpush(subscription_info={"endpoint": sub["endpoint"], "keys": sub["keys"]},
                data=json.dumps(payload, ensure_ascii=False), vapid_private_key=Vapid01.from_pem(priv.encode()),
                vapid_claims={"sub": CONTACT}, ttl=12 * 3600)
        return True
    except WebPushException as e:
        code = getattr(e.response, "status_code", None)
        if code in (404, 410):
            return False
        raise


LEVEL = {"ok": 0, "warn": 1, "bad": 2}


def budget_alerts(S, prev, lang):
    """Avisos de presupuesto que suben de nivel (80 % / 100 %) respecto a lo ya avisado este mes.
    Devuelve (mensaje o None, nuevo estado)."""
    mk = local_today().strftime("%Y-%m")
    seen = prev.get("niveles", {}) if prev.get("mes") == mk else {}
    new, lines = dict(seen), []
    for p in calc.presupuestos_estado(S, 0):
        k = p["categoria"].strip().lower()
        if LEVEL[p["nivel"]] > LEVEL.get(seen.get(k, "ok"), 0):
            new[k] = p["nivel"]
            lines.append(tx("pres_bad" if p["nivel"] == "bad" else "pres_warn", lang, c=p["categoria"], p=f"{p['pct']:.0f} %",
                            g=money(p["gastado"], lang), l=money(p["limite"], lang)))
    state = {"mes": mk, "niveles": new}
    if not lines:
        return None, state
    return {"title": tx("pres_t", lang), "body": "\n".join(lines[:4]), "tag": "pb-presupuesto", "url": "./"}, state


MESES = {"es": "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split(),
         "en": "January February March April May June July August September October November December".split(),
         "bg": "януари февруари март април май юни юли август септември октомври ноември декември".split()}


def is_last_day(d=None):
    d = d or local_today()
    return (d + timedelta(days=1)).month != d.month


def summary_message(S, lang):
    r = calc.month_summary(S, 0)
    if not r["total"]:
        return None
    body = tx("res_b", lang, t=money(r["total"], lang), f=money(r["fijos"], lang), d=money(r["dia"], lang))
    if r["dif"]:
        body += tx("res_up" if r["dif"] > 0 else "res_down", lang, x=money(abs(r["dif"]), lang))
    if r["top"]:
        body += tx("res_top", lang, c=r["top"][0][0], a=money(r["top"][0][1], lang))
    if r["n_pres"]:
        body += tx("res_pres", lang, ok=r["pres_ok"], n=r["n_pres"])
    m = MESES.get(lang, MESES["es"])[r["mes_n"] - 1]
    return {"title": tx("res_t", lang, m=m), "body": body, "tag": "pb-resumen", "url": "./?resumen=1"}

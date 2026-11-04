"""Personal Balance — versión web en Python (Flask).

Misma cuenta y mismos datos que la app del iPhone (Firebase).
El navegador inicia sesión con Firebase Auth y manda su token en la
cookie "pb_token"; el servidor lo verifica y lee/escribe Firestore.
"""
from __future__ import annotations

import base64
import html
import io
import json
import os
import secrets
from datetime import date
from functools import wraps

from flask import (Flask, Response, abort, g, make_response, redirect, render_template,
                   request, url_for)

import calc
from calc import r2
from store import DEV, store

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024  # fotos y copias de seguridad

APP_VERSION = "web-26"
FB_CFG = {
    "apiKey": "AIzaSyDCJX-0ByjCWV-mtH-WNop5-6wVF76JBAs",
    "authDomain": "personal-balance-dccca.firebaseapp.com",
    "projectId": "personal-balance-dccca",
    "storageBucket": "personal-balance-dccca.firebasestorage.app",
    "messagingSenderId": "778378922815",
    "appId": "1:778378922815:web:16071b8fb93c5a2957e18a",
}
CORS_ORIGINS = {"https://nicksonbg.github.io"} | set(filter(None, os.environ.get("PB_CORS", "").split(",")))
ICONS = ["😀", "😎", "🦊", "🐼", "🦁", "🐯", "🐸", "🦄", "🚀", "⭐", "💎", "🌿"]

# ---------- Idiomas ----------
with open(os.path.join(os.path.dirname(__file__), "translations.json"), encoding="utf-8") as f:
    TR = json.load(f)
TR.update({
    "adv_inv": ["Inversiones (avanzado)", "Investments (advanced)", "Инвестиции (за напреднали)"],
    "adv_inv_note": ["Muestra la pestaña Inversiones: cartera, seguimiento y conexión con brókeres.", "Shows the Investments tab: portfolio, watchlist and broker connection.", "Показва раздела Инвестиции: портфейл, следене и връзка с брокери."],
    "w_dev": ["Entrar (modo prueba)", "Sign in (test mode)", "Вход (тестов режим)"],
    "w_saved": ["Guardado", "Saved", "Запазено"],
    "w_imported": ["Datos cargados", "Data loaded", "Данните са заредени"],
    "w_reset_done": ["Datos borrados", "Data deleted", "Данните са изтрити"],
    "w_bad_file": ["El archivo no contiene datos válidos de Personal Balance.", "The file does not contain valid Personal Balance data.", "Файлът не съдържа валидни данни на Personal Balance."],
    "w_bad_img": ["No se pudo leer la imagen.", "Could not read the image.", "Неуспешно четене на снимката."],
    "w_web_note": ["Versión web: tus datos están en tu cuenta y se sincronizan con la app del iPhone.", "Web version: your data is in your account and syncs with the iPhone app.", "Уеб версия: данните са в профила ти и се синхронизират с приложението на iPhone."],
    "w_pass_sent": ["Te hemos enviado un correo para cambiar la contraseña.", "We sent you an email to change your password.", "Изпратихме ти имейл за смяна на паролата."],
    "w_soon": ["Inversiones llegará a la web en la siguiente fase. Mientras tanto, úsalas en la app del iPhone.", "Investments are coming to the web in the next phase. Meanwhile, use them in the iPhone app.", "Инвестициите идват в уеб версията в следващата фаза. Дотогава ги ползвай в приложението на iPhone."],
    "w_type_delete": ["Escribe ELIMINAR para confirmar", "Type DELETE to confirm", "Напиши ИЗТРИЙ за потвърждение"],
    "w_confirm_word": ["ELIMINAR", "DELETE", "ИЗТРИЙ"],
    "e_domain": ["Esta dirección aún no está autorizada para entrar con Google. Prueba con correo y contraseña.", "This address is not yet authorised for Google sign-in. Try email and password.", "Този адрес още не е разрешен за вход с Google. Опитай с имейл и парола."],
    "show_pass": ["Mostrar contraseña", "Show password", "Покажи паролата"],
    "hide_pass": ["Ocultar contraseña", "Hide password", "Скрий паролата"],
    "w_session": ["No se pudo abrir la sesión en la web.", "Could not open the session on the web.", "Неуспешно отваряне на сесията в уеб версията."],
    "w_error": ["Algo ha fallado en el servidor.", "Something went wrong on the server.", "Нещо се обърка на сървъра."],
    "w_retry": ["Volver a entrar", "Sign in again", "Влез отново"],
    "w_demo": ["Cargar datos de ejemplo", "Load sample data", "Зареди примерни данни"],
    "w_demo_t": ["Cuenta de pruebas", "Test account", "Тестов профил"],
    "w_demo_txt": ["Esta es una cuenta de pruebas: puedes llenarla con datos de ejemplo (gastos, préstamos, presupuestos, tickets e inversiones). Sustituye los datos de esta cuenta.", "This is a test account: you can fill it with sample data. It replaces this account's data.", "Това е тестов профил: можеш да го напълниш с примерни данни. Заменя данните на този профил."],
    "w_demo_ok": ["Datos de ejemplo cargados", "Sample data loaded", "Примерните данни са заредени"],
    "w_upd": ["Actualizar", "Refresh", "Обнови"],
})
with open(os.path.join(os.path.dirname(__file__), "tr_budget.json"), encoding="utf-8") as f:
    TR.update(json.load(f))
LANGS = {"es": {"i": 0, "dec": ",", "grp": ".", "sep": "/", "cur": "suf"},
         "en": {"i": 1, "dec": ".", "grp": ",", "sep": "/", "cur": "pre"},
         "bg": {"i": 2, "dec": ",", "grp": " ", "sep": ".", "cur": "suf"}}


def cur_lang():
    v = request.cookies.get("pb_lang")
    return v if v in LANGS else "es"


def t(k, **p):
    r = TR.get(k)
    s = r[LANGS[cur_lang()]["i"]] if r else k
    for a, b in p.items():
        s = s.replace("{" + a + "}", str(b))
    return s


def num(v, dec=2):
    L = LANGS[cur_lang()]
    v = float(v or 0)
    neg = v < 0
    s = f"{abs(v):,.{dec}f}"
    ip, _, fp = s.partition(".")
    ip = ip.replace(",", L["grp"])
    s = ip + (L["dec"] + fp if dec else "")
    return ("-" if neg else "") + s


def money(v):
    s = num(r2(v))
    if LANGS[cur_lang()]["cur"] == "pre":
        return ("-€" + s[1:]) if s.startswith("-") else "€" + s
    return s + " €"


def hero(v):
    """Separa una cantidad en parte entera y decimales para la cifra grande."""
    s = num(r2(v))
    d = LANGS[cur_lang()]["dec"]
    i, _, f = s.partition(d)
    return i, d + f


def fmt_d(s):
    if not s:
        return ""
    y, m, d = s.split("-")
    p = LANGS[cur_lang()]["sep"]
    return d + p + m + p + y


def dec1(v):
    return num(v, 1)


def esc(s):
    return html.escape(str(s if s is not None else ""), quote=True)


def valid_photo(s):
    return isinstance(s, str) and (s.startswith("data:image/jpeg;") or s.startswith("data:image/png;"))


# ---------- Sesión ----------
def verify(token):
    if DEV:
        return {"uid": "dev", "email": "dev@example.com", "email_verified": True} if token == "dev" else None
    from firebase_admin import auth
    try:
        return auth.verify_id_token(token, clock_skew_seconds=10)
    except Exception as e:  # el motivo se muestra en la pantalla de entrada
        g.auth_err = f"{type(e).__name__}: {str(e)[:180]}"
        print("verify_id_token:", g.auth_err, flush=True)
        return None


def login_required(f):
    @wraps(f)
    def w(*a, **k):
        tok = request.cookies.get("pb_token")
        if not tok:
            return redirect(url_for("login"))
        user = verify(tok)
        if not user:
            # Token caducado: la página pide uno nuevo al navegador y recarga
            if request.method == "POST":
                return render_template("wait.html", **ctx(None)), 401
            return render_template("wait.html", **ctx(None))
        g.user = user
        g.uid = user["uid"]
        return f(*a, **k)
    return w


def csrf_ok():
    c = request.cookies.get("pb_csrf")
    return c and secrets.compare_digest(c, request.form.get("csrf", ""))


@app.before_request
def check_csrf():
    if request.method == "OPTIONS":
        return
    # /api/: JSON o token Bearer -> el navegador exige CORS previo, así que no hay riesgo de CSRF
    if request.method == "POST" and request.path.startswith("/api/") and (
            request.headers.get("Authorization", "").startswith("Bearer ") or request.is_json):
        return
    if request.path.startswith("/cron/"):
        return
    if request.method == "POST" and not csrf_ok():
        abort(400, "CSRF")


@app.after_request
def set_csrf(resp):
    if not request.cookies.get("pb_csrf") and g.get("csrf_new"):
        resp.set_cookie("pb_csrf", g.csrf_new, samesite="Lax", secure=not DEV, httponly=True, max_age=31536000)
    if request.path.startswith("/api/") and request.headers.get("Origin") in CORS_ORIGINS:
        resp.headers["Access-Control-Allow-Origin"] = request.headers["Origin"]
        resp.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp.headers["Access-Control-Max-Age"] = "3600"
        resp.headers["Vary"] = "Origin"
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    return resp


def csrf_token():
    c = request.cookies.get("pb_csrf")
    if not c:
        c = g.get("csrf_new") or secrets.token_urlsafe(24)
        g.csrf_new = c
    return c


def inv_on(S):
    a = (S or {}).get("ajustes") or {}
    if isinstance(a.get("inversiones"), bool):
        return a["inversiones"]
    return bool((S or {}).get("inversiones") or (S or {}).get("watch"))


def ctx(tab, **kw):
    P = g.get("P") or {"nombre": "", "foto": "", "icono": ""}
    user = g.get("user") or {}
    nombre = P.get("nombre") or user.get("name") or ""
    if valid_photo(P.get("foto")):
        av = {"img": P["foto"]}
    else:
        av = {"txt": P.get("icono") or (nombre or user.get("email") or "?").strip()[:1].upper()}
    kw.setdefault("show_inv", inv_on(g.get("S")))
    return dict(t=t, money=money, hero=hero, fmt_d=fmt_d, dec1=dec1, num=num, tab=tab, lang=cur_lang(),
                theme=request.cookies.get("pb_theme", ""), csrf=csrf_token(), fb_cfg=json.dumps(FB_CFG),
                dev=DEV, avatar=av, user=user, msg=request.args.get("ok"), err=request.args.get("err"),
                version=APP_VERSION, **kw)


def load():
    g.S = store.load(g.uid)
    g.P = store.load_profile(g.uid)
    return g.S


def save_and_back(endpoint, ok="w_saved", **params):
    store.save(g.uid, g.S)
    return redirect(url_for(endpoint, ok=ok, **params))


def fnum(name, default=None):
    v = (request.form.get(name) or "").strip().replace(",", ".")
    if v == "":
        return default
    try:
        return float(v)
    except ValueError:
        return default


# ---------- Páginas ----------
@app.get("/login")
def login():
    return render_template("login.html", **ctx(None))


@app.get("/salir")
def salir():
    resp = make_response(render_template("logout.html", **ctx(None)))
    resp.delete_cookie("pb_token")
    return resp


@app.get("/")
@login_required
def resumen():
    S = load()
    off = request.args.get("m", 0, type=int)
    tm = calc.total_mes(S)
    pend = cap = paid = 0
    fin = None
    for l in S["prestamos"]:
        s = calc.loan_stats(l)
        pend += s["pendiente"]; cap += s["capital"]; paid += s["pagado"]
        if s["fin"] and (not fin or s["fin"] > fin):
            fin = s["fin"]
    fin_sub = ""
    if fin:
        m = calc.months_until(fin)
        fin_sub = t("dentro", m=m) if m > 0 else t("terminado_k")
    # Alertas
    alerts = []
    for l in S["prestamos"]:
        s = calc.loan_stats(l)
        if s["overdue"]:
            alerts.append(("bad", "⚠️", t("al_overdue", name=esc(l.get("nombre")), n=len(s["overdue"]), date=fmt_d(s["overdue"][0]["fecha"]))))
    soon = calc.upcoming(S, 7)
    if soon:
        alerts.append(("warn", "🔔", t("al_soon") + " " + " · ".join(
            t("al_soon_item", name=esc(u["nombre"]), amt=money(u["importe"]), date=fmt_d(u["fecha"])) for u in soon)))
    pres = calc.presupuestos_estado(S, 0)
    for p in pres:
        if p["nivel"] != "ok":
            alerts.append((p["nivel"], "🎯", t("al_pres_bad" if p["nivel"] == "bad" else "al_pres_warn", c=esc(p["categoria"]),
                                                p=f"{p['pct']:.0f} %", g=money(p["gastado"]), l=money(p["limite"]))))
    if not S["gastos"] and not S["prestamos"]:
        alerts.insert(0, ("info", "", t("welcome")))
    # Pendientes de este mes
    td = calc.iso(calc.today())
    mes_c = t("meses_c").split("|")
    up = []
    for u in calc.mes_items(S, 0)[1]:
        if u["pagado"]:
            continue
        if not u["fecha"]:
            up.append({**u, "dia": "—", "mes": t("sin_dia"), "pill": ("mute", t("sin_dia_pago"))})
            continue
        d = calc.parse(u["fecha"])
        days = (d - calc.today()).days
        pill = ("bad", t("vencido")) if days < 0 else ("warn", t("hoy")) if days == 0 else \
            ("warn" if days <= 7 else "mute", t("en_d", d=days))
        up.append({**u, "dia": d.day, "mes": mes_c[d.month - 1], "pill": pill})
    # Gastos del mes
    m0, items = calc.mes_items(S, off)
    for i in items:
        if i["pagado"]:
            i["st"] = ("ok", t("st_pagado"))
        elif not i["fecha"]:
            i["st"] = ("mute", t("st_sin_dia"))
        elif i["fecha"] < td:
            i["st"] = ("bad", t("st_vencido"))
        elif i["fecha"] == td:
            i["st"] = ("warn", t("st_hoy"))
        else:
            i["st"] = ("mute", t("en_d", d=(calc.parse(i["fecha"]) - calc.today()).days))
    items0 = calc.mes_items(S, 0)[1]
    mes_tot0 = r2(sum(i["importe"] for i in items0))
    mes_pag0 = r2(sum(i["importe"] for i in items0 if i["pagado"]))
    tot = r2(sum(i["importe"] for i in items))
    pag = r2(sum(i["importe"] for i in items if i["pagado"]))
    donut, legend = calc.donut_svg(S, money, t, esc)
    debt = calc.debt_chart(S, money, t, esc, mes_c, lambda v: num(v, 0 if v == int(v) else 1))
    return render_template(
        "resumen.html", **ctx("resumen", S=S, tm=tm, n_gastos=len(S["gastos"]), pend=pend, cap=cap, paid=paid,
                               fin=fin, fin_sub=fin_sub, alerts=alerts, up=up, up_total=sum(u["importe"] for u in up),
                               off=off, mes_lbl=t("meses").split("|")[m0.month - 1] + " " + str(m0.year),
                               items=items, pres=pres, mes_tot=tot, mes_pag=pag, mes_tot0=mes_tot0, mes_pag0=mes_pag0, donut=donut, legend=legend, debt=debt))


@app.post("/mes/toggle")
@login_required
def mes_toggle():
    S = load()
    tipo, a, b = request.form["ref"].split("|", 2)
    calc.toggle_mes(S, tipo, a, b, request.form.get("on") == "1")
    store.save(g.uid, S)
    return redirect(url_for("resumen", m=request.form.get("m", 0, type=int)) + "#mes")


@app.get("/gastos")
@login_required
def gastos():
    S = load()
    tabn = request.args.get("t") if request.args.get("t") in ("fijos", "dia", "pres") else "fijos"
    if tabn != "fijos":
        off = request.args.get("m", 0, type=int)
        m0 = calc.month_start(off)
        movs = calc.movimientos_mes(S, off)
        cats = sorted({*t("cats_dia").split("|"), *t("cats").split("|"),
                       *[x.get("categoria") for x in S["gastos"] + S["movimientos"] if x.get("categoria")]})
        return render_template("gastos_extra.html", **ctx(
            "gastos", tabn=tabn, off=off, mes_lbl=t("meses").split("|")[m0.month - 1] + " " + str(m0.year),
            movs=movs, mov_total=calc.r2(sum(float(m.get("importe") or 0) for m in movs)),
            pres=calc.presupuestos_estado(S, 0), cats=cats, today=calc.iso(calc.today())))
    tm = calc.total_mes(S)
    rows = []
    for gst in S["gastos"]:
        l = gst.get("prestamoId") and calc.loan_by_id(S, gst["prestamoId"])
        st = calc.loan_stats(l) if l else None
        rows.append({**gst, "pct": float(gst.get("importe") or 0) / tm * 100 if tm else 0,
                     "hasta": st["fin"] if st else None})
    return render_template("gastos.html", **ctx("gastos", S=S, tabn="fijos", rows=rows, tm=tm, cats=t("cats").split("|"),
                                                   gastos_json=json.dumps(S["gastos"])))


@app.post("/gastos/save")
@login_required
def gasto_save():
    S = load()
    v = {"concepto": request.form.get("concepto", "").strip(), "importe": r2(fnum("importe", 0)),
         "dia": int(fnum("dia")) if fnum("dia") else None,
         "categoria": request.form.get("categoria", "").strip(), "prestamoId": request.form.get("prestamoId", "")}
    if v["dia"] is not None:
        v["dia"] = max(1, min(31, v["dia"]))
    gid = request.form.get("id")
    gst = next((x for x in S["gastos"] if x["id"] == gid), None) if gid else None
    if gst:
        gst.update(v)
    else:
        S["gastos"].append({"id": calc.uid(), **v})
    return save_and_back("gastos")


@app.post("/gastos/delete")
@login_required
def gasto_delete():
    S = load()
    S["gastos"] = [x for x in S["gastos"] if x["id"] != request.form["id"]]
    return save_and_back("gastos")


@app.post("/mov/save")
@login_required
def mov_save():
    S = load()
    v = {"fecha": request.form.get("fecha") or calc.iso(calc.today()), "importe": r2(fnum("importe", 0)),
         "categoria": request.form.get("categoria", "").strip()[:40], "concepto": request.form.get("concepto", "").strip()[:80]}
    try:
        lin = json.loads(request.form.get("lineas") or "null")
    except ValueError:
        lin = None
    if isinstance(lin, list) and lin:
        v["lineas"] = [{"desc": str(x.get("desc", ""))[:60], "cant": x.get("cant", 1), "importe": r2(x.get("importe"))}
                       for x in lin[:120] if isinstance(x, dict)]
    try:
        tk = json.loads(request.form.get("ticket") or "null")
    except ValueError:
        tk = None
    if isinstance(tk, dict):
        v["ticket"] = {k: str(tk.get(k) or "")[:80] for k in ("comercio", "direccion", "nif", "hora", "forma_pago", "num_ticket")}
    mid = request.form.get("id")
    m = next((x for x in S["movimientos"] if x.get("id") == mid), None) if mid else None
    if m:
        m.update(v)
    else:
        S["movimientos"].append({"id": calc.uid(), **v})
    store.save(g.uid, S)
    return redirect(url_for("gastos", t="dia", m=request.form.get("m", 0, type=int), ok="w_saved"))


@app.post("/mov/delete")
@login_required
def mov_delete():
    S = load()
    S["movimientos"] = [x for x in S["movimientos"] if x.get("id") != request.form["id"]]
    store.save(g.uid, S)
    return redirect(url_for("gastos", t="dia", m=request.form.get("m", 0, type=int)))


@app.post("/pres/save")
@login_required
def pres_save():
    S = load()
    cat = request.form.get("categoria", "").strip()[:40]
    lim = r2(fnum("limite", 0))
    if cat and lim > 0:
        pid = request.form.get("id")
        p = next((x for x in S["presupuestos"] if x.get("id") == pid), None) if pid else \
            next((x for x in S["presupuestos"] if x.get("categoria", "").lower() == cat.lower()), None)
        if p:
            p.update(categoria=cat, limite=lim)
        else:
            S["presupuestos"].append({"id": calc.uid(), "categoria": cat, "limite": lim})
        store.save(g.uid, S)
    return redirect(url_for("gastos", t="pres", ok="w_saved"))


@app.post("/pres/delete")
@login_required
def pres_delete():
    S = load()
    S["presupuestos"] = [x for x in S["presupuestos"] if x.get("id") != request.form["id"]]
    store.save(g.uid, S)
    return redirect(url_for("gastos", t="pres"))


@app.get("/prestamos")
@login_required
def prestamos():
    S = load()
    loans, tot, pag, pen, fin = [], 0, 0, 0, None
    for l in S["prestamos"]:
        s = calc.loan_stats(l)
        tot += s["total"]; pag += s["pagado"]; pen += s["pendiente"]
        if s["fin"] and (not fin or s["fin"] > fin):
            fin = s["fin"]
        status = ("ok", t("terminado")) if s["nPend"] == 0 else ("bad", t("cuota_venc")) if s["overdue"] else ("mute", t("en_curso"))
        rows = [{**c, "paid": calc.is_paid(c), "next": bool(s["next"] and c["id"] == s["next"]["id"]),
                 "manual": c.get("pagada") is not None} for c in s["cs"]]
        loans.append({"l": l, "s": s, "pct": s["pagado"] / s["total"] * 100 if s["total"] else 0,
                      "status": status, "rows": rows})
    return render_template("prestamos.html", **ctx("prestamos", loans=loans, tot=tot, pag=pag, pen=pen, fin=fin,
                                                       today=calc.iso(calc.today())))


@app.post("/prestamos/new")
@login_required
def loan_new():
    S = load()
    n = int(fnum("n", 0) or 0)
    imp = fnum("importe", 0) or 0
    inicio = request.form.get("inicio") or calc.iso(calc.today())
    if n < 1 or imp <= 0:
        return redirect(url_for("prestamos"))
    l, q, day = calc.build_loan(request.form.get("nombre", "").strip(), request.form.get("entidad", "").strip(),
                                imp, fnum("tin", 0), n, inicio)
    S["prestamos"].append(l)
    if request.form.get("addGasto"):
        S["gastos"].append({"id": calc.uid(), "concepto": l["nombre"], "importe": q,
                            "categoria": t("cats").split("|")[1], "dia": day, "prestamoId": l["id"]})
    return save_and_back("prestamos")


@app.post("/prestamos/delete")
@login_required
def loan_delete():
    S = load()
    lid = request.form["id"]
    S["prestamos"] = [x for x in S["prestamos"] if x["id"] != lid]
    for gst in S["gastos"]:
        if gst.get("prestamoId") == lid:
            gst["prestamoId"] = ""
    return save_and_back("prestamos")


@app.post("/cuota/save")
@login_required
def cuota_save():
    S = load()
    l = calc.loan_by_id(S, request.form["lid"]) or abort(404)
    v = {"fecha": request.form["fecha"], "cuota": r2(fnum("cuota", 0)), "amortizacion": r2(fnum("amortizacion", 0)),
         "intereses": r2(fnum("intereses", 0)), "capitalAntes": r2(fnum("capitalAntes", 0)),
         "nota": request.form.get("nota", "").strip()}
    cid = request.form.get("cid")
    c = next((x for x in l["cuotas"] if x["id"] == cid), None) if cid else None
    if c:
        c.update(v)
    else:
        l["cuotas"].append({"id": calc.uid(), **v})
    store.save(g.uid, S)
    return redirect(url_for("prestamos", ok="w_saved") + "#l-" + l["id"])


@app.post("/cuota/delete")
@login_required
def cuota_delete():
    S = load()
    l = calc.loan_by_id(S, request.form["lid"]) or abort(404)
    l["cuotas"] = [x for x in l["cuotas"] if x["id"] != request.form["cid"]]
    store.save(g.uid, S)
    return redirect(url_for("prestamos", ok="w_saved") + "#l-" + l["id"])


@app.post("/cuota/toggle")
@login_required
def cuota_toggle():
    S = load()
    calc.toggle_cuota(S, request.form["lid"], request.form["cid"], request.form.get("on") == "1")
    store.save(g.uid, S)
    return redirect(url_for("prestamos") + "#l-" + request.form["lid"])


@app.get("/datos")
@login_required
def datos():
    load()
    return render_template("datos.html", **ctx("datos", test=DEV or calc.is_test_email(g.user.get("email"))))


@app.get("/datos/export")
@login_required
def datos_export():
    S = load()
    body = json.dumps(S, ensure_ascii=False, indent=2)
    return Response(body, mimetype="application/json",
                    headers={"Content-Disposition": f'attachment; filename="mis-gastos-{date.today().isoformat()}.json"'})


@app.post("/datos/import")
@login_required
def datos_import():
    load()
    raw = ""
    f = request.files.get("file")
    if f and f.filename:
        raw = f.read().decode("utf-8", "replace")
    else:
        raw = request.form.get("text", "")
    try:
        d = json.loads(raw.strip())
        if not isinstance(d, dict) or not isinstance(d.get("gastos"), list) or not isinstance(d.get("prestamos"), list):
            raise ValueError
    except ValueError:
        return redirect(url_for("datos", err="w_bad_file"))
    g.S = calc.normalize(d)
    return save_and_back("resumen", ok="w_imported")


@app.post("/datos/demo")
@login_required
def datos_demo():
    load()
    if not (DEV or calc.is_test_email(g.user.get("email"))):
        abort(403)
    g.S = calc.demo_data()
    return save_and_back("resumen", ok="w_demo_ok")


@app.route("/api/demo-data", methods=["POST", "OPTIONS"])
def api_demo():
    if request.method == "OPTIONS":
        return "", 204
    user = _api_user()
    if not user:
        return {"error": "auth"}, 401
    if not (DEV or calc.is_test_email(user.get("email"))):
        return {"error": "forbidden"}, 403
    return calc.demo_data()


@app.post("/datos/reset")
@login_required
def datos_reset():
    load()
    g.S = calc.seed()
    return save_and_back("datos", ok="w_reset_done")


@app.get("/perfil")
@login_required
def perfil():
    load()
    return render_template("perfil.html", **ctx("perfil", P=g.P, icons=ICONS, photo=valid_photo(g.P.get("foto"))))


@app.post("/perfil")
@login_required
def perfil_save():
    load()
    P = g.P
    P["nombre"] = request.form.get("nombre", "").strip()
    ic = request.form.get("icono", "")
    if ic in ICONS and ic != P.get("icono"):
        P["icono"], P["foto"] = ic, ""
    store.save_profile(g.uid, P)
    if not DEV and P["nombre"]:
        try:
            from firebase_admin import auth
            auth.update_user(g.uid, display_name=P["nombre"])
        except Exception:
            pass
    return redirect(url_for("perfil", ok="p_saved"))


@app.post("/perfil/foto")
@login_required
def perfil_foto():
    load()
    f = request.files.get("foto")
    try:
        from PIL import Image, ImageOps
        im = ImageOps.exif_transpose(Image.open(f.stream)).convert("RGB")
        w, h = im.size
        s = min(w, h)
        im = im.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s)).resize((256, 256), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=82)
    except Exception:
        return redirect(url_for("perfil", err="w_bad_img"))
    g.P["foto"] = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    g.P["icono"] = ""
    store.save_profile(g.uid, g.P)
    return redirect(url_for("perfil", ok="p_saved"))


@app.post("/perfil/foto/delete")
@login_required
def perfil_foto_delete():
    load()
    g.P["foto"] = ""
    store.save_profile(g.uid, g.P)
    return redirect(url_for("perfil", ok="p_saved"))


@app.post("/ajustes")
@login_required
def ajustes():
    resp = redirect(url_for("perfil", ok="w_saved"))
    lg = request.form.get("lang")
    if lg in LANGS:
        resp.set_cookie("pb_lang", lg, max_age=31536000, samesite="Lax")
    th = request.form.get("theme", "")
    if th in ("", "light", "dark"):
        resp.set_cookie("pb_theme", th, max_age=31536000, samesite="Lax")
    if request.form.get("adv_present"):
        S = load()
        S.setdefault("ajustes", {})["inversiones"] = bool(request.form.get("adv_inv"))
        store.save(g.uid, S)
    return resp


@app.post("/idioma")
def idioma():
    resp = redirect(request.form.get("next") or url_for("login"))
    lg = request.form.get("lang")
    if lg in LANGS:
        resp.set_cookie("pb_lang", lg, max_age=31536000, samesite="Lax")
    return resp


@app.post("/cuenta/eliminar")
@login_required
def cuenta_eliminar():
    if request.form.get("confirm", "").strip().upper() != t("w_confirm_word"):
        return redirect(url_for("perfil"))
    store.delete_user_data(g.uid)
    if not DEV:
        from firebase_admin import auth
        auth.delete_user(g.uid)
    return redirect(url_for("salir"))


# ---------- Inversiones (solo lectura; precios en vivo en el navegador) ----------
CRYPTO = {"BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "BNB", "DOT", "LTC", "AVAX", "LINK", "MATIC", "POL", "TRX", "SHIB",
          "USDT", "USDC", "ATOM", "XLM", "NEAR", "UNI", "BCH", "ETC", "APT", "ARB", "OP", "SUI", "PEPE", "TON", "HBAR"}
FIATS = {"USD", "EUR", "GBP", "CHF", "JPY", "BGN", "CAD", "AUD", "NZD", "SEK", "NOK", "DKK", "PLN", "CZK", "HUF", "RON",
         "TRY", "CNY", "INR", "BRL", "MXN"}
WIX = {"SP500": ("S&P 500", "SPY"), "SPX": ("S&P 500", "SPY"), "NASDAQ": ("NASDAQ 100", "QQQ"), "NASDAQ100": ("NASDAQ 100", "QQQ"),
       "NDX": ("NASDAQ 100", "QQQ"), "DOW": ("Dow Jones", "DIA"), "DOWJONES": ("Dow Jones", "DIA"), "DJI": ("Dow Jones", "DIA"),
       "RUSSELL2000": ("Russell 2000", "IWM"), "DAX": ("DAX", "EWG"), "IBEX": ("IBEX 35", "EWP"), "IBEX35": ("IBEX 35", "EWP"),
       "FTSE": ("FTSE 100", "EWU"), "NIKKEI": ("Nikkei 225", "EWJ"), "EUROSTOXX": ("Euro Stoxx 50", "FEZ")}
INV_TIPOS = ("cripto", "accion", "divisa", "indice")


def ibkr_connected(uid):
    if DEV or not getattr(store, "db", None):
        return False
    try:
        return store.db.collection("ibkr_secrets").document(uid).get().exists
    except Exception:
        return False


@app.get("/inversiones")
@login_required
def inversiones():
    S = load()
    tabn = request.args.get("t") if request.args.get("t") in ("cartera", "watch", "conectar") else "cartera"
    return render_template("inversiones.html", **ctx(
        "inversiones", tabn=tabn, inv=S.get("inversiones", []), watch=S.get("watch", []), fh=bool(S.get("finnhub")),
        fh_key=S.get("finnhub", ""), ibkr=ibkr_connected(g.uid), brokers=sorted({i.get("broker") for i in S.get("inversiones", []) if i.get("broker")})))


@app.post("/inversiones/save")
@login_required
def inv_save():
    S = load()
    tipo = request.form.get("tipo") if request.form.get("tipo") in ("cripto", "accion", "divisa") else "cripto"
    v = {"tipo": tipo, "simbolo": request.form.get("simbolo", "").strip().upper()[:20], "cantidad": fnum("cantidad", 0) or 0,
         "precioCompra": fnum("precioCompra"), "broker": request.form.get("broker", "").strip()[:60],
         "moneda": request.form.get("moneda") if request.form.get("moneda") in ("USD", "EUR") else "USD",
         "precioManual": fnum("precioManual")}
    if tipo != "accion":
        v["moneda"], v["precioManual"] = "EUR", None
    if not v["simbolo"]:
        return redirect(url_for("inversiones"))
    S.setdefault("inversiones", [])
    iid = request.form.get("id")
    it = next((x for x in S["inversiones"] if x.get("id") == iid), None) if iid else None
    if it:
        it.update(v)
    else:
        S["inversiones"].append({"id": calc.uid(), **v})
    return save_and_back("inversiones")


@app.post("/inversiones/delete")
@login_required
def inv_delete():
    S = load()
    S["inversiones"] = [x for x in S.get("inversiones", []) if x.get("id") != request.form["id"]]
    return save_and_back("inversiones")


@app.post("/watch/add")
@login_required
def watch_add():
    S = load()
    S.setdefault("watch", [])
    sy = request.form.get("simbolo", "").strip().upper().replace(" ", "").replace("/", "")[:20]
    tipo = request.form.get("tipo", "auto")
    if not sy:
        return redirect(url_for("inversiones", t="watch"))
    if len(S["watch"]) >= 20:
        return redirect(url_for("inversiones", t="watch", err="watch_full"))
    key = sy.replace("&", "").replace("-", "")
    if tipo not in INV_TIPOS:
        tipo = "indice" if key in WIX else "cripto" if sy in CRYPTO else "divisa" if sy in FIATS else "accion"
    item = {"id": calc.uid(), "tipo": tipo, "simbolo": sy}
    if tipo == "indice":
        nm, px = WIX.get(key, (sy, sy))
        item.update(simbolo=nm, proxy=px)
    if any(w.get("tipo") == item["tipo"] and w.get("simbolo") == item["simbolo"] for w in S["watch"]):
        return redirect(url_for("inversiones", t="watch", err="watch_dup"))
    S["watch"].append(item)
    store.save(g.uid, S)
    return redirect(url_for("inversiones", t="watch"))


@app.post("/watch/delete")
@login_required
def watch_delete():
    S = load()
    S["watch"] = [x for x in S.get("watch", []) if x.get("id") != request.form["id"]]
    store.save(g.uid, S)
    return redirect(url_for("inversiones", t="watch"))


@app.post("/inversiones/finnhub")
@login_required
def inv_finnhub():
    S = load()
    k = request.form.get("key", "").strip()[:80]
    if k:
        S["finnhub"] = k
    else:
        S.pop("finnhub", None)
    store.save(g.uid, S)
    return redirect(url_for("inversiones", t="conectar", ok="w_saved"))


@app.route("/api/ibkr-import", methods=["POST"])
def ibkr_import():
    user = _api_user()
    if not user:
        return {"error": "auth"}, 401
    S = store.load(user["uid"])
    pos = (request.get_json(silent=True) or {}).get("positions") or []
    keep = [i for i in S.get("inversiones", []) if i.get("fuente") != "ibkr"]
    nuevas = []
    for p in pos[:300]:
        tipo = p.get("tipo") if p.get("tipo") in ("cripto", "accion", "divisa") else "accion"
        nuevas.append({"id": calc.uid(), "tipo": tipo, "simbolo": str(p.get("simbolo", "")).upper()[:20],
                       "cantidad": float(p.get("cantidad") or 0), "precioCompra": p.get("precioCompra"),
                       "broker": "Interactive Brokers", "moneda": p.get("moneda") or ("USD" if tipo == "accion" else "EUR"),
                       "precioManual": p.get("precioManual"), "fuente": "ibkr"})
    S["inversiones"] = keep + nuevas
    store.save(user["uid"], S)
    return {"ok": True, "n": len(nuevas)}


@app.errorhandler(500)
def err500(e):
    import traceback
    orig = getattr(e, "original_exception", None) or e
    traceback.print_exception(orig)
    why = f"{type(orig).__name__}: {str(orig)[:200]}"
    return render_template("error.html", **ctx(None, why=why)), 500


@app.route("/api/agent", methods=["POST", "OPTIONS"])
def api_agent():
    if request.method == "OPTIONS":
        return "", 204
    h = request.headers.get("Authorization", "")
    tok = h[7:] if h.startswith("Bearer ") else request.cookies.get("pb_token")
    user = verify(tok) if tok else None
    if not user:
        return {"error": "auth"}, 401
    g.user, g.uid = user, user["uid"]
    body = request.get_json(silent=True) or {}
    S = store.load(g.uid)
    P = store.load_profile(g.uid)
    lang = body.get("lang") if body.get("lang") in LANGS else cur_lang()
    import agent
    limit = int(os.environ.get("AGENT_DAILY_LIMIT", "40"))
    try:
        ok, _ = store.ia_quota(g.uid, limit)
    except Exception as e:
        print("ia_quota:", repr(e), flush=True)
        ok = True
    if not ok:
        return {"error": "limit", "limit": limit}, 429
    try:
        out = agent.run(S, body.get("messages") or [], lang, P.get("nombre") or user.get("name", ""),
                        decision=body.get("decision"), save=lambda s: store.save(g.uid, s),
                        loans_cat=TR["cats"][LANGS[lang]["i"]].split("|")[1])
    except agent.AIBusy:
        return {"error": "busy"}, 429
    except Exception as e:  # error de la API de IA
        print("agent:", repr(e), flush=True)
        return {"error": "ai", "detail": f"{type(e).__name__}: {str(e)[:200]}"}, 502
    if out.get("error"):
        return out, 503
    return out


# ---------- Escáner de tickets ----------
@app.route("/api/scan", methods=["POST", "OPTIONS"])
def api_scan():
    if request.method == "OPTIONS":
        return "", 204
    user = _api_user()
    if not user:
        return {"error": "auth"}, 401
    import scan
    b = request.get_json(silent=True) or {}
    lang = b.get("lang") if b.get("lang") in LANGS else cur_lang()
    img = str(b.get("image") or "")
    if not img.startswith("data:image/") or len(img) > 12_000_000:
        return {"error": "bad"}, 400
    try:
        ok, _ = store.ia_quota(user["uid"], int(os.environ.get("AGENT_DAILY_LIMIT", "40")))
    except Exception:
        ok = True
    if not ok:
        return {"error": "limit"}, 429
    try:
        data_url = scan.prepare_image(base64.b64decode(img.split(",", 1)[1]))
        S = store.load(user["uid"])
        cats = list(dict.fromkeys([*TR["cats_dia"][LANGS[lang]["i"]].split("|")[:-1],
                                   *[m.get("categoria") for m in S.get("movimientos", []) if m.get("categoria")],
                                   TR["cats_dia"][LANGS[lang]["i"]].split("|")[-1]]))
        return scan.read_receipt(data_url, cats, lang)
    except scan.ScanError as e:
        code = str(e)
        if code in ("no_key", "busy", "unreadable"):
            return {"error": code}, 503 if code == "no_key" else 429 if code == "busy" else 422
        print("scan:", code, flush=True)
        return {"error": "ai", "detail": code[:200]}, 502
    except Exception as e:
        print("scan:", repr(e), flush=True)
        return {"error": "bad"}, 400


# ---------- Pagos con el móvil (automatización "Transacción" de Atajos) ----------
GUESS = [("Supermercado", "mercadona lidl carrefour aldi dia eroski hiperdino spar alcampo consum hipercor supermerc froiz ahorramas bonpreu"),
         ("Restaurantes", "restaurante bar cafe café cafeteria mcdonald burger kfc telepizza domino glovo just eat uber eats starbucks pizzeria tasca"),
         ("Transporte", "repsol cepsa shell bp disa galp gasolinera petrol uber cabify bolt renfe guaguas global metro taxi parking aparcamiento"),
         ("Compras", "amazon zara primark mediamarkt media markt corte ingles decathlon ikea leroy aliexpress shein h&m fnac"),
         ("Salud", "farmacia clinica clínica dental optica óptica"),
         ("Ocio", "netflix spotify cine cinesa yelmo steam playstation disney hbo")]


def guess_cat(merchant, lang="es"):
    m = (merchant or "").lower()
    cats = TR["cats_dia"][LANGS.get(lang, LANGS["es"])["i"]].split("|")
    es = TR["cats_dia"][0].split("|")
    for cat, words in GUESS:
        if any(w in m for w in words.split()):
            return cats[es.index(cat)] if cat in es else cat
    return cats[-1]


def pago_url():
    return request.host_url.rstrip("/").replace("http://", "https://") + url_for("api_pago")


@app.route("/api/pago/token", methods=["POST", "OPTIONS"])
def pago_token():
    if request.method == "OPTIONS":
        return "", 204
    user = _api_user()
    if not user:
        return {"error": "auth"}, 401
    b = request.get_json(silent=True) or {}
    if b.get("action") == "revoke":
        store.set_token(user["uid"], None)
        return {"ok": True, "token": None}
    tok = store.token_for(user["uid"])
    if not tok and b.get("action") == "create":
        tok = secrets.token_urlsafe(24)
        store.set_token(user["uid"], tok)
    return {"token": tok, "url": pago_url()}


@app.route("/api/pago", methods=["POST"])
def api_pago():
    b = request.get_json(silent=True) or request.form.to_dict() or {}
    tok = str(b.get("token") or request.args.get("token") or "").strip()
    uid = store.uid_for_token(tok) if tok else None
    if not uid:
        return {"error": "token"}, 403
    import scan
    imp = scan._num(b.get("importe"))
    if imp is None or imp == 0:
        return {"error": "importe"}, 400
    imp = calc.r2(abs(imp))
    comercio = str(b.get("comercio") or b.get("merchant") or "").strip()[:60] or "Pago con el móvil"
    S = store.load(uid)
    pend = S.setdefault("pagos_pendientes", [])
    from push import local_today
    from datetime import datetime as _dt
    import push as _push
    now = _dt.now(_push.TZ)
    lang = "es"
    subs = [x for x in store.list_subs() if x.get("uid") == uid]
    if subs:
        lang = subs[0].get("lang", "es")
    pend.append({"id": calc.uid(), "importe": imp, "comercio": comercio, "fecha": local_today().isoformat(),
                 "hora": now.strftime("%H:%M"), "tarjeta": str(b.get("tarjeta") or "")[:40],
                 "categoria": guess_cat(comercio, lang)})
    S["pagos_pendientes"] = pend[-20:]
    store.save(uid, S)
    try:
        priv = _push.vapid(store.db)[0]
        msg = {"title": _push.tx("pago_t", lang), "body": _push.tx("pago_b", lang, c=comercio, a=_push.money(imp, lang)),
               "tag": "pb-pago", "url": "./"}
        for sb in subs:
            if not _push.send(sb, msg, priv):
                store.delete_sub(sb["_id"])
    except Exception as e:
        print("pago push:", repr(e), flush=True)
    return {"ok": True}


# ---------- Notificaciones push (app del iPhone) ----------
def _api_user():
    h = request.headers.get("Authorization", "")
    tok = h[7:] if h.startswith("Bearer ") else request.cookies.get("pb_token")
    return verify(tok) if tok else None


@app.route("/api/push/key", methods=["GET", "OPTIONS"])
def push_key():
    import push
    return {"key": push.vapid(store.db)[1]}


@app.route("/api/push/subscribe", methods=["POST", "OPTIONS"])
def push_subscribe():
    if request.method == "OPTIONS":
        return "", 204
    user = _api_user()
    if not user:
        return {"error": "auth"}, 401
    import push
    b = request.get_json(silent=True) or {}
    sub = b.get("subscription") or {}
    if not str(sub.get("endpoint", "")).startswith("https://") or not (sub.get("keys") or {}).get("p256dh"):
        return {"error": "bad"}, 400
    lang = b.get("lang") if b.get("lang") in LANGS else "es"
    sid = push.sub_id(sub["endpoint"])
    store.save_sub(sid, {"uid": user["uid"], "endpoint": sub["endpoint"], "keys": sub["keys"], "lang": lang,
                         "creado": calc.iso(calc.today())})
    if b.get("test"):
        try:
            push.send(sub, {"title": push.tx("test_t", lang), "body": push.tx("test_b", lang), "tag": "pb-test", "url": "./"},
                      push.vapid(store.db)[0])
        except Exception as e:
            print("push test:", repr(e), flush=True)
            return {"ok": True, "test": False}
    return {"ok": True}


@app.route("/api/push/unsubscribe", methods=["POST", "OPTIONS"])
def push_unsubscribe():
    if request.method == "OPTIONS":
        return "", 204
    if not _api_user():
        return {"error": "auth"}, 401
    import push
    ep = (request.get_json(silent=True) or {}).get("endpoint", "")
    if ep:
        store.delete_sub(push.sub_id(ep))
    return {"ok": True}


@app.post("/cron/recordatorios")
def cron_recordatorios():
    key = os.environ.get("CRON_KEY", "")
    if not key or not secrets.compare_digest(request.headers.get("X-Cron-Key", ""), key):
        abort(403)
    import push
    priv = push.vapid(store.db)[0]
    subs = store.list_subs()
    by_uid = {}
    for sb in subs:
        by_uid.setdefault(sb["uid"], []).append(sb)
    sent = removed = users = 0
    for uid, lst in by_uid.items():
        try:
            S = store.load(uid)
            items = push.due_tomorrow(S)
            lang = lst[0].get("lang", "es")
            pmsg, pstate = push.budget_alerts(S, store.get_alert_state(uid), lang)
        except Exception as e:
            print("cron load:", uid, repr(e), flush=True)
            continue
        msgs = ([push.message(items, lang)] if items else []) + ([pmsg] if pmsg else [])
        if not msgs:
            continue
        users += 1
        for sb in list(lst):
            for m in msgs:
                try:
                    if push.send(sb, m, priv):
                        sent += 1
                    else:
                        store.delete_sub(sb["_id"]); removed += 1
                        break
                except Exception as e:
                    print("cron send:", repr(e), flush=True)
        if pmsg:
            store.set_alert_state(uid, pstate)
    print(f"recordatorios: usuarios={users} enviados={sent} borrados={removed}", flush=True)
    return {"users": users, "sent": sent, "removed": removed, "subs": len(subs)}


@app.get("/healthz")
def healthz():
    return "ok"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), debug=DEV)

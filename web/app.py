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
import re
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

APP_VERSION = "web-72"
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
    "op_btn": ["💬 Danos tu opinión", "💬 Give us feedback", "💬 Дай ни мнение"],
    "op_t": ["Tu opinión", "Your feedback", "Твоето мнение"],
    "op_intro": ["¿Algo no funciona, echas algo de menos o tienes una idea? Cuéntanoslo: lo leemos todo.", "Something not working, missing something or have an idea? Tell us: we read everything.", "Нещо не работи, липсва ти нещо или имаш идея? Кажи ни: четем всичко."],
    "op_tipo": ["Tipo", "Type", "Вид"],
    "op_idea": ["💡 Idea", "💡 Idea", "💡 Идея"],
    "op_fallo": ["🐞 Algo falla", "🐞 Something is broken", "🐞 Нещо не работи"],
    "op_gusta": ["❤️ Me gusta", "❤️ I like it", "❤️ Харесва ми"],
    "op_otro": ["💬 Otro", "💬 Other", "💬 Друго"],
    "op_nota": ["¿Qué te parece la app?", "How do you rate the app?", "Как оценяваш приложението?"],
    "op_texto": ["Escribe aquí…", "Write here…", "Пиши тук…"],
    "op_send": ["Enviar", "Send", "Изпрати"],
    "op_ok": ["¡Gracias! Hemos recibido tu opinión.", "Thank you! We got your feedback.", "Благодарим! Получихме мнението ти."],
    "op_limit": ["Ya has enviado muchas opiniones hoy. Prueba mañana.", "You have sent a lot of feedback today. Try tomorrow.", "Изпрати много мнения днес. Опитай утре."],
    "op_vacio": ["Escribe algo o pon estrellas antes de enviar.", "Write something or add stars before sending.", "Напиши нещо или дай звезди преди да изпратиш."],
    "op_admin": ["Opiniones recibidas", "Feedback received", "Получени мнения"],
    "op_nuevas": ["{n} sin leer", "{n} unread", "{n} непрочетени"],
    "op_leida": ["Marcar como leída", "Mark as read", "Маркирай като прочетено"],
    "op_noleida": ["Marcar sin leer", "Mark as unread", "Маркирай като непрочетено"],
    "op_borrar": ["Borrar", "Delete", "Изтрий"],
    "op_ninguna": ["Todavía no hay opiniones.", "No feedback yet.", "Още няма мнения."],
    "op_todas": ["Todas", "All", "Всички"],
    "sum_n": ["{n} gastos", "{n} expenses", "{n} разхода"],
    "sum_t": ["Resumen de {m}", "{m} summary", "Резюме за {m}"],
    "sum_total": ["Gastado en total", "Total spent", "Общо похарчено"],
    "sum_fijos": ["Gastos fijos", "Fixed expenses", "Фиксирани разходи"],
    "sum_dia": ["Día a día", "Day to day", "Ежедневни"],
    "sum_vs": ["vs. mes anterior", "vs. previous month", "спрямо миналия месец"],
    "sum_top": ["En qué se fue", "Where it went", "За какво отидоха"],
    "sum_mayor": ["Gasto más grande", "Biggest expense", "Най-голям разход"],
    "sum_pres": ["Presupuestos cumplidos", "Budgets kept", "Спазени бюджети"],
    "sum_pasados": ["Te pasaste en: {c}", "Over budget in: {c}", "Надвишени: {c}"],
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


# ---------- Límite de peticiones por IP (segunda barrera contra abuso) ----------
# Ventana deslizante en memoria. El límite firme por usuario (40 IA/día) sigue en Firestore;
# esto solo frena el martilleo automático antes de llegar a él.
import collections
import threading

_rl_lock = threading.Lock()
_rl_hits = collections.defaultdict(collections.deque)
RL_RULES = (("/api/agent", 20, 60), ("/api/scan", 20, 60), ("/api/opinion", 15, 60),
            ("/api/mensaje", 12, 60), ("/api/pago", 60, 60), ("/api/", 120, 60))
RL_DEFAULT = (240, 60)  # resto de la web


def client_ip():
    # En Cloud Run, Google añade la IP real del cliente al FINAL de X-Forwarded-For.
    # Lo que el cliente mande va delante y es falseable, así que tomamos la última.
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[-1].strip() or (request.remote_addr or "?")
    return request.remote_addr or "?"


def rate_limited():
    path = request.path
    limit, window = RL_DEFAULT
    for pref, lim, win in RL_RULES:
        if path.startswith(pref):
            limit, window = lim, win
            break
    import time as _t
    now = _t.monotonic()
    key = client_ip() + "|" + (next((p for p, *_ in RL_RULES if path.startswith(p)), "web"))
    with _rl_lock:
        q = _rl_hits[key]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            return True
        q.append(now)
        if len(_rl_hits) > 20000:  # evitar crecer sin control
            # quitar solo las entradas ya vencidas (no borrar los contadores de todos)
            for k in [k for k, dq in _rl_hits.items() if not dq or now - dq[-1] > 300]:
                del _rl_hits[k]
            if len(_rl_hits) > 20000:   # caso extremo: último recurso
                _rl_hits.clear()
    return False


@app.before_request
def throttle():
    if request.method == "OPTIONS" or request.path == "/healthz":
        return
    if rate_limited():
        if request.path.startswith("/api/"):
            return {"error": "rate_limited", "msg": "Demasiadas peticiones. Espera un momento."}, 429, {"Retry-After": "30"}
        return make_response(("Demasiadas peticiones. Espera un momento.", 429,
                              {"Retry-After": "30"}))


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
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Content-Security-Policy", "frame-ancestors 'none'; base-uri 'self'; object-src 'none'")
    resp.headers.setdefault("Permissions-Policy", "camera=(self), microphone=(), geolocation=()")
    if not DEV:
        resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    return resp


def csrf_token():
    c = request.cookies.get("pb_csrf")
    if not c:
        c = g.get("csrf_new") or secrets.token_urlsafe(24)
        g.csrf_new = c
    return c


def inv_on(S):
    a = (S or {}).get("ajustes") if isinstance(S, dict) else None
    if not isinstance(a, dict):
        a = {}
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
    kw.setdefault("admin", is_admin(user))
    return dict(t=t, money=money, hero=hero, fmt_d=fmt_d, dec1=dec1, num=num, tab=tab, lang=cur_lang(),
                theme=request.cookies.get("pb_theme", ""), csrf=csrf_token(), fb_cfg=json.dumps(FB_CFG),
                dev=DEV, avatar=av, user=user, msg=request.args.get("ok"), err=request.args.get("err"),
                version=APP_VERSION, **kw)


def track_usage():
    """Registra métricas de uso (no económicas) en el perfil: plataforma, día de
    actividad e idioma. Se llama en cada carga de datos, así que se dispara en
    cualquier página de la web, no solo en Resumen."""
    try:
        P = g.get("P")
        if P is None:
            return
        ua = request.headers.get("User-Agent", "")
        pl = "nav-movil" if any(x in ua for x in ("iPhone", "iPad", "Android", "Mobile")) else "nav-pc"
        hoy = calc.iso(calc.today())
        lang_h = (request.headers.get("Accept-Language", "").split(",")[0].strip())[:20]
        dias = P.get("dias") if isinstance(P.get("dias"), list) else []
        changed = False
        if (P.get("plat") or "") != pl:
            P["plat"] = pl; changed = True
        if hoy not in dias:
            dias.append(hoy); P["dias"] = dias; changed = True
        if lang_h and P.get("lang") != lang_h:
            P["lang"] = lang_h; changed = True
        from urllib.parse import unquote
        tzc = unquote(request.cookies.get("pb_tz") or "")[:64]
        if tzc and P.get("tz") != tzc:
            P["tz"] = tzc; changed = True
        if changed:
            store.save_profile(g.uid, P)
    except Exception as e:
        print("uso web:", repr(e), flush=True)


def load():
    g.S = store.load(g.uid)
    g.P = store.load_profile(g.uid)
    track_usage()
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
    mr = calc.mes_real(S, 0)
    anio_g = calc.anio_real(S, calc.today().year)
    hist_y = request.args.get("y", calc.today().year, type=int)
    hist = calc.historial_anio(S, hist_y)
    hist_tot = r2(sum(r["total"] for r in hist if r["total"]))
    hist_max = max([r["total"] for r in hist if r["total"]] or [0])
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
    td0 = calc.today()
    show_sum = request.args.get("resumen") == "1" or td0.day <= 5 or (td0 + __import__("datetime").timedelta(days=3)).month != td0.month
    msum = calc.month_summary(S, -1 if (td0.day <= 5 and request.args.get("resumen") != "1") else 0) if show_sum else None
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
    mes_dia = calc.mes_real(S, off)["d"]
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
                               items=items, pres=pres, msum=msum, mes_tot=tot, mes_pag=pag, mes_tot0=mes_tot0, mes_pag0=mes_pag0, donut=donut, legend=legend, debt=debt,
                               mr=mr, anio_g=anio_g, hist=hist, hist_y=hist_y, hist_tot=hist_tot, hist_max=hist_max, mes_dia=mes_dia))


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
        ms = calc.meses_de(gst)
        rows.append({**gst, "pct": calc.mensual(gst) / tm * 100 if tm else 0,
                     "meses_lbl": ", ".join(t("meses_c").split("|")[m - 1] for m in ms) if ms and not gst.get("prestamoId") else "",
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
    v["meses"] = calc.meses_de({"meses": request.form.getlist("meses")})
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
        status = ("ok", "✓ " + t("terminado")) if s["nPend"] == 0 else ("bad", t("cuota_venc")) if s["overdue"] else ("ok", "✓ " + t("al_dia"))
        rows = [{**c, "paid": calc.is_paid(c), "next": bool(s["next"] and c["id"] == s["next"]["id"]),
                 "manual": c.get("pagada") is not None} for c in s["cs"]]
        loans.append({"l": l, "s": s, "pct": s["pagado"] / s["total"] * 100 if s["total"] else 0,
                      "status": status, "rows": rows, "overdue": len(s["overdue"])})
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


@app.post("/prestamos/aldia")
@login_required
def loan_aldia():
    S = load()
    lid = request.form["id"]
    l = calc.loan_by_id(S, lid)
    if l:
        for c in l["cuotas"]:
            if c.get("pagada") is False:
                c.pop("pagada", None)
        store.save(g.uid, S)
    return redirect(url_for("prestamos") + "#l-" + lid)


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
    if len(json.dumps(g.S, ensure_ascii=False).encode("utf-8")) > 1_000_000:
        return redirect(url_for("datos", err="w_bad_file"))
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
    adm = is_admin(g.user)
    nuevas = sum(1 for o in store.list_opiniones() if not o.get("leida")) if adm else 0
    return render_template("perfil.html", **ctx("perfil", P=g.P, icons=ICONS, photo=valid_photo(g.P.get("foto")),
                                                admin=adm, op_nuevas=nuevas))


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
        resp.set_cookie("pb_lang", lg, max_age=31536000, samesite="Lax", secure=not DEV)
    th = request.form.get("theme", "")
    if th in ("", "light", "dark"):
        resp.set_cookie("pb_theme", th, max_age=31536000, samesite="Lax", secure=not DEV)
    if request.form.get("adv_present"):
        S = load()
        if not isinstance(S.get("ajustes"), dict):
            S["ajustes"] = {}
        S["ajustes"]["inversiones"] = bool(request.form.get("adv_inv"))
        store.save(g.uid, S)
    return resp


@app.post("/idioma")
def idioma():
    nxt = request.form.get("next") or ""
    # Solo rutas de esta misma web (evita redirigir a otra página)
    if not nxt.startswith("/") or nxt.startswith("//") or "\\" in nxt:
        nxt = url_for("login")
    resp = redirect(nxt)
    lg = request.form.get("lang")
    if lg in LANGS:
        resp.set_cookie("pb_lang", lg, max_age=31536000, samesite="Lax", secure=not DEV)
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
                       "broker": "Interactive Brokers", "moneda": (str(p.get("moneda") or "").upper() if re.fullmatch(r"[A-Za-z]{3}", str(p.get("moneda") or "")) else ("USD" if tipo == "accion" else "EUR")),
                       "precioManual": p.get("precioManual"), "fuente": "ibkr"})
    S["inversiones"] = keep + nuevas
    store.save(user["uid"], S)
    return {"ok": True, "n": len(nuevas)}


@app.errorhandler(500)
def err500(e):
    import traceback
    orig = getattr(e, "original_exception", None) or e
    traceback.print_exception(orig)
    try:
        store.log_error({"tipo": "server", "msg": str(orig)[:500],
                         "stack": traceback.format_exc()[:2000], "donde": request.path,
                         "uid": g.get("uid", ""), "email": (g.get("user") or {}).get("email", "")})
    except Exception:
        pass
    try:
        return render_template("error.html", **ctx(None, why=None)), 500
    except Exception:
        return "Error", 500


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
    msgs = body.get("messages") or []
    if isinstance(msgs, list):
        msgs = msgs[-60:]  # no mandar un historial enorme a la IA (coste)
        for mm in msgs:
            if isinstance(mm, dict) and mm.get("role") == "user" and isinstance(mm.get("content"), str):
                mm["content"] = mm["content"][:8000]
    else:
        msgs = []
    try:
        out = agent.run(S, msgs, lang, P.get("nombre") or user.get("name", ""),
                        decision=body.get("decision"), save=lambda s: store.save(g.uid, s),
                        loans_cat=TR["cats"][LANGS[lang]["i"]].split("|")[1])
    except agent.AIBusy:
        return {"error": "busy"}, 429
    except Exception as e:  # error de la API de IA
        print("agent:", repr(e), flush=True)
        return {"error": "ai"}, 502
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
        return {"error": "ai"}, 502
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
    tok = str(b.get("token") or "").strip()[:100]
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
    if not push.valid_endpoint(sub.get("endpoint")) or not (sub.get("keys") or {}).get("p256dh"):
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
    user = _api_user()
    ep = (request.get_json(silent=True) or {}).get("endpoint", "")
    if ep:
        sid = push.sub_id(str(ep))
        cur = store.get_sub(sid)
        if cur and cur.get("uid") == user["uid"]:
            store.delete_sub(sid)
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


@app.post("/cron/resumen")
def cron_resumen():
    """Resumen del mes: se llama cada noche; solo envía el último día del mes (o con force=1 para probar)."""
    key = os.environ.get("CRON_KEY", "")
    if not key or not secrets.compare_digest(request.headers.get("X-Cron-Key", ""), key):
        abort(403)
    import push
    if not push.is_last_day() and request.args.get("force") != "1":
        return {"skipped": "no es el último día del mes"}
    priv = push.vapid(store.db)[0]
    by_uid = {}
    for sb in store.list_subs():
        by_uid.setdefault(sb["uid"], []).append(sb)
    sent = 0
    for uid, lst in by_uid.items():
        try:
            msg = push.summary_message(store.load(uid), lst[0].get("lang", "es"))
        except Exception as e:
            print("resumen:", uid, repr(e), flush=True)
            continue
        if not msg:
            continue
        for sb in lst:
            try:
                if push.send(sb, msg, priv):
                    sent += 1
                else:
                    store.delete_sub(sb["_id"])
            except Exception as e:
                print("resumen send:", repr(e), flush=True)
    print(f"resumen mensual: enviados={sent}", flush=True)
    return {"sent": sent, "users": len(by_uid)}


# ---------- Opiniones ----------
# Solo el administrador puede leerlas. Se compara la huella sha256 del correo,
# así el correo no queda escrito en el código.
ADMIN_HASHES = {"eded3749028b56140a97b33c73f700e9dc6fdab29c5f2498da788406783348df"} | {h for h in os.environ.get("PB_ADMIN_HASHES", "").split(",") if h}
OP_TIPOS = ("idea", "fallo", "gusta", "otro")


def is_admin(user):
    import hashlib
    e = ((user or {}).get("email") or "").strip().lower()
    if DEV and e == "dev@example.com":
        return True
    return bool((user or {}).get("email_verified")) and hashlib.sha256(e.encode()).hexdigest() in ADMIN_HASHES


def _save_opinion(user, data, origen):
    from store import now_iso
    texto = str(data.get("texto") or "").strip()[:3000]
    tipo = data.get("tipo") if data.get("tipo") in OP_TIPOS else "otro"
    try:
        nota = max(0, min(5, int(data.get("nota") or 0)))
    except (TypeError, ValueError):
        nota = 0
    # El texto es opcional con «Me gusta» o con estrellas; si no, hace falta escribir algo
    if not texto and tipo != "gusta" and not nota:
        return "op_vacio"
    doc = {"uid": user["uid"], "email": user.get("email", ""), "nombre": user.get("name", ""), "texto": texto,
           "tipo": tipo, "nota": nota, "origen": origen, "version": str(data.get("version") or APP_VERSION)[:20],
           "idioma": str(data.get("lang") or cur_lang())[:5], "fecha": now_iso(), "leida": False}
    return None if store.add_opinion(user["uid"], doc) else "op_limit"


@app.get("/opinion")
@login_required
def opinion():
    load()
    return render_template("opinion.html", **ctx("perfil"))


@app.post("/opinion")
@login_required
def opinion_send():
    load()
    err = _save_opinion(g.user, request.form, "web")
    if err:
        return redirect(url_for("opinion", err=err))
    return redirect(url_for("perfil", ok="op_ok"))


@app.route("/api/opinion", methods=["POST", "OPTIONS"])
def api_opinion():
    if request.method == "OPTIONS":
        return "", 204
    user = _api_user()
    if not user:
        return {"error": "auth"}, 401
    d = request.get_json(silent=True) or {}
    err = _save_opinion(user, d, "app")
    if err:
        return {"error": err, "msg": TR[err][{"es": 0, "en": 1, "bg": 2}.get(d.get("lang"), 0)]}, 429 if err == "op_limit" else 400
    return {"ok": True}


# ---------- Mensajes de problemas (soporte) ----------
def _encode_captura(data_url):
    """Re-codifica la captura a un JPEG acotado (máx. 1000 px, calidad 72) para no
    superar el límite de Firestore. Devuelve '' si no es una imagen válida."""
    if not (isinstance(data_url, str) and data_url.startswith("data:image/") and "," in data_url):
        return ""
    try:
        from PIL import Image
        raw = base64.b64decode(data_url.split(",", 1)[1])
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        im.thumbnail((1000, 1000))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=72)
        out = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
        return out if len(out) <= 900_000 else ""
    except Exception:
        return ""


def _revisar_captura(data_url):
    """La IA mira la captura y dice si se ven cantidades de dinero o datos sensibles.
    Best-effort: si la IA no está disponible o falla, devolvemos hay=None y el cliente
    muestra un recordatorio genérico. La IA solo AVISA; tapar los números lo hace el usuario."""
    key = os.environ.get("GROQ_API_KEY")
    if not key or not (isinstance(data_url, str) and data_url.startswith("data:image/")):
        return {"hay": None}
    try:
        import httpx
        from scan import VISION_MODEL, URL as GURL
        p = ("Mira esta captura de pantalla de una app de finanzas personales. ¿Se ven cantidades "
             "de dinero, saldos, importes o números de cuenta/tarjeta? Responde SOLO un JSON: "
             '{"hay_cifras": true o false}. No expliques nada.')
        body = {"model": VISION_MODEL, "temperature": 0, "max_completion_tokens": 200,
                "messages": [{"role": "user", "content": [{"type": "text", "text": p},
                              {"type": "image_url", "image_url": {"url": data_url}}]}],
                "response_format": {"type": "json_object"}, "reasoning_format": "hidden", "reasoning_effort": "none"}
        r = httpx.post(GURL, json=body, timeout=30, headers={"Authorization": f"Bearer {key}"})
        if r.status_code >= 400:
            return {"hay": None}
        txt = r.json()["choices"][0]["message"].get("content") or "{}"
        txt = re.sub(r"<think>.*?</think>", "", txt, flags=re.S)
        m = re.search(r"\{.*\}", txt, re.S)
        return {"hay": bool(json.loads(m.group(0) if m else txt).get("hay_cifras"))}
    except Exception as e:
        print("revisar_captura:", repr(e), flush=True)
        return {"hay": None}


def _save_mensaje(user, data):
    from store import now_iso
    texto = str(data.get("texto") or "").strip()[:3000]
    if not texto:
        return "msg_vacio"
    doc = {"uid": user["uid"], "email": user.get("email", ""), "nombre": user.get("name", "") or "",
           "texto": texto, "foto": _encode_captura(data.get("foto") or ""),
           "plat": str(data.get("plat") or "")[:20], "version": str(data.get("version") or APP_VERSION)[:20],
           "idioma": str(data.get("lang") or cur_lang())[:5], "fecha": now_iso(), "resuelto": False}
    return None if store.add_mensaje(doc) else "msg_fallo"


@app.route("/api/mensaje", methods=["POST", "OPTIONS"])
def api_mensaje():
    if request.method == "OPTIONS":
        return "", 204
    user = _api_user()
    if not user:
        return {"error": "auth"}, 401
    err = _save_mensaje(user, request.get_json(silent=True) or {})
    return ({"error": err}, 400) if err else {"ok": True}


@app.route("/api/mensaje/revisar", methods=["POST", "OPTIONS"])
def api_mensaje_revisar():
    if request.method == "OPTIONS":
        return "", 204
    if not _api_user():
        return {"error": "auth"}, 401
    return _revisar_captura((request.get_json(silent=True) or {}).get("foto") or "")


@app.get("/opiniones")
@login_required
def opiniones():
    if not is_admin(g.user):
        abort(404)
    load()
    f = request.args.get("f", "")
    ops = store.list_opiniones()
    nuevas = sum(1 for o in ops if not o.get("leida"))
    if f in OP_TIPOS:
        ops = [o for o in ops if o.get("tipo") == f]
    elif f == "nuevas":
        ops = [o for o in ops if not o.get("leida")]
    return render_template("opiniones.html", **ctx("perfil", ops=ops, nuevas=nuevas, f=f, tipos=OP_TIPOS))


@app.post("/opiniones/marcar")
@login_required
def opiniones_marcar():
    if not is_admin(g.user):
        abort(404)
    oid = request.form.get("id", "")
    if request.form.get("accion") == "borrar":
        store.delete_opinion(oid)
    else:
        store.set_opinion(oid, leida=request.form.get("leida") == "1")
    return redirect(url_for("opiniones", f=request.form.get("f", "")))


@app.get("/panel")
@login_required
def panel():
    if not is_admin(g.user):
        abort(404)
    from datetime import datetime, timezone, timedelta

    def ms_dt(ms):
        try:
            return datetime.fromtimestamp(ms / 1000, tz=timezone.utc) if ms else None
        except (TypeError, ValueError, OSError):
            return None

    def iso_dt(s):
        if not s:
            return None
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None

    diag = []
    usage = {}
    try:
        usage = store.usage()
    except Exception as e:
        print("panel usage:", repr(e), flush=True)
        diag.append("usage: " + str(e)[:300])

    users = []
    try:
        from firebase_admin import auth
        for u in auth.list_users().iterate_all():
            md = u.user_metadata
            created = ms_dt(getattr(md, "creation_timestamp", None))
            signed = ms_dt(getattr(md, "last_sign_in_timestamp", None))
            act = iso_dt((usage.get(u.uid) or {}).get("actualizado"))
            last = max([x for x in (signed, act) if x], default=None)
            provs = {p.provider_id for p in (u.provider_data or [])}
            prov = "google" if "google.com" in provs else "apple" if "apple.com" in provs else "correo" if "password" in provs else "otro"
            users.append({
                "uid": u.uid,
                "nombre": u.display_name or "",
                "email": u.email or "",
                "verif": bool(u.email_verified),
                "created": created, "last": last,
                "prov": prov, "plat": (usage.get(u.uid) or {}).get("plat") or "",
            })
    except Exception as e:
        print("panel list_users:", repr(e), flush=True)
        diag.append("list_users: " + str(e)[:300])

    now = datetime.now(timezone.utc)
    d7, d30 = now - timedelta(days=7), now - timedelta(days=30)
    stats = {
        "total": len(users),
        "verif": sum(1 for u in users if u["verif"]),
        "act7": sum(1 for u in users if u["last"] and u["last"] >= d7),
        "act30": sum(1 for u in users if u["last"] and u["last"] >= d30),
        "new7": sum(1 for u in users if u["created"] and u["created"] >= d7),
        "new30": sum(1 for u in users if u["created"] and u["created"] >= d30),
    }
    # Mensajes de problemas sin resolver: esos usuarios suben al principio y se marcan.
    try:
        _msgs = store.list_mensajes(300)
    except Exception:
        _msgs = []
    abiertos = {m.get("uid") for m in _msgs if not m.get("resuelto") and m.get("uid")}
    n_msg = sum(1 for m in _msgs if not m.get("resuelto"))
    for u in users:
        u["msg"] = u["uid"] in abiertos
    users.sort(key=lambda u: (u["msg"], u["last"] or u["created"] or now.replace(year=1)), reverse=True)

    def fmt_dt(dt):
        if not dt:
            return "—"
        days = (now - dt).days
        if days <= 0:
            return t("pa_hoy")
        if days == 1:
            return t("pa_ayer")
        if days < 30:
            return t("pa_hace_d", d=days)
        return dt.strftime("%d/%m/%Y")

    rows = [{"uid": u["uid"], "nombre": u["nombre"], "email": u["email"], "verif": u["verif"],
             "alta": u["created"].strftime("%d/%m/%Y") if u["created"] else "—",
             "ult": fmt_dt(u["last"]), "msg": u["msg"]} for u in users]

    # Altas por mes (últimos 12 meses)
    mes_c = t("meses_c").split("|")
    meses = []
    for k in range(11, -1, -1):
        y, m = divmod(now.year * 12 + now.month - 1 - k, 12)
        meses.append({"key": f"{y}-{m+1:02d}", "lbl": f"{mes_c[m]} {str(y)[2:]}", "n": 0})
    idx = {x["key"]: x for x in meses}
    for u in users:
        if u["created"]:
            x = idx.get(u["created"].strftime("%Y-%m"))
            if x:
                x["n"] += 1
    altas_max = max([x["n"] for x in meses] or [0])

    # Cómo entran (proveedor) y dispositivo
    def breakdown(key, labels):
        c = {}
        for u in users:
            c[u[key]] = c.get(u[key], 0) + 1
        tot = sum(c.values()) or 1
        return [{"lbl": labels.get(k, k), "n": n, "pct": round(n / tot * 100)}
                for k, n in sorted(c.items(), key=lambda kv: -kv[1]) if n]

    prov_bd = breakdown("prov", {"google": "Google", "apple": "Apple", "correo": t("pa_correo"), "otro": t("pa_otro")})
    plat_labels = {"app-ios": t("pa_app_ios"), "app-android": t("pa_app_android"), "app-otro": t("pa_app_otro"),
                   "nav-movil": t("pa_nav_movil"), "nav-pc": t("pa_nav_pc"), "": t("pa_plat_nd")}
    plat_bd = breakdown("plat", plat_labels)

    try:
        n_err = len(store.list_errores(100))
    except Exception:
        n_err = 0

    return render_template("panel.html", **ctx("admin", stats=stats, rows=rows, n_err=n_err, n_msg=n_msg,
                                               meses=meses, altas_max=altas_max, prov_bd=prov_bd, plat_bd=plat_bd,
                                               diag=diag))


@app.get("/panel/u/<uid>")
@login_required
def panel_user(uid):
    if not is_admin(g.user):
        abort(404)
    from datetime import datetime, timezone, date as _date
    from firebase_admin import auth
    try:
        u = auth.get_user(uid)
    except Exception as e:
        print("panel_user:", repr(e), flush=True)
        abort(404)

    prof = store.load_profile(uid)
    S = store.load(uid)

    def ms_dt(ms):
        try:
            return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%d/%m/%Y %H:%M") if ms else "—"
        except (TypeError, ValueError, OSError):
            return "—"

    def ms_date(ms):
        try:
            return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date() if ms else None
        except (TypeError, ValueError, OSError):
            return None

    provs = {p.provider_id for p in (u.provider_data or [])}
    prov = "Google" if "google.com" in provs else "Apple" if "apple.com" in provs else t("pa_correo") if "password" in provs else t("pa_otro")
    plat_labels = {"app-ios": t("pa_app_ios"), "app-android": t("pa_app_android"), "app-otro": t("pa_app_otro"),
                   "nav-movil": t("pa_nav_movil"), "nav-pc": t("pa_nav_pc"), "": t("pa_plat_nd")}

    # País aproximado: PRIMERO por zona horaria (señal real de ubicación) y, solo
    # si no hay, por la región del idioma (poco fiable: mucha gente usa en-US).
    PAISES = {"ES": "España", "GB": "Reino Unido", "US": "EE. UU.", "FR": "Francia", "DE": "Alemania",
              "IT": "Italia", "PT": "Portugal", "BG": "Bulgaria", "MA": "Marruecos", "MX": "México",
              "AR": "Argentina", "CO": "Colombia", "RO": "Rumanía", "NL": "Países Bajos", "BE": "Bélgica",
              "CH": "Suiza", "IE": "Irlanda", "BR": "Brasil", "EC": "Ecuador", "PE": "Perú"}
    TZ_PAIS = {"Europe/Madrid": "España", "Atlantic/Canary": "España", "Africa/Ceuta": "España",
               "Europe/Sofia": "Bulgaria", "Europe/Lisbon": "Portugal", "Atlantic/Azores": "Portugal",
               "Europe/London": "Reino Unido", "Europe/Paris": "Francia", "Europe/Berlin": "Alemania",
               "Europe/Rome": "Italia", "Europe/Amsterdam": "Países Bajos", "Europe/Brussels": "Bélgica",
               "Europe/Zurich": "Suiza", "Europe/Dublin": "Irlanda", "Europe/Bucharest": "Rumanía",
               "Africa/Casablanca": "Marruecos"}
    lang = prof.get("lang") or ""
    tz = prof.get("tz") or ""
    region = ""
    for sep in ("-", "_"):
        if sep in lang:
            region = lang.split(sep)[1][:2].upper()
            break
    if tz:
        pais = TZ_PAIS.get(tz) or (tz.split("/")[-1].replace("_", " ") if "/" in tz else PAISES.get(region) or "—")
    else:
        pais = PAISES.get(region) or "—"

    # Frecuencia de uso a partir de los días de actividad registrados
    hoy = calc.today()
    def _d(s):
        try:
            return _date.fromisoformat(s)
        except (TypeError, ValueError):
            return None
    ds = sorted({x for x in (_d(s) for s in (prof.get("dias") or [])) if x})
    act7 = sum(1 for x in ds if 0 <= (hoy - x).days < 7)
    act30 = sum(1 for x in ds if 0 <= (hoy - x).days < 30)
    alta_d = ms_date(getattr(u.user_metadata, "creation_timestamp", None))
    desde_ini = min([d for d in (alta_d, ds[0] if ds else None) if d], default=None)
    dias_app = (hoy - desde_ini).days if desde_ini else None

    cuenta = {
        "uid": uid, "email": u.email or "—", "nombre": u.display_name or prof.get("nombre") or "—",
        "verif": bool(u.email_verified), "prov": prov,
        "plat": plat_labels.get(prof.get("plat") or "", t("pa_plat_nd")),
        "pais": pais, "tz": tz or "—", "lang": lang or "—",
        "alta": ms_dt(getattr(u.user_metadata, "creation_timestamp", None)),
        "acceso": ms_dt(getattr(u.user_metadata, "last_sign_in_timestamp", None)),
        "desde": desde_ini.strftime("%d/%m/%Y") if desde_ini else "—", "dias_app": dias_app,
    }
    uso = {"act7": act7, "act30": act30, "total_dias": len(ds),
           "n_gastos": len(S.get("gastos", [])), "n_mov": len(S.get("movimientos", [])),
           "n_prest": len(S.get("prestamos", [])),
           "n_pres": len(S.get("presupuestos", [])), "n_inv": len(S.get("inversiones", []))}
    return render_template("panel_user.html", **ctx("admin", cuenta=cuenta, uso=uso))


@app.route("/api/error", methods=["POST", "OPTIONS"])
def api_error():
    if request.method == "OPTIONS":
        return "", 204
    user = _api_user()
    if not user:
        return {"error": "auth"}, 401
    b = request.get_json(silent=True) or {}
    store.log_error({
        "tipo": "client",
        "uid": user.get("uid", ""), "email": user.get("email", ""),
        "msg": str(b.get("msg") or "")[:500],
        "stack": str(b.get("stack") or "")[:2000],
        "donde": str(b.get("donde") or "")[:160],
        "plat": str(b.get("plat") or "")[:120],
        "ua": str(b.get("ua") or request.headers.get("User-Agent", ""))[:300],
    })
    return "", 204


@app.get("/panel/errores")
@login_required
def panel_errores():
    if not is_admin(g.user):
        abort(404)
    from datetime import datetime
    errs = store.list_errores(150)

    def fmt(ts):
        try:
            return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).strftime("%d/%m %H:%M")
        except Exception:
            return str(ts or "")[:16]

    for e in errs:
        e["cuando"] = fmt(e.get("ts"))
    return render_template("panel_errores.html", **ctx("admin", errs=errs))


@app.post("/panel/errores/clear")
@login_required
def panel_errores_clear():
    if not is_admin(g.user):
        abort(404)
    store.clear_errores()
    return redirect(url_for("panel_errores"))


@app.post("/panel/errores/resolver")
@login_required
def panel_errores_resolver():
    if not is_admin(g.user):
        abort(404)
    eid = request.form.get("id", "")
    e = store.get_error(eid)
    if not e:
        return {"error": "no encontrado"}, 404
    nuevo = not e.get("resuelto")
    store.set_error(eid, {"resuelto": nuevo})
    return {"resuelto": nuevo}


@app.get("/panel/mensajes")
@login_required
def panel_mensajes():
    if not is_admin(g.user):
        abort(404)
    from datetime import datetime
    msgs = store.list_mensajes(300)

    def fmt(ts):
        try:
            return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).strftime("%d/%m %H:%M")
        except Exception:
            return str(ts or "")[:16]
    for m in msgs:
        m["cuando"] = fmt(m.get("ts"))
    nuevos = sum(1 for m in msgs if not m.get("resuelto"))
    return render_template("panel_mensajes.html", **ctx("admin", msgs=msgs, nuevos=nuevos))


@app.post("/panel/mensajes/resolver")
@login_required
def panel_mensajes_resolver():
    if not is_admin(g.user):
        abort(404)
    mid = request.form.get("id", "")
    m = store.get_mensaje(mid)
    if not m:
        return {"error": "no encontrado"}, 404
    nuevo = not m.get("resuelto")
    store.set_mensaje(mid, {"resuelto": nuevo})
    return {"resuelto": nuevo}


@app.post("/panel/mensajes/borrar")
@login_required
def panel_mensajes_borrar():
    if not is_admin(g.user):
        abort(404)
    store.delete_mensaje(request.form.get("id", ""))
    return redirect(url_for("panel_mensajes"))


@app.post("/panel/errores/analizar")
@login_required
def panel_errores_analizar():
    if not is_admin(g.user):
        abort(404)
    e = store.get_error(request.form.get("id", ""))
    if not e:
        return {"error": "no encontrado"}, 404
    return {"texto": _analizar_error(e)}


def _analizar_error(e):
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        return "La IA no está disponible ahora mismo."
    sysmsg = ("Eres un ayudante técnico para el desarrollador de 'Personal Balance', una app de finanzas "
              "personales (PWA en JavaScript en el móvil + backend Flask/Python con Firebase/Firestore). "
              "Te paso un error real de la app. Responde en español de España, breve y claro, con tres puntos: "
              "1) qué significa el error, 2) la causa más probable, 3) una sugerencia concreta de por dónde "
              "mirar para arreglarlo. No inventes; si falta información para estar seguro, dilo.")
    txt = (f"Tipo: {e.get('tipo')}\nMensaje: {e.get('msg')}\nDónde: {e.get('donde')}\n"
           f"Plataforma: {e.get('plat')}\nTraza:\n{e.get('stack') or '(sin traza)'}")
    try:
        import httpx
        model = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
        body = {"model": model, "temperature": 0.3, "max_completion_tokens": 900,
                "messages": [{"role": "system", "content": sysmsg}, {"role": "user", "content": txt}]}
        if model.startswith("openai/gpt-oss"):
            body["reasoning_effort"] = "low"
        r = httpx.post("https://api.groq.com/openai/v1/chat/completions", json=body, timeout=60,
                       headers={"Authorization": "Bearer " + key})
        if r.status_code == 429:
            return "La IA está ocupada ahora mismo (límite gratuito). Prueba en un minuto."
        if r.status_code >= 400:
            return "No se pudo analizar (IA): HTTP " + str(r.status_code)
        return (r.json()["choices"][0]["message"].get("content") or "").strip() or "La IA no devolvió respuesta."
    except Exception as ex:
        return "No se pudo analizar: " + str(ex)[:150]


ERR_PANEL_URL = "https://personal-balance-web-778378922815.europe-west1.run.app/panel/errores"


def _push_admin(msg):
    """Envía un push SOLO a los dispositivos del admin (tú)."""
    import push
    from firebase_admin import auth
    priv = push.vapid(store.db)[0]
    sent, cache = 0, {}
    for sb in store.list_subs():
        uid = sb.get("uid")
        if uid not in cache:
            try:
                cache[uid] = is_admin({"email": auth.get_user(uid).email or ""})
            except Exception:
                cache[uid] = False
        if not cache[uid]:
            continue
        try:
            if push.send(sb, msg, priv):
                sent += 1
            else:
                store.delete_sub(sb["_id"])
        except Exception as e:
            print("push admin:", repr(e), flush=True)
    return sent


@app.post("/cron/error-alert")
def cron_error_alert():
    key = os.environ.get("CRON_KEY", "")
    if not key or not secrets.compare_digest(request.headers.get("X-Cron-Key", ""), key):
        abort(403)
    errs = [e for e in store.list_errores(100) if not e.get("avisado")]
    for e in errs:
        store.set_error(e["_id"], {"avisado": True})
    if not errs:
        return {"nuevos": 0}
    first = (errs[0].get("msg") or "(sin mensaje)")[:140]
    sent = _push_admin({"title": f"⚠️ {len(errs)} error(es) en la app", "body": first,
                        "tag": "pb-err", "url": ERR_PANEL_URL})
    return {"nuevos": len(errs), "enviados": sent}


@app.post("/cron/error-digest")
def cron_error_digest():
    key = os.environ.get("CRON_KEY", "")
    if not key or not secrets.compare_digest(request.headers.get("X-Cron-Key", ""), key):
        abort(403)
    from datetime import datetime, timezone, timedelta
    corte = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S")
    errs = [e for e in store.list_errores(150) if (e.get("ts") or "") >= corte]
    analizados = 0
    for e in errs:
        if not e.get("analisis") and analizados < 8:
            store.set_error(e["_id"], {"analisis": _analizar_error(e)})
            analizados += 1
    if not errs and request.args.get("force") != "1":
        return {"hoy": 0}
    cuerpo = f"{len(errs)} error(es) en 24 h." + (f" {analizados} analizados con IA." if analizados else "") + " Ábrelo para verlos."
    sent = _push_admin({"title": "📋 Resumen de errores", "body": cuerpo,
                        "tag": "pb-err-digest", "url": ERR_PANEL_URL})
    return {"hoy": len(errs), "analizados": analizados, "enviados": sent}


@app.get("/privacidad")
def privacidad():
    from datetime import date as _date
    back = request.referrer or url_for("login")
    return render_template("privacidad.html", **ctx(None, show_inv=False,
                           fecha=_date.today().strftime("%d/%m/%Y"), back=back))


@app.get("/healthz")
def healthz():
    return "ok"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), debug=DEV)

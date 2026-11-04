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

APP_VERSION = "web-6"
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
    "w_upd": ["Actualizar", "Refresh", "Обнови"],
})
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
    if request.method == "POST" and not csrf_ok():
        abort(400, "CSRF")


@app.after_request
def set_csrf(resp):
    if not request.cookies.get("pb_csrf") and g.get("csrf_new"):
        resp.set_cookie("pb_csrf", g.csrf_new, samesite="Lax", secure=not DEV, httponly=True, max_age=31536000)
    if request.path.startswith("/api/") and request.headers.get("Origin") in CORS_ORIGINS:
        resp.headers["Access-Control-Allow-Origin"] = request.headers["Origin"]
        resp.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
        resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
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


def ctx(tab, **kw):
    P = g.get("P") or {"nombre": "", "foto": "", "icono": ""}
    user = g.get("user") or {}
    nombre = P.get("nombre") or user.get("name") or ""
    if valid_photo(P.get("foto")):
        av = {"img": P["foto"]}
    else:
        av = {"txt": P.get("icono") or (nombre or user.get("email") or "?").strip()[:1].upper()}
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
                               items=items, mes_tot=tot, mes_pag=pag, mes_tot0=mes_tot0, mes_pag0=mes_pag0, donut=donut, legend=legend, debt=debt))


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
    tm = calc.total_mes(S)
    rows = []
    for gst in S["gastos"]:
        l = gst.get("prestamoId") and calc.loan_by_id(S, gst["prestamoId"])
        st = calc.loan_stats(l) if l else None
        rows.append({**gst, "pct": float(gst.get("importe") or 0) / tm * 100 if tm else 0,
                     "hasta": st["fin"] if st else None})
    return render_template("gastos.html", **ctx("gastos", S=S, rows=rows, tm=tm, cats=t("cats").split("|"),
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
    return render_template("datos.html", **ctx("datos"))


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


@app.get("/inversiones")
@login_required
def inversiones():
    load()
    return render_template("inversiones.html", **ctx("inversiones"))


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
    try:
        out = agent.run(S, body.get("messages") or [], lang, P.get("nombre") or user.get("name", ""),
                        decision=body.get("decision"), save=lambda s: store.save(g.uid, s),
                        loans_cat=TR["cats"][LANGS[lang]["i"]].split("|")[1])
    except Exception as e:  # error de la API de IA
        print("agent:", repr(e), flush=True)
        return {"error": "ai", "detail": f"{type(e).__name__}: {str(e)[:200]}"}, 502
    if out.get("error"):
        return out, 503
    return out


@app.get("/healthz")
def healthz():
    return "ok"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), debug=DEV)

"""Cálculos de Personal Balance (port fiel de la lógica de la app PWA).

Los datos (S) tienen la misma forma que en la app del iPhone:
  {"version":1, "gastos":[...], "prestamos":[...], "inversiones":[...], "watch":[...]}
"""
from __future__ import annotations

import calendar
import math
import random
import string
from datetime import date, timedelta


def r2(v) -> float:
    try:
        v = float(v or 0)
    except (TypeError, ValueError):
        v = 0.0
    # Igual que Math.round(v*100)/100 en JS
    return math.floor(v * 100 + 0.5) / 100


def uid() -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=8))


def today() -> date:
    return date.today()


def iso(d: date) -> str:
    return d.isoformat()


def parse(s: str) -> date:
    y, m, d = (int(x) for x in s.split("-"))
    return date(y, m, d)


def add_months(iso_str: str, k: int, day: int | None = None) -> str:
    d = parse(iso_str)
    y, m = divmod(d.month - 1 + k, 12)
    y += d.year
    m += 1
    last = calendar.monthrange(y, m)[1]
    return date(y, m, min(day or d.day, last)).isoformat()


def seed() -> dict:
    return {"version": 1, "gastos": [], "prestamos": [], "inversiones": [], "watch": [], "movimientos": [], "presupuestos": []}


def normalize(S: dict) -> dict:
    base = seed()
    if isinstance(S, dict):
        base.update(S)
    for k in ("gastos", "prestamos", "inversiones", "watch", "movimientos", "presupuestos", "pagos_pendientes"):
        if not isinstance(base.get(k), list):
            base[k] = []
    for l in base["prestamos"]:
        l.setdefault("cuotas", [])
    return base


def is_paid(c: dict, t: str | None = None) -> bool:
    t = t or iso(today())
    if c.get("pagada") is True:
        return True
    return c.get("pagada") is not False and (c.get("fecha") or "") <= t


def sorted_cuotas(l: dict) -> list:
    return sorted(l.get("cuotas", []), key=lambda c: c.get("fecha") or "")


def loan_stats(l: dict) -> dict:
    t = iso(today())
    cs = sorted_cuotas(l)
    paid = [c for c in cs if is_paid(c, t)]
    pend = [c for c in cs if not is_paid(c, t)]

    def s(a, k):
        return r2(sum(float(c.get(k) or 0) for c in a))

    return {
        "cs": cs, "n": len(cs), "nPaid": len(paid), "nPend": len(pend),
        "total": s(cs, "cuota"), "intereses": s(cs, "intereses"),
        "pagado": s(paid, "cuota"), "pendiente": s(pend, "cuota"),
        "capital": s(pend, "amortizacion"), "intPend": s(pend, "intereses"),
        "amortTotal": s(cs, "amortizacion"),
        "next": pend[0] if pend else None,
        "overdue": [c for c in pend if c.get("fecha", "") < t],
        "fin": cs[-1]["fecha"] if cs else None,
        "inicio": cs[0]["fecha"] if cs else None,
    }


def total_mes(S) -> float:
    return r2(sum(float(g.get("importe") or 0) for g in S["gastos"]))


def loan_by_id(S, lid):
    return next((l for l in S["prestamos"] if l.get("id") == lid), None)


def months_until(fin: str) -> int:
    d, n = parse(fin), today()
    return (d.year - n.year) * 12 + d.month - n.month


# ---------- Gastos del mes ----------
def month_start(off: int) -> date:
    n = today()
    y, m = divmod(n.month - 1 + off, 12)
    return date(n.year + y, m + 1, 1)


def mes_items(S, off: int = 0):
    m0 = month_start(off)
    mk = f"{m0.year}-{m0.month:02d}"
    t = iso(today())
    items = []
    for g in S["gastos"]:
        l = g.get("prestamoId") and loan_by_id(S, g["prestamoId"])
        if l:
            cs = sorted((c for c in l["cuotas"] if (c.get("fecha") or "")[:7] == mk), key=lambda c: c["fecha"])
            for c in cs:
                items.append({
                    "tipo": "cuota", "ref": f"{l['id']}|{c['id']}",
                    "concepto": g.get("concepto", "") + (f" ({c['nota']})" if c.get("nota") else ""),
                    "fecha": c["fecha"], "importe": float(c.get("cuota") or 0),
                    "pagado": is_paid(c, t), "manual": c.get("pagada") is not None,
                    "auto": c["fecha"] <= t,
                })
            continue
        fecha = None
        if g.get("dia"):
            last = calendar.monthrange(m0.year, m0.month)[1]
            fecha = f"{mk}-{min(int(g['dia']), last):02d}"
        ov = (g.get("pagos") or {}).get(mk)
        auto = bool(fecha) and fecha <= t
        items.append({
            "tipo": "gasto", "ref": f"{g['id']}|{mk}", "concepto": g.get("concepto", ""),
            "fecha": fecha, "importe": float(g.get("importe") or 0),
            "pagado": ov if ov is not None else auto, "manual": ov is not None, "auto": auto,
        })
    items.sort(key=lambda i: i["fecha"] or "9")
    return m0, items


def toggle_mes(S, tipo: str, a: str, b: str, on: bool, off: int = 0):
    t = iso(today())
    if tipo == "cuota":
        l = loan_by_id(S, a)
        c = next((x for x in l["cuotas"] if x["id"] == b), None) if l else None
        if not c:
            return
        auto = c["fecha"] <= t
        if on == auto:
            c.pop("pagada", None)
        else:
            c["pagada"] = on
    else:
        g = next((x for x in S["gastos"] if x["id"] == a), None)
        if not g:
            return
        # recalcular "auto" para ese mes
        y, m = (int(x) for x in b.split("-"))
        fecha = None
        if g.get("dia"):
            fecha = f"{b}-{min(int(g['dia']), calendar.monthrange(y, m)[1]):02d}"
        auto = bool(fecha) and fecha <= t
        g.setdefault("pagos", {})
        if on == auto:
            g["pagos"].pop(b, None)
        else:
            g["pagos"][b] = on


def toggle_cuota(S, lid: str, cid: str, on: bool):
    toggle_mes(S, "cuota", lid, cid, on)


def upcoming(S, days: int):
    t = iso(today())
    lim = iso(today() + timedelta(days=days))
    items = []
    linked = {l["id"] for l in S["prestamos"]}
    for l in S["prestamos"]:
        for c in sorted_cuotas(l):
            if not is_paid(c, t) and c["fecha"] <= lim:
                items.append({"fecha": c["fecha"], "nombre": l.get("nombre", ""), "importe": float(c.get("cuota") or 0)})
    n = today()
    for g in S["gastos"]:
        if not g.get("dia") or (g.get("prestamoId") and g["prestamoId"] in linked):
            continue
        for k in range(3):
            f = add_months(iso(date(n.year, n.month, 1)), k, int(g["dia"]))
            if t <= f <= lim:
                items.append({"fecha": f, "nombre": g.get("concepto", ""), "importe": float(g.get("importe") or 0)})
    return sorted(items, key=lambda i: i["fecha"])


# ---------- Préstamos ----------
def build_loan(nombre, entidad, importe, tin, n, inicio):
    P, n = float(importe), int(n)
    i = (float(tin or 0)) / 1200
    day = parse(inicio).day
    q = P * i / (1 - math.pow(1 + i, -n)) if i else P / n
    cuotas, cap = [], P
    for k in range(n):
        inte = r2(cap * i)
        am = r2(q - inte)
        if k == n - 1:
            am = r2(cap)
        cuotas.append({"id": uid(), "fecha": add_months(inicio, k, day), "cuota": r2(am + inte),
                       "amortizacion": am, "intereses": inte, "capitalAntes": r2(cap), "nota": ""})
        cap = r2(cap - am)
    return {"id": uid(), "nombre": nombre, "entidad": entidad, "cuotas": cuotas}, r2(q), day


# ---------- Gráficos (SVG) ----------
def donut_svg(S, money, t, esc):
    tm = total_mes(S)
    items = sorted([g for g in S["gastos"] if float(g.get("importe") or 0) > 0],
                   key=lambda g: -float(g["importe"]))
    R, r, C = 70, 44, 90
    a0 = -math.pi / 2
    svg = ""
    for i, g in enumerate(items):
        imp = float(g["importe"])
        frac = imp / tm if tm else 0
        a1 = a0 + frac * 2 * math.pi
        large = 1 if frac > .5 else 0
        col = f"var(--c{i % 8 + 1})"

        def p(a, rad):
            return C + rad * math.cos(a), C + rad * math.sin(a)

        if frac >= .9999:
            svg += f'<circle cx="{C}" cy="{C}" r="{(R + r) / 2}" fill="none" stroke="{col}" stroke-width="{R - r}"/>'
        else:
            (x1, y1), (x2, y2), (x3, y3), (x4, y4) = p(a0, R), p(a1, R), p(a1, r), p(a0, r)
            svg += (f'<path d="M{x1:.3f} {y1:.3f}A{R} {R} 0 {large} 1 {x2:.3f} {y2:.3f}L{x3:.3f} {y3:.3f}'
                    f'A{r} {r} 0 {large} 0 {x4:.3f} {y4:.3f}Z" fill="{col}" stroke="var(--card)" stroke-width="2">'
                    f'<title>{esc(g.get("concepto", ""))}: {money(imp)}</title></path>')
        a0 = a1
    svg += (f'<text x="{C}" y="{C - 4}" text-anchor="middle" style="font-size:12px;fill:var(--muted)">{t("al_mes")}</text>'
            f'<text x="{C}" y="{C + 14}" text-anchor="middle" style="font-size:15px;font-weight:650;fill:var(--text)">{money(tm)}</text>')
    legend = [{"concepto": g.get("concepto", ""), "importe": float(g["importe"]),
               "pct": float(g["importe"]) / tm * 100 if tm else 0, "color": f"var(--c{i % 8 + 1})"}
              for i, g in enumerate(items)]
    return f'<svg width="180" height="180" viewBox="0 0 180 180" role="img" aria-label="{t("aria_donut")}">{svg}</svg>', legend


def debt_chart(S, money, t, esc, mes_c, loc_k):
    loans = [l for l in S["prestamos"] if l.get("cuotas")]
    if not loans:
        return None
    stats = [loan_stats(l) for l in loans]
    mn = min(s["inicio"] for s in stats)
    mx = max(s["fin"] for s in stats)
    d = parse(mn).replace(day=1)
    end = parse(mx)
    months = []
    while d <= end:
        months.append(d)
        y, m = divmod(d.month, 12)
        d = date(d.year + y, m + 1, 1)
    data = []
    for m in months:
        eom = date(m.year, m.month, calendar.monthrange(m.year, m.month)[1]).isoformat()
        data.append([r2(sum(float(c.get("cuota") or 0) for c in l["cuotas"] if c["fecha"] > eom)) for l in loans])
    top = max([sum(v) for v in data] + [1])
    W, H, pl, pb, pt = 900, 240, 56, 26, 10
    bw = (W - pl - 10) / len(months)
    step = 2000 if top > 8000 else 1000 if top > 4000 else 500
    y_top = math.ceil(top / step) * step

    def y(v):
        return pt + (H - pt - pb) * (1 - v / y_top)

    s = ""
    v = 0
    while v <= y_top:
        s += (f'<line x1="{pl}" x2="{W - 10}" y1="{y(v):.2f}" y2="{y(v):.2f}" stroke="var(--line)"/>'
              f'<text x="{pl - 6}" y="{y(v) + 4:.2f}" text-anchor="end">{loc_k(v / 1000)} k€</text>')
        v += step
    now = today()
    for i, m in enumerate(months):
        acc = 0
        x = pl + i * bw + 1.5
        cur = m.year == now.year and m.month == now.month
        for j, l in enumerate(loans):
            val = data[i][j]
            if val <= 0:
                continue
            s += (f'<rect x="{x:.2f}" width="{max(bw - 3, 1):.2f}" y="{y(acc + val):.2f}" '
                  f'height="{y(acc) - y(acc + val):.2f}" fill="var(--c{j % 8 + 1})"{"" if cur else " opacity=\".75\""}/>')
            acc += val
        if m.month == 1 or i == 0:
            s += f'<text x="{x:.2f}" y="{H - 8}">{mes_c[m.month - 1]} {str(m.year)[2:]}</text>'
        if cur:
            s += (f'<text x="{x + bw / 2:.2f}" y="{pt + 8}" text-anchor="middle" style="fill:var(--text);font-weight:600">{t("hoy")}</text>'
                  f'<line x1="{x + bw / 2:.2f}" x2="{x + bw / 2:.2f}" y1="{pt + 12}" y2="{H - pb}" stroke="var(--text)" stroke-dasharray="3 3" opacity=".5"/>')
    for i, m in enumerate(months):
        tot = r2(sum(data[i]))
        tip = f"{mes_c[m.month - 1]} {m.year} — {t('restante')}: {money(tot)}" + "".join(
            f"\n{esc(l.get('nombre', ''))}: {money(data[i][j])}" for j, l in enumerate(loans))
        s += (f'<rect class="hit" x="{pl + i * bw:.2f}" y="{pt}" width="{bw:.2f}" height="{H - pt - pb}" '
              f'fill="transparent"><title>{tip}</title></rect>')
    svg = f'<svg class="debt-svg" viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="{t("aria_deuda")}">{s}</svg>'
    legend = [{"nombre": l.get("nombre", ""), "color": f"var(--c{j % 8 + 1})"} for j, l in enumerate(loans)]
    return {"svg": svg, "legend": legend}


# ---------- Gastos del día a día y presupuestos ----------
def normalize_extra(S):
    for k in ("movimientos", "presupuestos"):
        if not isinstance(S.get(k), list):
            S[k] = []
    return S


def month_key(off=0):
    m0 = month_start(off)
    return f"{m0.year}-{m0.month:02d}"


def gasto_por_categoria(S, mk):
    """Lo gastado en el mes mk (AAAA-MM) por categoría: gastos fijos (o sus cuotas) + gastos del día a día."""
    out = {}
    for g in S.get("gastos", []):
        cat = (g.get("categoria") or "").strip()
        if not cat:
            continue
        l = g.get("prestamoId") and loan_by_id(S, g["prestamoId"])
        if l:
            v = sum(float(c.get("cuota") or 0) for c in l.get("cuotas", []) if (c.get("fecha") or "")[:7] == mk)
        else:
            v = float(g.get("importe") or 0)
        out[cat.lower()] = out.get(cat.lower(), 0) + v
    for m in S.get("movimientos", []):
        if (m.get("fecha") or "")[:7] == mk:
            cat = (m.get("categoria") or "").strip().lower()
            out[cat] = out.get(cat, 0) + float(m.get("importe") or 0)
    return out


def presupuestos_estado(S, off=0):
    """Lista de presupuestos con lo gastado este mes, % y nivel (ok / warn >=80 % / bad >=100 %)."""
    mk = month_key(off)
    gasto = gasto_por_categoria(S, mk)
    out = []
    for p in S.get("presupuestos", []):
        lim = float(p.get("limite") or 0)
        g = r2(gasto.get((p.get("categoria") or "").strip().lower(), 0))
        pct = g / lim * 100 if lim > 0 else 0
        out.append({**p, "gastado": g, "pct": pct, "queda": r2(lim - g),
                    "nivel": "bad" if pct >= 100 else "warn" if pct >= 80 else "ok"})
    return sorted(out, key=lambda x: -x["pct"])


def movimientos_mes(S, off=0):
    mk = month_key(off)
    return sorted([m for m in S.get("movimientos", []) if (m.get("fecha") or "")[:7] == mk],
                  key=lambda m: (m.get("fecha") or "", m.get("id") or ""), reverse=True)


# ---------- Datos de ejemplo (solo cuentas de prueba) ----------
def is_test_email(email: str) -> bool:
    e = (email or "").lower()
    return "+prueba" in e or "+test" in e


def demo_data() -> dict:
    t0 = today()
    mk = f"{t0.year}-{t0.month:02d}"
    first = date(t0.year, t0.month, 1)
    coche, q1, d1 = build_loan("Préstamo coche", "Banco Demo", 12000, 6.5, 48, add_months(iso(first), -18, 5))
    movil, q2, d2 = build_loan("Móvil a plazos", "Tienda Demo", 900, 0, 12, add_months(iso(first), -4, 20))
    S = seed()
    S["prestamos"] = [coche, movil]
    S["gastos"] = [
        {"id": uid(), "concepto": "Alquiler", "importe": 750, "dia": 1, "categoria": "Vivienda", "prestamoId": ""},
        {"id": uid(), "concepto": "Luz", "importe": 65.4, "dia": 12, "categoria": "Suministros", "prestamoId": ""},
        {"id": uid(), "concepto": "Internet y móvil", "importe": 45, "dia": 8, "categoria": "Suministros", "prestamoId": ""},
        {"id": uid(), "concepto": "Gimnasio", "importe": 39.9, "dia": None, "categoria": "Salud", "prestamoId": ""},
        {"id": uid(), "concepto": "Netflix", "importe": 12.99, "dia": 15, "categoria": "Suscripciones", "prestamoId": ""},
        {"id": uid(), "concepto": coche["nombre"], "importe": q1, "dia": d1, "categoria": "Préstamos", "prestamoId": coche["id"]},
        {"id": uid(), "concepto": movil["nombre"], "importe": q2, "dia": d2, "categoria": "Préstamos", "prestamoId": movil["id"]},
    ]
    dias = [d for d in (1, 2, 3, 5, 6, 8) if d <= t0.day] or [t0.day]
    S["movimientos"] = [
        {"id": uid(), "fecha": f"{mk}-{dias[0]:02d}", "importe": 86.4, "categoria": "Supermercado", "concepto": "Mercadona",
         "lineas": [{"desc": "LECHE ENTERA", "cant": 6, "importe": 6.6}, {"desc": "PAN BARRA", "cant": 2, "importe": 1.7},
                    {"desc": "POLLO ENTERO", "cant": 1, "importe": 7.95}, {"desc": "FRUTA Y VERDURA", "cant": 1, "importe": 18.4},
                    {"desc": "LIMPIEZA HOGAR", "cant": 1, "importe": 22.15}, {"desc": "BEBIDAS", "cant": 1, "importe": 31.1},
                    {"desc": "DESC. PROMO", "cant": 1, "importe": -1.5}],
         "ticket": {"comercio": "MERCADONA S.A.", "direccion": "C/ Ejemplo 1, Las Palmas", "nif": "A00000000", "hora": "18:42",
                    "forma_pago": "Tarjeta", "num_ticket": "0001-001-123"}},
        {"id": uid(), "fecha": f"{mk}-{dias[-1]:02d}", "importe": 42.5, "categoria": "Supermercado", "concepto": "Lidl"},
        {"id": uid(), "fecha": f"{mk}-{dias[min(1, len(dias) - 1)]:02d}", "importe": 24.8, "categoria": "Restaurantes", "concepto": "Cena"},
        {"id": uid(), "fecha": f"{mk}-{dias[min(2, len(dias) - 1)]:02d}", "importe": 55, "categoria": "Transporte", "concepto": "Gasolina"},
    ]
    S["presupuestos"] = [{"id": uid(), "categoria": "Supermercado", "limite": 150},
                         {"id": uid(), "categoria": "Restaurantes", "limite": 100},
                         {"id": uid(), "categoria": "Transporte", "limite": 120}]
    S["inversiones"] = [
        {"id": uid(), "tipo": "cripto", "simbolo": "BTC", "cantidad": 0.02, "precioCompra": 40000, "broker": "Binance", "moneda": "EUR", "precioManual": None},
        {"id": uid(), "tipo": "accion", "simbolo": "AAPL", "cantidad": 5, "precioCompra": 150, "broker": "Demo Broker", "moneda": "USD", "precioManual": 230},
        {"id": uid(), "tipo": "accion", "simbolo": "KO", "cantidad": 10, "precioCompra": 55, "broker": "Demo Broker", "moneda": "USD", "precioManual": 70},
    ]
    S["watch"] = [{"id": uid(), "tipo": "cripto", "simbolo": "ETH"}, {"id": uid(), "tipo": "divisa", "simbolo": "USD"},
                  {"id": uid(), "tipo": "indice", "simbolo": "S&P 500", "proxy": "SPY"}]
    return S


# ---------- Resumen del mes ----------
def month_summary(S, off=0):
    """Totales de un mes: fijos (cuotas incluidas), día a día, por categoría, comparación y presupuestos."""
    m0 = month_start(off)
    mk = f"{m0.year}-{m0.month:02d}"

    def tot(o):
        _, it = mes_items(S, o)
        fij = r2(sum(i["importe"] for i in it))
        dia = r2(sum(float(m.get("importe") or 0) for m in S.get("movimientos", []) if (m.get("fecha") or "").startswith(month_key(o))))
        return fij, dia

    fij, dia = tot(off)
    pfij, pdia = tot(off - 1)
    cats = gasto_por_categoria(S, mk)
    names = {}
    for x in S.get("gastos", []) + S.get("movimientos", []):
        c = (x.get("categoria") or "").strip()
        if c:
            names.setdefault(c.lower(), c)
    top = sorted(((names.get(k, k.capitalize() or "—"), r2(v)) for k, v in cats.items() if v > 0), key=lambda x: -x[1])[:5]
    movs = [m for m in S.get("movimientos", []) if (m.get("fecha") or "").startswith(mk)]
    big = max(movs, key=lambda m: float(m.get("importe") or 0), default=None)
    pres = presupuestos_estado(S, off) if off == 0 else []
    total, ptotal = r2(fij + dia), r2(pfij + pdia)
    return {"mes": mk, "anio": m0.year, "mes_n": m0.month, "fijos": fij, "dia": dia, "total": total,
            "anterior": ptotal, "dif": r2(total - ptotal) if ptotal else None, "n_movs": len(movs),
            "top": top, "mayor": ({"concepto": big.get("concepto") or big.get("categoria"), "importe": float(big.get("importe") or 0)} if big else None),
            "pres_ok": sum(1 for p in pres if p["nivel"] != "bad"), "pres_pasados": [p["categoria"] for p in pres if p["nivel"] == "bad"],
            "n_pres": len(pres)}

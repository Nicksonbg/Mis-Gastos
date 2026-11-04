"""Asistente de IA de Personal Balance (Claude con herramientas).

- Las herramientas de lectura se ejecutan directamente.
- Las de escritura NO se ejecutan hasta que el usuario pulsa "Confirmar":
  el servidor devuelve la acción pendiente y el historial; el navegador lo
  reenvía con la decisión y entonces se aplica y la conversación sigue.
"""
from __future__ import annotations

import json
import os
from datetime import date

import calc
from calc import r2

MODEL = os.environ.get("AGENT_MODEL", "claude-sonnet-5-5")
MAX_STEPS = 8
MAX_HISTORY = 30

READ_TOOLS = [
    {"name": "ver_resumen",
     "description": "Resumen general: total mensual y anual de gastos fijos, pagado y pendiente del mes actual, deuda pendiente de préstamos y fecha del último pago.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "listar_gastos",
     "description": "Lista los gastos mensuales fijos con id, concepto, importe, día de cobro, categoría y préstamo vinculado.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "gastos_del_mes",
     "description": "Gastos de un mes concreto con su fecha de pago y si están pagados. offset 0 = mes actual, -1 = anterior, 1 = siguiente.",
     "input_schema": {"type": "object", "properties": {"offset": {"type": "integer"}}}},
    {"name": "listar_prestamos",
     "description": "Lista los préstamos con id, entidad, cuotas pagadas/pendientes, pagado, pendiente, capital pendiente, intereses, próxima cuota y fecha de fin.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "ver_cuotas",
     "description": "Cuadro de amortización de un préstamo (id, fecha, cuota, amortización, intereses, capital antes, pagada, nota). Opcionalmente filtra por rango de fechas ISO.",
     "input_schema": {"type": "object", "properties": {"prestamo_id": {"type": "string"}, "desde": {"type": "string"}, "hasta": {"type": "string"}},
                      "required": ["prestamo_id"]}},
    {"name": "listar_inversiones",
     "description": "Posiciones de inversión guardadas (símbolo, tipo, cantidad, precio de compra, bróker). No incluye precios en vivo.",
     "input_schema": {"type": "object", "properties": {}}},
]
WRITE_TOOLS = [
    {"name": "anadir_gasto",
     "description": "Añade un gasto mensual fijo.",
     "input_schema": {"type": "object", "properties": {
         "concepto": {"type": "string"}, "importe": {"type": "number", "description": "Euros al mes"},
         "dia": {"type": "integer", "description": "Día de cobro 1-31 (opcional)"},
         "categoria": {"type": "string"}}, "required": ["concepto", "importe"]}},
    {"name": "editar_gasto",
     "description": "Cambia campos de un gasto existente (solo los que se indiquen).",
     "input_schema": {"type": "object", "properties": {
         "id": {"type": "string"}, "concepto": {"type": "string"}, "importe": {"type": "number"},
         "dia": {"type": ["integer", "null"]}, "categoria": {"type": "string"}}, "required": ["id"]}},
    {"name": "borrar_gasto",
     "description": "Borra un gasto mensual.",
     "input_schema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}},
    {"name": "marcar_pago",
     "description": "Marca como pagado o no pagado un gasto en un mes (mes en formato AAAA-MM) o una cuota de préstamo.",
     "input_schema": {"type": "object", "properties": {
         "tipo": {"type": "string", "enum": ["gasto", "cuota"]},
         "gasto_id": {"type": "string"}, "mes": {"type": "string"},
         "prestamo_id": {"type": "string"}, "cuota_id": {"type": "string"},
         "pagado": {"type": "boolean"}}, "required": ["tipo", "pagado"]}},
    {"name": "crear_prestamo",
     "description": "Crea un préstamo con cuota fija (sistema francés) y opcionalmente añade la cuota a los gastos mensuales.",
     "input_schema": {"type": "object", "properties": {
         "nombre": {"type": "string"}, "entidad": {"type": "string"}, "importe": {"type": "number"},
         "tin": {"type": "number", "description": "Interés anual %"}, "n_cuotas": {"type": "integer"},
         "primera_cuota": {"type": "string", "description": "Fecha ISO de la 1ª cuota"},
         "anadir_a_gastos": {"type": "boolean"}}, "required": ["nombre", "importe", "n_cuotas", "primera_cuota"]}},
    {"name": "borrar_prestamo",
     "description": "Borra un préstamo y todas sus cuotas.",
     "input_schema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}},
]
WRITE_NAMES = {t["name"] for t in WRITE_TOOLS}
TOOLS = READ_TOOLS + WRITE_TOOLS

LANG_NAMES = {"es": "español", "en": "English", "bg": "български"}


def system_prompt(lang, nombre):
    return (
        "Eres el asistente de Personal Balance, la app de finanzas personales de "
        f"{nombre or 'el usuario'}. Hoy es {date.today().isoformat()}. "
        f"Responde siempre en {LANG_NAMES.get(lang, 'español')}, breve y claro, con importes en euros. "
        "Usa las herramientas para consultar los datos reales antes de responder; no inventes cifras. "
        "Para cambiar datos usa las herramientas de escritura: la app pedirá confirmación al usuario antes de aplicarlas, "
        "así que llámalas directamente cuando el usuario lo pida (no preguntes «¿quieres que lo haga?» antes), y de una en una. "
        "Si falta un dato imprescindible (por ejemplo el importe), pregúntalo. "
        "Si un nombre no coincide exactamente, busca el gasto o préstamo más parecido con las herramientas de lista. "
        "La sección de inversiones es de solo lectura: no hay herramientas para comprar o vender. "
        "No reveles ids internos al usuario. Formato: texto sencillo; puedes usar **negrita** y listas con guiones."
    )


# ---------- Herramientas ----------
def _money(v):
    return f"{r2(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " €"


def run_read(S, name, inp):
    if name == "ver_resumen":
        tm = calc.total_mes(S)
        _, items = calc.mes_items(S, 0)
        tot = r2(sum(i["importe"] for i in items))
        pag = r2(sum(i["importe"] for i in items if i["pagado"]))
        pend = cap = paid = 0
        fin = None
        for l in S["prestamos"]:
            s = calc.loan_stats(l)
            pend += s["pendiente"]; cap += s["capital"]; paid += s["pagado"]
            if s["fin"] and (not fin or s["fin"] > fin):
                fin = s["fin"]
        return {"total_mensual": tm, "total_anual": r2(tm * 12), "n_gastos": len(S["gastos"]),
                "mes_actual": {"total": tot, "pagado": pag, "pendiente": r2(tot - pag)},
                "prestamos": {"pendiente_de_pagar": r2(pend), "ya_pagado": r2(paid), "capital_pendiente": r2(cap),
                              "ultimo_pago": fin, "n": len(S["prestamos"])}}
    if name == "listar_gastos":
        return [{"id": g["id"], "concepto": g.get("concepto"), "importe": g.get("importe"), "dia": g.get("dia"),
                 "categoria": g.get("categoria"),
                 "prestamo": (calc.loan_by_id(S, g["prestamoId"]) or {}).get("nombre") if g.get("prestamoId") else None}
                for g in S["gastos"]]
    if name == "gastos_del_mes":
        m0, items = calc.mes_items(S, int(inp.get("offset") or 0))
        return {"mes": f"{m0.year}-{m0.month:02d}",
                "items": [{"concepto": i["concepto"], "fecha": i["fecha"], "importe": i["importe"], "pagado": i["pagado"],
                           "tipo": i["tipo"], "ref": i["ref"]} for i in items]}
    if name == "listar_prestamos":
        out = []
        for l in S["prestamos"]:
            s = calc.loan_stats(l)
            out.append({"id": l["id"], "nombre": l.get("nombre"), "entidad": l.get("entidad"),
                        "cuotas": f"{s['nPaid']} de {s['n']} pagadas", "pagado": s["pagado"], "pendiente": s["pendiente"],
                        "capital_pendiente": s["capital"], "intereses_total": s["intereses"], "intereses_pendientes": s["intPend"],
                        "proxima_cuota": ({"fecha": s["next"]["fecha"], "importe": s["next"]["cuota"]} if s["next"] else None),
                        "cuotas_vencidas_sin_pagar": len(s["overdue"]), "fin": s["fin"]})
        return out
    if name == "ver_cuotas":
        l = calc.loan_by_id(S, inp.get("prestamo_id"))
        if not l:
            return {"error": "Préstamo no encontrado"}
        d, h = inp.get("desde") or "0000", inp.get("hasta") or "9999"
        return [{"id": c["id"], "fecha": c["fecha"], "cuota": c.get("cuota"), "amortizacion": c.get("amortizacion"),
                 "intereses": c.get("intereses"), "capital_antes": c.get("capitalAntes"), "pagada": calc.is_paid(c),
                 "nota": c.get("nota") or ""} for c in calc.sorted_cuotas(l) if d <= c["fecha"] <= h][:120]
    if name == "listar_inversiones":
        return [{"simbolo": i.get("simbolo"), "tipo": i.get("tipo"), "cantidad": i.get("cantidad"),
                 "precio_compra_eur": i.get("precioCompra"), "broker": i.get("broker")} for i in S.get("inversiones", [])]
    return {"error": "herramienta desconocida"}


def describe(S, name, inp):
    """Texto de la acción para el botón de confirmar."""
    g = lambda gid: next((x for x in S["gastos"] if x["id"] == gid), None)  # noqa: E731
    if name == "anadir_gasto":
        s = f"Añadir gasto «{inp.get('concepto')}» de {_money(inp.get('importe'))} al mes"
        if inp.get("dia"):
            s += f", día {inp['dia']}"
        if inp.get("categoria"):
            s += f" ({inp['categoria']})"
        return s
    if name == "editar_gasto":
        x = g(inp.get("id"))
        cambios = ", ".join(f"{k}: {_money(v) if k == 'importe' else v}" for k, v in inp.items() if k != "id")
        return f"Editar «{(x or {}).get('concepto', '?')}» → {cambios}"
    if name == "borrar_gasto":
        return f"Borrar el gasto «{(g(inp.get('id')) or {}).get('concepto', '?')}»"
    if name == "marcar_pago":
        est = "pagado" if inp.get("pagado") else "no pagado"
        if inp.get("tipo") == "cuota":
            l = calc.loan_by_id(S, inp.get("prestamo_id")) or {}
            c = next((c for c in l.get("cuotas", []) if c["id"] == inp.get("cuota_id")), {})
            return f"Marcar como {est} la cuota de «{l.get('nombre', '?')}» del {c.get('fecha', '?')}"
        return f"Marcar como {est} «{(g(inp.get('gasto_id')) or {}).get('concepto', '?')}» en {inp.get('mes', '?')}"
    if name == "crear_prestamo":
        return (f"Crear préstamo «{inp.get('nombre')}»: {_money(inp.get('importe'))}, {inp.get('tin') or 0} % TIN, "
                f"{inp.get('n_cuotas')} cuotas desde el {inp.get('primera_cuota')}"
                + (" y añadir la cuota a los gastos" if inp.get("anadir_a_gastos", True) else ""))
    if name == "borrar_prestamo":
        return f"Borrar el préstamo «{(calc.loan_by_id(S, inp.get('id')) or {}).get('nombre', '?')}» y todas sus cuotas"
    return name


def run_write(S, name, inp, cats_loans="Préstamos"):
    if name == "anadir_gasto":
        dia = inp.get("dia")
        S["gastos"].append({"id": calc.uid(), "concepto": str(inp.get("concepto", "")).strip(), "importe": r2(inp.get("importe")),
                            "dia": max(1, min(31, int(dia))) if dia else None, "categoria": inp.get("categoria") or "",
                            "prestamoId": ""})
        return {"ok": True}
    if name == "editar_gasto":
        x = next((x for x in S["gastos"] if x["id"] == inp.get("id")), None)
        if not x:
            return {"error": "Gasto no encontrado"}
        for k in ("concepto", "categoria"):
            if k in inp:
                x[k] = str(inp[k]).strip()
        if "importe" in inp:
            x["importe"] = r2(inp["importe"])
        if "dia" in inp:
            x["dia"] = max(1, min(31, int(inp["dia"]))) if inp["dia"] else None
        return {"ok": True}
    if name == "borrar_gasto":
        n = len(S["gastos"])
        S["gastos"] = [x for x in S["gastos"] if x["id"] != inp.get("id")]
        return {"ok": len(S["gastos"]) < n}
    if name == "marcar_pago":
        if inp.get("tipo") == "cuota":
            calc.toggle_mes(S, "cuota", inp.get("prestamo_id", ""), inp.get("cuota_id", ""), bool(inp.get("pagado")))
        else:
            calc.toggle_mes(S, "gasto", inp.get("gasto_id", ""), inp.get("mes") or date.today().strftime("%Y-%m"), bool(inp.get("pagado")))
        return {"ok": True}
    if name == "crear_prestamo":
        l, q, day = calc.build_loan(inp.get("nombre", ""), inp.get("entidad", ""), inp.get("importe", 0),
                                    inp.get("tin", 0), int(inp.get("n_cuotas", 1)), inp.get("primera_cuota"))
        S["prestamos"].append(l)
        if inp.get("anadir_a_gastos", True):
            S["gastos"].append({"id": calc.uid(), "concepto": l["nombre"], "importe": q, "categoria": cats_loans,
                                "dia": day, "prestamoId": l["id"]})
        return {"ok": True, "cuota_mensual": q, "fin": l["cuotas"][-1]["fecha"]}
    if name == "borrar_prestamo":
        lid = inp.get("id")
        S["prestamos"] = [x for x in S["prestamos"] if x["id"] != lid]
        for x in S["gastos"]:
            if x.get("prestamoId") == lid:
                x["prestamoId"] = ""
        return {"ok": True}
    return {"error": "herramienta desconocida"}


# ---------- Bucle del agente ----------
def _client():
    if os.environ.get("PB_DEV") == "1" and os.environ.get("PB_FAKE_AI") == "1":
        from fake_ai import FakeClient  # solo para pruebas locales
        return FakeClient()
    import anthropic
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    return anthropic.Anthropic(api_key=key)


def _clean_history(messages):
    """Solo texto/tool_use/tool_result con la forma esperada, y recorta el historial."""
    ok = []
    for m in messages[-MAX_HISTORY:]:
        if m.get("role") not in ("user", "assistant"):
            continue
        c = m.get("content")
        if isinstance(c, str):
            ok.append({"role": m["role"], "content": c[:4000]})
        elif isinstance(c, list):
            blocks = [b for b in c if isinstance(b, dict) and b.get("type") in ("text", "tool_use", "tool_result")]
            if blocks:
                ok.append({"role": m["role"], "content": blocks})
    # El historial debe empezar por un mensaje del usuario con texto
    while ok and not (ok[0]["role"] == "user" and isinstance(ok[0]["content"], str)):
        ok.pop(0)
    return ok


def _blocks_to_dicts(content):
    out = []
    for b in content:
        if b.type == "text":
            out.append({"type": "text", "text": b.text})
        elif b.type == "tool_use":
            out.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
    return out


def run(S, messages, lang, nombre, decision=None, client=None, save=None, loans_cat="Préstamos"):
    """Ejecuta el agente. Devuelve dict con messages, reply, pending, changed."""
    client = client or _client()
    if client is None:
        return {"error": "no_key"}
    messages = _clean_history(messages)
    changed = False

    # Respuesta a una acción pendiente
    if decision:
        last = messages[-1] if messages else None
        uses = [b for b in (last or {}).get("content", []) if isinstance(b, dict) and b.get("type") == "tool_use"] \
            if last and last["role"] == "assistant" else []
        results = []
        for b in uses:
            if b["name"] in WRITE_NAMES:
                if decision.get("approve") and b["id"] == decision.get("id"):
                    res = run_write(S, b["name"], b["input"], loans_cat)
                    changed = changed or bool(res.get("ok"))
                    results.append({"type": "tool_result", "tool_use_id": b["id"], "content": json.dumps(res, ensure_ascii=False)})
                elif b["id"] == decision.get("id"):
                    results.append({"type": "tool_result", "tool_use_id": b["id"],
                                    "content": "El usuario ha cancelado esta acción. No la vuelvas a proponer salvo que lo pida."})
                else:
                    results.append({"type": "tool_result", "tool_use_id": b["id"],
                                    "content": "No se ha ejecutado: las acciones se confirman de una en una. Si sigue siendo necesaria, vuelve a llamarla."})
            else:
                results.append({"type": "tool_result", "tool_use_id": b["id"],
                                "content": json.dumps(run_read(S, b["name"], b["input"]), ensure_ascii=False, default=str)})
        if changed and save:
            save(S)
        messages.append({"role": "user", "content": results})

    system = system_prompt(lang, nombre)
    for _ in range(MAX_STEPS):
        resp = client.messages.create(model=MODEL, max_tokens=1500, system=system, tools=TOOLS, messages=messages)
        content = _blocks_to_dicts(resp.content)
        messages.append({"role": "assistant", "content": content})
        uses = [b for b in content if b["type"] == "tool_use"]
        text = "\n".join(b["text"] for b in content if b["type"] == "text").strip()
        if resp.stop_reason != "tool_use" or not uses:
            return {"messages": messages, "reply": text, "pending": None, "changed": changed}
        writes = [b for b in uses if b["name"] in WRITE_NAMES]
        if writes:
            w = writes[0]
            return {"messages": messages, "reply": text, "changed": changed,
                    "pending": {"id": w["id"], "summary": describe(S, w["name"], w["input"])}}
        results = [{"type": "tool_result", "tool_use_id": b["id"],
                    "content": json.dumps(run_read(S, b["name"], b["input"]), ensure_ascii=False, default=str)} for b in uses]
        messages.append({"role": "user", "content": results})
    return {"messages": messages, "reply": "…", "pending": None, "changed": changed}

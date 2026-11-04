"""Lectura de tickets y facturas con IA (Groq, modelo de visión del plan gratuito).

Devuelve los datos para RELLENAR el formulario; el usuario los revisa y guarda.
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
from datetime import date

import calc

VISION_MODEL = os.environ.get("GROQ_VISION_MODEL", "qwen/qwen3.8-27b")
URL = "https://api.groq.com/openai/v1/chat/completions"


class ScanError(Exception):
    pass


def prepare_image(raw: bytes) -> str:
    """Endereza, reduce a 1600 px y comprime en JPEG. Devuelve data URL."""
    from PIL import Image, ImageOps
    im = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
    im.thumbnail((1600, 1600))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def prompt(cats, lang):
    idioma = {"es": "español", "en": "English", "bg": "български"}.get(lang, "español")
    return (
        "Lee este ticket de compra o factura y devuelve SOLO un objeto JSON con estas claves:\n"
        '{"comercio": str, "fecha": "AAAA-MM-DD" o null, "total": número (importe final pagado, con impuestos), '
        '"moneda": código ISO (EUR por defecto), "categoria": una de ' + json.dumps(cats, ensure_ascii=False) + ", "
        '"concepto": descripción corta (máx. 40 caracteres), '
        '"lineas": [{"desc": str, "cant": número, "importe": número}], "hora": "HH:MM" o null, '
        '"direccion": str o null, "nif": str o null, "forma_pago": str o null (p. ej. Tarjeta, Efectivo), '
        '"num_ticket": str o null, "legible": true/false}\n'
        "Reglas: en \"lineas\" pon TODAS las líneas de productos o servicios del ticket, en el mismo orden, con el texto tal cual, "
        "la cantidad (1 si no aparece) y el importe de la línea; los descuentos y promociones van como líneas con importe negativo; "
        "no incluyas como líneas el subtotal, el IVA, el total, la forma de pago ni el cambio. "
        "Usa punto como separador decimal en los números; el total es el importe TOTAL/A PAGAR, no el subtotal "
        "ni la base imponible; si hay descuentos, el total ya los incluye; no inventes datos: si algo no se lee pon null. "
        f"Escribe comercio y concepto tal como aparecen; la categoría en {idioma}. Si la imagen no es un ticket o factura, "
        'devuelve {"legible": false}.'
    )


def _num(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[^\d,.\-]", "", str(v))
    if s.count(",") and s.count("."):
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def read_receipt(data_url: str, cats, lang="es", key=None, post=None):
    key = key or os.environ.get("GROQ_API_KEY")
    if not key:
        raise ScanError("no_key")
    msgs = [{"role": "user", "content": [{"type": "text", "text": prompt(cats, lang)},
                                         {"type": "image_url", "image_url": {"url": data_url}}]}]
    # 1º: modo JSON sin razonamiento visible (Groq exige reasoning_format parsed/hidden con JSON).
    # 2º (si Groq rechaza esos parámetros): petición simple y se extrae el JSON del texto.
    attempts = [
        {"response_format": {"type": "json_object"}, "reasoning_format": "hidden", "reasoning_effort": "none"},
        {},
    ]
    if post is None:
        import httpx
        post = httpx.post
    last = ""
    for extra in attempts:
        body = {"model": VISION_MODEL, "temperature": 0, "max_completion_tokens": 4000, "messages": msgs, **extra}
        r = post(URL, json=body, timeout=90, headers={"Authorization": f"Bearer {key}"})
        if r.status_code == 429:
            raise ScanError("busy")
        if r.status_code >= 400:
            last = f"Groq {r.status_code}: {r.text[:300]}"
            print("scan intento fallido:", last, flush=True)
            if r.status_code in (400, 422):
                continue
            raise ScanError(last)
        break
    else:
        raise ScanError(last)
    txt = r.json()["choices"][0]["message"].get("content") or "{}"
    txt = re.sub(r"<think>.*?</think>", "", txt, flags=re.S)
    m = re.search(r"\{.*\}", txt, re.S)
    try:
        d = json.loads(m.group(0) if m else txt)
    except ValueError:
        raise ScanError("unreadable")
    return clean(d, cats)


def clean(d, cats):
    if not isinstance(d, dict) or d.get("legible") is False:
        raise ScanError("unreadable")
    total = _num(d.get("total"))
    if total is None or total <= 0:
        raise ScanError("unreadable")
    fecha = d.get("fecha")
    try:
        f = date.fromisoformat(str(fecha)[:10])
        fecha = f.isoformat() if f <= date.today() and f.year >= date.today().year - 2 else None
    except (TypeError, ValueError):
        fecha = None
    cat = str(d.get("categoria") or "").strip()
    low = {c.lower(): c for c in cats}
    cat = low.get(cat.lower(), cats[-1])
    lineas = []
    for li in (d.get("lineas") or [])[:120]:
        if isinstance(li, dict):
            v = _num(li.get("importe"))
            if v is not None:
                q = _num(li.get("cant"))
                lineas.append({"desc": str(li.get("desc") or "")[:60], "cant": q if q and q != 1 else 1, "importe": calc.r2(v)})
    suma = calc.r2(sum(x["importe"] for x in lineas))
    comercio = str(d.get("comercio") or "").strip()[:60]
    concepto = str(d.get("concepto") or comercio).strip()[:60] or comercio
    moneda = str(d.get("moneda") or "EUR").upper()[:3]
    avisos = []
    if lineas and abs(suma - total) > 0.02:
        avisos.append("suma")
    if not fecha:
        avisos.append("fecha")
    if moneda != "EUR":
        avisos.append("moneda")
    txt = lambda k, n=60: (str(d.get(k)).strip()[:n] if d.get(k) not in (None, "", "null") else "")  # noqa: E731
    hora = txt("hora", 5)
    if hora and not re.match(r"^\d{1,2}:\d{2}$", hora):
        hora = ""
    return {"importe": calc.r2(total), "fecha": fecha or date.today().isoformat(), "categoria": cat,
            "concepto": concepto, "comercio": comercio, "moneda": moneda, "lineas": lineas, "suma_lineas": suma,
            "hora": hora, "direccion": txt("direccion", 80), "nif": txt("nif", 20), "forma_pago": txt("forma_pago", 30),
            "num_ticket": txt("num_ticket", 30), "avisos": avisos}

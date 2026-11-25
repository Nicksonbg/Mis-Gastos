"""Lectura y escritura de los datos del usuario.

Usa exactamente los mismos documentos de Firestore que la app del iPhone:
  users/{uid}/data/estado  -> {json: "<S en texto>", actualizado: "<ISO>"}
  users/{uid}/data/perfil  -> {nombre, foto, icono, actualizado}
Al guardar se escribe "actualizado" con la hora actual, así el iPhone
detecta el cambio y se sincroniza solo.

Con PB_DEV=1 se usa un archivo JSON local (para probar sin Firebase).
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from calc import normalize, seed

DEV = os.environ.get("PB_DEV") == "1"


def now_iso() -> str:
    d = datetime.now(timezone.utc)
    return d.strftime("%Y-%m-%dT%H:%M:%S.") + f"{d.microsecond // 1000:03d}Z"


# Campos del perfil y su valor por defecto. ÚNICA fuente de verdad: tanto lo que
# se guarda (clean_profile) como lo que se lee (load_profile en ambos almacenes)
# se limitan a estas claves, para que no puedan volver a desincronizarse.
PROFILE_FIELDS = {"nombre": "", "foto": "", "icono": "", "plat": "", "dias": [], "tz": "", "lang": ""}


def profile_defaults() -> dict:
    """Perfil vacío con los campos por defecto (copia nueva de las listas)."""
    return {k: (list(v) if isinstance(v, list) else v) for k, v in PROFILE_FIELDS.items()}


def read_profile(raw) -> dict:
    """Lee un perfil guardado quedándose solo con los campos conocidos (PROFILE_FIELDS)."""
    p = profile_defaults()
    if isinstance(raw, dict):
        p.update({k: v for k, v in raw.items() if k in PROFILE_FIELDS})
    return p


def clean_profile(P: dict) -> dict:
    """Saneado del perfil antes de guardar: nombre e icono recortados; la foto SOLO si
    es una imagen subida (data URL de imagen < 950 KB, sin SVG), para no superar el
    límite de 1 MB por documento de Firestore. No se aceptan enlaces externos como foto.
    Solo emite claves de PROFILE_FIELDS (ver arriba)."""
    P = P if isinstance(P, dict) else {}
    foto = P.get("foto", "")
    if not (isinstance(foto, str) and foto.startswith("data:image/")
            and not foto.startswith("data:image/svg") and len(foto) <= 950_000):
        foto = ""
    out = {"nombre": str(P.get("nombre", ""))[:80], "foto": foto, "icono": str(P.get("icono", ""))[:8]}
    if P.get("plat") in ("app-ios", "app-android", "app-otro", "nav-movil", "nav-pc"):
        out["plat"] = P["plat"]
    # Métricas de uso (no económicas): días de actividad, zona horaria e idioma.
    dias = P.get("dias")
    if isinstance(dias, list):
        ds = sorted({d for d in dias if isinstance(d, str) and len(d) == 10 and d[4] == "-" and d[7] == "-"})
        if ds:
            out["dias"] = ds[-120:]
    if isinstance(P.get("tz"), str) and P.get("tz"):
        out["tz"] = P["tz"][:64]
    if isinstance(P.get("lang"), str) and P.get("lang"):
        out["lang"] = P["lang"][:20]
    # Red de seguridad: nunca emitir una clave que load_profile no vaya a leer.
    return {k: v for k, v in out.items() if k in PROFILE_FIELDS}


class FirestoreStore:
    def __init__(self):
        import firebase_admin
        from firebase_admin import firestore
        if not firebase_admin._apps:
            firebase_admin.initialize_app(options={"projectId": os.environ.get("GOOGLE_CLOUD_PROJECT", "personal-balance-dccca")})
        self.db = firestore.client()

    def _ref(self, uid, doc):
        return self.db.collection("users").document(uid).collection("data").document(doc)

    def load(self, uid):
        snap = self._ref(uid, "estado").get()
        if snap.exists:
            d = snap.to_dict() or {}
            try:
                return normalize(json.loads(d.get("json") or "{}"))
            except ValueError:
                pass
        return seed()

    def save(self, uid, S):
        S = normalize(S)  # saneado antes de guardar (recorta textos, acota listas, números finitos)
        self._ref(uid, "estado").set({"json": json.dumps(S, ensure_ascii=False, separators=(",", ":")),
                                      "actualizado": now_iso()})

    def load_profile(self, uid):
        snap = self._ref(uid, "perfil").get()
        return read_profile(snap.to_dict() if snap.exists else None)

    def save_profile(self, uid, P):
        self._ref(uid, "perfil").set(clean_profile(P) | {"actualizado": now_iso()})

    def delete_user_data(self, uid):
        for d in ("estado", "perfil", "ibkr"):
            try:
                self._ref(uid, d).delete()
            except Exception:
                pass


    def ia_quota(self, uid, limit):
        """Suma un uso de IA de hoy y dice si aún está dentro del límite.
        Va en la colección "ia_uso", que los clientes no pueden escribir (solo el servidor)."""
        from google.cloud import firestore as gfs
        ref = self.db.collection("ia_uso").document(uid)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        @gfs.transactional
        def tx(t):
            snap = ref.get(transaction=t)
            d = snap.to_dict() if snap.exists else {}
            n = d.get("n", 0) if d.get("fecha") == today else 0
            if n >= limit:
                return False, n
            t.set(ref, {"fecha": today, "n": n + 1, "total": d.get("total", 0) + 1})
            return True, n + 1
        return tx(self.db.transaction())


    # ---- Suscripciones push (colección solo del servidor) ----
    def save_sub(self, sid, data):
        self.db.collection("push_subs").document(sid).set(data)

    def delete_sub(self, sid):
        self.db.collection("push_subs").document(sid).delete()

    def get_sub(self, sid):
        d = self.db.collection("push_subs").document(sid).get()
        return d.to_dict() if d.exists else None

    def list_subs(self):
        return [d.to_dict() | {"_id": d.id} for d in self.db.collection("push_subs").stream()]

    # ---- Tokens del atajo de pagos (colección solo del servidor) ----
    def token_for(self, uid):
        d = self.db.collection("pago_tokens_uid").document(uid).get()
        return (d.to_dict() or {}).get("token") if d.exists else None

    def set_token(self, uid, token):
        old = self.token_for(uid)
        if old:
            self.db.collection("pago_tokens").document(old).delete()
        if token:
            self.db.collection("pago_tokens").document(token).set({"uid": uid})
            self.db.collection("pago_tokens_uid").document(uid).set({"token": token})
        else:
            self.db.collection("pago_tokens_uid").document(uid).delete()

    def uid_for_token(self, token):
        d = self.db.collection("pago_tokens").document(token).get()
        return (d.to_dict() or {}).get("uid") if d.exists else None

    def get_alert_state(self, uid):
        d = self.db.collection("budget_alerts").document(uid).get()
        return d.to_dict() if d.exists else {}

    def set_alert_state(self, uid, data):
        self.db.collection("budget_alerts").document(uid).set(data)

    # ---- Opiniones de los usuarios (colección solo del servidor) ----
    def add_opinion(self, uid, data, limit=10):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        ref = self.db.collection("opinion_uso").document(uid)
        snap = ref.get()
        d = snap.to_dict() if snap.exists else {}
        n = d.get("n", 0) if d.get("fecha") == today else 0
        if n >= limit:
            return False
        ref.set({"fecha": today, "n": n + 1})
        self.db.collection("opiniones").add(data)
        return True

    def list_opiniones(self, limit=300):
        from google.cloud import firestore as gfs
        q = self.db.collection("opiniones").order_by("fecha", direction=gfs.Query.DESCENDING).limit(limit)
        return [d.to_dict() | {"_id": d.id} for d in q.stream()]

    def set_opinion(self, oid, **fields):
        self.db.collection("opiniones").document(oid).update(fields)

    def delete_opinion(self, oid):
        self.db.collection("opiniones").document(oid).delete()

    def usage(self):
        """{uid: {'actualizado': ISO|None, 'plat': str}} con la última actividad y el dispositivo de cada usuario."""
        out = {}
        for d in self.db.collection_group("data").stream():
            uid = d.reference.parent.parent.id
            rec = out.setdefault(uid, {})
            doc = d.to_dict() or {}
            if d.id == "estado":
                rec["actualizado"] = doc.get("actualizado")
            elif d.id == "perfil":
                rec["plat"] = doc.get("plat") or ""
        return out

    def log_error(self, data):
        try:
            d = dict(data)
            d["ts"] = now_iso()
            self.db.collection("errores").add(d)
        except Exception as e:
            print("log_error:", repr(e), flush=True)

    def list_errores(self, limit=150):
        from google.cloud import firestore as gfs
        q = self.db.collection("errores").order_by("ts", direction=gfs.Query.DESCENDING).limit(limit)
        return [d.to_dict() | {"_id": d.id} for d in q.stream()]

    def clear_errores(self, limit=500):
        n = 0
        for d in self.db.collection("errores").limit(limit).stream():
            d.reference.delete()
            n += 1
        return n

    def get_error(self, eid):
        d = self.db.collection("errores").document(eid).get()
        return (d.to_dict() | {"_id": d.id}) if d.exists else None

    def set_error(self, eid, fields):
        try:
            self.db.collection("errores").document(eid).update(fields)
        except Exception as e:
            print("set_error:", repr(e), flush=True)


class LocalStore:
    """Solo para desarrollo: guarda en un archivo JSON."""

    def __init__(self, path=None):
        self.path = path or os.environ.get("PB_DEV_FILE", "dev-data.json")

    def _all(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def _write(self, d):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)

    def load(self, uid):
        return normalize(self._all().get(uid, {}).get("estado") or {})

    def save(self, uid, S):
        d = self._all()
        d.setdefault(uid, {})["estado"] = normalize(S)
        self._write(d)

    def load_profile(self, uid):
        return read_profile(self._all().get(uid, {}).get("perfil"))

    def save_profile(self, uid, P):
        d = self._all()
        d.setdefault(uid, {})["perfil"] = clean_profile(P)
        self._write(d)

    _uso = {}
    db = None
    _subs = {}

    def save_sub(self, sid, data):
        self._subs[sid] = data

    def delete_sub(self, sid):
        self._subs.pop(sid, None)

    def get_sub(self, sid):
        return self._subs.get(sid)

    def list_subs(self):
        return [v | {"_id": k} for k, v in self._subs.items()]

    _alerts = {}
    _tok = {}

    def token_for(self, uid):
        return next((k for k, v in self._tok.items() if v == uid), None)

    def set_token(self, uid, token):
        for k in [k for k, v in self._tok.items() if v == uid]:
            self._tok.pop(k)
        if token:
            self._tok[token] = uid

    def uid_for_token(self, token):
        return self._tok.get(token)

    def get_alert_state(self, uid):
        return self._alerts.get(uid, {})

    def set_alert_state(self, uid, data):
        self._alerts[uid] = data

    _ops = {}
    _ops_n = {}

    def add_opinion(self, uid, data, limit=10):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        f, n = self._ops_n.get(uid, (today, 0))
        n = n if f == today else 0
        if n >= limit:
            return False
        self._ops_n[uid] = (today, n + 1)
        self._ops[str(len(self._ops) + 1)] = dict(data)
        return True

    def list_opiniones(self, limit=300):
        return sorted([v | {"_id": k} for k, v in self._ops.items()], key=lambda x: x.get("fecha", ""), reverse=True)[:limit]

    def set_opinion(self, oid, **fields):
        if oid in self._ops:
            self._ops[oid].update(fields)

    def delete_opinion(self, oid):
        self._ops.pop(oid, None)

    def ia_quota(self, uid, limit):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        f, n = self._uso.get(uid, (today, 0))
        n = n if f == today else 0
        if n >= limit:
            return False, n
        self._uso[uid] = (today, n + 1)
        return True, n + 1

    def delete_user_data(self, uid):
        d = self._all()
        d.pop(uid, None)
        self._write(d)

    def usage(self):
        return {uid: {"actualizado": (v.get("estado") or {}).get("_actualizado"),
                      "plat": (v.get("perfil") or {}).get("plat", "")}
                for uid, v in self._all().items()}

    def log_error(self, data):
        errs = self.list_errores(999)
        rec = dict(data)
        rec["ts"] = now_iso()
        rec["_id"] = str(len(errs))
        errs.insert(0, rec)
        json.dump(errs[:500], open("dev-errores.json", "w"))

    def list_errores(self, limit=150):
        try:
            return json.load(open("dev-errores.json"))[:limit]
        except Exception:
            return []

    def clear_errores(self, limit=500):
        n = len(self.list_errores(999))
        json.dump([], open("dev-errores.json", "w"))
        return n

    def get_error(self, eid):
        for e in self.list_errores(999):
            if e.get("_id") == eid:
                return e
        return None

    def set_error(self, eid, fields):
        errs = self.list_errores(999)
        for e in errs:
            if e.get("_id") == eid:
                e.update(fields)
        json.dump(errs, open("dev-errores.json", "w"))


store = LocalStore() if DEV else FirestoreStore()

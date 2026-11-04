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
        self._ref(uid, "estado").set({"json": json.dumps(S, ensure_ascii=False, separators=(",", ":")),
                                      "actualizado": now_iso()})

    def load_profile(self, uid):
        snap = self._ref(uid, "perfil").get()
        p = {"nombre": "", "foto": "", "icono": ""}
        if snap.exists:
            p.update({k: v for k, v in (snap.to_dict() or {}).items() if k in p})
        return p

    def save_profile(self, uid, P):
        self._ref(uid, "perfil").set({"nombre": P.get("nombre", ""), "foto": P.get("foto", ""),
                                      "icono": P.get("icono", ""), "actualizado": now_iso()})

    def delete_user_data(self, uid):
        for d in ("estado", "perfil", "ibkr"):
            try:
                self._ref(uid, d).delete()
            except Exception:
                pass


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
        d.setdefault(uid, {})["estado"] = S
        self._write(d)

    def load_profile(self, uid):
        p = {"nombre": "", "foto": "", "icono": ""}
        p.update(self._all().get(uid, {}).get("perfil") or {})
        return p

    def save_profile(self, uid, P):
        d = self._all()
        d.setdefault(uid, {})["perfil"] = P
        self._write(d)

    def delete_user_data(self, uid):
        d = self._all()
        d.pop(uid, None)
        self._write(d)


store = LocalStore() if DEV else FirestoreStore()

"""IA simulada para probar el asistente sin clave (solo con PB_DEV=1 y PB_FAKE_AI=1)."""
from types import SimpleNamespace as NS
import json


class _Msgs:
    def create(self, model, max_tokens, system, tools, messages):
        last = messages[-1]
        first_user = next(m["content"] for m in reversed(messages) if m["role"] == "user" and isinstance(m["content"], str))
        if last["role"] == "user" and isinstance(last["content"], list):  # tool_result
            res = last["content"][0]["content"]
            if "Netflix" in first_user:
                txt = "Hecho: he añadido **Netflix** (12,99 €, día 5)." if '"ok": true' in res else "Vale, no lo añado."
            else:
                d = json.loads(res)
                txt = f"Pagas **{d['total_mensual']:.2f} €** al mes en gastos fijos.\n- Pendiente este mes: {d['mes_actual']['pendiente']:.2f} €\n- Deuda de préstamos: {d['prestamos']['pendiente_de_pagar']:.2f} €"
            return NS(stop_reason="end_turn", content=[NS(type="text", text=txt)])
        if "Netflix" in first_user:
            return NS(stop_reason="tool_use", content=[NS(type="text", text="Lo añado."),
                      NS(type="tool_use", id="tu_1", name="anadir_gasto", input={"concepto": "Netflix", "importe": 12.99, "dia": 5, "categoria": "Suscripciones"})])
        return NS(stop_reason="tool_use", content=[NS(type="tool_use", id="tu_0", name="ver_resumen", input={})])


class FakeClient:
    messages = _Msgs()

"""
Simulación de pasarela de pagos (estilo Wompi), más fiel a la realidad:

- Checkout con formulario de tarjeta (número, vencimiento, CVC).
- Tarjetas de prueba: 4242 4242 4242 4242 aprueba, 4111 1111 1111 1111 es
  rechazada por fondos insuficientes; cualquier otro número falla el Luhn.
- Cada transacción recibe un ID (TRX-...), estado y marca de tiempo, y el
  "webhook" interno actualiza el pago como lo haría el evento real de Wompi.

No se procesa ningún pago real ni se almacenan datos de tarjeta.
"""

from __future__ import annotations

import datetime as dt
import re
import uuid
from typing import Any

from . import knowledge as kb

CARD_APPROVE = "4242424242424242"
CARD_DECLINE = "4111111111111111"


def luhn_ok(number: str) -> bool:
    digits = [int(d) for d in number]
    odd = digits[-1::-2]
    even = [sum(divmod(2 * d, 10)) for d in digits[-2::-2]]
    return (sum(odd) + sum(even)) % 10 == 0


def process_card(pago: dict[str, Any], card_number: str, exp: str, cvc: str) -> dict[str, Any]:
    """Simula el cargo. Muta el pago y devuelve {estado, detalle, trx}."""
    num = re.sub(r"[\s-]", "", card_number or "")
    trx = "TRX-" + uuid.uuid4().hex[:10].upper()
    now = dt.datetime.now().isoformat(timespec="seconds")

    if not re.fullmatch(r"\d{13,19}", num) or not luhn_ok(num):
        estado, detalle = "rechazado", "Número de tarjeta inválido (falla verificación Luhn)."
    elif not re.fullmatch(r"(0[1-9]|1[0-2])\s*/\s*\d{2}", (exp or "").strip()):
        estado, detalle = "rechazado", "Fecha de vencimiento inválida (usa MM/AA)."
    elif not re.fullmatch(r"\d{3,4}", (cvc or "").strip()):
        estado, detalle = "rechazado", "CVC inválido."
    elif num == CARD_DECLINE:
        estado, detalle = "rechazado", "Transacción DECLINED: fondos insuficientes (tarjeta de prueba)."
    else:
        estado, detalle = "aprobado", "Transacción APPROVED por el emisor (entorno de prueba)."

    pago["estado"] = estado
    pago["trx"] = trx
    pago["procesado_at"] = now
    pago["detalle"] = detalle
    pago["ultimos4"] = num[-4:] if len(num) >= 4 else "????"
    pago.setdefault("intentos", 0)
    pago["intentos"] += 1
    return {"estado": estado, "detalle": detalle, "trx": trx}


# --------------------------------------------------------------------------
# Plantillas HTML del checkout
# --------------------------------------------------------------------------
_BASE_CSS = """
 *{box-sizing:border-box}
 body{margin:0;font-family:"Segoe UI",Roboto,Arial,sans-serif;background:#eef2f7;color:#0f1e2e;
  display:grid;place-items:center;min-height:100vh;padding:20px}
 .card{background:#fff;border-radius:16px;box-shadow:0 20px 50px rgba(16,30,46,.15);width:100%;
  max-width:430px;overflow:hidden}
 .top{background:linear-gradient(90deg,#0a8f4d,#00b573);color:#fff;padding:18px 22px}
 .top b{font-size:18px}.top span{opacity:.85;font-size:12.5px}
 .body{padding:24px 22px}
 .row{display:flex;justify-content:space-between;padding:9px 0;border-bottom:1px dashed #e2e8f0;font-size:14px}
 .row .v{font-weight:700}
 .total{display:flex;justify-content:space-between;margin:14px 0;font-size:16px}
 .total b{font-size:24px;color:#0a8f4d}
 label{display:block;font-size:12px;font-weight:700;color:#33465c;margin:12px 0 4px}
 input{width:100%;border:1px solid #d3dbe6;border-radius:9px;padding:11px 12px;font:inherit;font-size:14px;outline:none}
 input:focus{border-color:#0a8f4d;box-shadow:0 0 0 3px #e7f5ee}
 .grid2{display:grid;grid-template-columns:1fr 1fr;gap:12px}
 .pay{width:100%;border:none;background:#0a8f4d;color:#fff;font-weight:700;font-size:16px;padding:14px;
  border-radius:11px;cursor:pointer;margin-top:18px}
 .pay:hover{background:#087a41}
 .secure{display:flex;align-items:center;gap:7px;color:#6b7a90;font-size:12px;margin-top:16px;justify-content:center}
 .note{font-size:11.5px;color:#94a3b8;text-align:center;margin-top:10px;line-height:1.5}
 .testcards{background:#f6f9fc;border:1px solid #e2e8f0;border-radius:9px;padding:10px 12px;margin-top:14px;font-size:12px;color:#33465c}
 .testcards code{background:#fff;border:1px solid #e2e8f0;border-radius:5px;padding:1px 6px}
 .ok{color:#0a8f4d;font-weight:700}.err{color:#c62828;font-weight:700}
 .badge{width:64px;height:64px;border-radius:50%;display:grid;place-items:center;margin:0 auto 14px;font-size:30px}
 .badge.ok{background:#e7f5ee}.badge.err{background:#fbeaea}
 .center{text-align:center}
 a.back{display:inline-block;margin-top:14px;color:#0a8f4d;font-weight:700;text-decoration:none;font-size:14px}
"""


def checkout_html(session_id: str, token: str, producto: str, precio: str,
                  referencia: str, pago: dict[str, Any]) -> str:
    if pago["estado"] == "aprobado":
        return result_html(True, producto, precio, referencia, pago, ya_estaba=True)
    error = ""
    if pago["estado"] == "rechazado":
        error = f"<p class='err' style='font-size:13px'>{pago.get('detalle', 'Pago rechazado.')} Intenta de nuevo.</p>"
    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pago seguro - Wompi (sandbox)</title><style>{_BASE_CSS}</style></head><body>
 <div class="card">
  <div class="top"><b>Wompi</b> <span>· sandbox de pagos</span>
   <div style="margin-top:6px;font-size:13px">Colsubsidio Seguros</div></div>
  <div class="body">
   <div class="row"><span>Producto</span><span class="v">{producto}</span></div>
   <div class="row"><span>Referencia</span><span class="v">{referencia}</span></div>
   <div class="row"><span>Frecuencia</span><span class="v">Mensual</span></div>
   <div class="total"><span>Total a pagar</span><b>{precio}</b></div>
   {error}
   <form method="post" action="/pay/{session_id}/{token}">
     <label>Número de tarjeta</label>
     <input name="card" inputmode="numeric" placeholder="4242 4242 4242 4242" maxlength="19" required>
     <div class="grid2">
       <div><label>Vencimiento</label><input name="exp" placeholder="MM/AA" maxlength="5" required></div>
       <div><label>CVC</label><input name="cvc" inputmode="numeric" placeholder="123" maxlength="4" required></div>
     </div>
     <button type="submit" class="pay">Pagar {precio}</button>
   </form>
   <div class="testcards">
     Tarjetas de prueba: <code>4242 4242 4242 4242</code> aprueba ·
     <code>4111 1111 1111 1111</code> rechaza por fondos.
   </div>
   <div class="secure">🔒 Transacción cifrada de extremo a extremo (simulación)</div>
   <div class="note">Entorno sandbox. No se procesan pagos reales ni se almacenan datos de tarjeta.</div>
  </div>
 </div>
</body></html>"""


def result_html(aprobado: bool, producto: str, precio: str, referencia: str,
                pago: dict[str, Any], ya_estaba: bool = False) -> str:
    trx = pago.get("trx", "—")
    if aprobado:
        icon, klass, titulo = "✓", "ok", "Pago aprobado"
        msg = ("Este pago ya había sido aprobado." if ya_estaba
               else "Ya puedes volver a la conversación con Lara.<br>Estamos confirmando tu vinculación.")
        extra = ""
    else:
        icon, klass, titulo = "✕", "err", "Pago rechazado"
        msg = pago.get("detalle", "La transacción fue rechazada.")
        extra = f'<a class="back" href="javascript:history.back()">← Intentar de nuevo</a>'
    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{titulo}</title><style>{_BASE_CSS}</style></head><body>
 <div class="card"><div class="body center">
  <div class="badge {klass}"><span class="{klass}">{icon}</span></div>
  <h2 style="margin:0 0 6px">{titulo}</h2>
  <p style="color:#6b7a90;font-size:14px;margin:4px 0">{producto}</p>
  <div style="font-size:22px;font-weight:800;color:#0a8f4d;margin:10px 0">{precio}</div>
  <p style="font-size:13px">Referencia: <b>{referencia}</b> · Transacción: <b>{trx}</b></p>
  <p style="color:#6b7a90;font-size:13.5px">{msg}</p>
  {extra}
 </div></div>
</body></html>"""


def crear_pago(producto_id: str, precio: int) -> dict[str, Any]:
    """Crea el registro de pago pendiente con token y referencia únicos."""
    return {
        "producto": producto_id,
        "precio": precio,
        "estado": "pendiente",
        "referencia": "REF-" + uuid.uuid4().hex[:8].upper(),
        "token": uuid.uuid4().hex[:10],
        "creado_at": dt.datetime.now().isoformat(timespec="seconds"),
        "intentos": 0,
        "confirmado": False,
    }


def format_precio(pago: dict[str, Any]) -> str:
    return kb.format_cop(pago.get("precio", 0))

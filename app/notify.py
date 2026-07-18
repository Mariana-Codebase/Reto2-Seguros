"""
Entrega de mensajes y documentos (correo SMTP y Twilio opcional).

Si no hay credenciales configuradas, opera en modo SIMULADO: registra la
entrega y la reporta como tal, sin enviar nada. Todo devuelve
{ok, simulado, detalle}.
"""

from __future__ import annotations

import logging
import pathlib
import smtplib
import ssl
from email.message import EmailMessage
from typing import Any

from .config import settings

logger = logging.getLogger("clara.notify")


def email_configurado() -> bool:
    return bool(settings.SMTP_HOST and settings.SMTP_USER and settings.SMTP_PASS)


def send_email(to: str, subject: str, body: str, pdf_path: str | None = None) -> dict[str, Any]:
    if not email_configurado():
        detalle = f"[SIMULADO] Correo a {to} con asunto '{subject}'"
        if pdf_path:
            detalle += f" y adjunto {pathlib.Path(pdf_path).name}"
        logger.info(detalle)
        return {"ok": True, "simulado": True, "detalle": detalle}
    try:
        msg = EmailMessage()
        msg["From"] = settings.SMTP_FROM
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        if pdf_path and pathlib.Path(pdf_path).exists():
            data = pathlib.Path(pdf_path).read_bytes()
            msg.add_attachment(data, maintype="application", subtype="pdf",
                               filename=pathlib.Path(pdf_path).name)
        ctx = ssl.create_default_context()
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30) as s:
            s.starttls(context=ctx)
            s.login(settings.SMTP_USER, settings.SMTP_PASS)
            s.send_message(msg)
        logger.info("Correo enviado a %s (%s)", to, subject)
        return {"ok": True, "simulado": False, "detalle": f"Correo enviado a {to}"}
    except Exception as e:  # noqa: BLE001
        logger.error("Error SMTP enviando a %s: %s", to, e)
        return {"ok": False, "simulado": False, "detalle": f"Error SMTP: {e}"}


def _twilio_send(from_: str, to: str, body: str, media_url: str | None) -> dict[str, Any]:
    if not (settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN and from_):
        detalle = f"[SIMULADO] Mensaje a {to}: {body[:60]}"
        logger.info(detalle)
        return {"ok": True, "simulado": True, "detalle": detalle}
    try:
        import requests
        data = {"From": from_, "To": to, "Body": body}
        if media_url:
            data["MediaUrl"] = media_url
        r = requests.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Messages.json",
            data=data, auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN), timeout=30,
        )
        r.raise_for_status()
        return {"ok": True, "simulado": False, "detalle": f"Mensaje Twilio enviado a {to}"}
    except Exception as e:  # noqa: BLE001
        logger.error("Error Twilio enviando a %s: %s", to, e)
        return {"ok": False, "simulado": False, "detalle": f"Error Twilio: {e}"}


def send_whatsapp(to: str, body: str, media_url: str | None = None) -> dict[str, Any]:
    to_fmt = to if to.startswith("whatsapp:") else f"whatsapp:{to}"
    return _twilio_send(settings.TWILIO_WHATSAPP_FROM, to_fmt, body, media_url)


def send_sms(to: str, body: str) -> dict[str, Any]:
    return _twilio_send(settings.TWILIO_SMS_FROM, to, body, None)

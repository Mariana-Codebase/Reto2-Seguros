"""
Configuración central de la aplicación.

Todas las variables de entorno se leen aquí una sola vez, con valores por
defecto seguros. El resto del código importa `settings` y no toca os.environ.
"""

from __future__ import annotations

import logging
import os
import pathlib

from dotenv import load_dotenv

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


class Settings:
    # --- Gemini (proveedor de LLM) ---
    GEMINI_API_KEY: str = _env("GEMINI_API_KEY")
    GEMINI_MODEL: str = _env("GEMINI_MODEL", "gemini-2.0-flash")
    GEMINI_BASE_URL: str = _env(
        "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta"
    )
    LLM_TEMPERATURE: float = float(_env("LLM_TEMPERATURE", "0.4"))
    LLM_TIMEOUT: int = int(_env("LLM_TIMEOUT", "60"))
    LLM_MAX_RETRIES: int = int(_env("LLM_MAX_RETRIES", "2"))

    # --- Servidor ---
    PORT: int = int(_env("PORT", "8000"))
    ENV: str = _env("APP_ENV", "development")  # development | production
    LOG_LEVEL: str = _env("LOG_LEVEL", "INFO")

    # --- URL pública para enlaces (pago, PDFs) ---
    @property
    def public_base_url(self) -> str:
        explicit = _env("PUBLIC_BASE_URL")
        if explicit:
            return explicit.rstrip("/")
        space_host = _env("SPACE_HOST")  # inyectada por Hugging Face Spaces
        if space_host:
            return f"https://{space_host}".rstrip("/")
        return f"http://localhost:{self.PORT}"

    # --- Rutas ---
    VAR_DIR: pathlib.Path = BASE_DIR / "var"
    DOCS_DIR: pathlib.Path = BASE_DIR / "var" / "docs"
    DB_PATH: pathlib.Path = BASE_DIR / "var" / "clara.db"
    STATIC_DIR: pathlib.Path = BASE_DIR / "static"
    INDEX_HTML: pathlib.Path = BASE_DIR / "static" / "index.html"

    # --- Sesiones ---
    SESSION_TTL_HOURS: int = int(_env("SESSION_TTL_HOURS", "24"))

    # --- Correo (SMTP) ---
    SMTP_HOST: str = _env("SMTP_HOST")
    SMTP_PORT: int = int(_env("SMTP_PORT", "587"))
    SMTP_USER: str = _env("SMTP_USER")
    SMTP_PASS: str = _env("SMTP_PASS")
    SMTP_FROM: str = _env(
        "SMTP_FROM", "Clara - Colsubsidio Seguros <no-reply@colsubsidio.demo>"
    )

    # --- Twilio (WhatsApp / SMS, opcional) ---
    TWILIO_ACCOUNT_SID: str = _env("TWILIO_ACCOUNT_SID")
    TWILIO_AUTH_TOKEN: str = _env("TWILIO_AUTH_TOKEN")
    TWILIO_WHATSAPP_FROM: str = _env("TWILIO_WHATSAPP_FROM")
    TWILIO_SMS_FROM: str = _env("TWILIO_SMS_FROM")

    @property
    def is_production(self) -> bool:
        return self.ENV.lower() == "production"

    def validate(self) -> list[str]:
        """Devuelve una lista de advertencias de configuración (no aborta)."""
        warnings: list[str] = []
        if not self.GEMINI_API_KEY:
            warnings.append(
                "GEMINI_API_KEY no está configurada: el agente no podrá responder."
            )
        if not (self.SMTP_HOST and self.SMTP_USER and self.SMTP_PASS):
            warnings.append("SMTP sin configurar: los correos se simulan.")
        return warnings


settings = Settings()

# Carpetas de trabajo
settings.VAR_DIR.mkdir(exist_ok=True)
settings.DOCS_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s %(levelname)-7s [%(name)s] %(message)s",
)
logger = logging.getLogger("clara")

for w in settings.validate():
    logger.warning(w)

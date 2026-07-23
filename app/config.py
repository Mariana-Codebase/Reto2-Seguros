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
    LLM_MAX_TOKENS: int = int(_env("LLM_MAX_TOKENS", "1024"))

    # --- Anthropic / Claude (proveedor alternativo de LLM) ---
    # Si GEMINI_API_KEY empieza por 'sk-ant-' se usa Claude en vez de Gemini.
    # También puede declararse en su propia variable ANTHROPIC_API_KEY, dejando
    # GEMINI_API_KEY libre para una clave Gemini real: en ese caso Gemini queda
    # disponible como RESPALDO automático si Claude falla (créditos agotados,
    # caída del servicio, etc.).
    ANTHROPIC_API_KEY: str = _env("ANTHROPIC_API_KEY")
    ANTHROPIC_MODEL: str = _env("ANTHROPIC_MODEL", "claude-sonnet-5")
    ANTHROPIC_VERSION: str = _env("ANTHROPIC_VERSION", "2023-06-01")
    ANTHROPIC_BASE_URL: str = _env("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1")
    # Opus 4.8 y otros modelos recientes deprecaron `temperature`. Déjalo en 0
    # salvo que uses un modelo que aún lo acepte.
    ANTHROPIC_SEND_TEMPERATURE: bool = _env("ANTHROPIC_SEND_TEMPERATURE", "0") in ("1", "true", "True")

    # --- Modelo servido por endpoint compatible con OpenAI ---
    # Cubre dos despliegues con el mismo código:
    #   · Ollama local:  http://localhost:11434/v1  (sin token)
    #   · Router de HF:  https://router.huggingface.co/v1  (con HF_TOKEN)
    OLLAMA_BASE_URL: str = _env("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    OLLAMA_MODEL: str = _env("OLLAMA_MODEL", "qwen3:4b")
    HF_TOKEN: str = _env("HF_TOKEN")

    # Proveedor explícito: ollama | anthropic | vertex | aistudio.
    # Vacío => se detecta por el prefijo de la clave. Ollama no tiene clave, así
    # que para usarlo hay que declararlo aquí.
    LLM_PROVIDER: str = _env("LLM_PROVIDER").lower()

    @property
    def anthropic_key(self) -> str:
        """Clave de Claude: ANTHROPIC_API_KEY dedicada, o GEMINI_API_KEY si
        contiene una clave 'sk-ant-' (compatibilidad con la config anterior)."""
        if self.ANTHROPIC_API_KEY:
            return self.ANTHROPIC_API_KEY
        if self.GEMINI_API_KEY.startswith("sk-ant-"):
            return self.GEMINI_API_KEY
        return ""

    @property
    def gemini_key(self) -> str:
        """Clave Gemini real (AIza... de AI Studio o AQ. de Vertex Express)."""
        if self.GEMINI_API_KEY and not self.GEMINI_API_KEY.startswith("sk-ant-"):
            return self.GEMINI_API_KEY
        return ""

    @property
    def llm_provider(self) -> str:
        """Proveedor efectivo: LLM_PROVIDER manda; si está vacío se detecta por
        las claves disponibles."""
        if self.LLM_PROVIDER:
            return self.LLM_PROVIDER
        if self.anthropic_key and not self.gemini_key:
            return "anthropic"
        if self.anthropic_key and self.gemini_key:
            return "anthropic"   # Claude primario, Gemini queda de respaldo
        if self.gemini_key.startswith("AQ."):
            return "vertex"
        return "aistudio"

    @property
    def llm_fallback_gemini(self) -> bool:
        """True si hay una clave Gemini disponible para usar como respaldo
        cuando el proveedor primario (Claude/Ollama) falle."""
        return self.llm_provider not in ("aistudio", "vertex") and bool(self.gemini_key)

    @property
    def llm_model(self) -> str:
        provider = self.llm_provider
        if provider == "ollama":
            return self.OLLAMA_MODEL
        if provider == "anthropic":
            return self.ANTHROPIC_MODEL
        return self.GEMINI_MODEL

    @property
    def llm_needs_key(self) -> bool:
        """Ollama en local no usa clave; el router de HF sí (HF_TOKEN)."""
        return self.llm_provider != "ollama"

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
    DATA_DIR: pathlib.Path = BASE_DIR / "data"

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
        if self.llm_needs_key and not (self.GEMINI_API_KEY or self.ANTHROPIC_API_KEY):
            warnings.append(
                "Ninguna clave de modelo configurada (GEMINI_API_KEY / ANTHROPIC_API_KEY): el agente no podrá responder."
            )
        if self.llm_provider == "ollama":
            destino = self.OLLAMA_BASE_URL
            if "huggingface" in destino and not self.HF_TOKEN:
                warnings.append(
                    "OLLAMA_BASE_URL apunta al router de Hugging Face pero falta HF_TOKEN: "
                    "el agente no podrá responder."
                )
            elif "localhost" in destino or "127.0.0.1" in destino:
                warnings.append(
                    f"Modelo local: {self.OLLAMA_MODEL} en {destino}. "
                    "Requiere Ollama corriendo (`ollama serve`)."
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

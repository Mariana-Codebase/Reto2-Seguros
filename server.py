"""
Clara — Venta automatizada de seguros · Colsubsidio × 30X (julio de 2026).

Punto de entrada del servidor:

    python server.py            # http://localhost:8000 (o el PORT del .env)

En desarrollo activa autoreload; en producción (APP_ENV=production) lo apaga
y desactiva la documentación OpenAPI. La configuración vive en app/config.py.
"""

import uvicorn

from app.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=not settings.is_production,
    )

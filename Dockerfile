# Imagen de producción (compatible con Hugging Face Spaces, SDK: docker).
# El cerebro es la API de Gemini: configura GEMINI_API_KEY como secret.
FROM python:3.12-slim

# Usuario sin privilegios
RUN useradd -m -u 1000 clara
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY static ./static
COPY server.py .

# Carpeta de trabajo escribible (PDFs generados + SQLite)
RUN mkdir -p /app/var/docs && chown -R clara:clara /app/var

ENV APP_ENV=production
ENV PORT=7860

USER clara
EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://localhost:{os.environ.get(\"PORT\",7860)}/api/health')" || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860} --workers 1"]

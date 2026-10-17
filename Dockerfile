# Civora AI - FULL app (FastAPI), unchanged. Works on Render, Railway, Hugging Face Spaces (Docker), any VPS.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
# OCR for scanned drawings (PNG/JPG/scanned PDF)
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements-app.txt .
RUN pip install -r requirements-app.txt
COPY . .
# data/ (database, uploads, session key) and backups/ must be writable; mount a persistent disk at /app/data to keep projects
RUN mkdir -p /app/data /app/backups && useradd -m -u 1000 civora && chown -R civora /app
USER civora
ENV PORT=7860
EXPOSE 7860
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]

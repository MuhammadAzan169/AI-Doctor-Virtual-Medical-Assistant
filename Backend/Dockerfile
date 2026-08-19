# ── AI Doctor — Backend (Render-ready) ────────────────────────────────
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ curl \
    && rm -rf /var/lib/apt/lists/*

# Core deps (lean) — matches the Render free-plan build.
# To enable the local ML features instead, swap this for requirements-local.txt
# and set ENABLE_FRACTURE / ENABLE_OCR / ENABLE_VOICE — see README.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p var/uploads var/output var/pdfs

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=20s --start-period=40s --retries=3 \
    CMD curl -f "http://localhost:${PORT}/health" || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

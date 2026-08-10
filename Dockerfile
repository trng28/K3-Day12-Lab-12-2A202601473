FROM node:22-alpine AS frontend-builder

WORKDIR /frontend
COPY research_app/frontend/package*.json ./
RUN npm ci
COPY research_app/frontend/ ./
RUN npm run build

FROM python:3.11-slim AS builder

WORKDIR /app
COPY requirements.txt ./
COPY research_app/requirements.txt ./research-requirements.txt
RUN pip install --no-cache-dir --prefix=/install \
    -r requirements.txt -r research-requirements.txt

FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY --from=builder /install /usr/local

# Keep the Day12 modules in the image for the checkpoint contract.
COPY app ./app
COPY utils ./utils
COPY requirements.txt ./

COPY research_app ./research_app
COPY --from=frontend-builder /frontend/dist ./research_app/frontend/dist

RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('PORT', '8000') + '/health', timeout=3).read()" || exit 1

CMD ["sh", "-c", "cd /app/research_app && exec uvicorn api:app --host 0.0.0.0 --port ${PORT:-8000}"]

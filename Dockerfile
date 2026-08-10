# ═══════════════════════════════════════════════════════════════════
# CP2 — Containerization
#
# Multi-stage build: stage `builder` cài dependency (được phép nặng, có
# compiler), stage `runtime` chỉ copy KẾT QUẢ sang → image nhỏ, không root,
# đọc cổng từ $PORT, có HEALTHCHECK.
#
# Kiểm tra:  pytest tests/test_cp2.py -v
# Build thử: docker build -t day12-agent:prod .
#            docker images day12-agent:prod     # xem dung lượng
# ═══════════════════════════════════════════════════════════════════

FROM python:3.11-slim AS builder

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim AS runtime

WORKDIR /app

COPY --from=builder /install /usr/local

COPY app ./app
COPY utils ./utils
COPY requirements.txt .

RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health').read()" || exit 1

CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

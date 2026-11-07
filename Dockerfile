# API FastAPI cho server. Xem docs/deploy.md.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    WYCKOFF_OFFLINE=1 \
    WYCKOFF_CACHE_DIR=/data/cache \
    WYCKOFF_OUT_DIR=/data/output \
    WYCKOFF_PORTFOLIO_DB=/data/portfolio/portfolio.db

WORKDIR /app
COPY requirements-prod.txt .
RUN pip install --no-cache-dir --root-user-action=ignore --disable-pip-version-check -r requirements-prod.txt

RUN useradd --create-home --uid 1000 app \
    && mkdir -p /data/cache /data/output /data/portfolio \
    && chown -R app:app /data

COPY serve.py .
COPY config ./config
COPY wyckoff ./wyckoff

USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"
CMD ["python", "serve.py", "--host", "0.0.0.0", "--port", "8000"]

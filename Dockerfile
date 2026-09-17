# CareCap — the care captain's OS
#
# Slim, non-root, healthchecked. The state file lives in /srv/data —
# mount a volume there for persistence; without one, the app re-seeds the
# demo family fresh on every boot (which is exactly what a demo wants).
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

RUN useradd -m -u 10001 carecap \
    && mkdir -p /srv/data \
    && chown -R carecap:carecap /srv
USER carecap

ENV CARECAP_DATA=/srv/data/carecap.json
EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8001/api/health', timeout=2).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ORBYTHRA_ENV=production \
    ORBYTHRA_DB_PATH=/data/orbythra.db

WORKDIR /app

RUN groupadd --system orbythra \
    && useradd --system --gid orbythra --home-dir /app orbythra \
    && mkdir -p /data \
    && chown -R orbythra:orbythra /data /app

COPY requirements.txt requirements.lock ./
RUN pip install --no-cache-dir --disable-pip-version-check -r requirements.txt -c requirements.lock

COPY --chown=orbythra:orbythra app ./app

USER orbythra

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).read()"

CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]

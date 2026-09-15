FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN useradd --create-home --uid 10001 appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chown -R appuser:appuser /app
USER appuser

# Platforms inject PORT at runtime and this default keeps compose and local runs
# on the previous port, so one image serves every target without an override.
ENV PORT=8787 \
    WEB_CONCURRENCY=1

EXPOSE 8787

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:'+(os.environ.get('PORT') or '8787')+'/health',timeout=3)"

CMD ["sh", "-c", "exec uvicorn app:app --host 0.0.0.0 --port \"${PORT:-8787}\" --workers \"${WEB_CONCURRENCY:-1}\""]

# Imagem única para API e worker (o compose define o comando de cada serviço).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Usuário não-root dedicado.
RUN useradd --create-home --uid 10001 meteoro

WORKDIR /workspace
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY backend /workspace/backend
COPY frontend /workspace/frontend

# Diretório de payloads brutos (montado como volume em produção).
RUN mkdir -p /data/raw && chown -R meteoro:meteoro /data /workspace

WORKDIR /workspace/backend
ENV PYTHONPATH=/workspace/backend
USER meteoro

# Liveness do container (a API do compose usa /health; o worker sobrescreve).
HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

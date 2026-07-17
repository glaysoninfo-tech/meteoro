FROM python:3.12-slim

WORKDIR /workspace
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY backend /workspace/backend
COPY frontend /workspace/frontend

WORKDIR /workspace/backend
ENV PYTHONPATH=/workspace/backend
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

"""Etapa 6 — middleware de produção: request-id, headers, gzip e envelope de erro."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_toda_resposta_carrega_request_id(client: TestClient) -> None:
    response = client.get("/health")
    assert response.headers.get("X-Request-ID")


def test_request_id_do_cliente_e_propagado(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "meu-rastreio-123"})
    assert response.headers["X-Request-ID"] == "meu-rastreio-123"


def test_security_headers_presentes(client: TestClient) -> None:
    response = client.get("/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"


def test_gzip_para_respostas_grandes(client: TestClient) -> None:
    response = client.get("/openapi.json", headers={"Accept-Encoding": "gzip"})
    assert response.status_code == 200
    assert response.headers.get("Content-Encoding") == "gzip"


def test_erro_interno_retorna_envelope_sem_stacktrace() -> None:
    rota = "/api/v1/_teste_erro_interno"

    @app.get(rota, include_in_schema=False)
    def _explode() -> None:  # pragma: no cover - corpo irrelevante
        raise RuntimeError("falha proposital para o teste")

    try:
        with TestClient(app, raise_server_exceptions=False) as test_client:
            response = test_client.get(rota)
        assert response.status_code == 500
        payload = response.json()
        assert payload["detail"] == "Erro interno do servidor. O evento foi registrado."
        assert payload["request_id"]
        assert "RuntimeError" not in response.text
        assert "Traceback" not in response.text
    finally:
        app.router.routes = [
            route for route in app.router.routes if getattr(route, "path", None) != rota
        ]

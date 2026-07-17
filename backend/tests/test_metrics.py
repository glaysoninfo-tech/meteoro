"""Etapa 12 — métricas Prometheus, incluindo staleness por fonte."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import bootstrap_admin


def test_metrics_expoe_formato_prometheus(client: TestClient) -> None:
    client.get("/health")  # garante ao menos uma requisição contabilizada
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    corpo = response.text
    assert "meteoro_http_requests_total" in corpo
    assert "meteoro_quality_issues_pending" in corpo
    assert "meteoro_ready" in corpo
    assert "meteoro_worker_queue_available" in corpo


def test_metrics_reporta_staleness_de_fonte(client: TestClient) -> None:
    headers = bootstrap_admin(client)
    created = client.post(
        "/api/v1/catalog/sources",
        headers=headers,
        json={
            "institution_name": "Instituto Teste",
            "source_name": "Fonte Métrica",
            "source_type": "meteorology_model",
            "access_method": "http",
            "authentication_type": "none",
            "endpoint_reference": "https://api.example.org/dados",
            "expected_frequency_minutes": 60,
            "criticality": "high",
        },
    )
    assert created.status_code == 201, created.text
    corpo = client.get("/metrics").text
    # Fonte nunca coletada aparece com o marcador específico e criticidade.
    assert 'meteoro_source_never_collected{source_name="Fonte Métrica",criticality="high"}' in corpo


def test_metrics_contabiliza_status_http(client: TestClient) -> None:
    client.get("/api/v1/rota-que-nao-existe")
    corpo = client.get("/metrics").text
    assert 'meteoro_http_requests_total{status_class="4xx"}' in corpo

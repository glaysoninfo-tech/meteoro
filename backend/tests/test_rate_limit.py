"""Etapa 7 — rate limiting da superfície pública."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.ratelimit import reset_rate_limits
from app.core.settings import settings


@pytest.fixture()
def rate_limited_client(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(settings, "public_rate_limit_enabled", True)
    monkeypatch.setattr(settings, "public_rate_limit_per_minute", 3)
    monkeypatch.setattr(settings, "public_csv_rate_limit_per_minute", 2)
    reset_rate_limits()
    yield client
    reset_rate_limits()


def test_public_dentro_do_limite_passa(rate_limited_client: TestClient) -> None:
    for _ in range(3):
        response = rate_limited_client.get("/api/v1/public/alerts")
        assert response.status_code != 429


def test_public_acima_do_limite_recebe_429_com_retry_after(
    rate_limited_client: TestClient,
) -> None:
    for _ in range(3):
        rate_limited_client.get("/api/v1/public/alerts")
    response = rate_limited_client.get("/api/v1/public/alerts")
    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) >= 1
    assert "Limite de requisições" in response.json()["detail"]


def test_csv_tem_limite_mais_restrito(rate_limited_client: TestClient) -> None:
    caminho = "/api/v1/public/open-data/observations.csv"
    for _ in range(2):
        rate_limited_client.get(caminho)
    response = rate_limited_client.get(caminho)
    assert response.status_code == 429


def test_buckets_sao_independentes(rate_limited_client: TestClient) -> None:
    caminho_csv = "/api/v1/public/open-data/observations.csv"
    for _ in range(2):
        rate_limited_client.get(caminho_csv)
    assert rate_limited_client.get(caminho_csv).status_code == 429
    # O bucket geral continua com folga.
    assert rate_limited_client.get("/api/v1/public/alerts").status_code != 429


def test_endpoints_nao_publicos_nao_sao_limitados(rate_limited_client: TestClient) -> None:
    for _ in range(10):
        response = rate_limited_client.get("/health")
        assert response.status_code == 200

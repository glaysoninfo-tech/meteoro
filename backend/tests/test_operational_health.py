from __future__ import annotations

import importlib
import re

import pytest
from fastapi.testclient import TestClient


def test_liveness_returns_and_preserves_valid_request_id(client: TestClient) -> None:
    response = client.get("/health/live", headers={"X-Request-ID": "municipio-123"})

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["X-Request-ID"] == "municipio-123"


def test_invalid_request_id_is_replaced(client: TestClient) -> None:
    response = client.get("/health/live", headers={"X-Request-ID": "id com espaço"})

    assert response.status_code == 200
    assert re.fullmatch(r"[0-9a-f-]{36}", response.headers["X-Request-ID"])


def test_readiness_returns_503_when_required_component_is_down(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    main_module = importlib.import_module("app.main")
    monkeypatch.setattr(
        main_module,
        "readiness_report",
        lambda: ({"status": "not_ready", "components": {}}, False),
    )

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"

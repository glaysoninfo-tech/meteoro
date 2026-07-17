from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
import pytest

from app.modules.ingestion import connectors
from tests.conftest import bootstrap_admin


def _create_source(client: TestClient, headers: dict[str, str], **overrides: object) -> dict:
    payload: dict[str, object] = {
        "institution_name": "Prefeitura",
        "source_name": "Leituras municipais",
        "source_type": "sensor",
        "access_method": "manual_file",
        "authentication_type": "none",
        "endpoint_reference": "manual://leituras.json",
        "expected_frequency_minutes": 60,
        "criticality": "medium",
    }
    payload.update(overrides)
    response = client.post("/api/v1/catalog/sources", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_upload_is_idempotent_and_enforces_file_limit(client: TestClient) -> None:
    headers = bootstrap_admin(client)
    source = _create_source(client, headers)
    content = (
        b'[{"observed_at":"2026-07-14T12:00:00Z","variable_code":"temperature_c",'
        b'"value":25,"unit":"C","location":"S1"}]'
    )

    first = client.post(
        f"/api/v1/ingestion/runs/import/source/{source['source_id']}",
        headers=headers,
        files={"file": ("leituras.json", content, "application/json")},
    )
    second = client.post(
        f"/api/v1/ingestion/runs/import/source/{source['source_id']}",
        headers=headers,
        files={"file": ("leituras.json", content, "application/json")},
    )

    assert first.status_code == 200, first.text
    assert first.json()["records_accepted"] == 1
    assert second.status_code == 200, second.text
    assert second.json()["records_accepted"] == 0
    assert second.json()["records_deduplicated"] == 1

    oversized = client.post(
        f"/api/v1/ingestion/runs/import/source/{source['source_id']}",
        headers=headers,
        files={"file": ("leituras.json", b"x" * (25 * 1024 * 1024 + 1), "application/json")},
    )
    assert oversized.status_code == 413

    unsupported = client.post(
        f"/api/v1/ingestion/runs/import/source/{source['source_id']}",
        headers=headers,
        files={"file": ("leituras.xml", b"<value>1</value>", "application/xml")},
    )
    assert unsupported.status_code == 415


def test_reprocess_passes_explicit_period_to_http_source(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = bootstrap_admin(client)
    source = _create_source(
        client,
        headers,
        institution_name="INMET",
        source_name="Histórico",
        source_type="api",
        access_method="http",
        endpoint_reference="https://api.example.org/readings?fixed=1",
        connector_config_json=(
            '{"reprocess":{"start_query_param":"from","end_query_param":"to"}}'
        ),
    )

    class Response:
        headers = {"Content-Type": "application/json", "Content-Length": "112"}

        def __enter__(self) -> "Response":
            self._sent = False
            return self

        def __exit__(self, *args: object) -> bool:
            return False

        def read(self, _size: int) -> bytes:
            if self._sent:
                return b""
            self._sent = True
            return (
                b'[{"observed_at":"2026-07-14T12:00:00Z","variable_code":"temperature_c",'
                b'"value":25,"unit":"C","location":"S1"}]'
            )

    seen_urls: list[str] = []
    monkeypatch.setattr(connectors, "resolve_public_destination", lambda _url: None)
    monkeypatch.setattr(
        connectors,
        "_open_pinned_http_request",
        lambda *, request, timeout_seconds: (seen_urls.append(request.full_url) or Response()),
    )

    response = client.post(
        "/api/v1/ingestion/runs/reprocess",
        headers=headers,
        json={
            "source_id": source["source_id"],
            "period_start_utc": "2026-07-01T00:00:00Z",
            "period_end_utc": "2026-07-02T00:00:00Z",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["trigger_type"] == "reprocess"
    query = parse_qs(urlparse(seen_urls[0]).query)
    assert query["from"] == ["2026-07-01T00:00:00+00:00"]
    assert query["to"] == ["2026-07-02T00:00:00+00:00"]

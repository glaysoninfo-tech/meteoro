from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
import pytest

from app.core.settings import settings
from tests.conftest import bootstrap_admin, create_authority_headers


def _create_source(client: TestClient, headers: dict[str, str], *, public: bool) -> dict:
    response = client.post(
        "/api/v1/catalog/sources",
        headers=headers,
        json={
            "institution_name": "Fonte de teste",
            "source_name": "Dados publicáveis" if public else "Dados internos",
            "source_type": "meteorology_model",
            "access_method": "manual_file",
            "authentication_type": "none",
            "endpoint_reference": "manual://public-test.json",
            "connector_config_json": '{"parser":"sensor_stream","classification":"public","data_kind":"model_estimate_or_forecast"}' if public else '{"parser":"sensor_stream"}',
            "expected_frequency_minutes": 60,
            "criticality": "low",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _import_one(client: TestClient, headers: dict[str, str], source_id: str, *, value: int) -> None:
    observed_at = datetime.now(tz=timezone.utc).replace(microsecond=0).isoformat()
    payload = (
        f'[{{"observed_at":"{observed_at}","variable_code":"temperature_c",'
        f'"value":{value},"unit":"C","location":"BETIM_MODEL_POINT"}}]'
    ).encode()
    response = client.post(
        f"/api/v1/ingestion/runs/import/source/{source_id}",
        headers=headers,
        files={"file": ("reading.json", payload, "application/json")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["records_accepted"] == 1, response.text


def test_public_api_only_exposes_current_published_and_classified_data(
    client: TestClient,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = bootstrap_admin(client)
    # The public surface is intentionally bound to one municipal organization.
    from app.modules.identity.models import UserModel
    from sqlalchemy import select

    session = session_factory()
    try:
        admin = session.scalar(select(UserModel).where(UserModel.email == "admin@example.org"))
        assert admin is not None
        monkeypatch.setattr(settings, "public_organization_id", admin.organization_id)
    finally:
        session.close()

    public_source = _create_source(client, headers, public=True)
    private_source = _create_source(client, headers, public=False)
    _import_one(client, headers, public_source["source_id"], value=26)
    _import_one(client, headers, private_source["source_id"], value=27)

    recommendation = client.post(
        "/api/v1/recommendations/",
        headers=headers,
        json={
            "title": "Hidratação em calor intenso",
            "audience": "cidadão",
            "criteria": {"valid_from_utc": "2026-01-01T00:00:00Z", "valid_to_utc": "2027-01-01T00:00:00Z"},
            "content": {"citizen_text": "Beba água ao longo do dia."},
        },
    )
    assert recommendation.status_code == 201, recommendation.text
    review = client.patch(
        f"/api/v1/recommendations/{recommendation.json()['recommendation_revision_id']}",
        headers=headers,
        json={"status": "in_review", "change_reason": "Encaminhada para validação."},
    )
    assert review.status_code == 200, review.text
    approver_headers = create_authority_headers(session_factory)
    approved = client.post(
        f"/api/v1/recommendations/{review.json()['recommendation_revision_id']}/approve",
        headers=approver_headers,
        json={"reason": "Conteúdo técnico revisado."},
    )
    assert approved.status_code == 200, approved.text
    published = client.post(
        f"/api/v1/recommendations/{review.json()['recommendation_revision_id']}/publish",
        headers=approver_headers,
        json={"reason": "Liberada para o portal público."},
    )
    assert published.status_code == 200, published.text

    now = datetime.now(tz=timezone.utc)
    for code, valid_from, valid_to in [
        ("ATIVO-001", now - timedelta(minutes=5), now + timedelta(hours=1)),
        ("VENCIDO-001", now - timedelta(hours=2), now - timedelta(minutes=1)),
    ]:
        created = client.post(
            "/api/v1/alerts/official",
            headers=headers,
            json={
                "source_id": public_source["source_id"], "issuer": "Órgão oficial", "alert_code": code,
                "severity": "high", "issued_at_utc": now.isoformat(), "valid_from_utc": valid_from.isoformat(),
                "valid_to_utc": valid_to.isoformat(), "title": code, "message": "Mensagem oficial.",
            },
        )
        assert created.status_code == 200, created.text

    observations = client.get("/api/v1/public/open-data/observations")
    assert observations.status_code == 200, observations.text
    assert observations.json()["total"] == 1
    assert observations.json()["items"][0]["value"] == 26
    assert observations.json()["items"][0]["data_kind"] == "model_estimate_or_forecast"

    alerts = client.get("/api/v1/public/alerts")
    assert alerts.status_code == 200, alerts.text
    assert [item["alert_code"] for item in alerts.json()] == ["ATIVO-001"]

    recommendations = client.get("/api/v1/public/recommendations")
    assert recommendations.status_code == 200, recommendations.text
    assert recommendations.json()[0]["title"] == "Hidratação em calor intenso"

    csv_export = client.get("/api/v1/public/open-data/observations.csv")
    assert csv_export.status_code == 200
    assert "26.0" in csv_export.text


def test_recommendation_requires_a_separate_authority_approver(client: TestClient, session_factory) -> None:
    headers = bootstrap_admin(client)
    created = client.post(
        "/api/v1/recommendations/",
        headers=headers,
        json={"title": "Teste aprovado", "audience": "cidadão", "criteria": {}, "content": {"text": "x"}},
    )
    assert created.status_code == 201
    reviewed = client.patch(
        f"/api/v1/recommendations/{created.json()['recommendation_revision_id']}",
        headers=headers,
        json={"status": "in_review", "change_reason": "Revisão necessária."},
    )
    assert reviewed.status_code == 200
    # Granting the authority role to a different account is required; author and approver stay distinct.
    approver_headers = create_authority_headers(session_factory)
    result = client.post(
        f"/api/v1/recommendations/{reviewed.json()['recommendation_revision_id']}/approve",
        headers=approver_headers,
        json={"reason": "Aprovada por segunda pessoa."},
    )
    assert result.status_code == 200

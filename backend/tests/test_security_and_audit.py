from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.orm import Session, sessionmaker

from app.core.settings import Settings
from app.modules.audit.service import audit_service
from tests.conftest import bootstrap_admin


def test_production_settings_require_non_example_secret_https_and_explicit_hosts() -> None:
    with pytest.raises(ValidationError):
        Settings(
            environment="production",
            jwt_secret_key="change-this-secret-in-production",
            allowed_hosts="*",
            force_https=False,
        )

    settings = Settings(
        environment="production",
        jwt_secret_key="segredo-de-producao-exclusivo-com-mais-de-trinta-e-dois-caracteres",
        allowed_hosts="meteoro.betim.mg.gov.br",
        force_https=True,
    )
    assert settings.force_https is True


def test_audit_endpoint_filters_events_without_crossing_organization(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    headers = bootstrap_admin(client)
    session: Session = session_factory()
    try:
        now = datetime.now(tz=timezone.utc)
        admin_login = "admin@example.org"
        organization_id = client.get("/api/v1/auth/me", headers=headers).json()["organization_id"]
        audit_service.create_event(
            session,
            module="quality",
            action="review",
            actor=admin_login,
            organization_id=organization_id,
            resource_type="quality_issue",
            resource_id="issue-001",
            reason="Revisão de teste",
        )
        audit_service.create_event(
            session,
            module="ingestion",
            action="run",
            actor="worker",
            organization_id=organization_id,
            resource_type="job",
            resource_id="job-001",
        )
    finally:
        session.close()

    response = client.get(
        "/api/v1/audit/events",
        headers=headers,
        params={
            "module": "quality",
            "action": "review",
            "resource_id": "issue-001",
            "occurred_from": (now - timedelta(minutes=1)).isoformat(),
        },
    )
    assert response.status_code == 200, response.text
    assert len(response.json()) == 1
    assert response.json()[0]["reason"] == "Revisão de teste"


def test_health_response_has_baseline_security_headers(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"

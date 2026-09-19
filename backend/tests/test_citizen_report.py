"""Canal público de denúncia e relato (SEMMAD)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.settings import settings
from app.modules.identity.models import UserModel
from app.modules.incidents.models import IncidentReportModel
from tests.conftest import bootstrap_admin


@pytest.fixture()
def public_client(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> TestClient:
    """Portal público apontando para a organização criada no bootstrap."""
    bootstrap_admin(client)
    session = session_factory()
    try:
        admin = session.scalar(select(UserModel).where(UserModel.email == "admin@example.org"))
        monkeypatch.setattr(settings, "public_organization_id", admin.organization_id)
    finally:
        session.close()
    return client


def _payload(**overrides) -> dict:
    base = {
        "category": "queimada_recorrente",
        "description": "Queimada se repete todo fim de semana no terreno da esquina.",
        "neighborhood": "Bandeirinhas",
    }
    base.update(overrides)
    return base


def test_relato_gera_protocolo_e_entra_na_triagem(
    public_client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    response = public_client.post("/api/v1/public/incident-report", json=_payload())
    assert response.status_code == 201, response.text
    corpo = response.json()
    assert corpo["protocol"]
    assert "SEMMAD" in corpo["detail"]
    assert "193" in corpo["disclaimer"]

    session = session_factory()
    try:
        registro = session.scalar(select(IncidentReportModel))
        assert registro is not None
        assert registro.triage_status == "pending"
        assert registro.category_code == "queimada_recorrente"
        assert registro.report_origin == "citizen"
    finally:
        session.close()


def test_relato_com_coordenada_preserva_geometria(
    public_client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    response = public_client.post(
        "/api/v1/public/incident-report",
        json=_payload(latitude=-19.9676, longitude=-44.1983),
    )
    assert response.status_code == 201, response.text
    session = session_factory()
    try:
        registro = session.scalar(select(IncidentReportModel))
        assert registro.location_geojson is not None
        assert "-44.19" in registro.location_geojson
    finally:
        session.close()


def test_categoria_invalida_e_rejeitada(public_client: TestClient) -> None:
    response = public_client.post(
        "/api/v1/public/incident-report", json=_payload(category="assunto_qualquer")
    )
    assert response.status_code == 422


def test_descricao_curta_e_rejeitada(public_client: TestClient) -> None:
    response = public_client.post("/api/v1/public/incident-report", json=_payload(description="fogo"))
    assert response.status_code == 422


def test_coordenada_fora_da_regiao_e_rejeitada(public_client: TestClient) -> None:
    response = public_client.post(
        "/api/v1/public/incident-report",
        json=_payload(latitude=-23.55, longitude=-46.63),  # São Paulo
    )
    assert response.status_code == 422


def test_monitoring_points_publico_responde(public_client: TestClient) -> None:
    response = public_client.get("/api/v1/public/monitoring-points")
    assert response.status_code == 200
    corpo = response.json()
    assert "points" in corpo and "generated_at_utc" in corpo

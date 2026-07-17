from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from tests.conftest import bootstrap_admin, create_authority_headers, create_role_headers


def _create_recommendation(client: TestClient, headers: dict[str, str]) -> dict:
    response = client.post(
        "/api/v1/recommendations/",
        headers=headers,
        json={
            "title": "Hidratação em período seco",
            "audience": "cidadãos",
            "criteria": {"hazard": "baixa_umidade"},
            "content": {"citizen_text": "Beba água regularmente."},
            "change_reason": "Primeira versão técnica.",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_recommendation_requires_segregated_approval_then_publication(
    client: TestClient,
    session_factory: sessionmaker,
) -> None:
    admin_headers = bootstrap_admin(client)
    recommendation = _create_recommendation(client, admin_headers)

    own_approval = client.post(
        f"/api/v1/recommendations/{recommendation['recommendation_revision_id']}/approve",
        headers=admin_headers,
        json={},
    )
    assert own_approval.status_code == 403

    authority_headers = create_authority_headers(session_factory)
    approved = client.post(
        f"/api/v1/recommendations/{recommendation['recommendation_revision_id']}/approve",
        headers=authority_headers,
        json={"reason": "Revisão técnica concluída."},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert approved.json()["approved_by"] == "autoridade@example.org"

    published = client.post(
        f"/api/v1/recommendations/{recommendation['recommendation_revision_id']}/publish",
        headers=admin_headers,
        json={"reason": "Publicação no portal municipal."},
    )
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "published"
    assert published.json()["published_by"] == "admin@example.org"


def test_operator_cannot_approve_recommendation(
    client: TestClient,
    session_factory: sessionmaker,
) -> None:
    admin_headers = bootstrap_admin(client)
    recommendation = _create_recommendation(client, admin_headers)
    operator_headers = create_role_headers(
        session_factory, email="operador-recomendacao@example.org", role_name="operator"
    )
    response = client.post(
        f"/api/v1/recommendations/{recommendation['recommendation_revision_id']}/approve",
        headers=operator_headers,
        json={},
    )
    assert response.status_code == 403

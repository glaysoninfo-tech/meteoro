from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from tests.conftest import bootstrap_admin, create_authority_headers, create_role_headers


def test_protocol_requires_a_different_authority_for_approval(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    admin_headers = bootstrap_admin(client)
    authority_headers = create_authority_headers(session_factory)
    protocol = client.post(
        "/api/v1/alerts/protocols",
        headers=admin_headers,
        json={
            "protocol_name": "Resposta a calor extremo",
            "version": "1.0",
            "status": "active",
            "trigger_type": "official_alert",
            "action_steps_json": '[{"action":"avisar defesa civil"}]',
            "requires_authority_approval": True,
        },
    )
    assert protocol.status_code == 200, protocol.text

    activation = client.post(
        f"/api/v1/alerts/protocols/{protocol.json()['protocol_id']}/activate",
        headers=admin_headers,
        json={"severity": "high", "trigger_reason": "temperatura extrema"},
    )
    assert activation.status_code == 200, activation.text

    same_person = client.post(
        f"/api/v1/alerts/protocol-activations/{activation.json()['activation_id']}/approve",
        headers=admin_headers,
        json={},
    )
    assert same_person.status_code == 403

    approved = client.post(
        f"/api/v1/alerts/protocol-activations/{activation.json()['activation_id']}/approve",
        headers=authority_headers,
        json={},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "active"
    assert approved.json()["approved_by"] == "autoridade@example.org"


def test_approval_endpoint_rejects_operator_without_authority_role(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    bootstrap_admin(client)
    operator_headers = create_role_headers(
        session_factory,
        email="operador@example.org",
        role_name="operator",
    )
    response = client.post(
        "/api/v1/alerts/protocol-activations/not-found/approve",
        headers=operator_headers,
        json={},
    )
    assert response.status_code == 403


def test_protocol_update_creates_immutable_new_revision_and_audit_snapshot(client: TestClient) -> None:
    headers = bootstrap_admin(client)
    original = client.post(
        "/api/v1/alerts/protocols",
        headers=headers,
        json={
            "protocol_name": "Resposta a enxurrada",
            "version": "1.0",
            "status": "active",
            "trigger_type": "official_alert",
            "action_steps_json": '[{"action":"monitorar"}]',
            "requires_authority_approval": True,
        },
    )
    assert original.status_code == 200, original.text

    revision = client.patch(
        f"/api/v1/alerts/protocols/{original.json()['protocol_id']}",
        headers=headers,
        json={
            "version": "1.1",
            "status": "active",
            "action_steps_json": '[{"action":"acionar defesa civil"}]',
            "change_reason": "Ajuste após simulado municipal.",
        },
    )
    assert revision.status_code == 200, revision.text
    assert revision.json()["protocol_id"] != original.json()["protocol_id"]
    assert revision.json()["revision_number"] == 2
    assert revision.json()["supersedes_protocol_id"] == original.json()["protocol_id"]
    assert revision.json()["content_hash"] != original.json()["content_hash"]

    protocols = client.get("/api/v1/alerts/protocols", headers=headers)
    original_after = next(item for item in protocols.json() if item["protocol_id"] == original.json()["protocol_id"])
    assert original_after["status"] == "superseded"

    audit_events = client.get("/api/v1/audit/events", headers=headers)
    revision_event = next(
        event
        for event in audit_events.json()
        if event["resource_id"] == revision.json()["protocol_id"]
    )
    assert revision_event["after_state_json"] is not None
    assert revision_event["reason"] == "Ajuste após simulado municipal."

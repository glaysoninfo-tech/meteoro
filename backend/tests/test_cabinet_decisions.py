from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import bootstrap_admin


def test_cabinet_decision_has_owner_deadline_and_audit_trail(client: TestClient) -> None:
    headers = bootstrap_admin(client)
    created = client.post(
        "/api/v1/planning/cabinet/decisions",
        headers=headers,
        json={
            "risk_key": "alert:abc:centro",
            "territory": "Centro",
            "decision": "Acionar equipe de campo.",
            "responsible_action": "Coordenar resposta local.",
            "responsible_role": "Defesa Civil",
            "deadline_utc": "2026-07-15T12:00:00Z",
            "status": "open",
            "notes": "Decisão registrada em reunião extraordinária.",
        },
    )
    assert created.status_code == 201, created.text
    decision = created.json()
    assert decision["status"] == "open"
    assert decision["responsible_role"] == "Defesa Civil"

    completed = client.patch(
        f"/api/v1/planning/cabinet/decisions/{decision['decision_id']}",
        headers=headers,
        json={"status": "completed", "notes": "Ação concluída e registrada."},
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["completed_at_utc"] is not None

    events = client.get(
        "/api/v1/audit/events",
        headers=headers,
        params={"resource_id": decision["decision_id"], "resource_type": "cabinet_decision"},
    )
    assert events.status_code == 200, events.text
    assert {event["action"] for event in events.json()} == {
        "cabinet.decision_created",
        "cabinet.decision_updated",
    }

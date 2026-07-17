from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import bootstrap_admin


def test_audit_events_can_be_filtered_by_resource(client: TestClient) -> None:
    headers = bootstrap_admin(client)
    current_user = client.get("/api/v1/auth/me", headers=headers)
    assert current_user.status_code == 200, current_user.text

    response = client.get(
        "/api/v1/audit/events",
        headers=headers,
        params={
            "resource_id": current_user.json()["user_id"],
            "resource_type": "user",
            "limit": 10,
        },
    )

    assert response.status_code == 200, response.text
    events = response.json()
    assert events
    assert all(event["resource_id"] == current_user.json()["user_id"] for event in events)
    assert all(event["resource_type"] == "user" for event in events)

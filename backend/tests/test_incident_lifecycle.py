from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import bootstrap_admin


def test_confirmed_report_becomes_incident_with_actions_and_controlled_closure(client: TestClient) -> None:
    headers = bootstrap_admin(client)
    source = client.post(
        "/api/v1/catalog/sources",
        headers=headers,
        json={
            "institution_name": "Defesa Civil",
            "source_name": "Ocorrências municipais",
            "source_type": "incident_report",
            "access_method": "manual_file",
            "authentication_type": "none",
            "endpoint_reference": "manual://ocorrencias.json",
            "expected_frequency_minutes": 15,
            "criticality": "high",
        },
    )
    assert source.status_code == 201, source.text
    imported = client.post(
        f"/api/v1/ingestion/runs/import/source/{source.json()['source_id']}",
        headers=headers,
        files={
            "file": (
                "ocorrencias.json",
                b'[{"reported_at":"2026-07-14T12:00:00Z","origin":"inspection",'
                b'"category":"smoke","severity":"high","description":"Fumaca densa",'
                b'"location":"Petrovale","protocol":"DC-001"}]',
                "application/json",
            )
        },
    )
    assert imported.status_code == 200, imported.text
    report = client.get("/api/v1/incidents/reports", headers=headers).json()[0]

    unconfirmed = client.post(
        f"/api/v1/incidents/reports/{report['report_id']}/convert",
        headers=headers,
        json={"incident_type": "smoke", "responsible_name": "Defesa Civil"},
    )
    assert unconfirmed.status_code == 409

    confirmed = client.post(
        f"/api/v1/incidents/reports/{report['report_id']}/confirm",
        headers=headers,
        json={"confirmation_status": "confirmed", "evidence_json": '{"inspection_id":"VIST-1"}'},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["confirmation_status"] == "confirmed"

    incident = client.post(
        f"/api/v1/incidents/reports/{report['report_id']}/convert",
        headers=headers,
        json={"incident_type": "smoke", "severity": "high", "responsible_name": "Defesa Civil"},
    )
    assert incident.status_code == 201, incident.text

    action = client.post(
        f"/api/v1/incidents/cases/{incident.json()['incident_id']}/actions",
        headers=headers,
        json={"title": "Vistoriar local", "responsible_name": "Equipe de campo"},
    )
    assert action.status_code == 201, action.text

    premature_close = client.post(
        f"/api/v1/incidents/cases/{incident.json()['incident_id']}/close",
        headers=headers,
        json={"closure_notes": "Tentativa antes da vistoria."},
    )
    assert premature_close.status_code == 409

    completed = client.patch(
        f"/api/v1/incidents/actions/{action.json()['action_id']}",
        headers=headers,
        json={"status": "completed", "notes": "Vistoria concluída."},
    )
    assert completed.status_code == 200, completed.text

    closed = client.post(
        f"/api/v1/incidents/cases/{incident.json()['incident_id']}/close",
        headers=headers,
        json={"closure_notes": "Providência executada e risco encerrado."},
    )
    assert closed.status_code == 200, closed.text
    assert closed.json()["status"] == "closed"

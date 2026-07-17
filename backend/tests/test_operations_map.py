from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from tests.conftest import bootstrap_admin


def test_operational_map_keeps_supplied_geometries_and_never_estimates_incident_locations(client: TestClient) -> None:
    headers = bootstrap_admin(client)
    territory = client.post(
        "/api/v1/geospatial/territories",
        headers=headers,
        json={
            "territory_code": "BETIM-CENTRO", "territory_name": "Centro", "territory_type": "bairro",
            "geometry_geojson": {"type": "Polygon", "coordinates": [[[-44.22, -19.98], [-44.18, -19.98], [-44.18, -19.95], [-44.22, -19.95], [-44.22, -19.98]]]},
        },
    )
    assert territory.status_code == 201, territory.text
    station = client.post(
        "/api/v1/geospatial/stations",
        headers=headers,
        json={
            "territory_id": territory.json()["territory_id"], "station_code": "EST-01", "station_name": "Estação Centro", "station_type": "air_quality",
            "location_geojson": {"type": "Point", "coordinates": [-44.1983, -19.9676]},
        },
    )
    assert station.status_code == 201, station.text
    source = client.post(
        "/api/v1/catalog/sources",
        headers=headers,
        json={
            "institution_name": "SEMMAD", "source_name": "Ocorrências de campo", "source_type": "incident_report",
            "access_method": "manual_file", "authentication_type": "none", "endpoint_reference": "manual://reports.json",
            "expected_frequency_minutes": 60, "criticality": "medium",
        },
    )
    assert source.status_code == 201, source.text
    payload = b'[{"reported_at":"2026-07-15T12:00:00Z","origin":"inspection","category":"smoke","severity":"high","description":"Fumaca observada","bairro":"Centro","latitude":-19.9676,"longitude":-44.1983}]'
    imported = client.post(
        f"/api/v1/ingestion/runs/import/source/{source.json()['source_id']}", headers=headers,
        files={"file": ("reports.json", payload, "application/json")},
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["records_accepted"] == 1
    now = datetime.now(tz=timezone.utc)
    alert = client.post(
        "/api/v1/alerts/official",
        headers=headers,
        json={
            "source_id": source.json()["source_id"], "issuer": "Defesa Civil", "alert_code": "CHUVA-001", "severity": "high",
            "issued_at_utc": now.isoformat(), "valid_from_utc": now.isoformat(), "valid_to_utc": (now + timedelta(hours=1)).isoformat(),
            "title": "Alerta de teste", "message": "Cobertura territorial.",
            "geometry_geojson": '{"type":"Polygon","coordinates":[[[-44.21,-19.98],[-44.19,-19.98],[-44.19,-19.96],[-44.21,-19.96],[-44.21,-19.98]]]}',
        },
    )
    assert alert.status_code == 200, alert.text
    result = client.get("/api/v1/operations/map", headers=headers)
    assert result.status_code == 200, result.text
    body = result.json()
    assert len(body["territories"]["features"]) == 1
    assert len(body["stations"]["features"]) == 1
    assert len(body["alerts"]["features"]) == 1
    assert len(body["incidents"]["features"]) == 1
    assert body["incidents"]["features"][0]["geometry"]["coordinates"] == [-44.1983, -19.9676]

from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from tests.conftest import bootstrap_admin


def test_station_health_keeps_valid_zero_and_exposes_gap_not_filled_zero(client: TestClient) -> None:
    headers = bootstrap_admin(client)
    station = client.post(
        "/api/v1/geospatial/stations",
        headers=headers,
        json={
            "station_code": "AQ-001",
            "station_name": "Estação Ar",
            "station_type": "air_quality",
            "location_geojson": {"type": "Point", "coordinates": [-44.2, -19.9]},
        },
    )
    assert station.status_code == 201, station.text
    sensor = client.post(
        "/api/v1/geospatial/sensors",
        headers=headers,
        json={
            "station_id": station.json()["station_id"],
            "sensor_code": "PM25-001",
            "sensor_name": "PM2.5",
            "variable_code": "pm25_ug_m3",
            "unit_canonical": "ug/m3",
        },
    )
    assert sensor.status_code == 201, sensor.text
    source = client.post(
        "/api/v1/catalog/sources",
        headers=headers,
        json={
            "institution_name": "MonitorAr",
            "source_name": "PM2.5 Estação Ar",
            "source_type": "sensor",
            "station_id": station.json()["station_id"],
            "sensor_id": sensor.json()["sensor_id"],
            "access_method": "manual_file",
            "authentication_type": "none",
            "endpoint_reference": "manual://pm25.json",
            "expected_frequency_minutes": 60,
            "criticality": "high",
        },
    )
    assert source.status_code == 201, source.text
    observed_at = datetime.now(tz=timezone.utc).isoformat()
    imported = client.post(
        f"/api/v1/ingestion/runs/import/source/{source.json()['source_id']}",
        headers=headers,
        files={
            "file": (
                "pm25.json",
                (
                    f'{{"observed_at":"{observed_at}","variable_code":"pm25_ug_m3",'
                    '"value":0,"unit":"ug/m3"}'
                ).encode(),
                "application/json",
            )
        },
    )
    assert imported.status_code == 200, imported.text

    health = client.get(
        f"/api/v1/geospatial/stations/{station.json()['station_id']}/health", headers=headers
    )
    assert health.status_code == 200, health.text
    sensor_health = health.json()["sensors"][0]
    assert sensor_health["latest_value"] == 0
    assert sensor_health["observations_24h"] == 1
    assert sensor_health["expected_observations_24h"] == 24
    assert sensor_health["has_data_gap"] is True
    assert sensor_health["state"] == "OPERATIONAL_WITH_RESTRICTION"

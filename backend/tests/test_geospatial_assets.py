from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import bootstrap_admin


def test_geospatial_assets_link_a_source_and_its_observations(client: TestClient) -> None:
    headers = bootstrap_admin(client)
    territory = client.post(
        "/api/v1/geospatial/territories",
        headers=headers,
        json={
            "territory_code": "CENTRO",
            "territory_name": "Centro",
            "territory_type": "neighborhood",
            "geometry_geojson": {
                "type": "Polygon",
                "coordinates": [[[-46.64, -23.56], [-46.63, -23.56], [-46.63, -23.55], [-46.64, -23.56]]],
            },
        },
    )
    assert territory.status_code == 201, territory.text

    station = client.post(
        "/api/v1/geospatial/stations",
        headers=headers,
        json={
            "territory_id": territory.json()["territory_id"],
            "station_code": "EST-001",
            "station_name": "Estação Centro",
            "station_type": "meteorological",
            "location_geojson": {"type": "Point", "coordinates": [-46.635, -23.555]},
        },
    )
    assert station.status_code == 201, station.text

    sensor = client.post(
        "/api/v1/geospatial/sensors",
        headers=headers,
        json={
            "station_id": station.json()["station_id"],
            "sensor_code": "TEMP-001",
            "sensor_name": "Termômetro",
            "variable_code": "temperature_c",
            "unit_canonical": "C",
        },
    )
    assert sensor.status_code == 201, sensor.text

    source = client.post(
        "/api/v1/catalog/sources",
        headers=headers,
        json={
            "institution_name": "Prefeitura",
            "source_name": "Sensor Centro",
            "source_type": "sensor",
            "access_method": "manual_file",
            "authentication_type": "none",
            "endpoint_reference": "manual://estacao-centro.json",
            "station_id": station.json()["station_id"],
            "sensor_id": sensor.json()["sensor_id"],
            "expected_frequency_minutes": 60,
            "criticality": "medium",
        },
    )
    assert source.status_code == 201, source.text

    uploaded = client.post(
        f"/api/v1/ingestion/runs/import/source/{source.json()['source_id']}",
        headers=headers,
        files={
            "file": (
                "estacao.json",
                b'[{"observed_at":"2026-07-14T12:00:00Z","variable_code":"temperature_c","value":25,"unit":"C"}]',
                "application/json",
            )
        },
    )
    assert uploaded.status_code == 200, uploaded.text
    observations = client.get("/api/v1/ingestion/observations/latest", headers=headers)
    assert observations.status_code == 200
    assert observations.json()[0]["station_id"] == station.json()["station_id"]
    assert observations.json()[0]["sensor_id"] == sensor.json()["sensor_id"]

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.settings import settings
from app.modules.identity.models import UserModel
from tests.conftest import bootstrap_admin


def test_public_api_exposes_only_explicitly_public_geospatial_records(
    client: TestClient,
    session_factory: sessionmaker,
    monkeypatch,
) -> None:
    headers = bootstrap_admin(client)
    session = session_factory()
    try:
        admin = session.scalar(select(UserModel).where(UserModel.email == "admin@example.org"))
        assert admin is not None
        monkeypatch.setattr(settings, "public_organization_id", admin.organization_id)
    finally:
        session.close()

    territory = client.post(
        "/api/v1/geospatial/territories",
        headers=headers,
        json={
            "territory_code": "PUB",
            "territory_name": "Território Público",
            "territory_type": "neighborhood",
            "visibility": "public",
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
            "station_code": "PUB-001",
            "station_name": "Estação pública",
            "station_type": "meteorological",
            "visibility": "public",
            "location_geojson": {"type": "Point", "coordinates": [-46.635, -23.555]},
        },
    )
    assert station.status_code == 201, station.text
    internal_station = client.post(
        "/api/v1/geospatial/stations",
        headers=headers,
        json={
            "station_code": "INT-001",
            "station_name": "Estação interna",
            "station_type": "meteorological",
            "location_geojson": {"type": "Point", "coordinates": [-46.635, -23.555]},
        },
    )
    assert internal_station.status_code == 201, internal_station.text

    public_stations = client.get("/api/v1/public/stations")
    assert public_stations.status_code == 200, public_stations.text
    assert [item["station_code"] for item in public_stations.json()] == ["PUB-001"]

    status = client.get(f"/api/v1/public/stations/{station.json()['station_id']}/status")
    assert status.status_code == 200, status.text
    assert status.json()["observed_at_utc"] is None

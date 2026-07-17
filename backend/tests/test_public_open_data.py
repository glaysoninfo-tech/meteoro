from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.settings import settings
from app.modules.identity.models import UserModel
from tests.conftest import bootstrap_admin


def test_public_open_data_exports_only_valid_observations_of_public_stations(
    client: TestClient, session_factory: sessionmaker, monkeypatch
) -> None:
    headers = bootstrap_admin(client)
    session = session_factory()
    try:
        admin = session.scalar(select(UserModel).where(UserModel.email == "admin@example.org"))
        assert admin is not None
        monkeypatch.setattr(settings, "public_organization_id", admin.organization_id)
    finally:
        session.close()
    station = client.post(
        "/api/v1/geospatial/stations",
        headers=headers,
        json={
            "station_code": "PUB-DATA",
            "station_name": "Estação aberta",
            "station_type": "meteorological",
            "visibility": "public",
            "location_geojson": {"type": "Point", "coordinates": [-44.2, -19.9]},
        },
    )
    assert station.status_code == 201, station.text
    source = client.post(
        "/api/v1/catalog/sources",
        headers=headers,
        json={
            "institution_name": "INMET",
            "source_name": "Leituras abertas",
            "source_type": "sensor",
            "station_id": station.json()["station_id"],
            "access_method": "manual_file",
            "authentication_type": "none",
            "endpoint_reference": "manual://public.json",
            "expected_frequency_minutes": 60,
            "criticality": "medium",
        },
    )
    assert source.status_code == 201, source.text
    observed_at = datetime.now(tz=timezone.utc).isoformat()
    imported = client.post(
        f"/api/v1/ingestion/runs/import/source/{source.json()['source_id']}",
        headers=headers,
        files={
            "file": (
                "public.json",
                f'{{"observed_at":"{observed_at}","variable_code":"temperature_c","value":0,"unit":"C"}}'.encode(),
                "application/json",
            )
        },
    )
    assert imported.status_code == 200, imported.text

    payload = client.get("/api/v1/public/open-data/observations")
    assert payload.status_code == 200, payload.text
    assert payload.json()["total"] == 1
    assert payload.json()["items"][0]["value"] == 0
    assert payload.json()["items"][0]["station_code"] == "PUB-DATA"

    csv_export = client.get("/api/v1/public/open-data/observations.csv")
    assert csv_export.status_code == 200, csv_export.text
    assert "PUB-DATA" in csv_export.text
    assert "quality_status" in csv_export.text

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import bootstrap_admin


def test_forecast_and_station_reports_have_json_csv_and_pdf_outputs(client: TestClient) -> None:
    headers = bootstrap_admin(client)
    station = client.post(
        "/api/v1/geospatial/stations",
        headers=headers,
        json={
            "station_code": "EST-REPORT",
            "station_name": "Estação de Relatório",
            "station_type": "meteorological",
            "location_geojson": {"type": "Point", "coordinates": [-44.2, -19.97]},
        },
    )
    assert station.status_code == 201, station.text
    sensor = client.post(
        "/api/v1/geospatial/sensors",
        headers=headers,
        json={
            "station_id": station.json()["station_id"],
            "sensor_code": "TEMP-REPORT",
            "sensor_name": "Temperatura",
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
            "source_name": "Fonte de Relatório",
            "source_type": "sensor",
            "access_method": "manual_file",
            "authentication_type": "none",
            "endpoint_reference": "manual://estacao-relatorio.json",
            "station_id": station.json()["station_id"],
            "sensor_id": sensor.json()["sensor_id"],
            "expected_frequency_minutes": 60,
            "criticality": "medium",
        },
    )
    assert source.status_code == 201, source.text
    upload = client.post(
        f"/api/v1/ingestion/runs/import/source/{source.json()['source_id']}",
        headers=headers,
        files={
            "file": (
                "series.json",
                b'[{"observed_at":"2026-07-14T10:00:00Z","variable_code":"temperature_c","value":24,"unit":"C"},{"observed_at":"2026-07-14T11:00:00Z","variable_code":"temperature_c","value":25,"unit":"C"},{"observed_at":"2026-07-14T12:00:00Z","variable_code":"temperature_c","value":26,"unit":"C"}]',
                "application/json",
            )
        },
    )
    assert upload.status_code == 200, upload.text

    forecast = client.get(
        "/api/v1/meteorology/forecast?issued_at_utc=2026-07-14T12:00:00Z&horizon_hours=12&step_hours=6",
        headers=headers,
    )
    assert forecast.status_code == 200, forecast.text
    assert forecast.json()["horizon_hours"] == 12
    assert forecast.json()["series"][0]["points"][0]["risk_level"] == "normal"

    query = "period_start_utc=2026-07-14T09:00:00Z&period_end_utc=2026-07-14T13:00:00Z"
    availability = client.get(f"/api/v1/planning/stations/availability?{query}", headers=headers)
    assert availability.status_code == 200, availability.text
    assert availability.json()["stations"][0]["station_code"] == "EST-REPORT"
    assert availability.json()["stations"][0]["completeness_percent"] == 75.0

    csv_output = client.get(f"/api/v1/planning/stations/availability.csv?{query}", headers=headers)
    assert csv_output.status_code == 200
    assert "EST-REPORT" in csv_output.text
    pdf_output = client.get(f"/api/v1/planning/stations/availability.pdf?{query}", headers=headers)
    assert pdf_output.status_code == 200
    assert pdf_output.headers["content-type"].startswith("application/pdf")
    assert pdf_output.content.startswith(b"%PDF-")

    committee_pdf = client.get(
        "/api/v1/planning/committee/climate-report.pdf?period_start_utc=2026-07-14T09:00:00Z&period_end_utc=2026-07-14T13:00:00Z",
        headers=headers,
    )
    assert committee_pdf.status_code == 200
    assert committee_pdf.content.startswith(b"%PDF-")
    committee_csv = client.get(
        "/api/v1/planning/committee/climate-report.csv?period_start_utc=2026-07-14T09:00:00Z&period_end_utc=2026-07-14T13:00:00Z",
        headers=headers,
    )
    assert committee_csv.status_code == 200
    assert "temperature_c" in committee_csv.text

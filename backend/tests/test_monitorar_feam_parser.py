from datetime import datetime, timezone
from types import SimpleNamespace

from app.modules.ingestion.parsers import _parse_inmet, _parse_monitorar_feam, _parse_open_meteo, _parse_redemet_metar, _parse_redemet_status, _load_records
from app.modules.ingestion.connectors import SourcePayload


def test_monitorar_parser_preserves_station_and_pollutants() -> None:
    observations = _parse_monitorar_feam(
        [
            {
                "codigo_estacao": "ALTEROSA",
                "data_hora": "2026-07-15T12:00:00-03:00",
                "PM2.5": "12,4",
                "PM10": 21.0,
                "o3": 45.0,
            }
        ]
    )

    assert {(item.variable_code, item.value_canonical, item.location_code) for item in observations} == {
        ("pm25_ugm3", 12.4, "ALTEROSA"),
        ("pm10_ugm3", 21.0, "ALTEROSA"),
        ("o3_ugm3", 45.0, "ALTEROSA"),
    }
    assert all(item.observed_at_utc == datetime(2026, 7, 15, 15, tzinfo=timezone.utc) for item in observations)
    assert all(item.unit_canonical == "µg/m³" for item in observations)


def test_geojson_feature_collection_is_unwrapped_for_monitorar_payloads() -> None:
    payload = SourcePayload(
        content_bytes=(
            b'{"features":[{"type":"Feature","properties":{"station_code":"PETROVALE",'
            b'"timestamp":"2026-07-15T15:00:00Z","poluente":"MP10","valor":31,"unidade":"ug/m3"}}]}'
        ),
        content_type="application/geo+json",
        source_timestamp=None,
        metadata_json=None,
    )

    records = _load_records(payload=payload, endpoint_reference="https://dados.oficiais.example/monitorar.geojson")
    observations = _parse_monitorar_feam(records)

    assert records[0]["station_code"] == "PETROVALE"
    assert len(observations) == 1
    assert observations[0].variable_code == "pm10_ugm3"
    assert observations[0].location_code == "PETROVALE"


def test_inmet_csv_export_uses_date_time_utc_and_configured_station_code() -> None:
    source = SimpleNamespace(
        institution_name="INMET",
        source_name="Dados horários Pampulha",
        source_type="meteorology",
        access_method="manual_file",
        connector_config_json='{"parser":"inmet","station_code":"SBBH"}',
    )
    observations = _parse_inmet(
        [
            {
                "Data": "29/01/2026",
                "Hora (UTC)": "0000",
                "Temp. Ins. (C)": "23,3",
                "Umi. Ins. (%)": "65,0",
                "Vel. Vento (m/s)": "1,9",
                "Chuva (mm)": "0,0",
            }
        ],
        source=source,
    )

    assert [item.variable_code for item in observations] == [
        "temperature_c", "humidity_pct", "rainfall_mm_1h", "wind_speed_mps"
    ]
    assert all(item.location_code == "SBBH" for item in observations)
    assert all(item.observed_at_utc == datetime(2026, 1, 29, tzinfo=timezone.utc) for item in observations)


def test_inmet_semicolon_csv_export_is_read_as_multiple_columns() -> None:
    payload = SourcePayload(
        content_bytes=(
            '"Data";"Hora (UTC)";"Temp. Ins. (C)";"Umi. Ins. (%)"\n'
            '"29/01/2026";"0000";"23,3";"65,0"\n'
        ).encode(),
        content_type="text/csv",
        source_timestamp=None,
        metadata_json=None,
    )

    records = _load_records(payload=payload, endpoint_reference="arquivo.csv")

    assert records == [{"Data": "29/01/2026", "Hora (UTC)": "0000", "Temp. Ins. (C)": "23,3", "Umi. Ins. (%)": "65,0"}]


def test_open_meteo_hourly_model_series_is_normalized_and_identified() -> None:
    source = SimpleNamespace(connector_config_json='{"parser":"open_meteo","station_code":"BETIM_MODEL_POINT"}')
    observations = _parse_open_meteo(
        [{
            "hourly": {
                "time": ["2026-07-15T12:00", "2026-07-15T13:00"],
                "temperature_2m": [22.5, 23.0],
                "relative_humidity_2m": [64, 61],
                "precipitation": [0.0, 0.2],
                "wind_speed_10m": [18.0, 7.2],
            }
        }],
        source=source,
    )

    assert len(observations) == 8
    assert {item.location_code for item in observations} == {"BETIM_MODEL_POINT"}
    wind = next(item for item in observations if item.variable_code == "wind_speed_mps")
    assert wind.value_canonical == 5.0
    assert all(item.observed_at_utc.tzinfo == timezone.utc for item in observations)


def test_redemet_status_and_metar_parsers_keep_aviation_context() -> None:
    status = _parse_redemet_status([{"icao": "SBBH", "status": "y"}, {"icao": "SNDV", "status": "r"}])
    assert [(item.location_code, item.value_canonical) for item in status] == [("SBBH", 1.0), ("SNDV", 2.0)]
    metar = _parse_redemet_metar(
        [{"id_localidade": "SBBH", "validade_inicial": "2026-07-15 12:00:00", "mens": "METAR SBBH 151200Z 09010KT 9999 FEW020 23/14 Q1018="}],
        source=SimpleNamespace(connector_config_json='{"station_code":"SBBH"}'),
    )
    values = {item.variable_code: item for item in metar}
    assert values["temperature_c"].value_canonical == 23.0
    assert round(values["wind_speed_mps"].value_canonical, 3) == 5.144
    assert values["visibility_m"].value_canonical == 9999.0

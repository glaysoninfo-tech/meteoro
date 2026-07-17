from __future__ import annotations

from types import SimpleNamespace

from app.modules.ingestion.connectors import SourcePayload
from app.modules.ingestion.parsers import parse_source_payload


def test_bdmep_parser_normalizes_local_timestamp_and_weather_fields() -> None:
    source = SimpleNamespace(
        institution_name="INMET", source_name="BDMEP manual",
        source_type="inmet_bdmep_manual", access_method="manual_file",
        endpoint_reference="manual://inmet-bdmep",
    )
    payload = SourcePayload(
        content_bytes=(
            "CD_ESTACAO;DATA_MEDICAO;HORA_MEDICAO;TEMPERATURA DO AR - BULBO SECO;"
            "UMIDADE RELATIVA;PRECIPITACAO TOTAL HORARIO;VELOCIDADE DO VENTO\n"
            "A001;2026-07-14;0900;24,5;61;2,4;3,6\n"
        ).encode("utf-8"),
        content_type="text/csv", source_timestamp=None, metadata_json=None,
    )
    observations = parse_source_payload(source, payload)
    by_variable = {item.variable_code: item for item in observations}
    assert by_variable["temperature_c"].value_canonical == 24.5
    assert by_variable["humidity_pct"].value_canonical == 61
    assert by_variable["rainfall_mm_1h"].value_canonical == 2.4
    assert by_variable["wind_speed_mps"].value_canonical == 3.6
    assert by_variable["temperature_c"].observed_at_utc.hour == 12

"""Regressão: horas futuras do Open-Meteo não viram observação.

As horas de previsão permanecem no payload bruto (consumidas por
public/model_forecast); somente horas já ocorridas entram no pipeline de
observações — evitando a inundação da fila de qualidade com timestamp_future.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from app.modules.catalog.models import SourceModel
from app.modules.ingestion.connectors import SourcePayload
from app.modules.ingestion.parsers import parse_source_payload


def _source() -> SourceModel:
    return SourceModel(
        organization_id="org-teste",
        institution_name="Open-Meteo",
        source_name="Betim — modelo horário",
        source_type="meteorology_model",
        access_method="http",
        authentication_type="none",
        endpoint_reference="https://api.open-meteo.com/v1/forecast?latitude=-19.96",
        connector_config_json=json.dumps(
            {"parser": "open_meteo", "station_code": "BETIM_MODEL_POINT"}
        ),
        status="active",
        expected_frequency_minutes=60,
        criticality="low",
    )


def test_horas_futuras_sao_descartadas() -> None:
    now = datetime.now(tz=timezone.utc).replace(minute=0, second=0, microsecond=0)
    past = (now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
    future = (now + timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M")
    body = {
        "hourly": {
            "time": [past, future],
            "temperature_2m": [21.5, 30.0],
            "relative_humidity_2m": [60, 40],
            "precipitation": [0.0, 5.0],
            "wind_speed_10m": [10.0, 50.0],
        }
    }
    payload = SourcePayload(
        content_bytes=json.dumps(body).encode("utf-8"),
        content_type="application/json",
        source_timestamp=None,
        metadata_json=None,
    )
    observations = parse_source_payload(source=_source(), payload=payload)
    assert observations, "hora passada deveria gerar observações"
    limite = datetime.now(tz=timezone.utc) + timedelta(minutes=5)
    assert all(item.observed_at_utc <= limite for item in observations)
    # 4 variáveis da hora passada; nada da hora futura.
    assert len(observations) == 4

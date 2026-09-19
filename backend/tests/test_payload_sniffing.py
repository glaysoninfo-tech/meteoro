"""Detecção de formato quando o servidor não declara Content-Type confiável.

A API do INMET responde JSON como application/octet-stream; sem a dedução por
conteúdo, as estações automáticas nunca são ingeridas.
"""

from __future__ import annotations

import json

from app.modules.catalog.models import SourceModel
from app.modules.ingestion.connectors import SourcePayload
from app.modules.ingestion.parsers import parse_source_payload


def _inmet_source() -> SourceModel:
    return SourceModel(
        organization_id="org-teste",
        institution_name="INMET",
        source_name="INMET — estação automática A555 (Ibirité — Rola-Moça)",
        source_type="weather_station_observation",
        access_method="http",
        authentication_type="none",
        endpoint_reference="https://apitempo.inmet.gov.br/estacao/2026-07-18/2026-07-19/A555",
        connector_config_json=json.dumps({"parser": "inmet", "station_code": "A555"}),
        status="active",
        expected_frequency_minutes=60,
        criticality="medium",
    )


def _payload(body: str, content_type: str) -> SourcePayload:
    return SourcePayload(
        content_bytes=body.encode("utf-8"),
        content_type=content_type,
        source_timestamp=None,
        metadata_json=None,
    )


def test_json_sem_content_type_correto_e_reconhecido() -> None:
    corpo = json.dumps([
        {
            "CD_ESTACAO": "A555",
            "DT_MEDICAO": "2026-07-18",
            "HR_MEDICAO": "1200",
            "TEM_INS": "21.4",
            "UMD_INS": "58",
            "CHUVA": "0",
            "VEN_VEL": "2.3",
            "VL_LATITUDE": "-20.0316",
            "VL_LONGITUDE": "-44.0114",
        }
    ])
    observations = parse_source_payload(
        source=_inmet_source(),
        payload=_payload(corpo, "application/octet-stream"),
    )
    assert observations, "payload JSON deveria ser reconhecido mesmo sem content-type"
    codigos = {item.variable_code for item in observations}
    assert "temperature_c" in codigos
    assert all(item.location_code == "A555" for item in observations)


def test_csv_sem_content_type_correto_e_reconhecido() -> None:
    corpo = "CD_ESTACAO;DT_MEDICAO;HR_MEDICAO;TEM_INS;UMD_INS\nA555;2026-07-18;1200;21.4;58\n"
    observations = parse_source_payload(
        source=_inmet_source(),
        payload=_payload(corpo, "application/octet-stream"),
    )
    assert observations
    assert {item.variable_code for item in observations} >= {"temperature_c", "humidity_pct"}


def test_formato_realmente_desconhecido_ainda_falha() -> None:
    observations_error = None
    try:
        parse_source_payload(
            source=_inmet_source(),
            payload=_payload("conteudo binario qualquer", "application/octet-stream"),
        )
    except ValueError as exc:
        observations_error = str(exc)
    assert observations_error is not None
    assert "não suportado" in observations_error

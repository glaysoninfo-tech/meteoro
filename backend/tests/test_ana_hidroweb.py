"""Conector ANA HidroWeb: parser de telemetria fluviométrica e instalação."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.modules.catalog.models import SourceModel
from app.modules.ingestion.connectors import SourcePayload, _apply_date_placeholders
from app.modules.ingestion.parsers import parse_source_payload
from tests.conftest import bootstrap_admin


def _source() -> SourceModel:
    return SourceModel(
        organization_id="org-teste",
        institution_name="ANA / HidroWeb Telemetria",
        source_name="ANA — telemetria fluviométrica 40800001",
        source_type="hydrology_telemetry",
        access_method="http",
        authentication_type="none",
        endpoint_reference=(
            "https://telemetriaws1.ana.gov.br/ServiceANA.asmx/DadosHidrometeorologicos"
            "?CodEstacao=40800001&DataInicio={DATA_ONTEM_BR}&DataFim={DATA_HOJE_BR}"
        ),
        connector_config_json=json.dumps(
            {"parser": "ana_hidroweb", "station_code": "ANA_40800001", "timezone_offset_hours": -3}
        ),
        status="active",
        expected_frequency_minutes=60,
        criticality="high",
    )


def _xml(nivel_cm: str, data_hora: str) -> bytes:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<DataTable xmlns="http://MRCS/">
  <DocumentElement>
    <DadosHidrometereologicos>
      <CodEstacao>40800001</CodEstacao>
      <DataHora>{data_hora}</DataHora>
      <Vazao>125,4</Vazao>
      <Nivel>{nivel_cm}</Nivel>
      <Chuva>0,2</Chuva>
    </DadosHidrometereologicos>
    <DadosHidrometereologicos>
      <CodEstacao>40800001</CodEstacao>
      <DataHora>{data_hora}</DataHora>
      <Vazao></Vazao>
      <Nivel></Nivel>
      <Chuva></Chuva>
    </DadosHidrometereologicos>
  </DocumentElement>
</DataTable>""".encode("utf-8")


def test_parser_ana_converte_nivel_cm_para_metros() -> None:
    agora_local = datetime.now(tz=timezone(timedelta(hours=-3))) - timedelta(hours=2)
    data_hora = agora_local.strftime("%Y-%m-%d %H:%M:%S")
    payload = SourcePayload(
        content_bytes=_xml("245", data_hora),
        content_type="text/xml",
        source_timestamp=None,
        metadata_json=None,
    )
    observations = parse_source_payload(source=_source(), payload=payload)
    por_variavel = {item.variable_code: item for item in observations}
    assert set(por_variavel) == {"river_level_m", "river_flow_m3s", "rainfall_mm_1h"}
    nivel = por_variavel["river_level_m"]
    assert nivel.value_original == 245.0
    assert nivel.value_canonical == 2.45  # cm -> m (alimenta river_level_high/critical)
    assert nivel.unit_canonical == "m"
    assert por_variavel["river_flow_m3s"].value_canonical == 125.4
    # Registro vazio (estação sem transmissão no horário) é ignorado sem erro.
    assert len(observations) == 3
    # Fuso: -3 convertido para UTC.
    assert nivel.observed_at_utc.tzinfo is not None


def test_placeholders_de_data_sao_substituidos() -> None:
    url = _apply_date_placeholders(
        "https://x/?DataInicio={DATA_ONTEM_BR}&DataFim={DATA_HOJE_BR}"
    )
    assert "{DATA" not in url
    hoje = datetime.now(tz=timezone.utc).strftime("%d/%m/%Y")
    assert hoje in url


def test_instalacao_de_perfis_ana(client: TestClient) -> None:
    headers = bootstrap_admin(client)
    response = client.post(
        "/api/v1/catalog/sources/profiles/ana-hidroweb",
        headers=headers,
        json={"station_codes": ["40800001", "40850000"]},
    )
    assert response.status_code == 200, response.text
    nomes = [item["source_name"] for item in response.json()]
    assert "ANA — telemetria fluviométrica 40800001" in nomes
    assert len(nomes) == 2


def test_instalacao_rejeita_codigo_invalido(client: TestClient) -> None:
    headers = bootstrap_admin(client)
    response = client.post(
        "/api/v1/catalog/sources/profiles/ana-hidroweb",
        headers=headers,
        json={"station_codes": ["abc123"]},
    )
    assert response.status_code == 400
    assert "inválido" in response.json()["detail"]

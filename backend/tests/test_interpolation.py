"""Interpolação IDW das condições de Betim a partir das estações da região."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session, sessionmaker

from app.modules.catalog.models import SourceModel
from app.modules.ingestion.models import ObservationModel
from app.modules.meteorology.service import meteorology_service


def _fonte(session: Session, org: str, nome: str, lat: float, lon: float) -> SourceModel:
    fonte = SourceModel(
        organization_id=org,
        institution_name="Teste",
        source_name=nome,
        source_type="weather_station_observation",
        access_method="http",
        authentication_type="none",
        endpoint_reference=f"https://api.exemplo.org/forecast?latitude={lat}&longitude={lon}",
        connector_config_json=json.dumps({"parser": "open_meteo", "station_code": nome}),
        status="active",
        expected_frequency_minutes=60,
        criticality="low",
    )
    session.add(fonte)
    session.flush()
    return fonte


def _obs(session: Session, org: str, fonte: SourceModel, variavel: str, valor: float) -> None:
    session.add(ObservationModel(
        organization_id=org,
        source_id=fonte.source_id,
        ingestion_run_id="run",
        raw_asset_id=None,
        observed_at_utc=datetime.now(tz=timezone.utc),
        variable_code=variavel,
        value_original=valor,
        unit_original="c",
        value_canonical=valor,
        unit_canonical="c",
        quality_status="valid",
        quality_score=100,
        location_code=fonte.source_name,
    ))


def test_idw_pondera_pela_proximidade(session_factory: sessionmaker[Session]) -> None:
    org = "org-idw"
    session = session_factory()
    try:
        # Estação muito próxima de Betim marca 20 °C; distante marca 30 °C.
        perto = _fonte(session, org, "Perto", -19.97, -44.20)
        longe = _fonte(session, org, "Longe", -21.50, -45.50)
        _obs(session, org, perto, "temperature_c", 20.0)
        _obs(session, org, longe, "temperature_c", 30.0)
        session.commit()
    finally:
        session.close()

    consulta = session_factory()
    try:
        resultado = meteorology_service.interpolated_betim_conditions(consulta, org)
    finally:
        consulta.close()

    temp = resultado["variables"]["temperature_c"]["value"]
    # O resultado deve pender fortemente para a estação próxima (20 °C).
    assert 20.0 <= temp < 22.0, f"esperado próximo de 20 °C, obtido {temp}"
    assert resultado["variables"]["temperature_c"]["stations_used"] == 2
    assert resultado["method"] == "idw_inverse_distance_weighting"


def test_sem_estacoes_retorna_vazio(session_factory: sessionmaker[Session]) -> None:
    consulta = session_factory()
    try:
        resultado = meteorology_service.interpolated_betim_conditions(consulta, "org-vazia")
    finally:
        consulta.close()
    assert resultado["variables"] == {}
    assert resultado["stations_available"] == 0

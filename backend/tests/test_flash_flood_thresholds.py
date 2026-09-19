"""Proxy de cheia urbana: limiares de chuva horária para bacias de resposta rápida."""

from __future__ import annotations

from datetime import datetime, timezone

from app.modules.ingestion.models import ObservationModel
from app.modules.planning.service import planning_service


def _obs(rainfall_mm: float) -> ObservationModel:
    return ObservationModel(
        organization_id="org-teste",
        source_id="fonte-teste",
        ingestion_run_id="run-teste",
        raw_asset_id=None,
        observed_at_utc=datetime.now(tz=timezone.utc),
        variable_code="rainfall_mm_1h",
        value_original=rainfall_mm,
        unit_original="mm",
        value_canonical=rainfall_mm,
        unit_canonical="mm",
        quality_status="valid",
        quality_score=100,
        location_code="CEMADEN_BETIM",
    )


def test_chuva_extrema_gera_alerta_critico_de_inundacao_rapida() -> None:
    alerta = planning_service._evaluate_alert(_obs(65.0))
    assert alerta is not None
    assert alerta.alert_code == "flash_flood_critical"
    assert alerta.severity == "critical"
    assert "Rio" in alerta.description and "Betim" in alerta.description


def test_limiares_classicos_preservados() -> None:
    assert planning_service._evaluate_alert(_obs(55.0)).alert_code == "storm_heavy_rain"
    assert planning_service._evaluate_alert(_obs(35.0)).alert_code == "storm_rain_watch"


def test_aviso_antecipado_para_bacia_urbana() -> None:
    alerta = planning_service._evaluate_alert(_obs(22.0))
    assert alerta is not None
    assert alerta.alert_code == "urban_rain_advisory"
    assert alerta.severity == "low"
    assert "CEMADEN" in alerta.description


def test_chuva_fraca_nao_gera_alerta() -> None:
    assert planning_service._evaluate_alert(_obs(8.0)) is None

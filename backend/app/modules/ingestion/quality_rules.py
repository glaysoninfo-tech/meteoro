from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(slots=True)
class QualityEvaluation:
    status: str
    score: int
    flag_code: str | None
    description: str | None


def evaluate_observation_quality(
    *,
    variable_code: str,
    value_canonical: float,
    observed_at_utc: datetime,
) -> QualityEvaluation:
    observed = _as_utc(value=observed_at_utc)
    now_utc = datetime.now(tz=timezone.utc)

    if observed > now_utc + timedelta(minutes=5):
        return QualityEvaluation(
            status="rejected",
            score=0,
            flag_code="timestamp_future",
            description="Timestamp informado no futuro.",
        )

    if observed < now_utc - timedelta(days=3650):
        return QualityEvaluation(
            status="suspect",
            score=50,
            flag_code="timestamp_stale",
            description="Timestamp muito antigo para série operacional.",
        )

    value_range = _value_ranges().get(variable_code)
    if value_range is not None and not (value_range[0] <= value_canonical <= value_range[1]):
        return QualityEvaluation(
            status="rejected",
            score=0,
            flag_code="value_out_of_range",
            description=(
                "Valor fora da faixa esperada: "
                f"{value_range[0]} <= x <= {value_range[1]}."
            ),
        )

    soft_range = _soft_ranges().get(variable_code)
    if soft_range is not None and not (soft_range[0] <= value_canonical <= soft_range[1]):
        return QualityEvaluation(
            status="suspect",
            score=75,
            flag_code="value_soft_outlier",
            description=(
                "Valor atípico para operação local: "
                f"{soft_range[0]} <= x <= {soft_range[1]}."
            ),
        )

    return QualityEvaluation(status="valid", score=100, flag_code=None, description=None)


def _value_ranges() -> dict[str, tuple[float, float]]:
    return {
        "temperature_c": (-30.0, 55.0),
        "humidity_pct": (0.0, 100.0),
        "rainfall_mm_1h": (0.0, 250.0),
        "wind_speed_mps": (0.0, 80.0),
        "river_level_m": (0.0, 30.0),
        "river_flow_m3s": (0.0, 20000.0),
        "pm25_ugm3": (0.0, 1000.0),
        "pm10_ugm3": (0.0, 1500.0),
        "o3_ugm3": (0.0, 2000.0),
        "no2_ugm3": (0.0, 2000.0),
        "so2_ugm3": (0.0, 2000.0),
        "co_mgm3": (0.0, 200.0),
    }


def _soft_ranges() -> dict[str, tuple[float, float]]:
    return {
        "temperature_c": (-5.0, 45.0),
        "humidity_pct": (5.0, 100.0),
        "rainfall_mm_1h": (0.0, 120.0),
        "wind_speed_mps": (0.0, 35.0),
        "river_level_m": (0.0, 10.0),
        "river_flow_m3s": (0.0, 5000.0),
        "pm25_ugm3": (0.0, 250.0),
        "pm10_ugm3": (0.0, 400.0),
        "o3_ugm3": (0.0, 300.0),
        "no2_ugm3": (0.0, 300.0),
        "so2_ugm3": (0.0, 300.0),
        "co_mgm3": (0.0, 30.0),
    }


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


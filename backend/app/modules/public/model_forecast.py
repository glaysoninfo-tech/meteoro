from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.catalog.models import SourceModel
from app.modules.ingestion.models import RawAssetModel
from app.modules.public.service import public_publication_service

VARIABLES = {
    "temperature_2m": ("temperature_c", "Temperatura a 2 m"),
    "relative_humidity_2m": ("humidity_pct", "Umidade relativa a 2 m"),
    "precipitation": ("rainfall_mm_1h", "Precipitação horária"),
    "wind_speed_10m": ("wind_speed_10m", "Vento a 10 m"),
}


def public_model_forecast(db: Session, organization_id: str) -> dict:
    sources = [source for source in public_publication_service.public_sources(db, organization_id) if source.source_type == "meteorology_model"]
    if not sources:
        raise ValueError("Fonte pública de previsão não configurada.")
    source = max(sources, key=lambda item: item.last_success_at or datetime.min.replace(tzinfo=timezone.utc))
    raw = db.scalar(select(RawAssetModel).where(
        RawAssetModel.organization_id == organization_id,
        RawAssetModel.source_id == source.source_id,
    ).order_by(RawAssetModel.collected_at.desc()))
    if raw is None or not Path(raw.object_uri).is_file():
        raise ValueError("Coleta de previsão ainda não disponível.")
    payload = json.loads(Path(raw.object_uri).read_text(encoding="utf-8"))
    hourly = payload.get("hourly", {})
    units = payload.get("hourly_units", {})
    times = hourly.get("time", [])
    parsed_times = [_utc(value) for value in times]
    now = datetime.now(timezone.utc)
    future_indices = [index for index, value in enumerate(parsed_times) if value > now]
    if not future_indices:
        raise ValueError("A coleta não contém horários futuros.")
    selected: list[int] = []
    for offset in (6, 12, 18, 24):
        target = now.timestamp() + offset * 3600
        selected.append(min(future_indices, key=lambda index: abs(parsed_times[index].timestamp() - target)))
    selected = list(dict.fromkeys(selected))
    series = []
    for remote_code, (variable_code, label) in VARIABLES.items():
        values = hourly.get(remote_code, [])
        points = [
            {"valid_at_utc": parsed_times[index].isoformat(), "predicted_value": float(values[index])}
            for index in selected if index < len(values) and values[index] is not None
        ]
        if points:
            series.append({"variable_code": variable_code, "label": label, "unit": units.get(remote_code, ""), "points": points})
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "issued_at_utc": raw.collected_at.isoformat(),
        "horizon_hours": 24,
        "step_hours": 6,
        "data_kind": "model_estimate_or_forecast",
        "source": {
            "institution": source.institution_name,
            "name": source.source_name,
            "provider": "Open-Meteo",
            "latitude": payload.get("latitude"),
            "longitude": payload.get("longitude"),
            "timezone": payload.get("timezone", "GMT"),
        },
        "series": series,
        "summary": "Previsão horária de modelo numérico selecionada em intervalos aproximados de seis horas.",
        "disclaimer": "Estimativa de modelo, não medição local nem alerta oficial. Consulte alertas e previsões oficiais antes de decisões de segurança.",
    }


def _utc(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)

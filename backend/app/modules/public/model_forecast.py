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

# Códigos WMO usados pelo Open-Meteo, em linguagem cidadã.
WEATHER_CODES: dict[int, tuple[str, str]] = {
    0: ("Céu limpo", "☀"),
    1: ("Predomínio de sol", "🌤"),
    2: ("Parcialmente nublado", "⛅"),
    3: ("Nublado", "☁"),
    45: ("Nevoeiro", "🌫"),
    48: ("Nevoeiro com geada", "🌫"),
    51: ("Garoa fraca", "🌦"),
    53: ("Garoa", "🌦"),
    55: ("Garoa intensa", "🌦"),
    61: ("Chuva fraca", "🌧"),
    63: ("Chuva", "🌧"),
    65: ("Chuva forte", "🌧"),
    66: ("Chuva congelante", "🌧"),
    67: ("Chuva congelante forte", "🌧"),
    71: ("Neve fraca", "❄"),
    73: ("Neve", "❄"),
    75: ("Neve forte", "❄"),
    80: ("Pancadas de chuva", "🌦"),
    81: ("Pancadas de chuva", "🌧"),
    82: ("Pancadas fortes de chuva", "⛈"),
    95: ("Trovoadas", "⛈"),
    96: ("Trovoadas com granizo", "⛈"),
    99: ("Trovoadas fortes com granizo", "⛈"),
}


def _uv_advice(uv_index: float | None) -> str | None:
    if uv_index is None:
        return None
    if uv_index >= 11:
        return "Índice UV extremo: evite o sol entre 10h e 16h."
    if uv_index >= 8:
        return "Índice UV muito alto: use protetor solar e busque sombra."
    if uv_index >= 6:
        return "Índice UV alto: proteção solar recomendada."
    if uv_index >= 3:
        return "Índice UV moderado: use protetor em exposição prolongada."
    return "Índice UV baixo."


def _hourly_for_day(payload: dict, day_iso: str) -> list[dict]:
    """Série horária do dia solicitado, para o detalhamento no portal."""
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    saida: list[dict] = []
    for index, marca in enumerate(times):
        if not str(marca).startswith(day_iso):
            continue

        def campo(nome: str):
            serie = hourly.get(nome) or []
            return serie[index] if index < len(serie) else None

        saida.append({
            "time_utc": _utc(marca).isoformat(),
            "temperature_c": campo("temperature_2m"),
            "humidity_pct": campo("relative_humidity_2m"),
            "precipitation_mm": campo("precipitation"),
            "wind_speed_ms": campo("wind_speed_10m"),
            "cloud_cover_pct": campo("cloud_cover"),
        })
    return saida


def public_daily_forecast(db: Session, organization_id: str, days: int = 3) -> dict:
    """Previsão diária para o portal do cidadão (padrão de leitura CPTEC).

    Cartões por dia com máxima/mínima, chuva prevista, probabilidade, vento,
    índice UV e condição predominante — horizonte de 72 h por padrão.
    """
    payload, source, raw = _latest_payload(db, organization_id)
    daily = payload.get("daily") or {}
    dates = daily.get("time") or []
    if not dates:
        raise ValueError(
            "A coleta atual não contém previsão diária. Atualize o endpoint da "
            "fonte pública para incluir os parâmetros daily do Open-Meteo."
        )

    hoje = datetime.now(timezone.utc).date()
    cartoes: list[dict] = []
    for index, dia_texto in enumerate(dates):
        try:
            dia = datetime.fromisoformat(str(dia_texto)).date()
        except ValueError:
            continue
        if dia < hoje or len(cartoes) >= days:
            continue

        def valor(campo: str):
            serie = daily.get(campo) or []
            return serie[index] if index < len(serie) and serie[index] is not None else None

        codigo = valor("weather_code")
        condicao, icone = WEATHER_CODES.get(
            int(codigo) if codigo is not None else -1, ("Condição indefinida", "•")
        )
        uv = valor("uv_index_max")
        cartoes.append({
            "date": dia.isoformat(),
            "is_today": dia == hoje,
            "condition": condicao,
            "icon": icone,
            "temperature_max_c": valor("temperature_2m_max"),
            "temperature_min_c": valor("temperature_2m_min"),
            "precipitation_mm": valor("precipitation_sum"),
            "precipitation_probability_pct": valor("precipitation_probability_max"),
            "wind_max_ms": valor("wind_speed_10m_max"),
            "uv_index_max": uv,
            "uv_advice": _uv_advice(uv),
            "sunrise": valor("sunrise"),
            "sunset": valor("sunset"),
            "hourly": _hourly_for_day(payload, dia.isoformat()),
        })

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "issued_at_utc": _utc(raw.collected_at).isoformat(),
        "horizon_days": len(cartoes),
        "data_kind": "model_estimate_or_forecast",
        "location": {
            "name": "Betim/MG",
            "latitude": payload.get("latitude"),
            "longitude": payload.get("longitude"),
        },
        "source": {"institution": source.institution_name, "provider": "Open-Meteo"},
        "days": cartoes,
        "disclaimer": (
            "Estimativa de modelo numérico, não é alerta oficial. Em situação de "
            "risco siga as orientações da Defesa Civil."
        ),
    }


def _latest_payload(db: Session, organization_id: str):
    """Payload bruto mais recente da fonte pública de previsão."""
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
    return payload, source, raw


def public_model_forecast(db: Session, organization_id: str) -> dict:
    payload, source, raw = _latest_payload(db, organization_id)
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
        "issued_at_utc": _utc(raw.collected_at).isoformat(),
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

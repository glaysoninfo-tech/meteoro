from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from urllib.request import Request, urlopen

from sqlalchemy.orm import Session

from app.core.settings import settings
from app.modules.meteorology.service import meteorology_service
from app.modules.public.model_forecast import public_model_forecast
from app.modules.public.service import public_publication_service

_cache: tuple[float, str, dict] | None = None
_lock = threading.Lock()


def build_daily_brief(db: Session, organization_id: str) -> dict:
    global _cache
    now = time.monotonic()
    cache_key = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H")
    with _lock:
        if _cache and _cache[1] == cache_key and now - _cache[0] < 1800:
            return _cache[2]
        facts = _facts(db, organization_id)
        fallback = _fallback_message(facts)
        message, mode = fallback, "factual_fallback"
        if settings.openai_api_key is not None:
            candidate = _openai_message(facts)
            if candidate and _valid(candidate, facts):
                message, mode = candidate, "ai_assisted"
        result = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "title": "Previsão do Dia",
            "message": message,
            "generation_mode": mode,
            "facts": facts,
            "sources": ["Base pública municipal", "Open-Meteo", "REDEMET/DECEA", "Alertas oficiais municipais"],
            "disclaimer": "Texto automatizado de apoio informativo. Consulte alertas oficiais antes de tomar decisões de segurança.",
        }
        _cache = (now, cache_key, result)
        return result


def _facts(db: Session, organization_id: str) -> dict:
    rows = public_publication_service.public_observations(db, organization_id)
    forecast = public_model_forecast(db, organization_id)
    projected = {
        series["variable_code"]: [round(point["predicted_value"], 1) for point in series["points"]]
        for series in forecast["series"]
    }
    map_data = meteorology_service.get_operational_map_layers(db, organization_id)
    return {
        "current": values,
        "next_24h": {
            "temperature_min_c": min(projected.get("temperature_c", [values["temperature_c"] or 0])),
            "temperature_max_c": max(projected.get("temperature_c", [values["temperature_c"] or 0])),
            "humidity_min_pct": min(projected.get("humidity_pct", [values["humidity_pct"] or 0])),
            "rainfall_max_mm_h": max(projected.get("rainfall_mm_1h", [0])),
            "wind_max_m_s": max(projected.get("wind_speed_mps", [0])),
        },
        "active_official_alerts": len(public_publication_service.active_alerts(db, organization_id)),
        "regional_thunderstorm_areas": len(map_data.thunderstorm_areas),
        "forecast_kind": "estimativa automatizada de tendência",
    }


def _fallback_message(facts: dict) -> str:
    future = facts["next_24h"]
    phrases = ["Olá!"]
    if future["temperature_max_c"] >= 32:
        phrases.append("O dia deve ter calor em Betim; leve água e prefira os horários mais amenos para atividades ao ar livre.")
    elif future["temperature_max_c"] <= 22:
        phrases.append("As temperaturas devem ficar mais amenas ao longo do dia.")
    else:
        phrases.append("A temperatura deve variar de forma moderada ao longo do dia.")
    if future["humidity_min_pct"] < 40:
        phrases.append("A umidade pode ficar baixa em parte do período; tenha água por perto e faça pausas se permanecer ao ar livre.")
    if future["rainfall_max_mm_h"] >= 2:
        phrases.append("Há indicação de chuva nas próximas horas; vale ter um guarda-chuva por perto.")
    else:
        phrases.append("A estimativa disponível não indica chuva significativa nas próximas horas, mas acompanhe as atualizações ao longo do dia.")
    if future["wind_max_m_s"] >= 10:
        phrases.append("O vento pode ficar forte: proteja objetos soltos e tenha atenção em áreas abertas.")
    if facts["regional_thunderstorm_areas"]:
        phrases.append("A REDEMET detecta área de trovoada na região; acompanhe as atualizações e os alertas oficiais.")
    return " ".join(phrases)


def _openai_message(facts: dict) -> str | None:
    prompt = (
        "Redija em português do Brasil uma mensagem pública de previsão do dia para Betim, com 45 a 80 palavras. "
        "Comece com 'Olá!'. Seja claro, acolhedor e útil. Use exclusivamente os fatos JSON fornecidos. "
        "Não mencione frente fria, poeira, fumaça, raios, granizo ou alertas se esses fatos não estiverem presentes. "
        "Não dê diagnóstico médico. Não use markdown.\nFATOS: " + json.dumps(facts, ensure_ascii=False)
    )
    body = json.dumps({"model": settings.openai_daily_brief_model, "input": prompt, "max_output_tokens": 180}).encode()
    request = Request("https://api.openai.com/v1/responses", data=body, method="POST", headers={
        "Authorization": f"Bearer {settings.openai_api_key.get_secret_value()}", "Content-Type": "application/json",
    })
    try:
        with urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None
    for item in data.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                return content["text"].strip()
    return None


def _valid(message: str, facts: dict) -> bool:
    if not 35 <= len(message.split()) <= 100 or not message.startswith("Olá!"):
        return False
    lower = message.lower()
    forbidden = ("frente fria", "granizo", "fumaça", "poeira")
    if any(term in lower for term in forbidden):
        return False
    if ("raio" in lower or "trovoada" in lower) and not facts["regional_thunderstorm_areas"]:
        return False
    if "alerta" in lower and not facts["active_official_alerts"]:
        return False
    return True

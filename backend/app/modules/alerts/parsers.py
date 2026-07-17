from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import csv
import json
from io import StringIO
from typing import Any

from app.modules.catalog.models import SourceModel
from app.modules.ingestion.connectors import SourcePayload


@dataclass(slots=True)
class ParsedOfficialAlert:
    external_alert_id: str | None
    issuer: str
    alert_code: str
    severity: str
    issued_at_utc: datetime
    valid_from_utc: datetime
    valid_to_utc: datetime
    title: str
    message: str
    territory_codes: list[str]
    geometry_geojson: str | None
    original_payload_json: str


def source_is_official_alert_profile(source: SourceModel) -> bool:
    signature = " ".join(
        (
            source.source_type.lower(),
            source.source_name.lower(),
            source.institution_name.lower(),
        )
    )
    markers = {
        "official_alert",
        "alerta_oficial",
        "alerta oficial",
        "cemaden",
        "inmet alerta",
        "rede met",
        "defesa civil alerta",
    }
    return any(marker in signature for marker in markers)


def parse_official_alert_payload(
    source: SourceModel,
    payload: SourcePayload,
) -> list[ParsedOfficialAlert]:
    records = _load_records(payload=payload, endpoint_reference=source.endpoint_reference)
    defaults = _resolve_defaults(source=source)

    parsed: list[ParsedOfficialAlert] = []
    for record in records:
        issued_at = _extract_datetime(
            record=record,
            aliases=["issued_at_utc", "issued_at", "data_emissao", "issued", "timestamp"],
        )
        valid_from = _extract_datetime(
            record=record,
            aliases=["valid_from_utc", "valid_from", "inicio_vigencia", "valid_from_at"],
            default=issued_at,
        )
        valid_to = _extract_datetime(
            record=record,
            aliases=["valid_to_utc", "valid_to", "fim_vigencia", "expires_at"],
            default=valid_from,
        )

        issuer = _extract_str(record=record, aliases=["issuer", "orgao", "emissor"]) or defaults["issuer"]
        alert_code = _extract_str(record=record, aliases=["alert_code", "tipo", "codigo_alerta"]) or defaults["alert_code"]
        severity = _normalize_severity(
            _extract_str(record=record, aliases=["severity", "severidade", "nivel"]) or "medium"
        )
        title = _extract_str(record=record, aliases=["title", "titulo", "headline"]) or "Alerta oficial"
        message = _extract_str(record=record, aliases=["message", "descricao", "texto", "description"]) or ""
        if message == "":
            message = title

        parsed.append(
            ParsedOfficialAlert(
                external_alert_id=_extract_str(
                    record=record,
                    aliases=["external_alert_id", "id_externo", "external_id", "id_alerta"],
                ),
                issuer=issuer,
                alert_code=alert_code,
                severity=severity,
                issued_at_utc=issued_at,
                valid_from_utc=valid_from,
                valid_to_utc=valid_to,
                title=title,
                message=message,
                territory_codes=_extract_territory_codes(record=record),
                geometry_geojson=_extract_str(
                    record=record,
                    aliases=["geometry_geojson", "geometry", "geojson"],
                ),
                original_payload_json=json.dumps(record, ensure_ascii=True),
            )
        )
    return parsed


def _resolve_defaults(source: SourceModel) -> dict[str, str]:
    issuer = source.institution_name.strip()
    if issuer == "":
        issuer = "Fonte oficial"
    alert_code = "alert_official"
    source_name = source.source_name.lower()
    if "chuva" in source_name:
        alert_code = "rainfall_alert"
    if "vento" in source_name:
        alert_code = "wind_alert"
    if "rio" in source_name or "vazao" in source_name or "nivel" in source_name:
        alert_code = "flood_alert"
    return {"issuer": issuer, "alert_code": alert_code}


def _load_records(payload: SourcePayload, endpoint_reference: str) -> list[dict[str, Any]]:
    content_type = payload.content_type.lower()
    endpoint_lower = endpoint_reference.lower()
    text = payload.content_bytes.decode("utf-8")

    if "json" in content_type or endpoint_lower.endswith(".json"):
        data = json.loads(text)
        if isinstance(data, list):
            return [_ensure_dict(item) for item in data]
        if isinstance(data, dict):
            for key in ("alerts", "data", "items"):
                nested = data.get(key)
                if isinstance(nested, list):
                    return [_ensure_dict(item) for item in nested]
            return [_ensure_dict(data)]
        raise ValueError("Payload JSON inválido para parsing de alertas oficiais.")

    if "csv" in content_type or endpoint_lower.endswith(".csv"):
        reader = csv.DictReader(StringIO(text))
        return [dict(row) for row in reader]

    raise ValueError(
        "Formato de payload não suportado para alertas oficiais. Use JSON ou CSV."
    )


def _extract_datetime(
    record: dict[str, Any],
    aliases: list[str],
    default: datetime | None = None,
) -> datetime:
    value = _extract_raw(record=record, aliases=aliases)
    if value is None:
        if default is not None:
            return default
        return datetime.now(tz=timezone.utc)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    text = str(value).strip()
    if text == "":
        if default is not None:
            return default
        return datetime.now(tz=timezone.utc)
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        if default is not None:
            return default
        return datetime.now(tz=timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _extract_str(record: dict[str, Any], aliases: list[str]) -> str | None:
    value = _extract_raw(record=record, aliases=aliases)
    if value is None:
        return None
    text = str(value).strip()
    if text == "":
        return None
    return text


def _extract_territory_codes(record: dict[str, Any]) -> list[str]:
    value = _extract_raw(
        record=record,
        aliases=[
            "territory_codes",
            "territorios",
            "bairros",
            "areas",
            "coverage_codes",
        ],
    )
    if value is None:
        return []
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            text = str(item).strip()
            if text:
                result.append(text)
        return result
    text_value = str(value).strip()
    if text_value == "":
        return []
    separators = [",", ";", "|"]
    normalized = text_value
    for sep in separators[1:]:
        normalized = normalized.replace(sep, separators[0])
    return [part.strip() for part in normalized.split(separators[0]) if part.strip() != ""]


def _normalize_severity(value: str) -> str:
    normalized = value.strip().lower()
    aliases = {
        "baixa": "low",
        "baixo": "low",
        "media": "medium",
        "média": "medium",
        "medio": "medium",
        "médio": "medium",
        "alta": "high",
        "alto": "high",
        "critica": "critical",
        "crítica": "critical",
        "extremo": "critical",
    }
    normalized = aliases.get(normalized, normalized)
    allowed = {"low", "medium", "high", "critical"}
    if normalized not in allowed:
        return "medium"
    return normalized


def _extract_raw(record: dict[str, Any], aliases: list[str]) -> Any:
    for alias in aliases:
        if alias in record:
            return record.get(alias)
    lowered = {str(key).lower(): value for key, value in record.items()}
    for alias in aliases:
        alias_lower = alias.lower()
        if alias_lower in lowered:
            return lowered[alias_lower]
    return None


def _ensure_dict(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return item
    raise ValueError("Lista de alertas oficiais deve conter objetos JSON.")

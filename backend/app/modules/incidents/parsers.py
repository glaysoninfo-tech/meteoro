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
class ParsedIncidentReport:
    reported_at_utc: datetime
    report_origin: str
    category_code: str
    severity: str
    description: str | None
    location_code: str | None
    location_geojson: str | None
    address_text: str | None
    reporter_name: str | None
    reporter_contact: str | None
    external_protocol: str | None


def source_is_incident_profile(source: SourceModel) -> bool:
    signature = " ".join(
        (
            source.source_type.lower(),
            source.source_name.lower(),
            source.institution_name.lower(),
        )
    )
    markers = {
        "incident",
        "denuncia",
        "denúncia",
        "fiscalizacao",
        "fiscalização",
        "complaint",
        "ouvidoria",
    }
    return any(marker in signature for marker in markers)


def parse_incident_payload(source: SourceModel, payload: SourcePayload) -> list[ParsedIncidentReport]:
    records = _load_records(payload=payload, endpoint_reference=source.endpoint_reference)
    default_origin = _resolve_default_origin(source=source)

    incidents: list[ParsedIncidentReport] = []
    for record in records:
        incidents.append(
            ParsedIncidentReport(
                reported_at_utc=_extract_datetime(
                    record=record,
                    aliases=["reported_at", "data_hora", "timestamp", "created_at"],
                ),
                report_origin=_normalize_origin(
                    _extract_str(
                        record=record,
                        aliases=["origem", "origin", "report_origin", "tipo_origem"],
                    )
                    or default_origin
                ),
                category_code=(
                    _extract_str(
                        record=record,
                        aliases=["categoria", "category", "category_code", "tipo_ocorrencia"],
                    )
                    or "general"
                ),
                severity=_normalize_severity(
                    _extract_str(record=record, aliases=["severidade", "severity", "priority"])
                    or "medium"
                ),
                description=_extract_str(
                    record=record,
                    aliases=["descricao", "description", "detalhe", "narrativa"],
                ),
                location_code=_extract_str(
                    record=record,
                    aliases=["bairro", "local", "location", "location_code"],
                ),
                location_geojson=_extract_point_geojson(record),
                address_text=_extract_str(
                    record=record,
                    aliases=["endereco", "address", "logradouro"],
                ),
                reporter_name=_extract_str(
                    record=record,
                    aliases=["reportante", "reporter_name", "nome"],
                ),
                reporter_contact=_extract_str(
                    record=record,
                    aliases=["contato", "reporter_contact", "telefone", "email"],
                ),
                external_protocol=_extract_str(
                    record=record,
                    aliases=["protocolo", "protocol", "external_protocol", "ticket"],
                ),
            )
        )
    return incidents


def _load_records(payload: SourcePayload, endpoint_reference: str) -> list[dict[str, Any]]:
    content_type = payload.content_type.lower()
    endpoint_lower = endpoint_reference.lower()
    text = payload.content_bytes.decode("utf-8")

    if "json" in content_type or endpoint_lower.endswith(".json"):
        data = json.loads(text)
        if isinstance(data, list):
            return [_ensure_dict(item) for item in data]
        if isinstance(data, dict):
            for field_name in ("reports", "incidents", "data", "items"):
                nested = data.get(field_name)
                if isinstance(nested, list):
                    return [_ensure_dict(item) for item in nested]
            return [_ensure_dict(data)]
        raise ValueError("Payload JSON inválido para parsing de incidentes.")

    if "csv" in content_type or endpoint_lower.endswith(".csv"):
        reader = csv.DictReader(StringIO(text))
        return [dict(row) for row in reader]

    raise ValueError(
        "Formato de payload não suportado para incidentes. Use JSON ou CSV."
    )


def _resolve_default_origin(source: SourceModel) -> str:
    signature = " ".join((source.source_name.lower(), source.institution_name.lower()))
    if "fiscalizacao" in signature or "fiscalização" in signature:
        return "inspection"
    if "denuncia" in signature or "denúncia" in signature or "ouvidoria" in signature:
        return "citizen"
    return "inspection"


def _extract_datetime(record: dict[str, Any], aliases: list[str]) -> datetime:
    value = _extract_raw(record=record, aliases=aliases)
    if value is None:
        return datetime.now(tz=timezone.utc)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    value_text = str(value).strip()
    if not value_text:
        return datetime.now(tz=timezone.utc)
    normalized = value_text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return datetime.now(tz=timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _extract_str(record: dict[str, Any], aliases: list[str]) -> str | None:
    value = _extract_raw(record=record, aliases=aliases)
    if value is None:
        return None
    value_text = str(value).strip()
    if value_text == "":
        return None
    return value_text


def _extract_raw(record: dict[str, Any], aliases: list[str]) -> Any:
    for alias in aliases:
        if alias in record:
            return record.get(alias)
    lower_index = {str(key).lower(): value for key, value in record.items()}
    for alias in aliases:
        if alias.lower() in lower_index:
            return lower_index[alias.lower()]
    return None


def _extract_point_geojson(record: dict[str, Any]) -> str | None:
    """Preserve a coordinate supplied by the source; never geocode an address implicitly."""
    geometry = _extract_raw(record, ["location_geojson", "geometry_geojson", "geometry"])
    if isinstance(geometry, str):
        try:
            geometry = json.loads(geometry)
        except json.JSONDecodeError:
            geometry = None
    if isinstance(geometry, dict) and geometry.get("type") == "Point":
        coordinates = geometry.get("coordinates")
        if _valid_position(coordinates):
            return json.dumps({"type": "Point", "coordinates": coordinates}, ensure_ascii=True, separators=(",", ":"))

    latitude = _as_float(_extract_raw(record, ["latitude", "lat", "y"]))
    longitude = _as_float(_extract_raw(record, ["longitude", "lon", "lng", "x"]))
    if latitude is not None and longitude is not None and -90 <= latitude <= 90 and -180 <= longitude <= 180:
        return json.dumps({"type": "Point", "coordinates": [longitude, latitude]}, ensure_ascii=True, separators=(",", ":"))
    return None


def _valid_position(value: Any) -> bool:
    return (
        isinstance(value, list) and len(value) >= 2 and isinstance(value[0], (int, float))
        and isinstance(value[1], (int, float)) and -180 <= value[0] <= 180 and -90 <= value[1] <= 90
    )


def _as_float(value: Any) -> float | None:
    try:
        return float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None


def _normalize_origin(value: str) -> str:
    normalized = value.strip().lower()
    if any(marker in normalized for marker in ("fiscal", "inspect", "agente")):
        return "inspection"
    if any(marker in normalized for marker in ("denunc", "morador", "citizen", "ouvid")):
        return "citizen"
    return "inspection"


def _normalize_severity(value: str) -> str:
    normalized = value.strip().lower()
    aliases = {
        "baixa": "low",
        "baixo": "low",
        "low": "low",
        "media": "medium",
        "média": "medium",
        "medio": "medium",
        "médio": "medium",
        "medium": "medium",
        "alta": "high",
        "alto": "high",
        "high": "high",
        "critica": "critical",
        "crítica": "critical",
        "critical": "critical",
        "urgente": "critical",
    }
    return aliases.get(normalized, normalized)


def _ensure_dict(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return item
    raise ValueError("Lista JSON de incidentes deve conter objetos.")

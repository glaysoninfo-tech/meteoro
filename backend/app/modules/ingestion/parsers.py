from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import csv
import json
from io import StringIO
import re
from typing import Any

from app.modules.catalog.models import SourceModel
from app.modules.ingestion.connectors import SourcePayload


@dataclass(slots=True)
class ParsedObservation:
    observed_at_utc: datetime
    variable_code: str
    value_original: float
    unit_original: str
    value_canonical: float
    unit_canonical: str
    location_code: str | None


def parse_source_payload(source: SourceModel, payload: SourcePayload) -> list[ParsedObservation]:
    records = _load_records(payload=payload, endpoint_reference=source.endpoint_reference)
    parser_name = _resolve_parser_name(source=source)

    if parser_name == "inmet":
        return _parse_inmet(records, source=source)
    if parser_name == "opmet":
        return _parse_opmet(records)
    if parser_name == "semmad":
        return _parse_semmad(records)
    if parser_name == "sentinel":
        return _parse_sentinel(records)
    if parser_name == "monitorar_feam":
        return _parse_monitorar_feam(records)
    if parser_name == "open_meteo":
        return _parse_open_meteo(records, source=source)
    if parser_name == "redemet_status":
        return _parse_redemet_status(records)
    if parser_name == "redemet_metar":
        return _parse_redemet_metar(records, source=source)
    if parser_name == "sensor_stream":
        return _parse_sensor_stream(records)
    return _parse_generic(records)


def _resolve_parser_name(source: SourceModel) -> str:
    institution = source.institution_name.lower()
    source_name = source.source_name.lower()
    source_type = source.source_type.lower()
    access_method = source.access_method.lower()
    connector_config = _connector_config(source.connector_config_json)
    explicit_parser = connector_config.get("parser")
    if explicit_parser in {
        "inmet", "opmet", "semmad", "sentinel", "sensor_stream", "monitorar_feam", "open_meteo",
        "redemet_status", "redemet_metar", "redemet_imagery", "lightning_geojson",
    }:
        return explicit_parser

    if access_method in {"mqtt", "opcua"}:
        return "sensor_stream"

    if "inmet" in institution or "inmet" in source_name:
        return "inmet"
    if "opmet" in institution or "opmet" in source_name:
        return "opmet"
    if "open-meteo" in institution or "open-meteo" in source_name:
        return "open_meteo"
    if "monitorar" in institution or "monitorar" in source_name:
        return "monitorar_feam"
    if "feam" in institution and "air" in source_type:
        return "monitorar_feam"
    if "semmad" in institution or "semmad" in source_name:
        return "semmad"
    if "sentinel" in source_name or "paraopeba" in source_name or "aws" in institution:
        return "sentinel"
    if "hydro" in source_type:
        return "sentinel"
    if "sensor" in source_type:
        return "sensor_stream"
    return "generic"


def _load_records(payload: SourcePayload, endpoint_reference: str) -> list[dict[str, Any]]:
    content_type = payload.content_type.lower()
    endpoint_lower = endpoint_reference.lower()
    text = payload.content_bytes.decode("utf-8")

    if "json" in content_type or endpoint_lower.endswith(".json"):
        data = json.loads(text)
        if isinstance(data, list):
            return [_ensure_dict(item) for item in data]
        if isinstance(data, dict):
            if isinstance(data.get("data"), list):
                return [_redemet_status_record(item) if isinstance(item, list) else _ensure_dict(item) for item in data["data"]]
            if isinstance(data.get("data"), dict) and isinstance(data["data"].get("data"), list):
                return [_ensure_dict(item) for item in data["data"]["data"]]
            if isinstance(data.get("results"), list):
                return [_ensure_dict(item) for item in data["results"]]
            if isinstance(data.get("features"), list):
                return [_geojson_feature_record(item) for item in data["features"]]
            return [data]
        raise ValueError("Payload JSON inválido para parsing.")

    if "csv" in content_type or endpoint_lower.endswith(".csv"):
        sample = text[:8192]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=";,\t,")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(StringIO(text), dialect=dialect)
        return [dict(row) for row in reader]

    raise ValueError(
        f"Formato de payload não suportado para parsing: content_type='{payload.content_type}'."
    )


def _parse_inmet(records: list[dict[str, Any]], source: SourceModel) -> list[ParsedObservation]:
    observations: list[ParsedObservation] = []
    for record in records:
        observed_at = _extract_inmet_datetime(record)
        location = _extract_str(record=record, aliases=["CD_ESTACAO", "station", "estacao"]) or _configured_location(source)
        observations.extend(
            _extract_variable_group(
                record=record,
                observed_at=observed_at,
                location_code=location,
                mappings=[
                    _mapping(
                        variable_code="temperature_c",
                        aliases=["TEM_INS", "temperature", "temperatura", "Temp. Ins. (C)"],
                        unit_aliases=["temperature_unit", "unidade_temperatura"],
                        default_unit="c",
                    ),
                    _mapping(
                        variable_code="humidity_pct",
                        aliases=["UMD_INS", "humidity", "umidade", "Umi. Ins. (%)"],
                        unit_aliases=["humidity_unit"],
                        default_unit="%",
                    ),
                    _mapping(
                        variable_code="rainfall_mm_1h",
                        aliases=["CHUVA", "rainfall", "precipitacao", "Chuva (mm)"],
                        unit_aliases=["rainfall_unit", "unidade_chuva"],
                        default_unit="mm",
                    ),
                    _mapping(
                        variable_code="wind_speed_mps",
                        aliases=["VEN_VEL", "wind_speed", "vento_velocidade", "Vel. Vento (m/s)"],
                        unit_aliases=["wind_unit", "unidade_vento"],
                        default_unit="m/s",
                    ),
                ],
            )
        )
    return observations


def _parse_opmet(records: list[dict[str, Any]]) -> list[ParsedObservation]:
    observations: list[ParsedObservation] = []
    for record in records:
        observed_at = _extract_datetime(
            record=record,
            aliases=["observation_time", "observed_at", "data_hora", "timestamp"],
        )
        location = _extract_str(record=record, aliases=["station", "icao", "aerodrome"])
        observations.extend(
            _extract_variable_group(
                record=record,
                observed_at=observed_at,
                location_code=location,
                mappings=[
                    _mapping(
                        variable_code="temperature_c",
                        aliases=["temperature_c", "temperature", "temp"],
                        unit_aliases=["temperature_unit"],
                        default_unit="c",
                    ),
                    _mapping(
                        variable_code="humidity_pct",
                        aliases=["humidity", "relative_humidity"],
                        unit_aliases=["humidity_unit"],
                        default_unit="%",
                    ),
                    _mapping(
                        variable_code="wind_speed_mps",
                        aliases=["wind_speed_mps", "wind_speed", "vento"],
                        unit_aliases=["wind_unit"],
                        default_unit="m/s",
                    ),
                ],
            )
        )
    return observations


def _parse_semmad(records: list[dict[str, Any]]) -> list[ParsedObservation]:
    observations: list[ParsedObservation] = []
    for record in records:
        observed_at = _extract_datetime(
            record=record,
            aliases=["data_hora", "timestamp", "datetime", "observed_at"],
        )
        location = _extract_str(record=record, aliases=["bairro", "local", "estacao"])

        variable_name = _extract_str(record=record, aliases=["variavel", "variable"])
        variable_value = _extract_float(record=record, aliases=["valor", "value"])
        variable_unit = _extract_str(record=record, aliases=["unidade", "unit"])
        if variable_name is not None and variable_value is not None:
            normalized_variable = _normalize_variable_name(variable_name)
            if normalized_variable is not None:
                observations.append(
                    _build_observation(
                        observed_at=observed_at,
                        variable_code=normalized_variable,
                        value_original=variable_value,
                        unit_original=variable_unit or _default_unit(normalized_variable),
                        location_code=location,
                    )
                )

        observations.extend(
            _extract_variable_group(
                record=record,
                observed_at=observed_at,
                location_code=location,
                mappings=[
                    _mapping(
                        variable_code="river_flow_m3s",
                        aliases=["vazao", "flow", "river_flow_m3s"],
                        unit_aliases=["vazao_unidade", "flow_unit"],
                        default_unit="m3/s",
                    ),
                    _mapping(
                        variable_code="river_level_m",
                        aliases=["nivel", "nivel_rio", "river_level_m"],
                        unit_aliases=["nivel_unidade", "level_unit"],
                        default_unit="m",
                    ),
                    _mapping(
                        variable_code="rainfall_mm_1h",
                        aliases=["chuva", "rainfall", "precipitacao"],
                        unit_aliases=["chuva_unidade", "rainfall_unit"],
                        default_unit="mm",
                    ),
                ],
            )
        )
    return observations


def _parse_sentinel(records: list[dict[str, Any]]) -> list[ParsedObservation]:
    observations: list[ParsedObservation] = []
    for record in records:
        observed_at = _extract_datetime(
            record=record,
            aliases=["timestamp", "observed_at", "data_hora", "datetime"],
        )
        location = _extract_str(record=record, aliases=["station", "location", "site", "ponto"])
        observations.extend(
            _extract_variable_group(
                record=record,
                observed_at=observed_at,
                location_code=location,
                mappings=[
                    _mapping(
                        variable_code="river_level_m",
                        aliases=["river_level_m", "nivel_rio", "nivel"],
                        unit_aliases=["river_level_unit", "nivel_unit"],
                        default_unit="m",
                    ),
                    _mapping(
                        variable_code="river_flow_m3s",
                        aliases=["river_flow_m3s", "vazao", "flow"],
                        unit_aliases=["river_flow_unit", "vazao_unit"],
                        default_unit="m3/s",
                    ),
                    _mapping(
                        variable_code="rainfall_mm_1h",
                        aliases=["rainfall_mm_1h", "rainfall", "precipitacao"],
                        unit_aliases=["rainfall_unit"],
                        default_unit="mm",
                    ),
                ],
            )
        )
    return observations


def _parse_monitorar_feam(records: list[dict[str, Any]]) -> list[ParsedObservation]:
    """Parseia leituras oficiais de qualidade do ar preservando a estação de origem.

    O MonitorAr/FEAM pode publicar campos com nomes diferentes conforme o produto.
    Por isso este parser aceita tanto uma leitura por linha (poluente/valor) como
    várias medições na mesma linha. A configuração da fonte continua responsável
    por apontar exclusivamente para um endereço oficial homologado.
    """

    observations: list[ParsedObservation] = []
    for record in records:
        observed_at = _extract_datetime(
            record=record,
            aliases=["data_hora", "datahora", "timestamp", "datetime", "observed_at", "date_time"],
        )
        location = _extract_str(
            record=record,
            aliases=[
                "codigo_estacao", "cd_estacao", "station_id", "station_code",
                "estacao", "estação", "station", "nome_estacao", "station_name",
            ],
        )

        pollutant = _extract_str(
            record=record,
            aliases=["poluente", "pollutant", "parametro", "parameter", "variavel", "variable"],
        )
        value = _extract_float(
            record=record,
            aliases=["valor", "value", "concentracao", "concentração", "concentration", "reading"],
        )
        unit = _extract_str(record=record, aliases=["unidade", "unit", "uom"])
        normalized_variable = _normalize_variable_name(pollutant) if pollutant else None
        if normalized_variable is not None and value is not None:
            observations.append(
                _build_observation(
                    observed_at=observed_at,
                    variable_code=normalized_variable,
                    value_original=value,
                    unit_original=unit or _default_unit(normalized_variable),
                    location_code=location,
                )
            )

        observations.extend(
            _extract_variable_group(
                record=record,
                observed_at=observed_at,
                location_code=location,
                mappings=[
                    _mapping(variable_code="pm25_ugm3", aliases=["pm2_5", "pm2.5", "pm25", "mp2_5", "mp2.5", "mp25"], unit_aliases=["pm25_unit", "unidade_pm25"], default_unit="µg/m³"),
                    _mapping(variable_code="pm10_ugm3", aliases=["pm10", "mp10"], unit_aliases=["pm10_unit", "unidade_pm10"], default_unit="µg/m³"),
                    _mapping(variable_code="o3_ugm3", aliases=["o3", "ozonio", "ozônio", "ozone"], unit_aliases=["o3_unit", "unidade_o3"], default_unit="µg/m³"),
                    _mapping(variable_code="no2_ugm3", aliases=["no2", "dioxido_nitrogenio", "dióxido_nitrogênio", "nitrogen_dioxide"], unit_aliases=["no2_unit", "unidade_no2"], default_unit="µg/m³"),
                    _mapping(variable_code="so2_ugm3", aliases=["so2", "dioxido_enxofre", "dióxido_enxofre", "sulfur_dioxide"], unit_aliases=["so2_unit", "unidade_so2"], default_unit="µg/m³"),
                    _mapping(variable_code="co_mgm3", aliases=["co", "monoxido_carbono", "monóxido_carbono", "carbon_monoxide"], unit_aliases=["co_unit", "unidade_co"], default_unit="mg/m³"),
                ],
            )
        )
    return observations


def _parse_open_meteo(records: list[dict[str, Any]], source: SourceModel) -> list[ParsedObservation]:
    """Converte as séries horárias do Open-Meteo em observações normalizadas.

    O produto deve ser cadastrado como estimativa/previsão de modelo: não é
    leitura de uma estação instalada em Betim. O horário da URL deve ser UTC
    para não introduzir ambiguidade na mudança de horário de verão.
    """
    observations: list[ParsedObservation] = []
    location = _configured_location(source) or "BETIM_MODEL_POINT"
    for record in records:
        hourly = record.get("hourly")
        if not isinstance(hourly, dict):
            continue
        times = hourly.get("time")
        if not isinstance(times, list):
            continue
        mappings = {
            "temperature_2m": ("temperature_c", "c"),
            "relative_humidity_2m": ("humidity_pct", "%"),
            "precipitation": ("rainfall_mm_1h", "mm"),
            "wind_speed_10m": ("wind_speed_mps", "km/h"),
        }
        for index, timestamp in enumerate(times):
            observed_at = _extract_datetime({"timestamp": timestamp}, aliases=["timestamp"])
            for field, (variable_code, unit) in mappings.items():
                values = hourly.get(field)
                if not isinstance(values, list) or index >= len(values):
                    continue
                value = _extract_float({"value": values[index]}, aliases=["value"])
                if value is None:
                    continue
                observations.append(
                    _build_observation(
                        observed_at=observed_at,
                        variable_code=variable_code,
                        value_original=value,
                        unit_original=unit,
                        location_code=location,
                    )
                )
    return observations


def _parse_redemet_status(records: list[dict[str, Any]]) -> list[ParsedObservation]:
    """Normaliza somente o código operacional do aeródromo da REDEMET.

    g/y/r é indicador aeronáutico baseado em visibilidade e teto; não é alerta
    meteorológico municipal e não mede a condição em Betim.
    """
    observations: list[ParsedObservation] = []
    score_by_category = {"g": 0.0, "y": 1.0, "r": 2.0}
    for record in records:
        category = (_extract_str(record, ["status", "category", "cor"]) or "").lower()
        score = score_by_category.get(category)
        if score is None:
            continue
        observations.append(
            _build_observation(
                observed_at=datetime.now(tz=timezone.utc),
                variable_code="aerodrome_status_index",
                value_original=score,
                unit_original="category",
                location_code=_extract_str(record, ["icao", "localidade", "id_localidade"]),
            )
        )
    return observations


def _parse_redemet_metar(records: list[dict[str, Any]], source: SourceModel) -> list[ParsedObservation]:
    """Extrai variáveis objetivas de METAR, preservando a mensagem bruta no payload."""
    observations: list[ParsedObservation] = []
    fallback_location = _configured_location(source)
    for record in records:
        message = _extract_str(record, ["mens", "message", "metar"])
        if not message:
            continue
        observed_at = _extract_datetime(record, ["validade_inicial", "observation_time", "timestamp"])
        location = _extract_str(record, ["id_localidade", "icao", "station"]) or fallback_location
        temp_match = re.search(r"\b(M?\d{2})/(M?\d{2})\b", message)
        if temp_match:
            observations.append(_build_observation(
                observed_at=observed_at,
                variable_code="temperature_c",
                value_original=_metar_signed_number(temp_match.group(1)),
                unit_original="c",
                location_code=location,
            ))
            observations.append(_build_observation(
                observed_at=observed_at,
                variable_code="dewpoint_c",
                value_original=_metar_signed_number(temp_match.group(2)),
                unit_original="c",
                location_code=location,
            ))
        wind_match = re.search(r"\b(?:\d{3}|VRB)(\d{2,3})(?:G\d{2,3})?KT\b", message)
        if wind_match:
            observations.append(_build_observation(
                observed_at=observed_at,
                variable_code="wind_speed_mps",
                value_original=float(wind_match.group(1)),
                unit_original="kt",
                location_code=location,
            ))
        visibility_match = re.search(r"\b(\d{4})\b", message)
        if visibility_match:
            observations.append(_build_observation(
                observed_at=observed_at,
                variable_code="visibility_m",
                value_original=float(visibility_match.group(1)),
                unit_original="m",
                location_code=location,
            ))
    return observations


def _parse_sensor_stream(records: list[dict[str, Any]]) -> list[ParsedObservation]:
    observations: list[ParsedObservation] = []
    for record in records:
        observed_at = _extract_datetime(
            record=record,
            aliases=["observed_at", "timestamp", "data_hora", "datetime"],
        )
        location = _extract_str(
            record=record,
            aliases=["location", "station", "topic", "node_id", "ponto"],
        )
        variable = _extract_str(
            record=record,
            aliases=["variable_code", "variable", "sensor", "measurement"],
        )
        value = _extract_float(record=record, aliases=["value", "valor", "reading", "payload"])
        unit = _extract_str(record=record, aliases=["unit", "unidade", "uom"])
        if variable is None or value is None:
            continue

        normalized_variable = _normalize_variable_name(variable) or variable.strip().lower()
        observations.append(
            _build_observation(
                observed_at=observed_at,
                variable_code=normalized_variable,
                value_original=value,
                unit_original=unit or _default_unit(normalized_variable),
                location_code=location,
            )
        )
    return observations


def _parse_generic(records: list[dict[str, Any]]) -> list[ParsedObservation]:
    observations: list[ParsedObservation] = []
    for record in records:
        observed_at = _extract_datetime(
            record=record,
            aliases=["observed_at", "timestamp", "data_hora", "datetime"],
        )
        location = _extract_str(record=record, aliases=["location", "station", "bairro"])
        observations.extend(
            _extract_variable_group(
                record=record,
                observed_at=observed_at,
                location_code=location,
                mappings=[
                    _mapping(
                        variable_code="temperature_c",
                        aliases=["temperature", "temp", "temperature_c"],
                        unit_aliases=["temperature_unit", "temp_unit"],
                        default_unit="c",
                    ),
                    _mapping(
                        variable_code="humidity_pct",
                        aliases=["humidity", "humidity_pct"],
                        unit_aliases=["humidity_unit"],
                        default_unit="%",
                    ),
                    _mapping(
                        variable_code="rainfall_mm_1h",
                        aliases=["rainfall", "rain", "rainfall_mm_1h"],
                        unit_aliases=["rainfall_unit"],
                        default_unit="mm",
                    ),
                    _mapping(
                        variable_code="river_level_m",
                        aliases=["river_level_m", "water_level", "nivel"],
                        unit_aliases=["river_level_unit", "level_unit"],
                        default_unit="m",
                    ),
                    _mapping(
                        variable_code="river_flow_m3s",
                        aliases=["river_flow_m3s", "flow"],
                        unit_aliases=["river_flow_unit", "flow_unit"],
                        default_unit="m3/s",
                    ),
                ],
            )
        )
    return observations


def _extract_variable_group(
    record: dict[str, Any],
    observed_at: datetime,
    location_code: str | None,
    mappings: list[dict[str, Any]],
) -> list[ParsedObservation]:
    observations: list[ParsedObservation] = []
    for mapping in mappings:
        value = _extract_float(record=record, aliases=mapping["aliases"])
        if value is None:
            continue
        unit_value = _extract_str(record=record, aliases=mapping["unit_aliases"])
        unit_original = unit_value or mapping["default_unit"]
        observations.append(
            _build_observation(
                observed_at=observed_at,
                variable_code=mapping["variable_code"],
                value_original=value,
                unit_original=unit_original,
                location_code=location_code,
            )
        )
    return observations


def _build_observation(
    *,
    observed_at: datetime,
    variable_code: str,
    value_original: float,
    unit_original: str,
    location_code: str | None,
) -> ParsedObservation:
    value_canonical, unit_canonical = _normalize_value(
        variable_code=variable_code,
        value=value_original,
        unit_original=unit_original,
    )
    return ParsedObservation(
        observed_at_utc=observed_at,
        variable_code=variable_code,
        value_original=value_original,
        unit_original=unit_original,
        value_canonical=value_canonical,
        unit_canonical=unit_canonical,
        location_code=location_code,
    )


def _normalize_value(variable_code: str, value: float, unit_original: str) -> tuple[float, str]:
    unit = unit_original.strip().lower()
    if variable_code == "temperature_c":
        if unit in {"f", "fahrenheit"}:
            return ((value - 32.0) * 5.0 / 9.0, "c")
        return (value, "c")

    if variable_code == "humidity_pct":
        return (value, "%")

    if variable_code == "rainfall_mm_1h":
        if unit in {"cm"}:
            return (value * 10.0, "mm")
        return (value, "mm")

    if variable_code == "wind_speed_mps":
        if unit in {"kt", "kts", "knot", "knots"}:
            return (value * 0.514444, "m/s")
        if unit in {"km/h", "kmh"}:
            return (value / 3.6, "m/s")
        return (value, "m/s")

    if variable_code == "river_level_m":
        if unit in {"cm"}:
            return (value / 100.0, "m")
        return (value, "m")

    if variable_code == "river_flow_m3s":
        if unit in {"l/s", "lps"}:
            return (value / 1000.0, "m3/s")
        return (value, "m3/s")

    return (value, unit_original)


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


def _extract_inmet_datetime(record: dict[str, Any]) -> datetime:
    """Reconhece também a exportação CSV do INMET com Data e Hora (UTC) separadas."""
    date_value = _extract_str(record=record, aliases=["Data"])
    hour_value = _extract_str(record=record, aliases=["Hora (UTC)", "Hora UTC", "Hora"])
    if date_value and hour_value:
        try:
            return datetime.strptime(
                f"{date_value} {hour_value.zfill(4)}", "%d/%m/%Y %H%M"
            ).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return _extract_datetime(
        record=record,
        aliases=["DT_MEDICAO", "observed_at", "data_hora", "timestamp"],
    )


def _extract_str(record: dict[str, Any], aliases: list[str]) -> str | None:
    value = _extract_raw(record=record, aliases=aliases)
    if value is None:
        return None
    value_text = str(value).strip()
    if value_text == "":
        return None
    return value_text


def _extract_float(record: dict[str, Any], aliases: list[str]) -> float | None:
    value = _extract_raw(record=record, aliases=aliases)
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    value_text = str(value).strip()
    if value_text == "":
        return None
    normalized = value_text.replace(",", ".")
    try:
        return float(normalized)
    except ValueError:
        return None


def _extract_raw(record: dict[str, Any], aliases: list[str]) -> Any:
    for alias in aliases:
        if alias in record:
            return record.get(alias)
    lower_index = {str(key).lower(): value for key, value in record.items()}
    for alias in aliases:
        if alias.lower() in lower_index:
            return lower_index[alias.lower()]
    return None


def _mapping(
    *,
    variable_code: str,
    aliases: list[str],
    unit_aliases: list[str],
    default_unit: str,
) -> dict[str, Any]:
    return {
        "variable_code": variable_code,
        "aliases": aliases,
        "unit_aliases": unit_aliases,
        "default_unit": default_unit,
    }


def _normalize_variable_name(value: str) -> str | None:
    key = value.strip().lower().replace(" ", "").replace("_", "").replace("-", "")
    aliases = {
        "temperatura": "temperature_c",
        "temperature": "temperature_c",
        "umidade": "humidity_pct",
        "humidity": "humidity_pct",
        "chuva": "rainfall_mm_1h",
        "precipitacao": "rainfall_mm_1h",
        "vazao": "river_flow_m3s",
        "fluxo": "river_flow_m3s",
        "nivel": "river_level_m",
        "nivel_rio": "river_level_m",
        "vento": "wind_speed_mps",
        "pm25": "pm25_ugm3",
        "mp25": "pm25_ugm3",
        "pm2,5": "pm25_ugm3",
        "pm2.5": "pm25_ugm3",
        "mp2,5": "pm25_ugm3",
        "mp2.5": "pm25_ugm3",
        "pm10": "pm10_ugm3",
        "mp10": "pm10_ugm3",
        "o3": "o3_ugm3",
        "ozonio": "o3_ugm3",
        "ozônio": "o3_ugm3",
        "no2": "no2_ugm3",
        "so2": "so2_ugm3",
        "co": "co_mgm3",
    }
    return aliases.get(key)


def _default_unit(variable_code: str) -> str:
    defaults = {
        "temperature_c": "c",
        "humidity_pct": "%",
        "rainfall_mm_1h": "mm",
        "river_flow_m3s": "m3/s",
        "river_level_m": "m",
        "wind_speed_mps": "m/s",
        "pm25_ugm3": "µg/m³",
        "pm10_ugm3": "µg/m³",
        "o3_ugm3": "µg/m³",
        "no2_ugm3": "µg/m³",
        "so2_ugm3": "µg/m³",
        "co_mgm3": "mg/m³",
    }
    return defaults.get(variable_code, "unit")


def _ensure_dict(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return item
    raise ValueError("Lista JSON deve conter objetos para parsing.")


def _redemet_status_record(item: list[Any]) -> dict[str, Any]:
    if len(item) < 5:
        raise ValueError("Registro de status REDEMET precisa conter ICAO, nome, latitude, longitude e cor.")
    return {"icao": item[0], "name": item[1], "latitude": item[2], "longitude": item[3], "status": item[4]}


def _metar_signed_number(value: str) -> float:
    return -float(value[1:]) if value.startswith("M") else float(value)


def _connector_config(value: str | None) -> dict[str, Any]:
    if value is None:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _configured_location(source: SourceModel) -> str | None:
    value = _connector_config(source.connector_config_json).get("station_code")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _geojson_feature_record(item: Any) -> dict[str, Any]:
    feature = _ensure_dict(item)
    properties = feature.get("properties")
    if not isinstance(properties, dict):
        raise ValueError("Feature GeoJSON deve conter properties como objeto.")
    return properties

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from http.client import HTTPConnection, HTTPSConnection
import json
import os
import socket
import time
import threading
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.error import HTTPError, URLError
from urllib.request import (
    HTTPHandler,
    HTTPRedirectHandler,
    HTTPSHandler,
    ProxyHandler,
    Request,
    build_opener,
)

from app.core.network_security import (
    resolve_public_destination,
    resolve_public_host,
    validate_connector_endpoint,
    validate_network_connector_runtime,
)
from app.core.settings import settings
from app.modules.catalog.models import SourceModel


@dataclass(slots=True)
class SourcePayload:
    content_bytes: bytes
    content_type: str
    source_timestamp: datetime | None
    metadata_json: str | None


def collect_from_source(
    source: SourceModel,
    collection_context: dict[str, str] | None = None,
) -> SourcePayload:
    validate_connector_endpoint(
        access_method=source.access_method,
        endpoint_reference=source.endpoint_reference,
    )
    if source.access_method == "http":
        return _collect_from_http(source=source, collection_context=collection_context)
    if collection_context is not None:
        raise ValueError(
            f"Reprocessamento por período ainda não é suportado para o conector '{source.access_method}'."
        )
    if source.access_method == "s3":
        return _collect_from_s3(source=source)
    if source.access_method == "mqtt":
        return _collect_from_mqtt(source=source)
    if source.access_method == "opcua":
        return _collect_from_opcua(source=source)
    raise ValueError(f"Método de acesso '{source.access_method}' não suportado para coleta automática.")


def _collect_from_http(
    source: SourceModel,
    collection_context: dict[str, str] | None,
) -> SourcePayload:
    config = _load_connector_config(source=source)
    headers = _build_http_headers(source=source, config=config)
    endpoint_reference = _resolve_http_endpoint_for_collection(
        source=source,
        config=config,
        collection_context=collection_context,
    )

    timeout_seconds = _as_positive_int(
        value=config.get("timeout_seconds", settings.ingestion_http_timeout_seconds),
        field_name="timeout_seconds",
    )
    if timeout_seconds > settings.ingestion_http_timeout_seconds:
        raise ValueError(
            "timeout_seconds não pode exceder INGESTION_HTTP_TIMEOUT_SECONDS."
        )
    retry_attempts = _as_bounded_positive_int(
        value=config.get("retry_attempts", settings.ingestion_http_retry_attempts),
        field_name="retry_attempts",
        maximum=10,
    )
    retry_backoff_seconds = _as_non_negative_float(
        value=config.get("retry_backoff_seconds", settings.ingestion_http_retry_backoff_seconds),
        field_name="retry_backoff_seconds",
    )
    if retry_backoff_seconds > 30:
        raise ValueError("retry_backoff_seconds não pode exceder 30 segundos.")
    max_response_bytes = _as_positive_int(
        value=config.get("max_response_bytes", settings.ingestion_http_max_response_bytes),
        field_name="max_response_bytes",
    )
    if max_response_bytes > settings.ingestion_http_max_response_bytes:
        raise ValueError(
            "max_response_bytes não pode exceder INGESTION_HTTP_MAX_RESPONSE_BYTES."
        )

    content_bytes, content_type = _fetch_http_with_retry(
        endpoint_reference=endpoint_reference,
        headers=headers,
        timeout_seconds=timeout_seconds,
        retry_attempts=retry_attempts,
        retry_backoff_seconds=retry_backoff_seconds,
        max_response_bytes=max_response_bytes,
    )

    metadata = {
        "endpoint": _safe_endpoint_reference(endpoint_reference),
        "method": "GET",
        "timeout_seconds": timeout_seconds,
        "retry_attempts": retry_attempts,
        "max_response_bytes": max_response_bytes,
    }
    if collection_context is not None:
        metadata["reprocess_period"] = collection_context
    return SourcePayload(
        content_bytes=content_bytes,
        content_type=content_type,
        source_timestamp=datetime.now(tz=timezone.utc),
        metadata_json=json.dumps(metadata, ensure_ascii=True),
    )


def _fetch_http_with_retry(
    *,
    endpoint_reference: str,
    headers: dict[str, str],
    timeout_seconds: int,
    retry_attempts: int,
    retry_backoff_seconds: float,
    max_response_bytes: int,
) -> tuple[bytes, str]:
    last_error: Exception | None = None
    for attempt in range(1, retry_attempts + 1):
        try:
            resolve_public_destination(endpoint_reference)
            request = Request(url=endpoint_reference, method="GET", headers=headers)
            with _open_pinned_http_request(request=request, timeout_seconds=timeout_seconds) as response:
                return (
                    _read_limited_response(response=response, max_response_bytes=max_response_bytes),
                    response.headers.get("Content-Type", "application/octet-stream"),
                )
        except HTTPError as exc:
            last_error = exc
            if exc.code < 500 or attempt == retry_attempts:
                raise
        except (URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt == retry_attempts:
                raise

        delay_seconds = retry_backoff_seconds * (2 ** (attempt - 1))
        if delay_seconds > 0:
            time.sleep(delay_seconds)

    if last_error is not None:
        raise last_error
    raise RuntimeError("Coleta HTTP terminou sem resposta ou erro.")


def _read_limited_response(response: Any, max_response_bytes: int) -> bytes:
    declared_size = response.headers.get("Content-Length")
    if declared_size is not None:
        try:
            parsed_size = int(declared_size)
        except ValueError:
            parsed_size = None
        if parsed_size is not None and parsed_size > max_response_bytes:
            raise ValueError(f"Resposta HTTP excede o limite de {max_response_bytes} bytes.")

    chunks: list[bytes] = []
    total_bytes = 0
    chunk_size = 64 * 1024
    while True:
        chunk = response.read(min(chunk_size, max_response_bytes - total_bytes + 1))
        if not chunk:
            return b"".join(chunks)
        total_bytes += len(chunk)
        if total_bytes > max_response_bytes:
            raise ValueError(f"Resposta HTTP excede o limite de {max_response_bytes} bytes.")
        chunks.append(chunk)


def _open_pinned_http_request(request: Request, timeout_seconds: int) -> Any:
    opener = build_opener(
        ProxyHandler({}),
        _NoRedirectHandler(),
        _PinnedHTTPHandler(),
        _PinnedHTTPSHandler(),
    )
    return opener.open(request, timeout=timeout_seconds)


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        raise HTTPError(
            url=req.full_url,
            code=code,
            msg="Redirecionamentos são bloqueados para conectores.",
            hdrs=headers,
            fp=fp,
        )


class _PinnedHTTPHandler(HTTPHandler):
    def http_open(self, req: Request):  # type: ignore[override]
        return self.do_open(_PinnedHTTPConnection, req)


class _PinnedHTTPSHandler(HTTPSHandler):
    def https_open(self, req: Request):  # type: ignore[override]
        return self.do_open(_PinnedHTTPSConnection, req)


class _PinnedHTTPConnection(HTTPConnection):
    def connect(self) -> None:
        self.sock = _connect_to_public_ip(
            hostname=self.host,
            port=self.port,
            timeout=self.timeout,
            source_address=self.source_address,
        )
        if self._tunnel_host:
            self._tunnel()


class _PinnedHTTPSConnection(HTTPSConnection):
    def connect(self) -> None:
        sock = _connect_to_public_ip(
            hostname=self.host,
            port=self.port,
            timeout=self.timeout,
            source_address=self.source_address,
        )
        if self._tunnel_host:
            self.sock = sock
            self._tunnel()
            sock = self.sock
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def _connect_to_public_ip(
    hostname: str,
    port: int,
    timeout: float | object,
    source_address: tuple[str, int] | None,
) -> socket.socket:
    errors: list[OSError] = []
    for address in resolve_public_host(hostname, port):
        try:
            return socket.create_connection(
                (address, port),
                timeout=timeout,
                source_address=source_address,
            )
        except OSError as exc:
            errors.append(exc)
    if errors:
        raise errors[-1]
    raise OSError(f"Não foi possível conectar a '{hostname}'.")


def _safe_endpoint_reference(endpoint_reference: str) -> str:
    parsed = urlparse(endpoint_reference)
    return urlunparse(parsed._replace(query="", fragment=""))


def _apply_date_placeholders(endpoint_reference: str) -> str:
    """Substitui marcadores de data na URL (APIs que exigem período explícito,
    como a telemetria da ANA que pede DataInicio/DataFim em dd/mm/aaaa)."""
    now = datetime.now(tz=timezone.utc)
    yesterday = now - timedelta(days=1)
    return (
        endpoint_reference
        .replace("{DATA_HOJE_BR}", now.strftime("%d/%m/%Y"))
        .replace("{DATA_ONTEM_BR}", yesterday.strftime("%d/%m/%Y"))
        .replace("{DATA_HOJE_ISO}", now.strftime("%Y-%m-%d"))
        .replace("{DATA_ONTEM_ISO}", yesterday.strftime("%Y-%m-%d"))
    )


def _resolve_http_endpoint_for_collection(
    source: SourceModel,
    config: dict[str, Any],
    collection_context: dict[str, str] | None,
) -> str:
    if collection_context is None:
        return _apply_date_placeholders(source.endpoint_reference)

    period_start = collection_context.get("period_start_utc")
    period_end = collection_context.get("period_end_utc")
    if not period_start or not period_end:
        raise ValueError("Reprocessamento HTTP exige início e fim do período.")

    reprocess_config = config.get("reprocess")
    if not isinstance(reprocess_config, dict):
        raise ValueError(
            "Conector HTTP não declara suporte a reprocessamento. "
            "Configure reprocess.start_query_param e reprocess.end_query_param."
        )
    start_param = reprocess_config.get("start_query_param")
    end_param = reprocess_config.get("end_query_param")
    if not isinstance(start_param, str) or not start_param.strip():
        raise ValueError("reprocess.start_query_param deve ser uma string não vazia.")
    if not isinstance(end_param, str) or not end_param.strip():
        raise ValueError("reprocess.end_query_param deve ser uma string não vazia.")

    parsed = urlparse(source.endpoint_reference)
    query_items = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key not in {start_param, end_param}
    ]
    query_items.extend(((start_param, period_start), (end_param, period_end)))
    return urlunparse(parsed._replace(query=urlencode(query_items)))


def _collect_from_s3(source: SourceModel) -> SourcePayload:
    config = _load_connector_config(source=source)
    if source.authentication_type not in {"none", "aws_env"}:
        raise ValueError(
            f"authentication_type '{source.authentication_type}' não suportado para método s3."
        )

    parsed = urlparse(source.endpoint_reference)
    if parsed.scheme != "s3" or not parsed.netloc or not parsed.path:
        raise ValueError("endpoint_reference inválido para S3. Use o formato s3://bucket/chave.")

    bucket_name = parsed.netloc
    object_key = parsed.path.lstrip("/")
    region_name = config.get("region_name")

    try:
        import boto3
    except ModuleNotFoundError as exc:
        raise RuntimeError("Dependência boto3 ausente para coletor S3.") from exc

    s3_client = boto3.client("s3", region_name=region_name)
    response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
    body = response["Body"].read()
    content_type = response.get("ContentType", "application/octet-stream")
    source_timestamp = response.get("LastModified")
    if isinstance(source_timestamp, datetime) and source_timestamp.tzinfo is None:
        source_timestamp = source_timestamp.replace(tzinfo=timezone.utc)

    metadata = {
        "bucket": bucket_name,
        "object_key": object_key,
        "region_name": region_name,
    }
    return SourcePayload(
        content_bytes=body,
        content_type=content_type,
        source_timestamp=source_timestamp,
        metadata_json=json.dumps(metadata, ensure_ascii=True),
    )


def _collect_from_mqtt(source: SourceModel) -> SourcePayload:
    try:
        import paho.mqtt.client as mqtt_client
    except ModuleNotFoundError as exc:
        raise RuntimeError("Dependência paho-mqtt ausente para coletor MQTT.") from exc

    config = _load_connector_config(source=source)
    validate_network_connector_runtime(
        endpoint_reference=source.endpoint_reference,
        access_method="mqtt",
    )
    parsed = urlparse(source.endpoint_reference)
    if parsed.scheme != "mqtt" or not parsed.hostname:
        raise ValueError("endpoint_reference inválido para MQTT. Use o formato mqtt://host:porta/topico.")
    topic = parsed.path.lstrip("/")
    if topic == "":
        raise ValueError("endpoint_reference MQTT deve incluir o tópico no path.")

    broker_host = parsed.hostname
    broker_port = parsed.port or 1883
    qos = _as_non_negative_int(value=config.get("qos", 0), field_name="qos")
    keepalive = _as_positive_int(value=config.get("keepalive_seconds", 30), field_name="keepalive_seconds")
    timeout_seconds = _as_positive_int(
        value=config.get("capture_timeout_seconds", settings.ingestion_mqtt_capture_timeout_seconds),
        field_name="capture_timeout_seconds",
    )
    message_count = _as_positive_int(value=config.get("message_count", 1), field_name="message_count")

    captured_messages: list[dict[str, Any]] = []
    lock = threading.Lock()
    completion_event = threading.Event()
    errors: list[str] = []

    def register_error(detail: str) -> None:
        with lock:
            if not errors:
                errors.append(detail)
        completion_event.set()

    def on_connect(client, _userdata, _flags, rc, _properties=None) -> None:
        if rc != 0:
            register_error(f"Falha ao conectar no broker MQTT (rc={rc}).")
            return
        client.subscribe(topic, qos=qos)

    def on_message(_client, _userdata, message) -> None:
        try:
            record = _coerce_mqtt_message_record(
                payload=bytes(message.payload),
                topic=message.topic,
                qos=message.qos,
                config=config,
            )
        except ValueError as exc:
            register_error(str(exc))
            return

        with lock:
            captured_messages.append(record)
            if len(captured_messages) >= message_count:
                completion_event.set()

    client = mqtt_client.Client()
    if source.authentication_type == "mqtt_userpass_env":
        username, password = _resolve_user_password_from_env(
            config=config,
            username_field_name="username_env_var",
            password_field_name="password_env_var",
            connector_name="mqtt",
        )
        client.username_pw_set(username=username, password=password)
    elif source.authentication_type != "none":
        raise ValueError(
            f"authentication_type '{source.authentication_type}' não suportado para método mqtt."
        )

    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(host=broker_host, port=broker_port, keepalive=keepalive)
        client.loop_start()
        finished = completion_event.wait(timeout=timeout_seconds)
        if not finished:
            raise TimeoutError(
                f"Timeout aguardando mensagens MQTT em '{topic}' ({timeout_seconds}s)."
            )
    finally:
        client.loop_stop()
        client.disconnect()

    if errors:
        raise RuntimeError(errors[0])
    if not captured_messages:
        raise RuntimeError(f"Nenhuma mensagem MQTT capturada no tópico '{topic}'.")

    now_utc = datetime.now(tz=timezone.utc)
    metadata = {
        "broker_host": broker_host,
        "broker_port": broker_port,
        "topic": topic,
        "qos": qos,
        "message_count": message_count,
    }
    return SourcePayload(
        content_bytes=json.dumps(captured_messages, ensure_ascii=True).encode("utf-8"),
        content_type="application/json",
        source_timestamp=now_utc,
        metadata_json=json.dumps(metadata, ensure_ascii=True),
    )


def _collect_from_opcua(source: SourceModel) -> SourcePayload:
    try:
        from opcua import Client as OpcuaClient
    except ModuleNotFoundError as exc:
        raise RuntimeError("Dependência opcua ausente para coletor OPC UA.") from exc

    config = _load_connector_config(source=source)
    validate_network_connector_runtime(
        endpoint_reference=source.endpoint_reference,
        access_method="opcua",
    )
    parsed = urlparse(source.endpoint_reference)
    if parsed.scheme != "opc.tcp":
        raise ValueError("endpoint_reference inválido para OPC UA. Use o formato opc.tcp://host:porta.")

    timeout_seconds = _as_positive_int(
        value=config.get("timeout_seconds", settings.ingestion_opcua_timeout_seconds),
        field_name="timeout_seconds",
    )
    nodes = config.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        raise ValueError(
            "Conector OPC UA exige 'nodes' no connector_config_json com ao menos um item."
        )

    client = OpcuaClient(source.endpoint_reference, timeout=timeout_seconds)
    if source.authentication_type == "opcua_userpass_env":
        username, password = _resolve_user_password_from_env(
            config=config,
            username_field_name="username_env_var",
            password_field_name="password_env_var",
            connector_name="opcua",
        )
        client.set_user(username)
        client.set_password(password)
    elif source.authentication_type != "none":
        raise ValueError(
            f"authentication_type '{source.authentication_type}' não suportado para método opcua."
        )

    records: list[dict[str, Any]] = []
    source_timestamps: list[datetime] = []
    client.connect()
    try:
        for item in nodes:
            if not isinstance(item, dict):
                raise ValueError("Cada item de 'nodes' deve ser objeto JSON.")
            node_id = item.get("node_id")
            if not isinstance(node_id, str) or node_id.strip() == "":
                raise ValueError("Cada item de 'nodes' deve conter 'node_id' string não vazia.")

            node = client.get_node(node_id)
            node_value = node.get_value()
            data_value = node.get_data_value()
            source_timestamp = _resolve_opcua_timestamp(data_value=data_value)
            if source_timestamp is not None:
                source_timestamps.append(source_timestamp)

            variable_code = item.get("variable_code")
            if not isinstance(variable_code, str) or variable_code.strip() == "":
                variable_code = _infer_variable_from_text(node_id)

            record = {
                "observed_at": (
                    source_timestamp.isoformat() if source_timestamp is not None else datetime.now(tz=timezone.utc).isoformat()
                ),
                "variable_code": variable_code,
                "value": node_value,
                "unit": item.get("unit") or "unit",
                "location": item.get("location_code"),
                "node_id": node_id,
            }
            records.append(record)
    finally:
        client.disconnect()

    if not records:
        raise RuntimeError("Conector OPC UA não retornou leituras.")

    source_timestamp = max(source_timestamps) if source_timestamps else datetime.now(tz=timezone.utc)
    metadata = {
        "endpoint_reference": source.endpoint_reference,
        "nodes_count": len(records),
    }
    return SourcePayload(
        content_bytes=json.dumps(records, ensure_ascii=True).encode("utf-8"),
        content_type="application/json",
        source_timestamp=source_timestamp,
        metadata_json=json.dumps(metadata, ensure_ascii=True),
    )


def _load_connector_config(source: SourceModel) -> dict[str, Any]:
    if not source.connector_config_json:
        return {}
    try:
        config = json.loads(source.connector_config_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"connector_config_json inválido para fonte '{source.source_id}'.") from exc
    if not isinstance(config, dict):
        raise ValueError("connector_config_json deve ser um objeto JSON.")
    return config


def _build_http_headers(source: SourceModel, config: dict[str, Any]) -> dict[str, str]:
    headers: dict[str, str] = {"User-Agent": "Meteoro-Ingestion/0.1"}
    config_headers = config.get("headers")
    if config_headers is not None:
        if not isinstance(config_headers, dict):
            raise ValueError("headers em connector_config_json deve ser objeto JSON.")
        for header_name, header_value in config_headers.items():
            if not isinstance(header_name, str) or not isinstance(header_value, str):
                raise ValueError("headers em connector_config_json deve mapear string para string.")
            if header_name.lower() in {
                "host",
                "connection",
                "content-length",
                "proxy-authorization",
                "transfer-encoding",
            }:
                raise ValueError(f"Header HTTP '{header_name}' não é permitido para conectores.")
            headers[header_name] = header_value

    if source.authentication_type == "none":
        return headers

    if source.authentication_type == "api_key_env":
        header_name = config.get("api_key_header")
        env_var = config.get("api_key_env_var")
        if not isinstance(header_name, str) or not isinstance(env_var, str):
            raise ValueError(
                "authentication_type=api_key_env exige api_key_header e api_key_env_var no connector_config_json."
            )
        api_key = os.getenv(env_var)
        if not api_key:
            raise ValueError(f"Variável de ambiente '{env_var}' não definida para API key.")
        headers[header_name] = api_key
        return headers

    if source.authentication_type == "bearer_env":
        env_var = config.get("bearer_token_env_var")
        if not isinstance(env_var, str):
            raise ValueError(
                "authentication_type=bearer_env exige bearer_token_env_var no connector_config_json."
            )
        bearer_token = os.getenv(env_var)
        if not bearer_token:
            raise ValueError(f"Variável de ambiente '{env_var}' não definida para token bearer.")
        headers["Authorization"] = f"Bearer {bearer_token}"
        return headers

    raise ValueError(
        f"Tipo de autenticação '{source.authentication_type}' não suportado para coletor HTTP."
    )


def _coerce_mqtt_message_record(
    payload: bytes,
    topic: str,
    qos: int,
    config: dict[str, Any],
) -> dict[str, Any]:
    payload_text = payload.decode("utf-8")
    try:
        parsed_payload: Any = json.loads(payload_text)
    except json.JSONDecodeError:
        parsed_payload = payload_text

    if isinstance(parsed_payload, dict):
        record = dict(parsed_payload)
    else:
        record = {"value": parsed_payload}

    if not isinstance(record, dict):
        raise ValueError("Payload MQTT inválido para composição de registro.")

    if "observed_at" not in record and "timestamp" not in record:
        record["observed_at"] = datetime.now(tz=timezone.utc).isoformat()

    variable_code = record.get("variable_code")
    if not isinstance(variable_code, str) or variable_code.strip() == "":
        topic_map = config.get("topic_variable_map")
        if isinstance(topic_map, dict):
            mapped_value = topic_map.get(topic)
            if isinstance(mapped_value, str) and mapped_value.strip() != "":
                variable_code = mapped_value
        if not isinstance(variable_code, str) or variable_code.strip() == "":
            configured_variable = config.get("variable_code")
            if isinstance(configured_variable, str) and configured_variable.strip() != "":
                variable_code = configured_variable
        if not isinstance(variable_code, str) or variable_code.strip() == "":
            variable_code = _infer_variable_from_text(topic)
        record["variable_code"] = variable_code

    if "unit" not in record:
        configured_unit = config.get("unit")
        if isinstance(configured_unit, str) and configured_unit.strip() != "":
            record["unit"] = configured_unit
    if "location" not in record and "station" not in record:
        configured_location = config.get("location_code")
        if isinstance(configured_location, str) and configured_location.strip() != "":
            record["location"] = configured_location
        else:
            record["location"] = topic

    record["topic"] = topic
    record["qos"] = qos
    return record


def _resolve_opcua_timestamp(data_value: Any) -> datetime | None:
    for field_name in ("SourceTimestamp", "ServerTimestamp"):
        field_value = getattr(data_value, field_name, None)
        if isinstance(field_value, datetime):
            if field_value.tzinfo is None:
                return field_value.replace(tzinfo=timezone.utc)
            return field_value.astimezone(timezone.utc)
    return None


def _resolve_user_password_from_env(
    *,
    config: dict[str, Any],
    username_field_name: str,
    password_field_name: str,
    connector_name: str,
) -> tuple[str, str]:
    username_env = config.get(username_field_name)
    password_env = config.get(password_field_name)
    if not isinstance(username_env, str) or not isinstance(password_env, str):
        raise ValueError(
            f"authentication_type de {connector_name} exige '{username_field_name}' e '{password_field_name}'."
        )

    username = os.getenv(username_env)
    password = os.getenv(password_env)
    if not username:
        raise ValueError(f"Variável de ambiente '{username_env}' não definida para {connector_name}.")
    if not password:
        raise ValueError(f"Variável de ambiente '{password_env}' não definida para {connector_name}.")
    return username, password


def _infer_variable_from_text(value: str) -> str:
    normalized = value.strip().lower()
    if "temp" in normalized:
        return "temperature_c"
    if "humid" in normalized or "umid" in normalized:
        return "humidity_pct"
    if "rain" in normalized or "chuva" in normalized:
        return "rainfall_mm_1h"
    if "wind" in normalized or "vento" in normalized:
        return "wind_speed_mps"
    if "level" in normalized or "nivel" in normalized:
        return "river_level_m"
    if "flow" in normalized or "vazao" in normalized:
        return "river_flow_m3s"
    return "sensor_value"


def _as_positive_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} deve ser inteiro positivo.")
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str) and value.strip() != "":
        parsed = int(value.strip())
    else:
        raise ValueError(f"{field_name} deve ser inteiro positivo.")
    if parsed <= 0:
        raise ValueError(f"{field_name} deve ser maior que zero.")
    return parsed


def _as_bounded_positive_int(value: Any, field_name: str, maximum: int) -> int:
    parsed = _as_positive_int(value=value, field_name=field_name)
    if parsed > maximum:
        raise ValueError(f"{field_name} não pode exceder {maximum}.")
    return parsed


def _as_non_negative_float(value: Any, field_name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} deve ser número não negativo.")
    if isinstance(value, (int, float)):
        parsed = float(value)
    elif isinstance(value, str) and value.strip() != "":
        try:
            parsed = float(value.strip())
        except ValueError as exc:
            raise ValueError(f"{field_name} deve ser número não negativo.") from exc
    else:
        raise ValueError(f"{field_name} deve ser número não negativo.")
    if parsed < 0:
        raise ValueError(f"{field_name} deve ser maior ou igual a zero.")
    return parsed


def _as_non_negative_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} deve ser inteiro não negativo.")
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str) and value.strip() != "":
        parsed = int(value.strip())
    else:
        raise ValueError(f"{field_name} deve ser inteiro não negativo.")
    if parsed < 0:
        raise ValueError(f"{field_name} deve ser maior ou igual a zero.")
    return parsed


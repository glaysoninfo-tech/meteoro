"""Validation and runtime safeguards for outbound connector destinations."""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import socket
from urllib.parse import urlparse

from app.core.settings import settings


@dataclass(frozen=True, slots=True)
class NetworkDestination:
    scheme: str
    hostname: str
    port: int


def validate_connector_endpoint(access_method: str, endpoint_reference: str) -> None:
    """Validate a configured endpoint without performing a network request."""
    if access_method == "manual_file":
        parsed = urlparse(endpoint_reference)
        if parsed.scheme != "manual":
            raise ValueError("endpoint_reference de fonte manual_file deve iniciar com manual://.")
        return

    if access_method == "s3":
        parsed = urlparse(endpoint_reference)
        if parsed.scheme != "s3" or not parsed.netloc or not parsed.path.strip("/"):
            raise ValueError("endpoint_reference inválido para S3. Use s3://bucket/chave.")
        _validate_allowed_s3_bucket(parsed.netloc)
        return

    supported_schemes = {
        "http": _csv_setting(settings.ingestion_http_allowed_schemes),
        "mqtt": {"mqtt"},
        "opcua": {"opc.tcp"},
    }
    allowed_schemes = supported_schemes.get(access_method)
    if allowed_schemes is None:
        raise ValueError(f"Método de acesso '{access_method}' não suportado para validação de destino.")

    destination = _parse_network_destination(
        endpoint_reference=endpoint_reference,
        allowed_schemes=allowed_schemes,
    )
    _validate_allowed_host(destination.hostname)
    _validate_allowed_port(destination.port)


def resolve_public_destination(endpoint_reference: str) -> NetworkDestination:
    """Resolve and validates a destination immediately before a network connection."""
    destination = _parse_network_destination(
        endpoint_reference=endpoint_reference,
        allowed_schemes=_csv_setting(settings.ingestion_http_allowed_schemes),
    )
    _validate_allowed_host(destination.hostname)
    _validate_allowed_port(destination.port)
    _resolve_public_ips(destination.hostname, destination.port)
    return destination


def resolve_public_host(hostname: str, port: int) -> list[str]:
    """Return public resolved IPs only; used to pin outbound HTTP connections."""
    _validate_allowed_host(hostname)
    _validate_allowed_port(port)
    return _resolve_public_ips(hostname, port)


def validate_network_connector_runtime(endpoint_reference: str, access_method: str) -> NetworkDestination:
    """Resolve a non-HTTP network connector before handing it to a client library."""
    allowed_schemes = {"mqtt"} if access_method == "mqtt" else {"opc.tcp"}
    destination = _parse_network_destination(endpoint_reference, allowed_schemes)
    _validate_allowed_host(destination.hostname)
    _validate_allowed_port(destination.port)
    _resolve_public_ips(destination.hostname, destination.port)
    return destination


def _parse_network_destination(
    endpoint_reference: str,
    allowed_schemes: set[str],
) -> NetworkDestination:
    try:
        parsed = urlparse(endpoint_reference)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("endpoint_reference contém porta inválida.") from exc

    scheme = parsed.scheme.lower()
    if scheme not in allowed_schemes:
        allowed = ", ".join(sorted(allowed_schemes)) or "nenhum"
        raise ValueError(f"Esquema de destino não permitido: '{scheme}'. Permitidos: {allowed}.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Credenciais não podem ser informadas na URL do conector.")
    if not parsed.hostname:
        raise ValueError("endpoint_reference deve conter um hostname.")

    hostname = parsed.hostname.rstrip(".").lower()
    if not hostname:
        raise ValueError("endpoint_reference deve conter um hostname válido.")
    default_ports = {"https": 443, "http": 80, "mqtt": 1883, "opc.tcp": 4840}
    return NetworkDestination(
        scheme=scheme,
        hostname=hostname,
        port=port or default_ports[scheme],
    )


def _validate_allowed_host(hostname: str) -> None:
    allowed_hosts = _csv_setting(settings.ingestion_network_allowed_hosts)
    if not allowed_hosts:
        raise ValueError(
            "Nenhum destino de rede está liberado. Configure INGESTION_NETWORK_ALLOWED_HOSTS."
        )
    if any(_host_matches_allowlist(hostname, rule) for rule in allowed_hosts):
        return
    raise ValueError(f"Hostname '{hostname}' não está na allowlist de conectores.")


def _validate_allowed_s3_bucket(bucket_name: str) -> None:
    allowed_buckets = _csv_setting(settings.ingestion_s3_allowed_buckets)
    if not allowed_buckets:
        raise ValueError("Nenhum bucket S3 está liberado. Configure INGESTION_S3_ALLOWED_BUCKETS.")
    if bucket_name in allowed_buckets:
        return
    raise ValueError(f"Bucket S3 '{bucket_name}' não está na allowlist de conectores.")


def _validate_allowed_port(port: int) -> None:
    allowed_ports = _int_csv_setting(settings.ingestion_network_allowed_ports)
    if port not in allowed_ports:
        allowed = ", ".join(str(item) for item in sorted(allowed_ports))
        raise ValueError(f"Porta {port} não está na allowlist de conectores ({allowed}).")


def _resolve_public_ips(hostname: str, port: int) -> list[str]:
    try:
        records = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f"Não foi possível resolver o hostname '{hostname}'.") from exc

    addresses: list[str] = []
    for _family, _socktype, _proto, _canonname, sockaddr in records:
        address = sockaddr[0]
        try:
            parsed_ip = ipaddress.ip_address(address)
        except ValueError as exc:
            raise ValueError(f"DNS retornou endereço inválido para '{hostname}'.") from exc
        if not parsed_ip.is_global:
            raise ValueError(
                f"Destino '{hostname}' resolve para endereço não público e foi bloqueado."
            )
        if address not in addresses:
            addresses.append(address)
    if not addresses:
        raise ValueError(f"Não foi encontrado endereço IP público para '{hostname}'.")
    return addresses


def _host_matches_allowlist(hostname: str, rule: str) -> bool:
    normalized_rule = rule.lower().rstrip(".")
    if normalized_rule.startswith("*."):
        suffix = normalized_rule[1:]
        return hostname.endswith(suffix) and hostname != suffix[1:]
    return hostname == normalized_rule


def _csv_setting(value: str) -> set[str]:
    return {item.strip().lower() for item in value.split(",") if item.strip()}


def _int_csv_setting(value: str) -> set[int]:
    parsed_values: set[int] = set()
    for item in value.split(","):
        stripped = item.strip()
        if not stripped:
            continue
        try:
            port = int(stripped)
        except ValueError as exc:
            raise ValueError("INGESTION_NETWORK_ALLOWED_PORTS deve conter somente inteiros.") from exc
        if not 1 <= port <= 65535:
            raise ValueError("INGESTION_NETWORK_ALLOWED_PORTS contém porta fora do intervalo válido.")
        parsed_values.add(port)
    if not parsed_values:
        raise ValueError("INGESTION_NETWORK_ALLOWED_PORTS não pode estar vazio.")
    return parsed_values

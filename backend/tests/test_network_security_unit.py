from __future__ import annotations

from urllib.error import URLError

import pytest

from app.core import network_security
from app.modules.ingestion import connectors


def test_destination_allowlist_rejects_private_and_unlisted_hosts() -> None:
    network_security.validate_connector_endpoint("http", "https://api.example.org/readings")

    with pytest.raises(ValueError, match="allowlist"):
        network_security.validate_connector_endpoint("http", "https://internal.example.net/readings")

    with pytest.raises(ValueError, match="allowlist"):
        network_security.validate_connector_endpoint("http", "https://127.0.0.1/readings")


def test_destination_rejects_http_when_only_https_is_allowed() -> None:
    with pytest.raises(ValueError, match="Esquema"):
        network_security.validate_connector_endpoint("http", "http://api.example.org/readings")


def test_http_fetch_retries_transient_error_and_limits_response(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    class Response:
        headers = {"Content-Type": "application/json", "Content-Length": "2"}

        def __enter__(self) -> "Response":
            self._sent = False
            return self

        def __exit__(self, *args: object) -> bool:
            return False

        def read(self, _size: int) -> bytes:
            if self._sent:
                return b""
            self._sent = True
            return b"{}"

    def open_once_then_succeed(*, request, timeout_seconds: int):  # type: ignore[no-untyped-def]
        calls.append(request.full_url)
        if len(calls) == 1:
            raise URLError("temporary network issue")
        assert timeout_seconds == 5
        return Response()

    monkeypatch.setattr(connectors, "resolve_public_destination", lambda _url: None)
    monkeypatch.setattr(connectors, "_open_pinned_http_request", open_once_then_succeed)
    body, content_type = connectors._fetch_http_with_retry(
        endpoint_reference="https://api.example.org/readings",
        headers={},
        timeout_seconds=5,
        retry_attempts=2,
        retry_backoff_seconds=0,
        max_response_bytes=10,
    )

    assert body == b"{}"
    assert content_type == "application/json"
    assert len(calls) == 2


def test_http_fetch_rejects_body_larger_than_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        headers = {"Content-Type": "application/json", "Content-Length": "11"}

        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *args: object) -> bool:
            return False

    monkeypatch.setattr(connectors, "resolve_public_destination", lambda _url: None)
    monkeypatch.setattr(
        connectors,
        "_open_pinned_http_request",
        lambda **_kwargs: Response(),
    )

    with pytest.raises(ValueError, match="excede o limite"):
        connectors._fetch_http_with_retry(
            endpoint_reference="https://api.example.org/readings",
            headers={},
            timeout_seconds=5,
            retry_attempts=1,
            retry_backoff_seconds=0,
            max_response_bytes=10,
        )

"""Contexto por requisição (request-id) propagado via contextvars.

Permite que qualquer log emitido durante o atendimento de uma requisição
carregue o mesmo identificador, correlacionando API, serviços e erros.
"""

from __future__ import annotations

from contextvars import ContextVar

_request_id: ContextVar[str | None] = ContextVar("meteoro_request_id", default=None)


def set_request_id(value: str) -> object:
    return _request_id.set(value)


def reset_request_id(token: object) -> None:
    _request_id.reset(token)  # type: ignore[arg-type]


def get_request_id() -> str | None:
    return _request_id.get()

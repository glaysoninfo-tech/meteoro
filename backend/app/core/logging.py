"""Logging estruturado (JSON) para API e worker.

Uma linha JSON por evento, com timestamp UTC, nível, logger, mensagem e
request_id quando disponível — pronto para agregadores (Loki, ELK) e para
grep humano em produção assistida.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

from app.core.request_context import get_request_id


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = get_request_id()
        if request_id:
            payload["request_id"] = request_id
        extra_fields = getattr(record, "extra_fields", None)
        if isinstance(extra_fields, dict):
            payload.update(extra_fields)
        if record.exc_info and record.exc_info != (None, None, None):
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    """Instala o formatador JSON no logger raiz (idempotente)."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = [handler]

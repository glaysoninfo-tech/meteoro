from __future__ import annotations

import os
from pathlib import Path

from redis import Redis
from sqlalchemy import text

from app.core.settings import settings
from app.db.session import engine


def readiness_report() -> tuple[dict[str, object], bool]:
    database_ok = _database_available()
    storage_ok = _storage_available()
    redis_ok = _redis_available()
    critical_ok = database_ok and storage_ok and (redis_ok or not settings.readiness_require_redis)
    degraded = critical_ok and not redis_ok
    report: dict[str, object] = {
        "status": "ready" if critical_ok and not degraded else "degraded" if critical_ok else "not_ready",
        "service": settings.app_name,
        "environment": settings.environment,
        "components": {
            "database": _component(database_ok, required=True),
            "raw_storage": _component(storage_ok, required=True),
            "redis": _component(redis_ok, required=settings.readiness_require_redis),
        },
    }
    return report, critical_ok


def _component(available: bool, required: bool) -> dict[str, object]:
    return {"status": "ok" if available else "unavailable", "required": required}


def _database_available() -> bool:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:  # Readiness must not expose dependency internals.
        return False


def _storage_available() -> bool:
    storage_path = Path(settings.ingestion_storage_path).expanduser()
    parent = storage_path if storage_path.exists() else storage_path.parent
    return parent.exists() and parent.is_dir() and os.access(parent, os.R_OK | os.W_OK)


def _redis_available() -> bool:
    try:
        client = Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=settings.readiness_redis_timeout_seconds,
            socket_timeout=settings.readiness_redis_timeout_seconds,
        )
        return bool(client.ping())
    except Exception:
        return False

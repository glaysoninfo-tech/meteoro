"""Exposição de métricas em formato Prometheus, sem dependências externas.

Métricas de processo (contadores HTTP) + métricas derivadas do estado real
(staleness por fonte, filas, prontidão). A mais importante para defesa civil
é `meteoro_source_staleness_seconds`: idade da última coleta bem-sucedida de
cada fonte ativa — é ela que denuncia pipeline parado com painel "verde".
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

_lock = threading.Lock()
_requests_by_class: dict[str, int] = {}
_request_duration_sum_ms = 0.0
_request_duration_count = 0


def record_request(status_code: int, duration_ms: float) -> None:
    """Chamado pelo middleware a cada requisição atendida."""
    global _request_duration_sum_ms, _request_duration_count
    status_class = f"{status_code // 100}xx"
    with _lock:
        _requests_by_class[status_class] = _requests_by_class.get(status_class, 0) + 1
        _request_duration_sum_ms += duration_ms
        _request_duration_count += 1


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def render_metrics(db: Session) -> str:
    from app.core.health import readiness_report
    from app.modules.catalog.models import SourceModel
    from app.modules.data_quality.models import QualityIssueModel

    now = datetime.now(tz=timezone.utc)
    lines: list[str] = []

    # --- HTTP ---
    lines.append("# TYPE meteoro_http_requests_total counter")
    with _lock:
        for status_class, count in sorted(_requests_by_class.items()):
            lines.append(
                f'meteoro_http_requests_total{{status_class="{status_class}"}} {count}'
            )
        lines.append("# TYPE meteoro_http_request_duration_ms_sum counter")
        lines.append(f"meteoro_http_request_duration_ms_sum {_request_duration_sum_ms:.1f}")
        lines.append(f"meteoro_http_request_duration_ms_count {_request_duration_count}")

    # --- Staleness por fonte ativa (a métrica que salva vidas) ---
    lines.append("# TYPE meteoro_source_staleness_seconds gauge")
    lines.append("# HELP meteoro_source_staleness_seconds Idade da última coleta bem-sucedida por fonte ativa")
    sources = db.scalars(
        select(SourceModel).where(SourceModel.status == "active")
    ).all()
    for source in sources:
        labels = (
            f'source_name="{_escape(source.source_name)}",'
            f'criticality="{_escape(source.criticality)}",'
            f'access_method="{_escape(source.access_method)}"'
        )
        if source.last_success_at is None:
            lines.append(f"meteoro_source_never_collected{{{labels}}} 1")
            continue
        staleness = (now - _aware(source.last_success_at)).total_seconds()
        lines.append(f"meteoro_source_staleness_seconds{{{labels}}} {staleness:.0f}")

    # --- Fila de qualidade ---
    pending_issues = db.scalar(
        select(func.count()).select_from(QualityIssueModel).where(
            QualityIssueModel.review_status == "pending"
        )
    ) or 0
    lines.append("# TYPE meteoro_quality_issues_pending gauge")
    lines.append(f"meteoro_quality_issues_pending {pending_issues}")

    # --- Prontidão e worker ---
    report, critical_ok = readiness_report()
    lines.append("# TYPE meteoro_ready gauge")
    lines.append(f"meteoro_ready {1 if critical_ok else 0}")
    components = report.get("components", {})
    for name, component in components.items():
        ok = 1 if component.get("status") == "ok" else 0
        lines.append(f'meteoro_component_ok{{component="{_escape(name)}"}} {ok}')

    try:
        from app.modules.ingestion.worker import RedisIngestionQueue

        status = RedisIngestionQueue().status()
        lines.append("# TYPE meteoro_worker_queue_available gauge")
        lines.append(f"meteoro_worker_queue_available {1 if status.get('queue_available') else 0}")
        queued = status.get("queued_jobs")
        if queued is not None:
            lines.append(f"meteoro_worker_queued_jobs {int(queued)}")
        heartbeat = status.get("heartbeat") or {}
        heartbeat_at = heartbeat.get("at_utc")
        if heartbeat_at:
            age = (now - datetime.fromisoformat(heartbeat_at)).total_seconds()
            lines.append(f"meteoro_worker_heartbeat_age_seconds {age:.0f}")
    except Exception:  # Redis fora não pode derrubar o scrape.
        lines.append("meteoro_worker_queue_available 0")

    return "\n".join(lines) + "\n"

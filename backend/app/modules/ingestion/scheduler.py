from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import threading

from sqlalchemy.orm import Session

from app.core.settings import settings
from app.db.session import SessionLocal
from app.modules.audit.service import audit_service
from app.modules.ingestion.schemas import (
    IngestionBatchSummary,
    IngestionSchedulerStatus,
    SchedulerTickSummary,
)
from app.modules.ingestion.service import ingestion_service

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _SchedulerState:
    enabled: bool
    running: bool
    in_progress: bool
    poll_interval_seconds: int
    last_started_at_utc: datetime | None
    last_finished_at_utc: datetime | None
    last_error: str | None
    last_tick: SchedulerTickSummary | None


class IngestionScheduler:
    def __init__(self) -> None:
        self._state = _SchedulerState(
            enabled=settings.ingestion_scheduler_enabled,
            running=False,
            in_progress=False,
            poll_interval_seconds=settings.ingestion_scheduler_poll_seconds,
            last_started_at_utc=None,
            last_finished_at_utc=None,
            last_error=None,
            last_tick=None,
        )
        self._state_lock = threading.Lock()
        self._run_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        with self._state_lock:
            self._state.enabled = settings.ingestion_scheduler_enabled
            self._state.poll_interval_seconds = settings.ingestion_scheduler_poll_seconds
            scheduler_enabled = self._state.enabled
            already_running = self._state.running

        if not scheduler_enabled:
            logger.info("Ingestion scheduler disabled by configuration.")
            return
        if already_running:
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="ingestion-scheduler",
            daemon=True,
        )
        self._thread.start()
        with self._state_lock:
            self._state.running = True
        logger.info("Ingestion scheduler started.")

    def stop(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=max(5, settings.ingestion_scheduler_poll_seconds + 1))
        with self._state_lock:
            self._state.running = False
        logger.info("Ingestion scheduler stopped.")

    def run_once(self) -> IngestionBatchSummary:
        with self._run_lock:
            started_at = datetime.now(tz=timezone.utc)
            with self._state_lock:
                self._state.in_progress = True
                self._state.last_started_at_utc = started_at
                self._state.last_error = None

            try:
                db = SessionLocal()
                try:
                    summary = ingestion_service.collect_due_sources_global(db=db)
                    self._audit_tick(db=db, summary=summary)
                finally:
                    db.close()
            except Exception as exc:
                finished_at = datetime.now(tz=timezone.utc)
                with self._state_lock:
                    self._state.in_progress = False
                    self._state.last_finished_at_utc = finished_at
                    self._state.last_error = str(exc)
                raise

            finished_at = datetime.now(tz=timezone.utc)
            with self._state_lock:
                self._state.in_progress = False
                self._state.last_finished_at_utc = finished_at
                self._state.last_error = None
                self._state.last_tick = SchedulerTickSummary(
                    tick_started_at_utc=started_at,
                    tick_finished_at_utc=finished_at,
                    total_sources=summary.total_sources,
                    collected_successfully=summary.collected_successfully,
                    failed=summary.failed,
                )
            return summary

    def get_status(self) -> IngestionSchedulerStatus:
        with self._state_lock:
            return IngestionSchedulerStatus(
                enabled=self._state.enabled,
                running=self._state.running,
                poll_interval_seconds=self._state.poll_interval_seconds,
                in_progress=self._state.in_progress,
                last_started_at_utc=self._state.last_started_at_utc,
                last_finished_at_utc=self._state.last_finished_at_utc,
                last_error=self._state.last_error,
                last_tick=self._state.last_tick,
            )

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                summary = self.run_once()
                logger.info(
                    "Ingestion scheduler tick finished: total=%s success=%s failed=%s",
                    summary.total_sources,
                    summary.collected_successfully,
                    summary.failed,
                )
            except Exception:
                logger.exception("Ingestion scheduler tick failed.")

            if self._stop_event.wait(settings.ingestion_scheduler_poll_seconds):
                break

    def _audit_tick(self, db: Session, summary: IngestionBatchSummary) -> None:
        per_organization: dict[str, dict[str, int]] = {}
        for result in summary.results:
            if result.organization_id is None:
                continue
            accumulator = per_organization.setdefault(
                result.organization_id,
                {"total": 0, "ok": 0, "failed": 0},
            )
            accumulator["total"] += 1
            if result.status == "completed":
                accumulator["ok"] += 1
            else:
                accumulator["failed"] += 1

        for organization_id, counters in per_organization.items():
            audit_service.create_event(
                db=db,
                module="ingestion",
                action="scheduler.tick",
                actor="system.scheduler",
                organization_id=organization_id,
                resource_type="ingestion_batch",
                resource_id=(
                    f"total:{counters['total']};ok:{counters['ok']};failed:{counters['failed']}"
                ),
            )


ingestion_scheduler = IngestionScheduler()

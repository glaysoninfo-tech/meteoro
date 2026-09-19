"""Redis-backed ingestion worker and scheduler, run outside the FastAPI process."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import secrets
import time
from typing import Any

from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.settings import settings
# O worker roda fora da API e não importa os routers; o import abaixo registra
# TODOS os models no metadata — sem ele, FKs entre módulos (ex.:
# ingestion_jobs.organization_id -> organizations) falham no flush.
from app.db import init_db as _models_registry  # noqa: F401
from app.db.session import SessionLocal
from app.modules.ingestion.models import IngestionJobModel
from app.modules.ingestion.service import ingestion_service

logger = logging.getLogger(__name__)


class RedisIngestionQueue:
    def __init__(self, client: Redis | None = None) -> None:
        self.client = client or Redis.from_url(settings.redis_url, decode_responses=True)
        self.queue_name = settings.ingestion_worker_queue_name
        self.heartbeat_key = f"{self.queue_name}:heartbeat"

    def enqueue(self, job_id: str) -> None:
        self.client.lpush(self.queue_name, job_id)

    def dequeue(self, timeout_seconds: int) -> str | None:
        item = self.client.brpop(self.queue_name, timeout=timeout_seconds)
        if item is None:
            return None
        _queue_name, job_id = item
        return str(job_id)

    def publish_heartbeat(self, detail: dict[str, Any]) -> None:
        payload = {"at_utc": datetime.now(tz=timezone.utc).isoformat(), **detail}
        self.client.set(
            self.heartbeat_key,
            json.dumps(payload, ensure_ascii=True),
            ex=max(settings.ingestion_worker_poll_seconds * 3, 30),
        )

    def status(self) -> dict[str, Any]:
        try:
            self.client.ping()
            raw_heartbeat = self.client.get(self.heartbeat_key)
            heartbeat = json.loads(raw_heartbeat) if raw_heartbeat else None
            return {
                "queue_available": True,
                "queued_jobs": int(self.client.llen(self.queue_name)),
                "heartbeat": heartbeat,
            }
        except (RedisError, json.JSONDecodeError):
            return {"queue_available": False, "queued_jobs": None, "heartbeat": None}


class RedisSourceLock:
    def __init__(self, client: Redis, source_id: str) -> None:
        self.client = client
        self.key = f"{settings.ingestion_worker_queue_name}:lock:source:{source_id}"
        self.token = secrets.token_urlsafe(24)

    def acquire(self) -> bool:
        return bool(
            self.client.set(
                self.key,
                self.token,
                nx=True,
                ex=settings.ingestion_worker_lock_ttl_seconds,
            )
        )

    def release(self) -> None:
        release_script = """
        if redis.call('get', KEYS[1]) == ARGV[1] then
            return redis.call('del', KEYS[1])
        end
        return 0
        """
        try:
            self.client.eval(release_script, 1, self.key, self.token)
        except RedisError:
            # Alguns clientes de teste não suportam Lua. Em Redis real o caminho acima
            # é atômico; esta alternativa só remove o lock quando o token ainda coincide.
            try:
                if self.client.get(self.key) == self.token:
                    self.client.delete(self.key)
            except RedisError:
                logger.exception(
                    "Falha ao liberar lock distribuído da fonte",
                    extra={"source_lock": self.key},
                )


class IngestionWorker:
    def __init__(
        self,
        queue: RedisIngestionQueue | None = None,
        session_factory: sessionmaker[Session] | None = None,
    ) -> None:
        self.queue = queue or RedisIngestionQueue()
        self.session_factory = session_factory or SessionLocal

    def enqueue_due_sources(self) -> int:
        with self.session_factory() as db:
            sources = ingestion_service.list_due_sources_global(db=db)
            created_jobs = 0
            for source in sources:
                job, created = ingestion_service.create_collection_job(
                    db=db,
                    organization_id=source.organization_id,
                    source_id=source.source_id,
                    trigger_type="scheduled",
                    run_metadata_json=None,
                    requested_by=None,
                )
                self.queue.enqueue(job.job_id)
                if created:
                    created_jobs += 1
            self.queue.publish_heartbeat({"event": "schedule_tick", "enqueued": created_jobs})
            return created_jobs

    def recover_queued_jobs(self) -> int:
        with self.session_factory() as db:
            jobs = list(
                db.scalars(
                    select(IngestionJobModel)
                    .where(IngestionJobModel.status == "queued")
                    .order_by(IngestionJobModel.created_at.asc())
                    .limit(500)
                ).all()
            )
            for job in jobs:
                self.queue.enqueue(job.job_id)
            return len(jobs)

    def process_next_job(self, timeout_seconds: int | None = None) -> bool:
        job_id = self.queue.dequeue(timeout_seconds or settings.ingestion_worker_poll_seconds)
        if job_id is None:
            self.queue.publish_heartbeat({"event": "idle"})
            return False
        self._process_job(job_id=job_id)
        return True

    def _process_job(self, job_id: str) -> None:
        with self.session_factory() as db:
            job = db.get(IngestionJobModel, job_id)
            if job is None or job.status != "queued":
                return

            lock = RedisSourceLock(self.queue.client, job.source_id)
            if not lock.acquire():
                self.queue.enqueue(job.job_id)
                self.queue.publish_heartbeat({"event": "lock_busy", "job_id": job.job_id})
                return

            try:
                job.status = "processing"
                job.started_at = datetime.now(tz=timezone.utc)
                job.attempts += 1
                job.error_summary = None
                db.commit()

                run = ingestion_service.collect_source(
                    db=db,
                    source_id=job.source_id,
                    organization_id=job.organization_id,
                    trigger_type=job.trigger_type,
                    run_metadata_json=job.run_metadata_json,
                    raise_on_failure=False,
                )
                job.ingestion_run_id = run.ingestion_run_id
                job.finished_at = datetime.now(tz=timezone.utc)
                job.status = "completed" if run.status == "completed" else "failed"
                job.error_summary = run.error_summary
                db.commit()
                self.queue.publish_heartbeat(
                    {"event": "job_finished", "job_id": job.job_id, "status": job.status}
                )
            except Exception as exc:
                db.rollback()
                failed_job = db.get(IngestionJobModel, job_id)
                if failed_job is not None:
                    failed_job.status = "failed"
                    failed_job.error_summary = str(exc)
                    failed_job.finished_at = datetime.now(tz=timezone.utc)
                    db.commit()
                self.queue.publish_heartbeat({"event": "job_failed", "job_id": job_id})
                logger.exception("Job de ingestão falhou", extra={"job_id": job_id})
            finally:
                lock.release()

    def run_forever(self) -> None:
        self.recover_queued_jobs()
        next_schedule_at = 0.0
        while True:
            now = time.monotonic()
            if settings.ingestion_scheduler_enabled and now >= next_schedule_at:
                try:
                    self.recover_queued_jobs()
                    self.enqueue_due_sources()
                except RedisError:
                    logger.exception("Não foi possível enfileirar coletas agendadas")
                next_schedule_at = now + settings.ingestion_scheduler_poll_seconds
            try:
                self.process_next_job()
            except RedisError:
                logger.exception("Worker perdeu conexão com Redis")
                time.sleep(settings.ingestion_worker_poll_seconds)


def main() -> None:
    from app.core.logging import configure_logging

    configure_logging()
    logger.info(
        "Worker de ingestão iniciado. Aguardando jobs na fila (Ctrl+C encerra).",
        extra={"extra_fields": {"queue": settings.ingestion_worker_queue_name}},
    )
    try:
        IngestionWorker().run_forever()
    except KeyboardInterrupt:
        # Encerramento solicitado pelo operador: saída limpa, sem stacktrace.
        logger.info("Worker de ingestão encerrado pelo operador.")


if __name__ == "__main__":
    main()

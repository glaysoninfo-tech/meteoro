from __future__ import annotations

import fakeredis
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.modules.ingestion import connectors
from app.modules.ingestion.models import IngestionJobModel
from app.modules.ingestion.service import ingestion_service
from app.modules.ingestion.worker import IngestionWorker, RedisIngestionQueue, RedisSourceLock
from tests.conftest import bootstrap_admin


def test_redis_source_lock_is_exclusive() -> None:
    client = fakeredis.FakeRedis(decode_responses=True)
    first = RedisSourceLock(client, "source-1")
    second = RedisSourceLock(client, "source-1")

    assert first.acquire() is True
    assert second.acquire() is False
    first.release()
    assert second.acquire() is True


def test_worker_executes_queued_collection_once(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch,
) -> None:
    headers = bootstrap_admin(client)
    source_response = client.post(
        "/api/v1/catalog/sources",
        headers=headers,
        json={
            "institution_name": "INMET",
            "source_name": "Leituras remotas",
            "source_type": "api",
            "access_method": "http",
            "authentication_type": "none",
            "endpoint_reference": "https://api.example.org/readings",
            "expected_frequency_minutes": 60,
            "criticality": "medium",
        },
    )
    assert source_response.status_code == 201, source_response.text
    source = source_response.json()

    class Response:
        headers = {"Content-Type": "application/json", "Content-Length": "105"}

        def __enter__(self) -> "Response":
            self._sent = False
            return self

        def __exit__(self, *args: object) -> bool:
            return False

        def read(self, _size: int) -> bytes:
            if self._sent:
                return b""
            self._sent = True
            return (
                b'[{"observed_at":"2026-07-14T12:00:00Z","variable_code":"temperature_c",'
                b'"value":24,"unit":"C"}]'
            )

    monkeypatch.setattr(connectors, "resolve_public_destination", lambda _url: None)
    monkeypatch.setattr(
        connectors,
        "_open_pinned_http_request",
        lambda **_kwargs: Response(),
    )
    redis_client = fakeredis.FakeRedis(decode_responses=True)
    queue = RedisIngestionQueue(client=redis_client)
    db = session_factory()
    try:
        job, created = ingestion_service.create_collection_job(
            db=db,
            organization_id=source["organization_id"],
            source_id=source["source_id"],
            trigger_type="manual_collect",
            run_metadata_json=None,
            requested_by="admin@example.org",
        )
        assert created is True
        queue.enqueue(job.job_id)
    finally:
        db.close()

    worker = IngestionWorker(queue=queue, session_factory=session_factory)
    assert worker.process_next_job(timeout_seconds=1) is True

    db = session_factory()
    try:
        completed = db.scalar(select(IngestionJobModel).where(IngestionJobModel.job_id == job.job_id))
        assert completed is not None
        assert completed.status == "completed"
        assert completed.ingestion_run_id is not None
        assert completed.attempts == 1
    finally:
        db.close()

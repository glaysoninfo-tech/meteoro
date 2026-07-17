from pathlib import Path
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from redis.exceptions import RedisError
from sqlalchemy.orm import Session

from app.core.settings import settings
from app.db.session import get_db
from app.modules.audit.service import audit_service
from app.modules.identity.dependencies import require_roles
from app.modules.identity.schemas import CurrentUser
from app.modules.ingestion.schemas import (
    ConnectorHealth,
    IngestionBatchSummary,
    IngestionJobOut,
    IngestionRunSummary,
    IngestionWorkerStatus,
    ObservationOut,
    ReprocessRequest,
)
from app.modules.ingestion.service import IngestionExecutionError, ingestion_service
from app.modules.ingestion.worker import RedisIngestionQueue

router = APIRouter()

_UPLOAD_CONTENT_TYPES: dict[str, set[str]] = {
    ".json": {"application/json", "text/json", "text/plain", "application/octet-stream"},
    ".csv": {"text/csv", "application/csv", "application/vnd.ms-excel", "text/plain", "application/octet-stream"},
}


async def _read_validated_upload(file: UploadFile) -> tuple[str, str, bytes]:
    filename = Path(file.filename or "").name
    if not filename:
        raise HTTPException(status_code=400, detail="Arquivo deve possuir nome.")

    extension = Path(filename).suffix.lower()
    allowed_content_types = _UPLOAD_CONTENT_TYPES.get(extension)
    if allowed_content_types is None:
        raise HTTPException(
            status_code=415,
            detail="Formato de arquivo não suportado. Envie um arquivo JSON ou CSV.",
        )

    content_type = (file.content_type or "application/octet-stream").split(";", 1)[0].strip().lower()
    if content_type not in allowed_content_types:
        raise HTTPException(
            status_code=415,
            detail=f"Content-Type '{content_type}' não é aceito para arquivos {extension}.",
        )

    chunks: list[bytes] = []
    total_bytes = 0
    while True:
        chunk = await file.read(settings.ingestion_upload_chunk_bytes)
        if not chunk:
            break
        total_bytes += len(chunk)
        if total_bytes > settings.ingestion_max_upload_bytes:
            raise HTTPException(
                status_code=413,
                detail=(
                    "Arquivo excede o limite de "
                    f"{settings.ingestion_max_upload_bytes} bytes para importação."
                ),
            )
        chunks.append(chunk)

    if total_bytes == 0:
        raise HTTPException(status_code=400, detail="Arquivo vazio.")
    return filename, content_type, b"".join(chunks)


@router.get("/runs/latest", response_model=list[IngestionRunSummary])
def latest_runs(
    current_user: CurrentUser = Depends(
        require_roles("admin_general", "operator", "analyst", "auditor")
    ),
    db: Session = Depends(get_db),
) -> list[IngestionRunSummary]:
    return ingestion_service.get_latest_runs(
        db=db,
        organization_id=current_user.organization_id,
    )


@router.post("/runs/reprocess", response_model=IngestionRunSummary)
def reprocess_period(
    payload: ReprocessRequest,
    current_user: CurrentUser = Depends(require_roles("admin_general", "operator")),
    db: Session = Depends(get_db),
) -> IngestionRunSummary:
    try:
        run = ingestion_service.request_reprocess(
            db=db,
            payload=payload,
            organization_id=current_user.organization_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IngestionExecutionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    audit_service.create_event(
        db=db,
        module="ingestion",
        action="run.reprocess_executed",
        actor=current_user.email,
        organization_id=current_user.organization_id,
        resource_type="ingestion_run",
        resource_id=run.ingestion_run_id,
    )
    return run


@router.post("/runs/collect/source/{source_id}", response_model=IngestionRunSummary)
def collect_source_now(
    source_id: str,
    current_user: CurrentUser = Depends(require_roles("admin_general", "operator")),
    db: Session = Depends(get_db),
) -> IngestionRunSummary:
    try:
        run = ingestion_service.collect_source(
            db=db,
            source_id=source_id,
            organization_id=current_user.organization_id,
            trigger_type="manual_collect",
            run_metadata_json=None,
            raise_on_failure=True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IngestionExecutionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    audit_service.create_event(
        db=db,
        module="ingestion",
        action="run.manual_collect",
        actor=current_user.email,
        organization_id=current_user.organization_id,
        resource_type="ingestion_run",
        resource_id=run.ingestion_run_id,
    )
    return run


@router.post(
    "/jobs/collect/source/{source_id}",
    response_model=IngestionJobOut,
    status_code=202,
)
def enqueue_source_collection(
    source_id: str,
    current_user: CurrentUser = Depends(require_roles("admin_general", "operator")),
    db: Session = Depends(get_db),
) -> IngestionJobOut:
    try:
        job, created = ingestion_service.create_collection_job(
            db=db,
            organization_id=current_user.organization_id,
            source_id=source_id,
            trigger_type="manual_collect",
            run_metadata_json=None,
            requested_by=current_user.email,
        )
        if created:
            RedisIngestionQueue().enqueue(job.job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RedisError as exc:
        raise HTTPException(
            status_code=503,
            detail="Job persistido, mas a fila Redis não está disponível. O worker fará recuperação.",
        ) from exc

    audit_service.create_event(
        db=db,
        module="ingestion",
        action="job.collection_queued",
        actor=current_user.email,
        organization_id=current_user.organization_id,
        resource_type="ingestion_job",
        resource_id=job.job_id,
    )
    return job


@router.get("/jobs/{job_id}", response_model=IngestionJobOut)
def get_ingestion_job(
    job_id: str,
    current_user: CurrentUser = Depends(
        require_roles("admin_general", "operator", "analyst", "auditor")
    ),
    db: Session = Depends(get_db),
) -> IngestionJobOut:
    job = ingestion_service.get_job(
        db=db,
        job_id=job_id,
        organization_id=current_user.organization_id,
    )
    if job is None:
        raise HTTPException(status_code=404, detail=f"job_id '{job_id}' não encontrado.")
    return job


@router.post("/runs/import/source/{source_id}", response_model=IngestionRunSummary)
async def import_source_file(
    source_id: str,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_roles("admin_general", "operator")),
    db: Session = Depends(get_db),
) -> IngestionRunSummary:
    file_name, file_content_type, file_bytes = await _read_validated_upload(file)

    try:
        run = ingestion_service.import_uploaded_file(
            db=db,
            organization_id=current_user.organization_id,
            source_id=source_id,
            file_name=file_name,
            file_content_type=file_content_type,
            file_bytes=file_bytes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IngestionExecutionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    audit_service.create_event(
        db=db,
        module="ingestion",
        action="run.manual_file_import",
        actor=current_user.email,
        organization_id=current_user.organization_id,
        resource_type="ingestion_run",
        resource_id=run.ingestion_run_id,
    )
    return run


@router.post("/runs/collect/all", response_model=IngestionBatchSummary)
def collect_all_sources(
    only_due: bool = Query(default=False),
    current_user: CurrentUser = Depends(require_roles("admin_general", "operator")),
    db: Session = Depends(get_db),
) -> IngestionBatchSummary:
    summary = ingestion_service.collect_sources_batch(
        db=db,
        organization_id=current_user.organization_id,
        only_due=only_due,
    )
    audit_service.create_event(
        db=db,
        module="ingestion",
        action="run.batch_collect",
        actor=current_user.email,
        organization_id=current_user.organization_id,
        resource_type="ingestion_batch",
        resource_id=f"count:{summary.total_sources}",
    )
    return summary


@router.get("/connectors/health", response_model=list[ConnectorHealth])
def connectors_health(
    current_user: CurrentUser = Depends(
        require_roles("admin_general", "operator", "analyst", "auditor")
    ),
    db: Session = Depends(get_db),
) -> list[ConnectorHealth]:
    return ingestion_service.get_connectors_health(
        db=db,
        organization_id=current_user.organization_id,
    )


@router.get("/observations/latest", response_model=list[ObservationOut])
def latest_observations(
    source_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: CurrentUser = Depends(
        require_roles("admin_general", "operator", "analyst", "auditor")
    ),
    db: Session = Depends(get_db),
) -> list[ObservationOut]:
    return ingestion_service.get_latest_observations(
        db=db,
        organization_id=current_user.organization_id,
        source_id=source_id,
        limit=limit,
    )


@router.get("/worker/status", response_model=IngestionWorkerStatus)
def worker_status(
    current_user: CurrentUser = Depends(
        require_roles("admin_general", "operator", "analyst", "auditor")
    ),
) -> IngestionWorkerStatus:
    status_data = RedisIngestionQueue().status()
    heartbeat = status_data["heartbeat"]
    last_heartbeat_at: datetime | None = None
    detail: str | None = None
    if isinstance(heartbeat, dict):
        raw_timestamp = heartbeat.get("at_utc")
        if isinstance(raw_timestamp, str):
            try:
                last_heartbeat_at = datetime.fromisoformat(raw_timestamp)
            except ValueError:
                detail = "Heartbeat do worker contém timestamp inválido."
        event = heartbeat.get("event")
        if isinstance(event, str):
            detail = event
    return IngestionWorkerStatus(
        queue_available=status_data["queue_available"],
        queued_jobs=status_data["queued_jobs"],
        last_heartbeat_at_utc=last_heartbeat_at,
        last_heartbeat_detail=detail,
    )

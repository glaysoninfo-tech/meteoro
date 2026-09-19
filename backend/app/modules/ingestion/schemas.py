from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class IngestionRunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ingestion_run_id: str
    organization_id: str
    source_id: str
    status: str
    trigger_type: str
    started_at: datetime
    finished_at: datetime | None = None
    records_received: int = Field(ge=0)
    records_accepted: int = Field(ge=0)
    records_rejected: int = Field(ge=0)
    records_deduplicated: int = Field(ge=0)
    error_summary: str | None = None
    run_metadata_json: str | None = None


class IngestionJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    job_id: str
    organization_id: str
    source_id: str
    trigger_type: str
    status: str
    run_metadata_json: str | None
    requested_by: str | None
    ingestion_run_id: str | None
    attempts: int
    error_summary: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class IngestionWorkerStatus(BaseModel):
    queue_available: bool
    queued_jobs: int | None
    last_heartbeat_at_utc: datetime | None
    last_heartbeat_detail: str | None


class ReprocessRequest(BaseModel):
    source_id: str = Field(min_length=1)
    period_start_utc: datetime
    period_end_utc: datetime


class CollectSourceRequest(BaseModel):
    source_id: str = Field(min_length=1)


class IngestionBatchResult(BaseModel):
    organization_id: str | None = None
    source_id: str
    source_name: str
    status: str
    run_id: str | None = None
    detail: str | None = None


class IngestionBatchSummary(BaseModel):
    total_sources: int
    collected_successfully: int
    failed: int
    results: list[IngestionBatchResult]


class ConnectorHealth(BaseModel):
    source_id: str
    source_name: str
    access_method: str
    status: str
    state: str
    expected_frequency_minutes: int
    delay_minutes: int | None
    last_collection_at: datetime | None
    last_success_at: datetime | None
    last_error: str | None


class ObservationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    observation_id: str
    source_id: str
    station_id: str | None = None
    sensor_id: str | None = None
    ingestion_run_id: str
    raw_asset_id: str
    observed_at_utc: datetime
    variable_code: str
    value_original: float
    unit_original: str
    value_canonical: float
    unit_canonical: str
    quality_status: str
    quality_score: int
    quality_flag_code: str | None = None
    quality_description: str | None = None
    location_code: str | None = None
    created_at: datetime


class SchedulerTickSummary(BaseModel):
    tick_started_at_utc: datetime
    tick_finished_at_utc: datetime
    total_sources: int
    collected_successfully: int
    failed: int


class IngestionSchedulerStatus(BaseModel):
    enabled: bool
    running: bool
    poll_interval_seconds: int
    in_progress: bool
    last_started_at_utc: datetime | None = None
    last_finished_at_utc: datetime | None = None
    last_error: str | None = None
    last_tick: SchedulerTickSummary | None = None

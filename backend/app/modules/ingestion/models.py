from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class IngestionRunModel(Base):
    __tablename__ = "ingestion_runs"

    ingestion_run_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.organization_id"), nullable=False
    )
    source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sources.source_id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    records_received: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_accepted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_rejected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_deduplicated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    run_metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class RawAssetModel(Base):
    __tablename__ = "raw_assets"

    raw_asset_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.organization_id"), nullable=False
    )
    source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sources.source_id"), nullable=False
    )
    ingestion_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ingestion_runs.ingestion_run_id"), nullable=False
    )
    object_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    parser_status: Mapped[str] = mapped_column(String(20), nullable=False, default="stored")
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class IngestionJobModel(Base):
    __tablename__ = "ingestion_jobs"

    job_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.organization_id"), nullable=False
    )
    source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sources.source_id"), nullable=False
    )
    trigger_type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    run_metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_by: Mapped[str | None] = mapped_column(String(160), nullable=True)
    ingestion_run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("ingestion_runs.ingestion_run_id"), nullable=True
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ObservationModel(Base):
    __tablename__ = "observations"
    __table_args__ = (
        UniqueConstraint("source_id", "record_fingerprint", name="uq_observations_source_fingerprint"),
    )

    observation_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.organization_id"), nullable=False
    )
    station_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("stations.station_id"), nullable=True
    )
    sensor_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("sensors.sensor_id"), nullable=True
    )
    source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sources.source_id"), nullable=False
    )
    ingestion_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ingestion_runs.ingestion_run_id"), nullable=False
    )
    raw_asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("raw_assets.raw_asset_id"), nullable=False
    )
    observed_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    variable_code: Mapped[str] = mapped_column(String(40), nullable=False)
    value_original: Mapped[float] = mapped_column(Float, nullable=False)
    unit_original: Mapped[str] = mapped_column(String(30), nullable=False)
    value_canonical: Mapped[float] = mapped_column(Float, nullable=False)
    unit_canonical: Mapped[str] = mapped_column(String(30), nullable=False)
    quality_status: Mapped[str] = mapped_column(String(20), nullable=False)
    quality_score: Mapped[int] = mapped_column(Integer, nullable=False)
    quality_flag_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    quality_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    record_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class IncidentReportModel(Base):
    __tablename__ = "incident_reports"
    __table_args__ = (
        UniqueConstraint("source_id", "record_fingerprint", name="uq_incident_reports_source_fingerprint"),
    )

    report_id: Mapped[str] = mapped_column(
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
    raw_asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("raw_assets.raw_asset_id"), nullable=False
    )
    reported_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    report_origin: Mapped[str] = mapped_column(String(20), nullable=False)
    category_code: Mapped[str] = mapped_column(String(60), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    location_geojson: Mapped[str | None] = mapped_column(Text, nullable=True)
    address_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    reporter_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reporter_contact: Mapped[str | None] = mapped_column(String(120), nullable=True)
    external_protocol: Mapped[str | None] = mapped_column(String(120), nullable=True)
    triage_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    triaged_by: Mapped[str | None] = mapped_column(String(160), nullable=True)
    triage_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    record_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

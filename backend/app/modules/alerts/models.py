from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OfficialAlertModel(Base):
    __tablename__ = "official_alerts"
    __table_args__ = (
        UniqueConstraint("source_id", "record_fingerprint", name="uq_official_alerts_source_fingerprint"),
    )

    official_alert_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.organization_id"), nullable=False
    )
    source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sources.source_id"), nullable=False
    )
    ingestion_run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("ingestion_runs.ingestion_run_id"), nullable=True
    )
    raw_asset_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("raw_assets.raw_asset_id"), nullable=True
    )
    external_alert_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    issuer: Mapped[str] = mapped_column(String(120), nullable=False)
    alert_code: Mapped[str] = mapped_column(String(60), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    issued_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_from_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    territory_codes_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    geometry_geojson: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    record_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class ProtocolTemplateModel(Base):
    __tablename__ = "protocol_templates"
    __table_args__ = (
        UniqueConstraint("protocol_family_id", "revision_number", name="uq_protocol_family_revision"),
    )

    protocol_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.organization_id"), nullable=False
    )
    protocol_family_id: Mapped[str] = mapped_column(String(36), nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    supersedes_protocol_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("protocol_templates.protocol_id"), nullable=True
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
    change_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    protocol_name: Mapped[str] = mapped_column(String(160), nullable=False)
    version: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(30), nullable=False)
    trigger_config_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_steps_json: Mapped[str] = mapped_column(Text, nullable=False)
    requires_authority_approval: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ProtocolActivationModel(Base):
    __tablename__ = "protocol_activations"

    activation_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.organization_id"), nullable=False
    )
    protocol_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("protocol_templates.protocol_id"), nullable=False
    )
    official_alert_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("official_alerts.official_alert_id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    trigger_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    initiated_by: Mapped[str] = mapped_column(String(160), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(160), nullable=True)
    closed_by: Mapped[str | None] = mapped_column(String(160), nullable=True)
    started_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    approved_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closure_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_log_json: Mapped[str | None] = mapped_column(Text, nullable=True)

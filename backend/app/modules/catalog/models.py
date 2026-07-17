from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SourceModel(Base):
    __tablename__ = "sources"

    source_id: Mapped[str] = mapped_column(
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
    institution_name: Mapped[str] = mapped_column(String(120), nullable=False)
    source_name: Mapped[str] = mapped_column(String(120), nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    access_method: Mapped[str] = mapped_column(String(30), nullable=False, default="http")
    authentication_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="none"
    )
    endpoint_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    connector_config_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    expected_frequency_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    criticality: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    last_collection_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

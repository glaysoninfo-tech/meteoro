from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TerritoryModel(Base):
    __tablename__ = "territories"
    __table_args__ = (
        UniqueConstraint("organization_id", "territory_code", name="uq_territory_org_code"),
    )

    territory_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.organization_id"), nullable=False
    )
    territory_code: Mapped[str] = mapped_column(String(80), nullable=False)
    territory_name: Mapped[str] = mapped_column(String(160), nullable=False)
    territory_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    geometry_geojson: Mapped[str] = mapped_column(Text, nullable=False)
    # PostgreSQL/PostGIS armazena geometry(GEOMETRY, 4326); SQLite de teste usa TEXT.
    geometry: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class StationModel(Base):
    __tablename__ = "stations"
    __table_args__ = (
        UniqueConstraint("organization_id", "station_code", name="uq_station_org_code"),
    )

    station_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.organization_id"), nullable=False
    )
    territory_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("territories.territory_id"), nullable=True
    )
    station_code: Mapped[str] = mapped_column(String(80), nullable=False)
    station_name: Mapped[str] = mapped_column(String(160), nullable=False)
    station_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    location_geojson: Mapped[str] = mapped_column(Text, nullable=False)
    # PostgreSQL/PostGIS armazena geometry(POINT, 4326); SQLite de teste usa TEXT.
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    elevation_meters: Mapped[float | None] = mapped_column(nullable=True)
    installed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    decommissioned_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SensorModel(Base):
    __tablename__ = "sensors"
    __table_args__ = (
        UniqueConstraint("station_id", "sensor_code", name="uq_sensor_station_code"),
    )

    sensor_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.organization_id"), nullable=False
    )
    station_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("stations.station_id"), nullable=False
    )
    sensor_code: Mapped[str] = mapped_column(String(80), nullable=False)
    sensor_name: Mapped[str] = mapped_column(String(160), nullable=False)
    variable_code: Mapped[str] = mapped_column(String(60), nullable=False)
    unit_canonical: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    manufacturer: Mapped[str | None] = mapped_column(String(120), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    calibration_due_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

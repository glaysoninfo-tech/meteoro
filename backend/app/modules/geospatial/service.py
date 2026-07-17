from __future__ import annotations

from datetime import datetime, timezone
import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.geospatial.models import SensorModel, StationModel, TerritoryModel
from app.modules.geospatial.schemas import (
    SensorCreate,
    SensorUpdate,
    StationCreate,
    StationUpdate,
    TerritoryCreate,
    TerritoryUpdate,
)


class GeospatialService:
    def list_territories(self, db: Session, organization_id: str) -> list[TerritoryModel]:
        stmt = (
            select(TerritoryModel)
            .where(TerritoryModel.organization_id == organization_id)
            .order_by(TerritoryModel.territory_name.asc())
        )
        return list(db.scalars(stmt).all())

    def create_territory(
        self, db: Session, organization_id: str, payload: TerritoryCreate
    ) -> TerritoryModel:
        now = datetime.now(tz=timezone.utc)
        geometry_json = self._geometry_json(payload.geometry_geojson)
        territory = TerritoryModel(
            organization_id=organization_id,
            territory_code=payload.territory_code.strip(),
            territory_name=payload.territory_name.strip(),
            territory_type=payload.territory_type.strip().lower(),
            status=payload.status.strip().lower(),
            geometry_geojson=geometry_json,
            geometry=self._geometry_value(db=db, geometry_json=geometry_json),
            created_at=now,
            updated_at=now,
        )
        db.add(territory)
        db.commit()
        db.refresh(territory)
        return territory

    def update_territory(
        self,
        db: Session,
        organization_id: str,
        territory_id: str,
        payload: TerritoryUpdate,
    ) -> TerritoryModel:
        territory = self._get_territory(db=db, organization_id=organization_id, territory_id=territory_id)
        if territory is None:
            raise LookupError(f"territory_id '{territory_id}' não encontrado.")
        values = payload.model_dump(exclude_unset=True)
        if "geometry_geojson" in values and values["geometry_geojson"] is not None:
            geometry_json = self._geometry_json(values.pop("geometry_geojson"))
            territory.geometry_geojson = geometry_json
            territory.geometry = self._geometry_value(db=db, geometry_json=geometry_json)
        for field_name, value in values.items():
            if isinstance(value, str):
                value = value.strip().lower() if field_name in {"territory_type", "status"} else value.strip()
            setattr(territory, field_name, value)
        territory.updated_at = datetime.now(tz=timezone.utc)
        db.commit()
        db.refresh(territory)
        return territory

    def list_stations(
        self, db: Session, organization_id: str, territory_id: str | None
    ) -> list[StationModel]:
        stmt = select(StationModel).where(StationModel.organization_id == organization_id)
        if territory_id is not None:
            stmt = stmt.where(StationModel.territory_id == territory_id)
        stmt = stmt.order_by(StationModel.station_name.asc())
        return list(db.scalars(stmt).all())

    def create_station(
        self, db: Session, organization_id: str, payload: StationCreate
    ) -> StationModel:
        self._assert_territory_ownership(db=db, organization_id=organization_id, territory_id=payload.territory_id)
        now = datetime.now(tz=timezone.utc)
        location_json = self._geometry_json(payload.location_geojson)
        station = StationModel(
            organization_id=organization_id,
            territory_id=payload.territory_id,
            station_code=payload.station_code.strip(),
            station_name=payload.station_name.strip(),
            station_type=payload.station_type.strip().lower(),
            status=payload.status.strip().lower(),
            location_geojson=location_json,
            location=self._point_value(db=db, geometry_json=location_json),
            elevation_meters=payload.elevation_meters,
            installed_on=payload.installed_on,
            decommissioned_on=None,
            created_at=now,
            updated_at=now,
        )
        db.add(station)
        db.commit()
        db.refresh(station)
        return station

    def update_station(
        self,
        db: Session,
        organization_id: str,
        station_id: str,
        payload: StationUpdate,
    ) -> StationModel:
        station = self._get_station(db=db, organization_id=organization_id, station_id=station_id)
        if station is None:
            raise LookupError(f"station_id '{station_id}' não encontrada.")
        values = payload.model_dump(exclude_unset=True)
        if "territory_id" in values:
            self._assert_territory_ownership(
                db=db,
                organization_id=organization_id,
                territory_id=values["territory_id"],
            )
        if "location_geojson" in values and values["location_geojson"] is not None:
            location_json = self._geometry_json(values.pop("location_geojson"))
            station.location_geojson = location_json
            station.location = self._point_value(db=db, geometry_json=location_json)
        for field_name, value in values.items():
            if isinstance(value, str):
                value = value.strip().lower() if field_name in {"station_type", "status"} else value.strip()
            setattr(station, field_name, value)
        station.updated_at = datetime.now(tz=timezone.utc)
        db.commit()
        db.refresh(station)
        return station

    def list_sensors(
        self, db: Session, organization_id: str, station_id: str | None
    ) -> list[SensorModel]:
        stmt = select(SensorModel).where(SensorModel.organization_id == organization_id)
        if station_id is not None:
            stmt = stmt.where(SensorModel.station_id == station_id)
        stmt = stmt.order_by(SensorModel.sensor_name.asc())
        return list(db.scalars(stmt).all())

    def create_sensor(self, db: Session, organization_id: str, payload: SensorCreate) -> SensorModel:
        station = self._get_station(db=db, organization_id=organization_id, station_id=payload.station_id)
        if station is None:
            raise LookupError(f"station_id '{payload.station_id}' não encontrada.")
        now = datetime.now(tz=timezone.utc)
        sensor = SensorModel(
            organization_id=organization_id,
            station_id=station.station_id,
            sensor_code=payload.sensor_code.strip(),
            sensor_name=payload.sensor_name.strip(),
            variable_code=payload.variable_code.strip().lower(),
            unit_canonical=payload.unit_canonical.strip(),
            status=payload.status.strip().lower(),
            manufacturer=self._clean_optional(payload.manufacturer),
            model=self._clean_optional(payload.model),
            serial_number=self._clean_optional(payload.serial_number),
            calibration_due_on=payload.calibration_due_on,
            created_at=now,
            updated_at=now,
        )
        db.add(sensor)
        db.commit()
        db.refresh(sensor)
        return sensor

    def update_sensor(
        self,
        db: Session,
        organization_id: str,
        sensor_id: str,
        payload: SensorUpdate,
    ) -> SensorModel:
        sensor = db.get(SensorModel, sensor_id)
        if sensor is None:
            raise LookupError(f"sensor_id '{sensor_id}' não encontrado.")
        if sensor.organization_id != organization_id:
            raise PermissionError("Acesso negado para este sensor.")
        for field_name, value in payload.model_dump(exclude_unset=True).items():
            if isinstance(value, str):
                if field_name in {"variable_code", "status"}:
                    value = value.strip().lower()
                else:
                    value = value.strip()
            setattr(sensor, field_name, value)
        sensor.updated_at = datetime.now(tz=timezone.utc)
        db.commit()
        db.refresh(sensor)
        return sensor

    def _get_territory(
        self, db: Session, organization_id: str, territory_id: str
    ) -> TerritoryModel | None:
        return db.scalar(
            select(TerritoryModel).where(
                TerritoryModel.territory_id == territory_id,
                TerritoryModel.organization_id == organization_id,
            )
        )

    def _get_station(self, db: Session, organization_id: str, station_id: str) -> StationModel | None:
        return db.scalar(
            select(StationModel).where(
                StationModel.station_id == station_id,
                StationModel.organization_id == organization_id,
            )
        )

    def _assert_territory_ownership(
        self, db: Session, organization_id: str, territory_id: str | None
    ) -> None:
        if territory_id is not None and self._get_territory(db, organization_id, territory_id) is None:
            raise ValueError(f"territory_id '{territory_id}' não pertence à organização.")

    def _geometry_json(self, value: dict[str, object]) -> str:
        return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))

    def _geometry_value(self, db: Session, geometry_json: str):
        if db.bind is not None and db.bind.dialect.name == "postgresql":
            return func.ST_SetSRID(func.ST_GeomFromGeoJSON(geometry_json), 4326)
        return geometry_json

    def _point_value(self, db: Session, geometry_json: str):
        return self._geometry_value(db=db, geometry_json=geometry_json)

    def _clean_optional(self, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


geospatial_service = GeospatialService()

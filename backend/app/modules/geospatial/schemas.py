from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TerritoryCreate(BaseModel):
    territory_code: str = Field(min_length=1, max_length=80)
    territory_name: str = Field(min_length=2, max_length=160)
    territory_type: str = Field(min_length=2, max_length=40)
    status: str = Field(default="active", min_length=3, max_length=20)
    geometry_geojson: dict[str, Any]

    @field_validator("geometry_geojson")
    @classmethod
    def validate_geometry(cls, value: dict[str, Any]) -> dict[str, Any]:
        _validate_geojson_geometry(value=value, expected_types={"Polygon", "MultiPolygon"})
        return value


class TerritoryUpdate(BaseModel):
    territory_name: str | None = Field(default=None, min_length=2, max_length=160)
    territory_type: str | None = Field(default=None, min_length=2, max_length=40)
    status: str | None = Field(default=None, min_length=3, max_length=20)
    geometry_geojson: dict[str, Any] | None = None

    @field_validator("geometry_geojson")
    @classmethod
    def validate_geometry(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is not None:
            _validate_geojson_geometry(value=value, expected_types={"Polygon", "MultiPolygon"})
        return value


class TerritoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    territory_id: str
    organization_id: str
    territory_code: str
    territory_name: str
    territory_type: str
    status: str
    geometry_geojson: str
    created_at: datetime
    updated_at: datetime


class StationCreate(BaseModel):
    territory_id: str | None = None
    station_code: str = Field(min_length=1, max_length=80)
    station_name: str = Field(min_length=2, max_length=160)
    station_type: str = Field(min_length=2, max_length=40)
    status: str = Field(default="active", min_length=3, max_length=20)
    location_geojson: dict[str, Any]
    elevation_meters: float | None = None
    installed_on: date | None = None

    @field_validator("location_geojson")
    @classmethod
    def validate_location(cls, value: dict[str, Any]) -> dict[str, Any]:
        _validate_geojson_geometry(value=value, expected_types={"Point"})
        return value


class StationUpdate(BaseModel):
    territory_id: str | None = None
    station_name: str | None = Field(default=None, min_length=2, max_length=160)
    station_type: str | None = Field(default=None, min_length=2, max_length=40)
    status: str | None = Field(default=None, min_length=3, max_length=20)
    location_geojson: dict[str, Any] | None = None
    elevation_meters: float | None = None
    installed_on: date | None = None
    decommissioned_on: date | None = None

    @field_validator("location_geojson")
    @classmethod
    def validate_location(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is not None:
            _validate_geojson_geometry(value=value, expected_types={"Point"})
        return value


class StationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    station_id: str
    organization_id: str
    territory_id: str | None
    station_code: str
    station_name: str
    station_type: str
    status: str
    location_geojson: str
    elevation_meters: float | None
    installed_on: date | None
    decommissioned_on: date | None
    created_at: datetime
    updated_at: datetime


class SensorCreate(BaseModel):
    station_id: str
    sensor_code: str = Field(min_length=1, max_length=80)
    sensor_name: str = Field(min_length=2, max_length=160)
    variable_code: str = Field(min_length=1, max_length=60)
    unit_canonical: str = Field(min_length=1, max_length=30)
    status: str = Field(default="active", min_length=3, max_length=20)
    manufacturer: str | None = Field(default=None, max_length=120)
    model: str | None = Field(default=None, max_length=120)
    serial_number: str | None = Field(default=None, max_length=120)
    calibration_due_on: date | None = None


class SensorUpdate(BaseModel):
    sensor_name: str | None = Field(default=None, min_length=2, max_length=160)
    variable_code: str | None = Field(default=None, min_length=1, max_length=60)
    unit_canonical: str | None = Field(default=None, min_length=1, max_length=30)
    status: str | None = Field(default=None, min_length=3, max_length=20)
    manufacturer: str | None = Field(default=None, max_length=120)
    model: str | None = Field(default=None, max_length=120)
    serial_number: str | None = Field(default=None, max_length=120)
    calibration_due_on: date | None = None


class SensorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sensor_id: str
    organization_id: str
    station_id: str
    sensor_code: str
    sensor_name: str
    variable_code: str
    unit_canonical: str
    status: str
    manufacturer: str | None
    model: str | None
    serial_number: str | None
    calibration_due_on: date | None
    created_at: datetime
    updated_at: datetime


def _validate_geojson_geometry(value: dict[str, Any], expected_types: set[str]) -> None:
    geometry_type = value.get("type")
    coordinates = value.get("coordinates")
    if geometry_type not in expected_types or coordinates is None:
        expected = ", ".join(sorted(expected_types))
        raise ValueError(f"GeoJSON deve ter type {expected} e coordinates.")
    if geometry_type == "Point":
        if not _is_position(coordinates):
            raise ValueError("GeoJSON Point deve conter posição [longitude, latitude].")
        _validate_position(coordinates)
        return

    positions = list(_iter_positions(coordinates))
    if not positions:
        raise ValueError("GeoJSON territorial deve conter ao menos uma posição.")
    for position in positions:
        _validate_position(position)


def _iter_positions(value: Any):
    if _is_position(value):
        yield value
        return
    if not isinstance(value, list):
        return
    for item in value:
        yield from _iter_positions(item)


def _is_position(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) >= 2
        and isinstance(value[0], (int, float))
        and not isinstance(value[0], bool)
        and isinstance(value[1], (int, float))
        and not isinstance(value[1], bool)
    )


def _validate_position(position: list[Any]) -> None:
    longitude, latitude = position[0], position[1]
    if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
        raise ValueError("Coordenadas GeoJSON devem estar em WGS84 (longitude/latitude).")

from datetime import datetime

from pydantic import BaseModel, Field


class ForecastPoint(BaseModel):
    valid_at_utc: datetime
    predicted_value: float
    risk_level: str
    confidence_score: int = Field(ge=0, le=100)


class ForecastSeries(BaseModel):
    variable_code: str
    unit: str
    sample_count: int = Field(ge=0)
    base_value: float
    trend_per_hour: float
    points: list[ForecastPoint]


class RequestedForecastResponse(BaseModel):
    generated_at_utc: datetime
    organization_id: str
    issued_at_utc: datetime
    horizon_hours: int = Field(ge=1)
    step_hours: int = Field(ge=1)
    source_scope: list[str]
    model_name: str
    model_version: str
    series: list[ForecastSeries]
    summary: str


class AviationCondition(BaseModel):
    icao: str
    airport_name: str
    latitude: float
    longitude: float
    flight_category: str | None = None
    status_collected_at_utc: datetime | None = None
    metar: str | None = None
    metar_valid_at_utc: datetime | None = None
    source_state: str
    source_note: str


class AviationConditionsResponse(BaseModel):
    generated_at_utc: datetime
    conditions: list[AviationCondition]
    disclaimer: str


class MapImageLayer(BaseModel):
    kind: str
    product: str
    image_url: str | None = None
    captured_at_utc: datetime | None = None
    bounds: list[list[float]] | None = None
    source_state: str
    source_note: str


class LightningEvent(BaseModel):
    latitude: float
    longitude: float
    occurred_at_utc: datetime | None = None
    intensity: float = 1.0


class OperationalMapResponse(BaseModel):
    generated_at_utc: datetime
    satellite: MapImageLayer | None = None
    radar: MapImageLayer | None = None
    lightning_available: bool
    lightning_count_last_60m: int | None = None
    lightning_events: list[LightningEvent] = []
    disclaimer: str

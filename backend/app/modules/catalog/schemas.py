from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SourceCreate(BaseModel):
    institution_name: str = Field(min_length=2, max_length=120)
    source_name: str = Field(min_length=2, max_length=120)
    source_type: str = Field(min_length=2, max_length=40)
    station_id: str | None = None
    sensor_id: str | None = None
    access_method: str = Field(default="http", min_length=2, max_length=30)
    authentication_type: str = Field(default="none", min_length=2, max_length=30)
    endpoint_reference: str = Field(min_length=3, max_length=500)
    connector_config_json: str | None = Field(default=None, max_length=10000)
    status: str = Field(default="active", min_length=3, max_length=20)
    expected_frequency_minutes: int = Field(ge=1, le=10080)
    criticality: str = Field(default="medium", min_length=3, max_length=20)


class AnaHidrowebInstallRequest(BaseModel):
    """Códigos ANA das estações fluviométricas a monitorar (popup da camada de réguas)."""

    station_codes: list[str] = Field(min_length=1, max_length=20)


class SourceUpdate(BaseModel):
    source_name: str | None = Field(default=None, min_length=2, max_length=120)
    source_type: str | None = Field(default=None, min_length=2, max_length=40)
    station_id: str | None = None
    sensor_id: str | None = None
    access_method: str | None = Field(default=None, min_length=2, max_length=30)
    authentication_type: str | None = Field(default=None, min_length=2, max_length=30)
    endpoint_reference: str | None = Field(default=None, min_length=3, max_length=500)
    connector_config_json: str | None = Field(default=None, max_length=10000)
    status: str | None = Field(default=None, min_length=3, max_length=20)
    expected_frequency_minutes: int | None = Field(default=None, ge=1, le=10080)
    criticality: str | None = Field(default=None, min_length=3, max_length=20)


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source_id: str
    organization_id: str
    institution_name: str
    source_name: str
    source_type: str
    station_id: str | None
    sensor_id: str | None
    access_method: str
    authentication_type: str
    endpoint_reference: str
    connector_config_json: str | None
    status: str
    expected_frequency_minutes: int
    criticality: str
    last_collection_at: datetime | None
    last_success_at: datetime | None
    last_error: str | None
    created_at: datetime

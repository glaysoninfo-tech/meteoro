from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class IncidentReport(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    report_id: str
    organization_id: str
    source_id: str
    ingestion_run_id: str
    raw_asset_id: str
    reported_at_utc: datetime
    report_origin: str
    category_code: str
    severity: str
    description: str | None = None
    location_code: str | None = None
    location_geojson: str | None = None
    address_text: str | None = None
    reporter_name: str | None = None
    reporter_contact: str | None = None
    external_protocol: str | None = None
    triage_status: str
    triaged_by: str | None = None
    triage_notes: str | None = None
    created_at: datetime


class IncidentTriageRequest(BaseModel):
    triage_status: str = Field(min_length=3, max_length=20)
    triage_notes: str | None = Field(default=None, max_length=2000)

    @field_validator("triage_status")
    @classmethod
    def validate_triage_status(cls, value: str) -> str:
        normalized = value.strip().lower()
        allowed = {"pending", "in_progress", "resolved", "invalid", "forwarded"}
        if normalized not in allowed:
            allowed_values = ", ".join(sorted(allowed))
            raise ValueError(f"triage_status inválido '{value}'. Permitidos: {allowed_values}.")
        return normalized

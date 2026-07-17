from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class OfficialAlertCreateRequest(BaseModel):
    source_id: str = Field(min_length=1)
    external_alert_id: str | None = Field(default=None, max_length=120)
    issuer: str = Field(min_length=2, max_length=120)
    alert_code: str = Field(min_length=2, max_length=60)
    severity: str = Field(min_length=3, max_length=20)
    issued_at_utc: datetime
    valid_from_utc: datetime
    valid_to_utc: datetime
    title: str = Field(min_length=2, max_length=200)
    message: str = Field(min_length=2, max_length=20000)
    territory_codes: list[str] | None = None
    geometry_geojson: str | None = Field(default=None, max_length=20000)
    original_payload_json: str | None = Field(default=None, max_length=50000)

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, value: str) -> str:
        normalized = value.strip().lower()
        allowed = {"low", "medium", "high", "critical"}
        aliases = {"baixa": "low", "media": "medium", "média": "medium", "alta": "high"}
        normalized = aliases.get(normalized, normalized)
        if normalized not in allowed:
            allowed_values = ", ".join(sorted(allowed))
            raise ValueError(f"severity inválida '{value}'. Permitidas: {allowed_values}.")
        return normalized


class OfficialAlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    official_alert_id: str
    organization_id: str
    source_id: str
    ingestion_run_id: str | None
    raw_asset_id: str | None
    external_alert_id: str | None
    issuer: str
    alert_code: str
    severity: str
    status: str
    issued_at_utc: datetime
    valid_from_utc: datetime
    valid_to_utc: datetime
    title: str
    message: str
    territory_codes_json: str | None
    geometry_geojson: str | None
    original_payload_json: str | None
    created_at: datetime
    closed_at_utc: datetime | None
    closed_reason: str | None


class CoverageSummaryItem(BaseModel):
    territory_code: str
    active_alerts: int = Field(ge=0)
    highest_severity: str
    latest_valid_to_utc: datetime | None = None


class OfficialAlertCloseRequest(BaseModel):
    closure_reason: str = Field(min_length=2, max_length=2000)


class ProtocolTemplateCreateRequest(BaseModel):
    protocol_name: str = Field(min_length=3, max_length=160)
    version: str = Field(default="1.0", min_length=1, max_length=30)
    status: str = Field(default="active", min_length=3, max_length=20)
    trigger_type: str = Field(default="official_alert", min_length=3, max_length=30)
    trigger_config_json: str | None = Field(default=None, max_length=20000)
    action_steps_json: str = Field(min_length=2, max_length=50000)
    requires_authority_approval: bool = True
    change_reason: str | None = Field(default=None, max_length=1000)


class ProtocolTemplateUpdateRequest(BaseModel):
    protocol_name: str | None = Field(default=None, min_length=3, max_length=160)
    version: str | None = Field(default=None, min_length=1, max_length=30)
    status: str | None = Field(default=None, min_length=3, max_length=20)
    trigger_type: str | None = Field(default=None, min_length=3, max_length=30)
    trigger_config_json: str | None = Field(default=None, max_length=20000)
    action_steps_json: str | None = Field(default=None, min_length=2, max_length=50000)
    requires_authority_approval: bool | None = None
    change_reason: str = Field(min_length=3, max_length=1000)


class ProtocolTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    protocol_id: str
    organization_id: str
    protocol_family_id: str
    revision_number: int
    supersedes_protocol_id: str | None
    content_hash: str
    created_by: str
    change_reason: str | None
    protocol_name: str
    version: str
    status: str
    trigger_type: str
    trigger_config_json: str | None
    action_steps_json: str
    requires_authority_approval: bool
    created_at: datetime
    updated_at: datetime


class ProtocolActivateRequest(BaseModel):
    official_alert_id: str | None = None
    severity: str = Field(default="medium", min_length=3, max_length=20)
    trigger_reason: str | None = Field(default=None, max_length=2000)
    action_log_json: str | None = Field(default=None, max_length=20000)

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, value: str) -> str:
        normalized = value.strip().lower()
        allowed = {"low", "medium", "high", "critical"}
        if normalized not in allowed:
            allowed_values = ", ".join(sorted(allowed))
            raise ValueError(f"severity inválida '{value}'. Permitidas: {allowed_values}.")
        return normalized


class ProtocolApprovalRequest(BaseModel):
    action_log_json: str | None = Field(default=None, max_length=20000)


class ProtocolCloseRequest(BaseModel):
    closure_notes: str = Field(min_length=2, max_length=4000)
    action_log_json: str | None = Field(default=None, max_length=20000)


class ProtocolActivationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    activation_id: str
    organization_id: str
    protocol_id: str
    official_alert_id: str | None
    status: str
    severity: str
    trigger_reason: str | None
    initiated_by: str
    approved_by: str | None
    closed_by: str | None
    started_at_utc: datetime
    approved_at_utc: datetime | None
    closed_at_utc: datetime | None
    closure_notes: str | None
    action_log_json: str | None

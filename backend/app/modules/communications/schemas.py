from datetime import datetime
import json

from pydantic import BaseModel, ConfigDict, Field, field_validator

ALLOWED_CHANNEL_TYPES = {"email", "sms", "whatsapp", "webhook"}
ALLOWED_CONSENT_STATUS = {"opt_in", "opt_out", "pending"}
ALLOWED_DISPATCH_STATUS = {"draft", "sent", "partial", "cancelled"}


class CommunicationRecipientCreateRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=160)
    channel_type: str = Field(min_length=3, max_length=20)
    destination: str = Field(min_length=3, max_length=300)
    consent_status: str = Field(default="pending", min_length=6, max_length=20)
    consent_reason: str | None = Field(default=None, max_length=2000)
    tags_json: str | None = Field(default=None, max_length=20000)

    @field_validator("channel_type")
    @classmethod
    def validate_channel_type(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in ALLOWED_CHANNEL_TYPES:
            allowed_values = ", ".join(sorted(ALLOWED_CHANNEL_TYPES))
            raise ValueError(f"channel_type inválido '{value}'. Permitidos: {allowed_values}.")
        return normalized

    @field_validator("consent_status")
    @classmethod
    def validate_consent_status(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in ALLOWED_CONSENT_STATUS:
            allowed_values = ", ".join(sorted(ALLOWED_CONSENT_STATUS))
            raise ValueError(f"consent_status inválido '{value}'. Permitidos: {allowed_values}.")
        return normalized

    @field_validator("tags_json")
    @classmethod
    def validate_tags_json(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = json.loads(value)
        if not isinstance(parsed, list):
            raise ValueError("tags_json deve conter lista JSON.")
        return value


class CommunicationRecipientConsentUpdateRequest(BaseModel):
    consent_status: str = Field(min_length=6, max_length=20)
    consent_reason: str | None = Field(default=None, max_length=2000)

    @field_validator("consent_status")
    @classmethod
    def validate_consent_status(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in ALLOWED_CONSENT_STATUS:
            allowed_values = ", ".join(sorted(ALLOWED_CONSENT_STATUS))
            raise ValueError(f"consent_status inválido '{value}'. Permitidos: {allowed_values}.")
        return normalized


class CommunicationRecipientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    recipient_id: str
    organization_id: str
    full_name: str
    channel_type: str
    destination: str
    consent_status: str
    consent_reason: str | None
    consent_updated_at: datetime | None
    is_active: bool
    tags_json: str | None
    created_at: datetime
    updated_at: datetime


class BulletinDispatchCreateRequest(BaseModel):
    bulletin_type: str = Field(default="manual", min_length=3, max_length=40)
    title: str = Field(min_length=3, max_length=200)
    content_text: str = Field(min_length=3, max_length=20000)
    channel_scope: list[str] | None = None
    send_immediately: bool = False

    @field_validator("bulletin_type")
    @classmethod
    def validate_bulletin_type(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("channel_scope")
    @classmethod
    def validate_channel_scope(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        normalized: list[str] = []
        for raw_value in values:
            channel = raw_value.strip().lower()
            if channel not in ALLOWED_CHANNEL_TYPES:
                allowed_values = ", ".join(sorted(ALLOWED_CHANNEL_TYPES))
                raise ValueError(f"channel_scope contém '{raw_value}'. Permitidos: {allowed_values}.")
            if channel not in normalized:
                normalized.append(channel)
        return normalized


class DailyBulletinGenerateRequest(BaseModel):
    period_hours: int = Field(default=24, ge=1, le=168)
    max_alerts: int = Field(default=20, ge=1, le=200)
    channel_scope: list[str] | None = None
    send_immediately: bool = True
    title: str | None = Field(default=None, min_length=3, max_length=200)

    @field_validator("channel_scope")
    @classmethod
    def validate_channel_scope(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        normalized: list[str] = []
        for raw_value in values:
            channel = raw_value.strip().lower()
            if channel not in ALLOWED_CHANNEL_TYPES:
                allowed_values = ", ".join(sorted(ALLOWED_CHANNEL_TYPES))
                raise ValueError(f"channel_scope contém '{raw_value}'. Permitidos: {allowed_values}.")
            if channel not in normalized:
                normalized.append(channel)
        return normalized


class BulletinDispatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    dispatch_id: str
    organization_id: str
    bulletin_type: str
    status: str
    title: str
    content_text: str
    requested_by: str
    channel_scope_json: str | None
    report_snapshot_json: str | None
    created_at: datetime
    sent_at_utc: datetime | None


class BulletinDeliveryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    delivery_id: str
    organization_id: str
    dispatch_id: str
    recipient_id: str
    channel_type: str
    destination: str
    delivery_status: str
    detail: str | None
    attempted_at_utc: datetime
    delivered_at_utc: datetime | None


class DispatchExecutionResult(BaseModel):
    dispatch: BulletinDispatchOut
    sent_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)


class DailyBulletinGenerationResult(DispatchExecutionResult):
    period_start_utc: datetime
    period_end_utc: datetime
    executive_summary: str
    active_official_alerts: int = Field(ge=0)

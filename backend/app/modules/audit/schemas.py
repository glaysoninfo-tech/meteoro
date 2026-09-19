from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: str
    organization_id: str
    module: str
    action: str
    actor: str
    occurred_at_utc: datetime
    resource_type: str
    resource_id: str
    before_state_json: str | None
    after_state_json: str | None
    reason: str | None

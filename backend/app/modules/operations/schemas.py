from datetime import datetime
from typing import Any

from pydantic import BaseModel


class OperationalMap(BaseModel):
    generated_at_utc: datetime
    territories: dict[str, Any]
    stations: dict[str, Any]
    alerts: dict[str, Any]
    incidents: dict[str, Any]
    notices: list[str]


class OperationalSituation(BaseModel):
    generated_at_utc: datetime
    platform_state: str
    active_alerts: int
    stations_total: int
    stations_degraded: int
    pending_quality_issues: int
    pending_incidents: int
    pending_protocol_approvals: int
    connectors_degraded: int
    connectors_stale: int
    notices: list[str]

from datetime import datetime

from pydantic import BaseModel, Field


class MitigationActionCreate(BaseModel):
    """Ação estruturante de mitigação/adaptação vinculada a um risco."""

    risk_theme: str = Field(
        pattern="^(calor|baixa_umidade|queimada|fumaca|cheia|deslizamento|qualidade_ar|outro)$"
    )
    territory: str = Field(min_length=2, max_length=160)
    title: str = Field(min_length=5, max_length=200)
    description: str = Field(min_length=5)
    responsible_role: str = Field(min_length=2, max_length=160)
    action_type: str = Field(
        default="mitigacao", pattern="^(mitigacao|adaptacao|preparacao|resposta|recuperacao)$"
    )
    priority: str = Field(default="media", pattern="^(baixa|media|alta|critica)$")
    deadline_utc: datetime | None = None
    estimated_cost_brl: float | None = Field(default=None, ge=0)
    indicator: str | None = Field(default=None, max_length=300)
    notes: str | None = None


class MitigationActionUpdate(BaseModel):
    status: str | None = Field(
        default=None, pattern="^(planejada|em_execucao|concluida|suspensa|cancelada)$"
    )
    progress_pct: int | None = Field(default=None, ge=0, le=100)
    deadline_utc: datetime | None = None
    estimated_cost_brl: float | None = Field(default=None, ge=0)
    indicator: str | None = Field(default=None, max_length=300)
    notes: str | None = None


class MitigationActionOut(BaseModel):
    action_id: str
    organization_id: str
    risk_theme: str
    territory: str
    title: str
    description: str
    responsible_role: str
    action_type: str
    priority: str
    status: str
    progress_pct: int
    deadline_utc: datetime | None
    estimated_cost_brl: float | None
    indicator: str | None
    notes: str | None
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime
    completed_at_utc: datetime | None

    model_config = {"from_attributes": True}


class CabinetDecisionCreate(BaseModel):
    risk_key: str = Field(min_length=3, max_length=240)
    territory: str = Field(min_length=2, max_length=160)
    decision: str = Field(min_length=5)
    responsible_action: str = Field(min_length=5, max_length=500)
    responsible_role: str = Field(min_length=2, max_length=160)
    deadline_utc: datetime | None = None
    status: str = Field(default="open", pattern="^(open|in_progress|completed|cancelled)$")
    notes: str | None = None


class CabinetDecisionUpdate(BaseModel):
    decision: str | None = Field(default=None, min_length=5)
    responsible_action: str | None = Field(default=None, min_length=5, max_length=500)
    responsible_role: str | None = Field(default=None, min_length=2, max_length=160)
    deadline_utc: datetime | None = None
    status: str | None = Field(default=None, pattern="^(open|in_progress|completed|cancelled)$")
    notes: str | None = None


class CabinetDecisionOut(BaseModel):
    decision_id: str
    organization_id: str
    risk_key: str
    territory: str
    decision: str
    responsible_action: str
    responsible_role: str
    deadline_utc: datetime | None
    status: str
    notes: str | None
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime
    completed_at_utc: datetime | None

    model_config = {"from_attributes": True}


class QualityDistribution(BaseModel):
    valid: int = Field(ge=0)
    suspect: int = Field(ge=0)
    rejected: int = Field(ge=0)


class SourceCoverageSummary(BaseModel):
    source_id: str
    sample_count: int = Field(ge=0)
    last_observed_at_utc: datetime | None = None


class VariableTrendSummary(BaseModel):
    variable_code: str
    unit: str
    sample_count: int = Field(ge=0)
    valid_sample_count: int = Field(ge=0)
    min_value: float | None = None
    max_value: float | None = None
    average_value: float | None = None
    first_value: float | None = None
    last_value: float | None = None
    trend_delta: float | None = None
    trend_direction: str


class ClimateAlert(BaseModel):
    alert_code: str
    severity: str
    variable_code: str
    source_id: str
    observed_at_utc: datetime
    location_code: str | None = None
    value: float
    unit: str
    threshold: float
    description: str


class CommitteeClimateReport(BaseModel):
    generated_at_utc: datetime
    organization_id: str
    period_start_utc: datetime
    period_end_utc: datetime
    source_scope: list[str]
    observations_considered: int = Field(ge=0)
    quality_distribution: QualityDistribution
    source_coverage: list[SourceCoverageSummary]
    trend_summaries: list[VariableTrendSummary]
    alerts: list[ClimateAlert]
    executive_summary: str


class StationAvailabilityItem(BaseModel):
    station_id: str
    station_code: str
    station_name: str
    station_type: str
    station_status: str
    sensor_count: int = Field(ge=0)
    observation_count: int = Field(ge=0)
    valid_observation_count: int = Field(ge=0)
    suspect_observation_count: int = Field(ge=0)
    rejected_observation_count: int = Field(ge=0)
    expected_observation_count: int | None = Field(default=None, ge=0)
    completeness_percent: float | None = Field(default=None, ge=0, le=100)
    last_observed_at_utc: datetime | None = None
    health_status: str
    variables: list[str]


class StationAvailabilityReport(BaseModel):
    generated_at_utc: datetime
    organization_id: str
    period_start_utc: datetime
    period_end_utc: datetime
    stations: list[StationAvailabilityItem]
    summary: str

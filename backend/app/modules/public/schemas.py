from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

CITIZEN_REPORT_CATEGORIES = {
    "queimada_recorrente": "Queimada recorrente",
    "bota_fora_entulho": "Bota-fora de entulho",
    "lixo_acumulado": "Lixo acumulado",
    "poluicao_industrial": "Poluição industrial",
    "esgoto_ceu_aberto": "Esgoto a céu aberto",
}


class CitizenReportRequest(BaseModel):
    """Denúncia/relato do cidadão para triagem da SEMMAD (não emergencial)."""

    category: Literal[
        "queimada_recorrente",
        "bota_fora_entulho",
        "lixo_acumulado",
        "poluicao_industrial",
        "esgoto_ceu_aberto",
    ]
    description: str = Field(min_length=10, max_length=2000)
    neighborhood: str | None = Field(default=None, max_length=120)
    address: str | None = Field(default=None, max_length=300)
    # Faixa aproximada da região de Betim — rejeita coordenadas absurdas.
    latitude: float | None = Field(default=None, ge=-21.0, le=-19.0)
    longitude: float | None = Field(default=None, ge=-45.5, le=-43.0)
    reporter_name: str | None = Field(default=None, max_length=120)
    reporter_contact: str | None = Field(default=None, max_length=120)


class CitizenReportResponse(BaseModel):
    protocol: str
    detail: str
    disclaimer: str


class PublicAlert(BaseModel):
    alert_code: str
    severity: str
    title: str
    message: str
    valid_from_utc: datetime
    valid_to_utc: datetime
    territory_codes: list[str]


class PublicTerritory(BaseModel):
    territory_code: str
    territory_name: str
    territory_type: str
    geometry_geojson: dict


class PublicRecommendation(BaseModel):
    recommendation_revision_id: str
    title: str
    audience: str
    content: dict
    valid_from_utc: datetime | None
    valid_to_utc: datetime | None
    updated_at: datetime


class PublicSourceHealth(BaseModel):
    source_id: str
    institution_name: str
    source_name: str
    source_type: str
    state: str
    last_success_at: datetime | None
    expected_frequency_minutes: int


class PublicSituation(BaseModel):
    generated_at_utc: datetime
    state: str
    active_alerts: int
    published_recommendations: int
    public_sources: list[PublicSourceHealth]
    notices: list[str]


class PublicObservation(BaseModel):
    observed_at_utc: datetime
    source_id: str
    station_id: str | None
    location_code: str | None
    variable_code: str
    value: float
    unit: str
    quality_status: str
    data_kind: str


class PublicObservationPage(BaseModel):
    generated_at_utc: datetime
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=1000)
    total: int
    items: list[PublicObservation]


class OpenDataResource(BaseModel):
    resource: str
    format: str
    url: str
    description: str


class PublicOpenDataCatalog(BaseModel):
    generated_at_utc: datetime
    license: str
    update_policy: str
    data_dictionary: dict[str, str]
    resources: list[OpenDataResource]


class PublicMethodology(BaseModel):
    title: str
    sections: list[dict[str, str]]

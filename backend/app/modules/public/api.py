from __future__ import annotations

import csv
from datetime import datetime, timezone
import io
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.settings import settings
from app.db.session import get_db
from app.modules.geospatial.models import TerritoryModel
from app.modules.public.schemas import (
    OpenDataResource,
    PublicAlert,
    PublicMethodology,
    PublicObservation,
    PublicObservationPage,
    PublicOpenDataCatalog,
    PublicRecommendation,
    PublicSituation,
    PublicSourceHealth,
    PublicTerritory,
)
from app.modules.public.service import public_publication_service

router = APIRouter()


@router.get("/alerts", response_model=list[PublicAlert])
def public_alerts(db: Session = Depends(get_db)) -> list[PublicAlert]:
    organization_id = _public_organization_id()
    return [_alert_out(item) for item in public_publication_service.active_alerts(db, organization_id)]


@router.get("/recommendations", response_model=list[PublicRecommendation])
def public_recommendations(db: Session = Depends(get_db)) -> list[PublicRecommendation]:
    organization_id = _public_organization_id()
    return [
        PublicRecommendation(
            recommendation_revision_id=item.recommendation_revision_id,
            title=item.title,
            audience=item.audience,
            content=content,
            valid_from_utc=valid_from,
            valid_to_utc=valid_to,
            updated_at=item.created_at,
        )
        for item, content, valid_from, valid_to in public_publication_service.public_recommendations(db, organization_id)
    ]


@router.get("/situation", response_model=PublicSituation)
def public_situation(db: Session = Depends(get_db)) -> PublicSituation:
    organization_id = _public_organization_id()
    now = datetime.now(tz=timezone.utc)
    alerts = public_publication_service.active_alerts(db, organization_id, now)
    recommendations = public_publication_service.public_recommendations(db, organization_id, now)
    sources = public_publication_service.public_sources(db, organization_id)
    health = [_source_out(item, now) for item in sources]
    states = {item.state for item in health}
    state = "operational" if not states or states == {"operational"} else "partial"
    notices = [
        "Somente alertas oficiais vigentes são exibidos.",
        "Observações, estimativas de modelo e previsões são identificadas separadamente.",
    ]
    if not sources:
        notices.append("Nenhuma fonte foi classificada para publicação pública.")
    return PublicSituation(
        generated_at_utc=now,
        state=state,
        active_alerts=len(alerts),
        published_recommendations=len(recommendations),
        public_sources=health,
        notices=notices,
    )


@router.get("/territories", response_model=list[PublicTerritory])
def public_territories(db: Session = Depends(get_db)) -> list[PublicTerritory]:
    organization_id = _public_organization_id()
    stmt = (
        select(TerritoryModel)
        .where(TerritoryModel.organization_id == organization_id, TerritoryModel.status == "active")
        .order_by(TerritoryModel.territory_name.asc())
    )
    result: list[PublicTerritory] = []
    for item in db.scalars(stmt).all():
        try:
            geometry = json.loads(item.geometry_geojson)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(geometry, dict):
            result.append(
                PublicTerritory(
                    territory_code=item.territory_code,
                    territory_name=item.territory_name,
                    territory_type=item.territory_type,
                    geometry_geojson=geometry,
                )
            )
    return result


@router.get("/open-data", response_model=PublicOpenDataCatalog)
def public_open_data_catalog() -> PublicOpenDataCatalog:
    return PublicOpenDataCatalog(
        generated_at_utc=datetime.now(tz=timezone.utc),
        license="A definir pelo Município e pela licença de cada fonte publicada.",
        update_policy="Atualizado após a ingestão, validação e classificação pública de cada fonte.",
        data_dictionary={
            "observed_at_utc": "Instante observado em UTC.",
            "data_kind": "observation, forecast ou model_estimate_or_forecast; não possuem o mesmo grau de certeza.",
            "quality_status": "A API pública publica somente registros com estado valid.",
            "value": "Valor canônico preservando a unidade indicada.",
        },
        resources=[
            OpenDataResource(
                resource="Observações e produtos publicados",
                format="JSON",
                url="/api/v1/public/open-data/observations",
                description="Consulta paginada, filtrável por estação e variável.",
            ),
            OpenDataResource(
                resource="Observações e produtos publicados",
                format="CSV",
                url="/api/v1/public/open-data/observations.csv",
                description="Exportação CSV dos registros retornados pelos mesmos filtros.",
            ),
        ],
    )


@router.get("/open-data/observations", response_model=PublicObservationPage)
def public_observations(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=1000),
    variable_code: str | None = Query(default=None, max_length=40),
    station_id: str | None = Query(default=None, max_length=36),
    db: Session = Depends(get_db),
) -> PublicObservationPage:
    organization_id = _public_organization_id()
    rows = public_publication_service.public_observations(
        db, organization_id, variable_code=variable_code, station_id=station_id
    )
    start = (page - 1) * page_size
    return PublicObservationPage(
        generated_at_utc=datetime.now(tz=timezone.utc),
        page=page,
        page_size=page_size,
        total=len(rows),
        items=[_observation_out(observation, source) for observation, source in rows[start : start + page_size]],
    )


@router.get("/open-data/observations.csv")
def public_observations_csv(
    variable_code: str | None = Query(default=None, max_length=40),
    station_id: str | None = Query(default=None, max_length=36),
    db: Session = Depends(get_db),
) -> Response:
    organization_id = _public_organization_id()
    rows = public_publication_service.public_observations(
        db, organization_id, variable_code=variable_code, station_id=station_id
    )
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream,
        fieldnames=["observed_at_utc", "source_id", "station_id", "location_code", "variable_code", "value", "unit", "quality_status", "data_kind"],
    )
    writer.writeheader()
    for observation, source in rows:
        writer.writerow(_observation_out(observation, source).model_dump(mode="json"))
    return Response(
        content=stream.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=meteoro-observacoes-publicadas.csv"},
    )


@router.get("/methodology", response_model=PublicMethodology)
def public_methodology() -> PublicMethodology:
    return PublicMethodology(
        title="Como o METEORO publica informação",
        sections=[
            {"title": "Evidência e origem", "text": "Cada registro mantém origem, horário e estado de qualidade no ambiente interno."},
            {"title": "Tipos de dado", "text": "Observação instrumental, previsão, estimativa de modelo, alerta oficial e ocorrência confirmada são apresentados como categorias distintas."},
            {"title": "Regra de publicação", "text": "A API pública exclui dados suspeitos ou rejeitados, fontes não classificadas como públicas, recomendações não publicadas e alertas vencidos."},
            {"title": "Limitações", "text": "Cobertura de um alerta não confirma ocorrência em cada bairro. Estimativas e previsões não substituem medição local."},
        ],
    )


def _alert_out(item: object) -> PublicAlert:
    territory_codes = []
    raw_codes = getattr(item, "territory_codes_json", None)
    if raw_codes:
        try:
            parsed = json.loads(raw_codes)
            territory_codes = parsed if isinstance(parsed, list) else []
        except (TypeError, json.JSONDecodeError):
            territory_codes = []
    return PublicAlert(
        alert_code=getattr(item, "alert_code"), severity=getattr(item, "severity"), title=getattr(item, "title"),
        message=getattr(item, "message"), valid_from_utc=getattr(item, "valid_from_utc"),
        valid_to_utc=getattr(item, "valid_to_utc"), territory_codes=territory_codes,
    )


def _source_out(item: object, now: datetime) -> PublicSourceHealth:
    return PublicSourceHealth(
        source_id=getattr(item, "source_id"), institution_name=getattr(item, "institution_name"),
        source_name=getattr(item, "source_name"), source_type=getattr(item, "source_type"),
        state=public_publication_service.source_state(item, now), last_success_at=getattr(item, "last_success_at"),
        expected_frequency_minutes=getattr(item, "expected_frequency_minutes"),
    )


def _observation_out(observation: object, source: object) -> PublicObservation:
    return PublicObservation(
        observed_at_utc=getattr(observation, "observed_at_utc"), source_id=getattr(observation, "source_id"),
        station_id=getattr(observation, "station_id"), location_code=getattr(observation, "location_code"),
        variable_code=getattr(observation, "variable_code"), value=getattr(observation, "value_canonical"),
        unit=getattr(observation, "unit_canonical"), quality_status=getattr(observation, "quality_status"),
        data_kind=public_publication_service.data_kind(source),
    )


def _public_organization_id() -> str:
    if settings.public_organization_id is None or not settings.public_organization_id.strip():
        raise HTTPException(status_code=404, detail="Portal público não configurado.")
    return settings.public_organization_id

from fastapi import APIRouter, Depends, HTTPException, status
from redis.exceptions import RedisError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.audit.service import audit_service
from app.modules.identity.dependencies import require_roles
from app.modules.identity.schemas import CurrentUser
from app.modules.ingestion.service import ingestion_service
from app.modules.ingestion.worker import RedisIngestionQueue
from app.modules.catalog.schemas import (
    AnaHidrowebInstallRequest,
    SourceCreate,
    SourceOut,
    SourceUpdate,
)
from app.modules.catalog.service import catalog_service

router = APIRouter()


@router.get("/sources", response_model=list[SourceOut])
def list_sources(
    current_user: CurrentUser = Depends(
        require_roles("admin_general", "operator", "analyst", "auditor")
    ),
    db: Session = Depends(get_db),
) -> list[SourceOut]:
    return catalog_service.list_sources(db=db, organization_id=current_user.organization_id)


@router.post("/sources", response_model=SourceOut, status_code=status.HTTP_201_CREATED)
def create_source(
    payload: SourceCreate,
    current_user: CurrentUser = Depends(require_roles("admin_general", "operator")),
    db: Session = Depends(get_db),
) -> SourceOut:
    try:
        source = catalog_service.create_source(
            db=db,
            payload=payload,
            organization_id=current_user.organization_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    audit_service.create_event(
        db=db,
        module="catalog",
        action="source.created",
        actor=current_user.email,
        organization_id=current_user.organization_id,
        resource_type="source",
        resource_id=source.source_id,
    )
    return source


@router.post("/sources/profiles/regional-context", response_model=list[SourceOut])
def install_regional_context_sources(
    current_user: CurrentUser = Depends(require_roles("admin_general", "operator")),
    db: Session = Depends(get_db),
) -> list[SourceOut]:
    """Instala referências modeladas regionais para contextualizar Betim."""
    try:
        sources = catalog_service.install_regional_context_profiles(
            db=db,
            organization_id=current_user.organization_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    audit_service.create_event(
        db=db,
        module="catalog",
        action="source.regional_context_profiles_installed",
        actor=current_user.email,
        organization_id=current_user.organization_id,
        resource_type="source_profile",
        resource_id="regional_context_betim",
    )
    return sources


@router.post("/sources/profiles/betim-open-meteo", response_model=list[SourceOut])
def install_betim_open_meteo_sources(
    current_user: CurrentUser = Depends(require_roles("admin_general", "operator")),
    db: Session = Depends(get_db),
) -> list[SourceOut]:
    """Instala idempotentemente os conectores Open-Meteo de Betim."""
    try:
        sources = catalog_service.install_betim_open_meteo_profiles(
            db=db,
            organization_id=current_user.organization_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Only the hourly source is collected after installation; the archive
    # source is intentionally manual/reprocess-only.
    hourly_source = next(
        source for source in sources if source.source_type == "meteorology_model"
    )
    if hourly_source.last_success_at is None:
        try:
            job, created = ingestion_service.create_collection_job(
                db=db,
                organization_id=current_user.organization_id,
                source_id=hourly_source.source_id,
                trigger_type="profile_install",
                run_metadata_json=None,
                requested_by=current_user.email,
            )
            if created:
                RedisIngestionQueue().enqueue(job.job_id)
        except RedisError:
            # The job stays persisted and is recovered by the worker once Redis returns.
            pass
        except ValueError:
            # A falha ao agendar a coleta inicial não deve desfazer a instalação
            # do perfil; a fonte pode ser coletada via collect/all ou agendamento.
            pass

    audit_service.create_event(
        db=db,
        module="catalog",
        action="source.betim_open_meteo_profiles_installed",
        actor=current_user.email,
        organization_id=current_user.organization_id,
        resource_type="source_profile",
        resource_id="betim_open_meteo",
    )
    return sources


@router.post("/sources/profiles/redemet-aviation", response_model=list[SourceOut])
def install_redemet_aviation_sources(
    current_user: CurrentUser = Depends(require_roles("admin_general", "operator")),
    db: Session = Depends(get_db),
) -> list[SourceOut]:
    """Instala os conectores REDEMET de contexto aeronáutico regional."""
    try:
        sources = catalog_service.install_redemet_aviation_profiles(
            db=db,
            organization_id=current_user.organization_id,
        )
        for source in sources:
            if source.last_success_at is None:
                job, created = ingestion_service.create_collection_job(
                    db=db,
                    organization_id=current_user.organization_id,
                    source_id=source.source_id,
                    trigger_type="profile_install",
                    run_metadata_json=None,
                    requested_by=current_user.email,
                )
                if created:
                    try:
                        RedisIngestionQueue().enqueue(job.job_id)
                    except RedisError:
                        pass
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    audit_service.create_event(
        db=db,
        module="catalog",
        action="source.redemet_aviation_profiles_installed",
        actor=current_user.email,
        organization_id=current_user.organization_id,
        resource_type="source_profile",
        resource_id="redemet_aviation_sbbh_sndv",
    )
    return sources


@router.post("/sources/profiles/redemet-imagery", response_model=list[SourceOut])
def install_redemet_imagery_sources(
    current_user: CurrentUser = Depends(require_roles("admin_general", "operator")),
    db: Session = Depends(get_db),
) -> list[SourceOut]:
    """Instala satélite e radar REDEMET como camadas de contexto visual."""
    try:
        sources = catalog_service.install_redemet_imagery_profiles(
            db=db, organization_id=current_user.organization_id,
        )
        for source in sources:
            if source.last_success_at is None:
                job, created = ingestion_service.create_collection_job(
                    db=db, organization_id=current_user.organization_id,
                    source_id=source.source_id, trigger_type="profile_install",
                    run_metadata_json=None, requested_by=current_user.email,
                )
                if created:
                    try:
                        RedisIngestionQueue().enqueue(job.job_id)
                    except RedisError:
                        pass
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.create_event(
        db=db, module="catalog", action="source.redemet_imagery_profiles_installed",
        actor=current_user.email, organization_id=current_user.organization_id,
        resource_type="source_profile", resource_id="redemet_imagery_betim",
    )
    return sources


@router.post("/sources/profiles/inmet-stations", response_model=list[SourceOut])
def install_inmet_regional_stations(
    current_user: CurrentUser = Depends(require_roles("admin_general", "operator")),
    db: Session = Depends(get_db),
) -> list[SourceOut]:
    """Instala as estações automáticas INMET vizinhas de Betim (observação real).

    Exige apitempo.inmet.gov.br na allowlist de rede. Os dados entram como
    'observation' na superfície pública, complementando o modelo Open-Meteo.
    """
    try:
        sources = catalog_service.install_inmet_regional_stations_profiles(
            db=db,
            organization_id=current_user.organization_id,
        )
        for source in sources:
            if source.last_success_at is None:
                try:
                    job, created = ingestion_service.create_collection_job(
                        db=db,
                        organization_id=current_user.organization_id,
                        source_id=source.source_id,
                        trigger_type="profile_install",
                        run_metadata_json=None,
                        requested_by=current_user.email,
                    )
                    if created:
                        RedisIngestionQueue().enqueue(job.job_id)
                except (RedisError, ValueError):
                    pass
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    audit_service.create_event(
        db=db,
        module="catalog",
        action="source.inmet_regional_stations_installed",
        actor=current_user.email,
        organization_id=current_user.organization_id,
        resource_type="source_profile",
        resource_id="inmet_regional_stations",
    )
    return sources


@router.post("/sources/profiles/ana-hidroweb", response_model=list[SourceOut])
def install_ana_hidroweb_sources(
    payload: AnaHidrowebInstallRequest,
    current_user: CurrentUser = Depends(require_roles("admin_general", "operator")),
    db: Session = Depends(get_db),
) -> list[SourceOut]:
    """Instala telemetria fluviométrica da ANA para os códigos informados.

    Alimenta river_level_m/river_flow_m3s e os limiares de cheia do
    planejamento (river_level_high/critical). Exige o host
    telemetriaws1.ana.gov.br na allowlist de rede.
    """
    try:
        sources = catalog_service.install_ana_hidroweb_profiles(
            db=db,
            organization_id=current_user.organization_id,
            station_codes=payload.station_codes,
        )
        for source in sources:
            if source.last_success_at is None:
                try:
                    job, created = ingestion_service.create_collection_job(
                        db=db,
                        organization_id=current_user.organization_id,
                        source_id=source.source_id,
                        trigger_type="profile_install",
                        run_metadata_json=None,
                        requested_by=current_user.email,
                    )
                    if created:
                        RedisIngestionQueue().enqueue(job.job_id)
                except (RedisError, ValueError):
                    # Fonte instalada; coleta ocorre via collect/all ou agendamento.
                    pass
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    audit_service.create_event(
        db=db,
        module="catalog",
        action="source.ana_hidroweb_profiles_installed",
        actor=current_user.email,
        organization_id=current_user.organization_id,
        resource_type="source_profile",
        resource_id=f"ana_hidroweb::{','.join(payload.station_codes)}"[:200],
    )
    return sources


@router.patch("/sources/{source_id}", response_model=SourceOut)
def update_source(
    source_id: str,
    payload: SourceUpdate,
    current_user: CurrentUser = Depends(require_roles("admin_general", "operator")),
    db: Session = Depends(get_db),
) -> SourceOut:
    try:
        source = catalog_service.update_source(
            db=db,
            source_id=source_id,
            organization_id=current_user.organization_id,
            payload=payload,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    audit_service.create_event(
        db=db,
        module="catalog",
        action="source.updated",
        actor=current_user.email,
        organization_id=current_user.organization_id,
        resource_type="source",
        resource_id=source.source_id,
    )
    return source

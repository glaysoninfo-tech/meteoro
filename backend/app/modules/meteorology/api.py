from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.audit.service import audit_service
from app.modules.identity.dependencies import require_roles
from app.modules.identity.schemas import CurrentUser
from app.modules.meteorology.schemas import AviationConditionsResponse, OperationalMapResponse, RequestedForecastResponse
from app.modules.meteorology.service import meteorology_service

router = APIRouter()


@router.get("/aviation/conditions", response_model=AviationConditionsResponse)
def aviation_conditions(
    current_user: CurrentUser = Depends(
        require_roles("admin_general", "operator", "analyst", "auditor")
    ),
    db: Session = Depends(get_db),
) -> AviationConditionsResponse:
    return meteorology_service.get_aviation_conditions(
        db=db,
        organization_id=current_user.organization_id,
    )


@router.get("/map/layers", response_model=OperationalMapResponse)
def operational_map_layers(
    current_user: CurrentUser = Depends(
        require_roles("admin_general", "operator", "analyst", "auditor")
    ),
    db: Session = Depends(get_db),
) -> OperationalMapResponse:
    return meteorology_service.get_operational_map_layers(
        db=db,
        organization_id=current_user.organization_id,
    )


@router.get("/monitoring-points")
def monitoring_points(
    current_user: CurrentUser = Depends(
        require_roles("admin_general", "operator", "analyst", "auditor")
    ),
    db: Session = Depends(get_db),
) -> dict:
    """Pontos estratégicos de monitoramento com últimas leituras, acumulados
    de chuva (1/6/24/72 h) e tendência de nível d'água."""
    return meteorology_service.get_monitoring_points(
        db=db,
        organization_id=current_user.organization_id,
    )


@router.get("/forecast", response_model=RequestedForecastResponse)
def requested_forecast(
    issued_at_utc: datetime | None = Query(default=None),
    horizon_hours: int = Query(default=24, ge=1, le=168),
    step_hours: int = Query(default=6, ge=1, le=24),
    base_window_hours: int = Query(default=72, ge=6, le=720),
    source_ids: list[str] | None = Query(default=None),
    current_user: CurrentUser = Depends(
        require_roles("admin_general", "operator", "analyst", "auditor")
    ),
    db: Session = Depends(get_db),
) -> RequestedForecastResponse:
    issued = issued_at_utc or datetime.now(tz=timezone.utc)
    if step_hours > horizon_hours:
        raise HTTPException(status_code=400, detail="step_hours não pode ser maior que horizon_hours.")

    try:
        response = meteorology_service.generate_requested_forecast(
            db=db,
            organization_id=current_user.organization_id,
            issued_at_utc=issued,
            horizon_hours=horizon_hours,
            step_hours=step_hours,
            base_window_hours=base_window_hours,
            source_ids=source_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    audit_service.create_event(
        db=db,
        module="meteorology",
        action="forecast.requested",
        actor=current_user.email,
        organization_id=current_user.organization_id,
        resource_type="forecast_request",
        resource_id=(
            f"issued:{response.issued_at_utc.isoformat()};"
            f"horizon:{horizon_hours};step:{step_hours};window:{base_window_hours}"
        ),
    )
    return response

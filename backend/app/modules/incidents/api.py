from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.audit.service import audit_service
from app.modules.identity.dependencies import require_roles
from app.modules.identity.schemas import CurrentUser
from app.modules.incidents.schemas import IncidentReport, IncidentTriageRequest
from app.modules.incidents.service import incidents_service

router = APIRouter()


@router.get("/reports", response_model=list[IncidentReport])
def list_reports(
    source_id: str | None = Query(default=None),
    triage_status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: CurrentUser = Depends(
        require_roles("admin_general", "operator", "analyst", "auditor")
    ),
    db: Session = Depends(get_db),
) -> list[IncidentReport]:
    return incidents_service.list_reports(
        db=db,
        organization_id=current_user.organization_id,
        source_id=source_id,
        triage_status=triage_status,
        limit=limit,
    )


@router.patch("/reports/{report_id}/triage", response_model=IncidentReport)
def triage_report(
    report_id: str,
    payload: IncidentTriageRequest,
    current_user: CurrentUser = Depends(require_roles("admin_general", "operator", "analyst")),
    db: Session = Depends(get_db),
) -> IncidentReport:
    try:
        report = incidents_service.triage_report(
            db=db,
            report_id=report_id,
            organization_id=current_user.organization_id,
            triaged_by=current_user.email,
            payload=payload,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    audit_service.create_event(
        db=db,
        module="incidents",
        action="incident.triaged",
        actor=current_user.email,
        organization_id=current_user.organization_id,
        resource_type="incident_report",
        resource_id=report.report_id,
    )
    return report

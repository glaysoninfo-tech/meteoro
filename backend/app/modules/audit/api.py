from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.identity.dependencies import require_roles
from app.modules.identity.schemas import CurrentUser
from app.modules.audit.schemas import AuditEvent
from app.modules.audit.service import audit_service

router = APIRouter()


@router.get("/events", response_model=list[AuditEvent])
def list_events(
    current_user: CurrentUser = Depends(require_roles("admin_general", "auditor")),
    db: Session = Depends(get_db),
) -> list[AuditEvent]:
    return audit_service.list_events(
        db=db,
        organization_id=current_user.organization_id,
    )

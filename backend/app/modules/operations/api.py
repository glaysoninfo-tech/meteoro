from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.identity.dependencies import require_roles
from app.modules.identity.schemas import CurrentUser
from app.modules.operations.schemas import OperationalMap, OperationalSituation
from app.modules.operations.service import operations_service

router = APIRouter()


@router.get("/situation", response_model=OperationalSituation)
def operational_situation(
    current_user: CurrentUser = Depends(require_roles("admin_general", "operator", "analyst", "auditor")),
    db: Session = Depends(get_db),
) -> OperationalSituation:
    return OperationalSituation(**operations_service.situation(db, current_user.organization_id))


@router.get("/map", response_model=OperationalMap)
def operational_map(
    current_user: CurrentUser = Depends(require_roles("admin_general", "operator", "analyst", "auditor")),
    db: Session = Depends(get_db),
) -> OperationalMap:
    return OperationalMap(**operations_service.map(db, current_user.organization_id))

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.settings import settings
from app.db.session import get_db
from app.modules.health.service import environmental_health_service
from app.modules.identity.dependencies import require_roles
from app.modules.identity.schemas import CurrentUser

router = APIRouter()


@router.get("/indicators")
def environmental_health_indicators(
    current_user: CurrentUser = Depends(
        require_roles("admin_general", "operator", "analyst", "auditor")
    ),
    db: Session = Depends(get_db),
) -> dict:
    """Índices de saúde ambiental: calor, baixa umidade, queimada e fumaça."""
    return environmental_health_service.build_indicators(
        db=db,
        organization_id=current_user.organization_id,
    )


@router.get("/public/indicators")
def public_environmental_health_indicators(db: Session = Depends(get_db)) -> dict:
    """Mesma leitura, na superfície pública (linguagem cidadã)."""
    organization_id = settings.public_organization_id
    if not organization_id:
        return {"state": "sem_dado", "indicators": [], "recommended_actions": []}
    return environmental_health_service.build_indicators(
        db=db,
        organization_id=organization_id,
    )

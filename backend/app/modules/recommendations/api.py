from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.audit.service import audit_service
from app.modules.identity.dependencies import require_roles
from app.modules.identity.schemas import CurrentUser
from app.modules.recommendations.schemas import (
    RecommendationApprovalRequest,
    RecommendationCreate,
    RecommendationOut,
    RecommendationPublicationRequest,
    RecommendationRevise,
)
from app.modules.recommendations.service import recommendation_service

router = APIRouter()

@router.get("/", response_model=list[RecommendationOut])
def list_recommendations(current_user: CurrentUser = Depends(require_roles("admin_general", "operator", "analyst", "auditor")), db: Session = Depends(get_db)) -> list[RecommendationOut]:
    return recommendation_service.list(db, current_user.organization_id)

@router.post("/", response_model=RecommendationOut, status_code=status.HTTP_201_CREATED)
def create_recommendation(payload: RecommendationCreate, current_user: CurrentUser = Depends(require_roles("admin_general", "operator", "analyst")), db: Session = Depends(get_db)) -> RecommendationOut:
    item = recommendation_service.create(db, current_user.organization_id, payload, current_user.email)
    _audit(db, current_user, item)
    return item

@router.patch("/{revision_id}", response_model=RecommendationOut)
def revise_recommendation(revision_id: str, payload: RecommendationRevise, current_user: CurrentUser = Depends(require_roles("admin_general", "operator", "analyst")), db: Session = Depends(get_db)) -> RecommendationOut:
    try:
        item = recommendation_service.revise(db, current_user.organization_id, revision_id, payload, current_user.email)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    _audit(db, current_user, item)
    return item


@router.post("/{revision_id}/approve", response_model=RecommendationOut)
def approve_recommendation(
    revision_id: str,
    payload: RecommendationApprovalRequest,
    current_user: CurrentUser = Depends(require_roles("authority_approver")),
    db: Session = Depends(get_db),
) -> RecommendationOut:
    try:
        item = recommendation_service.approve(db, current_user.organization_id, revision_id, current_user.email)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (PermissionError, ValueError) as exc:
        raise HTTPException(status_code=403 if isinstance(exc, PermissionError) else 400, detail=str(exc)) from exc
    _audit(db, current_user, item, action="recommendation.approved", reason=payload.reason)
    return item


@router.post("/{revision_id}/publish", response_model=RecommendationOut)
def publish_recommendation(
    revision_id: str,
    payload: RecommendationPublicationRequest,
    current_user: CurrentUser = Depends(require_roles("authority_approver")),
    db: Session = Depends(get_db),
) -> RecommendationOut:
    try:
        item = recommendation_service.publish(db, current_user.organization_id, revision_id, current_user.email)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (PermissionError, ValueError) as exc:
        raise HTTPException(status_code=403 if isinstance(exc, PermissionError) else 400, detail=str(exc)) from exc
    _audit(db, current_user, item, action="recommendation.published", reason=payload.reason)
    return item

def _audit(db: Session, user: CurrentUser, item, action: str = "recommendation.revision_created", reason: str | None = None) -> None:
    audit_service.create_event(db=db, module="recommendations", action=action, actor=user.email, organization_id=user.organization_id, resource_type="recommendation", resource_id=item.recommendation_revision_id, after_state={"family_id": item.recommendation_family_id, "revision": item.revision_number, "hash": item.content_hash, "status": item.status, "approved_by": item.approved_by, "published_by": item.published_by}, reason=reason if reason is not None else item.change_reason)

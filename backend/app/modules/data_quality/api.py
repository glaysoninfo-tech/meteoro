from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.audit.service import audit_service
from app.modules.identity.dependencies import require_roles
from app.modules.identity.schemas import CurrentUser
from app.modules.data_quality.schemas import (
    QualityIssue,
    QualityReview,
    RuleRevisionCreate,
    RuleRevisionOut,
    RuleRevisionUpdate,
)
from app.modules.data_quality.service import data_quality_service

router = APIRouter()


@router.get("/rules", response_model=list[RuleRevisionOut])
def list_rule_revisions(
    current_user: CurrentUser = Depends(
        require_roles("admin_general", "operator", "analyst", "auditor")
    ),
    db: Session = Depends(get_db),
) -> list[RuleRevisionOut]:
    return data_quality_service.list_rule_revisions(db, current_user.organization_id)


@router.post("/rules", response_model=RuleRevisionOut, status_code=201)
def create_rule_revision(
    payload: RuleRevisionCreate,
    current_user: CurrentUser = Depends(require_roles("admin_general", "operator", "analyst")),
    db: Session = Depends(get_db),
) -> RuleRevisionOut:
    rule = data_quality_service.create_rule_revision(
        db, current_user.organization_id, payload, current_user.email
    )
    audit_service.create_event(
        db=db, module="data_quality", action="rule.revision_created", actor=current_user.email,
        organization_id=current_user.organization_id, resource_type="data_quality_rule",
        resource_id=rule.rule_revision_id,
        after_state={"family_id": rule.rule_family_id, "revision": rule.revision_number, "hash": rule.content_hash},
        reason=rule.change_reason,
    )
    return rule


@router.patch("/rules/{rule_revision_id}", response_model=RuleRevisionOut)
def revise_rule(
    rule_revision_id: str,
    payload: RuleRevisionUpdate,
    current_user: CurrentUser = Depends(require_roles("admin_general", "operator", "analyst")),
    db: Session = Depends(get_db),
) -> RuleRevisionOut:
    try:
        rule = data_quality_service.revise_rule(
            db, current_user.organization_id, rule_revision_id, payload, current_user.email
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    audit_service.create_event(
        db=db, module="data_quality", action="rule.revision_created", actor=current_user.email,
        organization_id=current_user.organization_id, resource_type="data_quality_rule",
        resource_id=rule.rule_revision_id,
        after_state={"family_id": rule.rule_family_id, "revision": rule.revision_number, "hash": rule.content_hash},
        reason=rule.change_reason,
    )
    return rule


@router.get("/issues", response_model=list[QualityIssue])
def list_issues(
    current_user: CurrentUser = Depends(
        require_roles("admin_general", "operator", "analyst", "auditor")
    ),
    db: Session = Depends(get_db),
) -> list[QualityIssue]:
    return data_quality_service.list_issues(
        db=db,
        organization_id=current_user.organization_id,
    )


@router.post("/issues/{issue_id}/review", response_model=QualityIssue)
def review_issue(
    issue_id: str,
    payload: QualityReview,
    current_user: CurrentUser = Depends(require_roles("admin_general", "operator", "analyst")),
    db: Session = Depends(get_db),
) -> QualityIssue:
    try:
        issue = data_quality_service.review_issue(
            db=db,
            issue_id=issue_id,
            payload=payload,
            organization_id=current_user.organization_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    audit_service.create_event(
        db=db,
        module="data_quality",
        action="issue.reviewed",
        actor=current_user.email,
        organization_id=current_user.organization_id,
        resource_type="quality_issue",
        resource_id=issue.issue_id,
    )
    return issue

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.audit.service import audit_service
from app.modules.communications.schemas import (
    BulletinDeliveryOut,
    BulletinDispatchCreateRequest,
    BulletinDispatchOut,
    CommunicationRecipientConsentUpdateRequest,
    CommunicationRecipientCreateRequest,
    CommunicationRecipientOut,
    DailyBulletinGenerateRequest,
    DailyBulletinGenerationResult,
    DispatchExecutionResult,
)
from app.modules.communications.service import communications_service
from app.modules.identity.dependencies import require_roles
from app.modules.identity.schemas import CurrentUser

router = APIRouter()


@router.get("/recipients", response_model=list[CommunicationRecipientOut])
def list_recipients(
    channel_type: str | None = Query(default=None),
    consent_status: str | None = Query(default=None),
    include_inactive: bool = Query(default=False),
    current_user: CurrentUser = Depends(
        require_roles("admin_general", "operator", "analyst", "auditor")
    ),
    db: Session = Depends(get_db),
) -> list[CommunicationRecipientOut]:
    try:
        return communications_service.list_recipients(
            db=db,
            organization_id=current_user.organization_id,
            channel_type=channel_type,
            consent_status=consent_status,
            include_inactive=include_inactive,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/recipients", response_model=CommunicationRecipientOut)
def create_recipient(
    payload: CommunicationRecipientCreateRequest,
    current_user: CurrentUser = Depends(require_roles("admin_general", "operator")),
    db: Session = Depends(get_db),
) -> CommunicationRecipientOut:
    try:
        recipient = communications_service.create_recipient(
            db=db,
            organization_id=current_user.organization_id,
            payload=payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    audit_service.create_event(
        db=db,
        module="communications",
        action="recipient.created",
        actor=current_user.email,
        organization_id=current_user.organization_id,
        resource_type="communication_recipient",
        resource_id=recipient.recipient_id,
    )
    return recipient


@router.patch("/recipients/{recipient_id}/consent", response_model=CommunicationRecipientOut)
def update_recipient_consent(
    recipient_id: str,
    payload: CommunicationRecipientConsentUpdateRequest,
    current_user: CurrentUser = Depends(require_roles("admin_general", "operator")),
    db: Session = Depends(get_db),
) -> CommunicationRecipientOut:
    try:
        recipient = communications_service.update_recipient_consent(
            db=db,
            organization_id=current_user.organization_id,
            recipient_id=recipient_id,
            payload=payload,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    audit_service.create_event(
        db=db,
        module="communications",
        action="recipient.consent_updated",
        actor=current_user.email,
        organization_id=current_user.organization_id,
        resource_type="communication_recipient",
        resource_id=recipient.recipient_id,
    )
    return recipient


@router.get("/dispatches", response_model=list[BulletinDispatchOut])
def list_dispatches(
    status: str | None = Query(default=None),
    bulletin_type: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: CurrentUser = Depends(
        require_roles("admin_general", "operator", "analyst", "auditor")
    ),
    db: Session = Depends(get_db),
) -> list[BulletinDispatchOut]:
    try:
        return communications_service.list_dispatches(
            db=db,
            organization_id=current_user.organization_id,
            status=status,
            bulletin_type=bulletin_type,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/dispatches/{dispatch_id}/deliveries", response_model=list[BulletinDeliveryOut])
def list_dispatch_deliveries(
    dispatch_id: str,
    current_user: CurrentUser = Depends(
        require_roles("admin_general", "operator", "analyst", "auditor")
    ),
    db: Session = Depends(get_db),
) -> list[BulletinDeliveryOut]:
    try:
        return communications_service.list_dispatch_deliveries(
            db=db,
            organization_id=current_user.organization_id,
            dispatch_id=dispatch_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/dispatches", response_model=DispatchExecutionResult)
def create_dispatch(
    payload: BulletinDispatchCreateRequest,
    current_user: CurrentUser = Depends(require_roles("admin_general", "operator", "analyst")),
    db: Session = Depends(get_db),
) -> DispatchExecutionResult:
    try:
        result = communications_service.create_dispatch(
            db=db,
            organization_id=current_user.organization_id,
            requested_by=current_user.email,
            payload=payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    audit_service.create_event(
        db=db,
        module="communications",
        action="dispatch.created",
        actor=current_user.email,
        organization_id=current_user.organization_id,
        resource_type="bulletin_dispatch",
        resource_id=result.dispatch.dispatch_id,
    )
    if payload.send_immediately:
        audit_service.create_event(
            db=db,
            module="communications",
            action="dispatch.sent",
            actor=current_user.email,
            organization_id=current_user.organization_id,
            resource_type="bulletin_dispatch",
            resource_id=result.dispatch.dispatch_id,
        )

    return DispatchExecutionResult(
        dispatch=result.dispatch,
        sent_count=result.sent_count,
        skipped_count=result.skipped_count,
        failed_count=result.failed_count,
    )


@router.post("/dispatches/{dispatch_id}/send", response_model=DispatchExecutionResult)
def send_dispatch(
    dispatch_id: str,
    current_user: CurrentUser = Depends(require_roles("admin_general", "operator", "analyst")),
    db: Session = Depends(get_db),
) -> DispatchExecutionResult:
    try:
        result = communications_service.send_dispatch(
            db=db,
            organization_id=current_user.organization_id,
            dispatch_id=dispatch_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    audit_service.create_event(
        db=db,
        module="communications",
        action="dispatch.sent",
        actor=current_user.email,
        organization_id=current_user.organization_id,
        resource_type="bulletin_dispatch",
        resource_id=result.dispatch.dispatch_id,
    )
    return DispatchExecutionResult(
        dispatch=result.dispatch,
        sent_count=result.sent_count,
        skipped_count=result.skipped_count,
        failed_count=result.failed_count,
    )


@router.post("/bulletins/daily/generate", response_model=DailyBulletinGenerationResult)
def generate_daily_bulletin(
    payload: DailyBulletinGenerateRequest,
    current_user: CurrentUser = Depends(require_roles("admin_general", "operator", "analyst")),
    db: Session = Depends(get_db),
) -> DailyBulletinGenerationResult:
    try:
        result = communications_service.generate_daily_bulletin(
            db=db,
            organization_id=current_user.organization_id,
            requested_by=current_user.email,
            payload=payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    audit_service.create_event(
        db=db,
        module="communications",
        action="daily_bulletin.generated",
        actor=current_user.email,
        organization_id=current_user.organization_id,
        resource_type="bulletin_dispatch",
        resource_id=result.execution.dispatch.dispatch_id,
    )
    if payload.send_immediately:
        audit_service.create_event(
            db=db,
            module="communications",
            action="dispatch.sent",
            actor=current_user.email,
            organization_id=current_user.organization_id,
            resource_type="bulletin_dispatch",
            resource_id=result.execution.dispatch.dispatch_id,
        )

    return DailyBulletinGenerationResult(
        dispatch=result.execution.dispatch,
        sent_count=result.execution.sent_count,
        skipped_count=result.execution.skipped_count,
        failed_count=result.execution.failed_count,
        period_start_utc=result.period_start_utc,
        period_end_utc=result.period_end_utc,
        executive_summary=result.executive_summary,
        active_official_alerts=result.active_official_alerts,
    )

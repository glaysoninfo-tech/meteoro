from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.alerts.schemas import (
    CoverageSummaryItem,
    OfficialAlertCloseRequest,
    OfficialAlertCreateRequest,
    OfficialAlertOut,
    ProtocolActivationOut,
    ProtocolActivateRequest,
    ProtocolApprovalRequest,
    ProtocolCloseRequest,
    ProtocolTemplateCreateRequest,
    ProtocolTemplateOut,
    ProtocolTemplateUpdateRequest,
)
from app.modules.alerts.service import alerts_service
from app.modules.audit.service import audit_service
from app.modules.identity.dependencies import require_roles
from app.modules.identity.schemas import CurrentUser

router = APIRouter()


@router.get("/official", response_model=list[OfficialAlertOut])
def list_official_alerts(
    status: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    source_id: str | None = Query(default=None),
    include_expired: bool = Query(default=True),
    current_user: CurrentUser = Depends(
        require_roles("admin_general", "operator", "analyst", "auditor")
    ),
    db: Session = Depends(get_db),
) -> list[OfficialAlertOut]:
    return alerts_service.list_official_alerts(
        db=db,
        organization_id=current_user.organization_id,
        status=status,
        severity=severity,
        source_id=source_id,
        include_expired=include_expired,
    )


@router.post("/official", response_model=OfficialAlertOut)
def create_official_alert(
    payload: OfficialAlertCreateRequest,
    current_user: CurrentUser = Depends(require_roles("admin_general", "operator", "analyst")),
    db: Session = Depends(get_db),
) -> OfficialAlertOut:
    try:
        alert = alerts_service.create_official_alert(
            db=db,
            organization_id=current_user.organization_id,
            payload=payload,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    audit_service.create_event(
        db=db,
        module="alerts",
        action="official_alert.created",
        actor=current_user.email,
        organization_id=current_user.organization_id,
        resource_type="official_alert",
        resource_id=alert.official_alert_id,
    )
    return alert


@router.post("/official/close-expired")
def close_expired_official_alerts(
    current_user: CurrentUser = Depends(require_roles("admin_general", "operator")),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    closed_count = alerts_service.close_expired_alerts(
        db=db,
        organization_id=current_user.organization_id,
    )
    if closed_count > 0:
        audit_service.create_event(
            db=db,
            module="alerts",
            action="official_alert.expired_closed",
            actor=current_user.email,
            organization_id=current_user.organization_id,
            resource_type="official_alert_batch",
            resource_id=f"count:{closed_count}",
        )
    return {"closed_count": closed_count}


@router.post("/official/{official_alert_id}/close", response_model=OfficialAlertOut)
def close_official_alert(
    official_alert_id: str,
    payload: OfficialAlertCloseRequest,
    current_user: CurrentUser = Depends(require_roles("admin_general", "operator")),
    db: Session = Depends(get_db),
) -> OfficialAlertOut:
    try:
        alert = alerts_service.close_official_alert(
            db=db,
            organization_id=current_user.organization_id,
            official_alert_id=official_alert_id,
            closure_reason=payload.closure_reason,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    audit_service.create_event(
        db=db,
        module="alerts",
        action="official_alert.closed",
        actor=current_user.email,
        organization_id=current_user.organization_id,
        resource_type="official_alert",
        resource_id=alert.official_alert_id,
    )
    return alert


@router.get("/official/coverage", response_model=list[CoverageSummaryItem])
def official_alert_coverage(
    current_user: CurrentUser = Depends(
        require_roles("admin_general", "operator", "analyst", "auditor")
    ),
    db: Session = Depends(get_db),
) -> list[CoverageSummaryItem]:
    return alerts_service.list_coverage_summary(
        db=db,
        organization_id=current_user.organization_id,
    )


@router.get("/protocols", response_model=list[ProtocolTemplateOut])
def list_protocol_templates(
    current_user: CurrentUser = Depends(
        require_roles("admin_general", "operator", "analyst", "auditor")
    ),
    db: Session = Depends(get_db),
) -> list[ProtocolTemplateOut]:
    return alerts_service.list_protocol_templates(
        db=db,
        organization_id=current_user.organization_id,
    )


@router.post("/protocols", response_model=ProtocolTemplateOut)
def create_protocol_template(
    payload: ProtocolTemplateCreateRequest,
    current_user: CurrentUser = Depends(require_roles("admin_general", "operator")),
    db: Session = Depends(get_db),
) -> ProtocolTemplateOut:
    try:
        protocol = alerts_service.create_protocol_template(
            db=db,
            organization_id=current_user.organization_id,
            payload=payload,
            created_by=current_user.email,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    audit_service.create_event(
        db=db,
        module="alerts",
        action="protocol.revision_created",
        actor=current_user.email,
        organization_id=current_user.organization_id,
        resource_type="protocol_template",
        resource_id=protocol.protocol_id,
        after_state={
            "family_id": protocol.protocol_family_id,
            "revision": protocol.revision_number,
            "content_hash": protocol.content_hash,
            "status": protocol.status,
        },
        reason=protocol.change_reason,
    )
    return protocol


@router.patch("/protocols/{protocol_id}", response_model=ProtocolTemplateOut)
def update_protocol_template(
    protocol_id: str,
    payload: ProtocolTemplateUpdateRequest,
    current_user: CurrentUser = Depends(require_roles("admin_general", "operator")),
    db: Session = Depends(get_db),
) -> ProtocolTemplateOut:
    try:
        protocol = alerts_service.update_protocol_template(
            db=db,
            organization_id=current_user.organization_id,
            protocol_id=protocol_id,
            payload=payload,
            created_by=current_user.email,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    audit_service.create_event(
        db=db,
        module="alerts",
        action="protocol.revision_created",
        actor=current_user.email,
        organization_id=current_user.organization_id,
        resource_type="protocol_template",
        resource_id=protocol.protocol_id,
        after_state={
            "family_id": protocol.protocol_family_id,
            "revision": protocol.revision_number,
            "supersedes": protocol.supersedes_protocol_id,
            "content_hash": protocol.content_hash,
            "status": protocol.status,
        },
        reason=protocol.change_reason,
    )
    return protocol


@router.get("/protocol-activations", response_model=list[ProtocolActivationOut])
def list_protocol_activations(
    status: str | None = Query(default=None),
    current_user: CurrentUser = Depends(
        require_roles("admin_general", "operator", "analyst", "auditor")
    ),
    db: Session = Depends(get_db),
) -> list[ProtocolActivationOut]:
    return alerts_service.list_protocol_activations(
        db=db,
        organization_id=current_user.organization_id,
        status=status,
    )


@router.post("/protocols/{protocol_id}/activate", response_model=ProtocolActivationOut)
def activate_protocol(
    protocol_id: str,
    payload: ProtocolActivateRequest,
    current_user: CurrentUser = Depends(require_roles("admin_general", "operator", "analyst")),
    db: Session = Depends(get_db),
) -> ProtocolActivationOut:
    try:
        activation = alerts_service.activate_protocol(
            db=db,
            organization_id=current_user.organization_id,
            protocol_id=protocol_id,
            payload=payload,
            initiated_by=current_user.email,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    audit_service.create_event(
        db=db,
        module="alerts",
        action="protocol.activation_started",
        actor=current_user.email,
        organization_id=current_user.organization_id,
        resource_type="protocol_activation",
        resource_id=activation.activation_id,
    )
    return activation


@router.post("/protocol-activations/{activation_id}/approve", response_model=ProtocolActivationOut)
def approve_protocol_activation(
    activation_id: str,
    payload: ProtocolApprovalRequest,
    current_user: CurrentUser = Depends(require_roles("admin_general", "authority_approver")),
    db: Session = Depends(get_db),
) -> ProtocolActivationOut:
    try:
        activation = alerts_service.approve_protocol_activation(
            db=db,
            organization_id=current_user.organization_id,
            activation_id=activation_id,
            approved_by=current_user.email,
            payload=payload,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    audit_service.create_event(
        db=db,
        module="alerts",
        action="protocol.activation_approved",
        actor=current_user.email,
        organization_id=current_user.organization_id,
        resource_type="protocol_activation",
        resource_id=activation.activation_id,
    )
    return activation


@router.post("/protocol-activations/{activation_id}/close", response_model=ProtocolActivationOut)
def close_protocol_activation(
    activation_id: str,
    payload: ProtocolCloseRequest,
    current_user: CurrentUser = Depends(require_roles("admin_general", "operator", "analyst")),
    db: Session = Depends(get_db),
) -> ProtocolActivationOut:
    try:
        activation = alerts_service.close_protocol_activation(
            db=db,
            organization_id=current_user.organization_id,
            activation_id=activation_id,
            closed_by=current_user.email,
            payload=payload,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    audit_service.create_event(
        db=db,
        module="alerts",
        action="protocol.activation_closed",
        actor=current_user.email,
        organization_id=current_user.organization_id,
        resource_type="protocol_activation",
        resource_id=activation.activation_id,
    )
    return activation

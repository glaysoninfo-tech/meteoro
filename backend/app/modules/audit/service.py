from datetime import datetime, timezone
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.audit.models import AuditEventModel


class AuditService:
    def list_events(self, db: Session, organization_id: str) -> list[AuditEventModel]:
        stmt = (
            select(AuditEventModel)
            .where(AuditEventModel.organization_id == organization_id)
            .order_by(AuditEventModel.occurred_at_utc.desc())
            .limit(100)
        )
        return list(db.scalars(stmt).all())

    def create_event(
        self,
        db: Session,
        module: str,
        action: str,
        actor: str,
        organization_id: str,
        resource_type: str,
        resource_id: str,
        before_state: dict[str, Any] | None = None,
        after_state: dict[str, Any] | None = None,
        reason: str | None = None,
    ) -> AuditEventModel:
        event = AuditEventModel(
            organization_id=organization_id,
            module=module,
            action=action,
            actor=actor,
            occurred_at_utc=datetime.now(tz=timezone.utc),
            resource_type=resource_type,
            resource_id=resource_id,
            before_state_json=self._serialize_state(before_state),
            after_state_json=self._serialize_state(after_state),
            reason=reason,
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        return event

    def _serialize_state(self, state: dict[str, Any] | None) -> str | None:
        if state is None:
            return None
        return json.dumps(state, ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str)


audit_service = AuditService()

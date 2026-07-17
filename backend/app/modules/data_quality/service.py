from datetime import datetime, timezone
import hashlib
import json
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.data_quality.models import DataQualityRuleRevisionModel, QualityIssueModel
from app.modules.data_quality.schemas import (
    QualityReview,
    RuleRevisionCreate,
    RuleRevisionUpdate,
)


class DataQualityService:
    def list_issues(self, db: Session, organization_id: str) -> list[QualityIssueModel]:
        stmt = (
            select(QualityIssueModel)
            .where(QualityIssueModel.organization_id == organization_id)
            .order_by(QualityIssueModel.detected_at_utc.desc())
        )
        return list(db.scalars(stmt).all())

    def review_issue(
        self,
        db: Session,
        issue_id: str,
        payload: QualityReview,
        organization_id: str,
    ) -> QualityIssueModel:
        issue = db.get(QualityIssueModel, issue_id)
        if issue is None:
            raise KeyError(f"issue_id '{issue_id}' não encontrada.")
        if issue.organization_id != organization_id:
            raise PermissionError("Acesso negado para este registro.")

        issue.review_status = "reviewed"
        issue.reviewed_by = payload.reviewer_id
        issue.review_decision = payload.decision
        issue.review_reason = payload.reason
        if issue.detected_at_utc is None:
            issue.detected_at_utc = datetime.now(tz=timezone.utc)

        db.commit()
        db.refresh(issue)
        return issue

    def list_rule_revisions(
        self, db: Session, organization_id: str
    ) -> list[DataQualityRuleRevisionModel]:
        stmt = (
            select(DataQualityRuleRevisionModel)
            .where(DataQualityRuleRevisionModel.organization_id == organization_id)
            .order_by(
                DataQualityRuleRevisionModel.rule_family_id,
                DataQualityRuleRevisionModel.revision_number.desc(),
            )
        )
        return list(db.scalars(stmt).all())

    def create_rule_revision(
        self, db: Session, organization_id: str, payload: RuleRevisionCreate, created_by: str
    ) -> DataQualityRuleRevisionModel:
        now = datetime.now(tz=timezone.utc)
        scope_json = self._canonical_json(payload.scope)
        condition_json = self._canonical_json(payload.condition)
        rule = DataQualityRuleRevisionModel(
            organization_id=organization_id,
            rule_family_id=str(uuid4()),
            revision_number=1,
            supersedes_rule_revision_id=None,
            rule_name=payload.rule_name.strip(),
            scope_json=scope_json,
            condition_json=condition_json,
            severity=payload.severity.strip().lower(),
            status=payload.status.strip().lower(),
            content_hash=self._hash(scope_json, condition_json, payload.rule_name, payload.severity, payload.status),
            created_by=created_by,
            change_reason=payload.change_reason,
            created_at=now,
        )
        db.add(rule)
        db.commit()
        db.refresh(rule)
        return rule

    def revise_rule(
        self,
        db: Session,
        organization_id: str,
        rule_revision_id: str,
        payload: RuleRevisionUpdate,
        created_by: str,
    ) -> DataQualityRuleRevisionModel:
        previous = db.get(DataQualityRuleRevisionModel, rule_revision_id)
        if previous is None:
            raise LookupError(f"rule_revision_id '{rule_revision_id}' não encontrado.")
        if previous.organization_id != organization_id:
            raise PermissionError("Acesso negado para esta regra.")
        values = payload.model_dump(exclude_unset=True)
        reason = values.pop("change_reason")
        scope_json = self._canonical_json(values.get("scope", json.loads(previous.scope_json)))
        condition_json = self._canonical_json(values.get("condition", json.loads(previous.condition_json)))
        name = values.get("rule_name", previous.rule_name).strip()
        severity = values.get("severity", previous.severity).strip().lower()
        status = values.get("status", "draft").strip().lower()
        revision = DataQualityRuleRevisionModel(
            organization_id=organization_id,
            rule_family_id=previous.rule_family_id,
            revision_number=previous.revision_number + 1,
            supersedes_rule_revision_id=previous.rule_revision_id,
            rule_name=name,
            scope_json=scope_json,
            condition_json=condition_json,
            severity=severity,
            status=status,
            content_hash=self._hash(scope_json, condition_json, name, severity, status),
            created_by=created_by,
            change_reason=reason,
            created_at=datetime.now(tz=timezone.utc),
        )
        db.add(revision)
        db.commit()
        db.refresh(revision)
        return revision

    def _canonical_json(self, value: dict) -> str:
        return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))

    def _hash(self, *parts: str) -> str:
        return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


data_quality_service = DataQualityService()

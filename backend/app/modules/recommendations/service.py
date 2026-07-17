from datetime import datetime, timezone
import hashlib
import json
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.recommendations.models import RecommendationRevisionModel
from app.modules.recommendations.schemas import RecommendationCreate, RecommendationRevise


class RecommendationService:
    def list(self, db: Session, organization_id: str) -> list[RecommendationRevisionModel]:
        stmt = select(RecommendationRevisionModel).where(
            RecommendationRevisionModel.organization_id == organization_id
        ).order_by(RecommendationRevisionModel.recommendation_family_id, RecommendationRevisionModel.revision_number.desc())
        return list(db.scalars(stmt).all())

    def create(self, db: Session, organization_id: str, payload: RecommendationCreate, actor: str) -> RecommendationRevisionModel:
        values = payload.model_dump()
        values["status"] = "draft"
        return self._persist(db, organization_id, None, values, actor, payload.change_reason)

    def revise(self, db: Session, organization_id: str, revision_id: str, payload: RecommendationRevise, actor: str) -> RecommendationRevisionModel:
        previous = db.get(RecommendationRevisionModel, revision_id)
        if previous is None:
            raise LookupError(f"recommendation_revision_id '{revision_id}' não encontrada.")
        if previous.organization_id != organization_id:
            raise PermissionError("Acesso negado para esta recomendação.")
        values = payload.model_dump(exclude_unset=True)
        reason = values.pop("change_reason")
        values.setdefault("title", previous.title)
        values.setdefault("audience", previous.audience)
        values.setdefault("criteria", json.loads(previous.criteria_json))
        values.setdefault("content", json.loads(previous.content_json))
        requested_status = values.get("status", "draft").strip().lower()
        if requested_status not in {"draft", "in_review"}:
            raise ValueError("Uma revisão só pode ficar em draft ou in_review; aprovação e publicação usam rotas segregadas.")
        values["status"] = requested_status
        return self._persist(db, organization_id, previous, values, actor, reason)

    def approve(self, db: Session, organization_id: str, revision_id: str, actor: str) -> RecommendationRevisionModel:
        item = self._get(db, organization_id, revision_id)
        if item.created_by == actor:
            raise PermissionError("O autor não pode aprovar a própria recomendação.")
        if item.status != "in_review":
            raise ValueError("Somente uma recomendação em in_review pode ser aprovada.")
        item.status = "approved"
        item.approved_by = actor
        item.approved_at = datetime.now(tz=timezone.utc)
        db.commit()
        db.refresh(item)
        return item

    def publish(self, db: Session, organization_id: str, revision_id: str, actor: str) -> RecommendationRevisionModel:
        item = self._get(db, organization_id, revision_id)
        if item.status != "approved" or not item.approved_by:
            raise ValueError("Somente uma recomendação aprovada pode ser publicada.")
        item.status = "published"
        item.published_by = actor
        item.published_at = datetime.now(tz=timezone.utc)
        db.commit()
        db.refresh(item)
        return item

    def _get(self, db: Session, organization_id: str, revision_id: str) -> RecommendationRevisionModel:
        item = db.get(RecommendationRevisionModel, revision_id)
        if item is None:
            raise LookupError(f"recommendation_revision_id '{revision_id}' não encontrada.")
        if item.organization_id != organization_id:
            raise PermissionError("Acesso negado para esta recomendação.")
        return item

    def _persist(self, db: Session, organization_id: str, previous: RecommendationRevisionModel | None, values: dict, actor: str, reason: str | None) -> RecommendationRevisionModel:
        criteria_json = self._json(values["criteria"])
        content_json = self._json(values["content"])
        status = values["status"].strip().lower()
        title = values["title"].strip()
        audience = values["audience"].strip().lower()
        item = RecommendationRevisionModel(
            organization_id=organization_id,
            recommendation_family_id=previous.recommendation_family_id if previous else str(uuid4()),
            revision_number=(previous.revision_number + 1) if previous else 1,
            supersedes_recommendation_revision_id=previous.recommendation_revision_id if previous else None,
            title=title, audience=audience, criteria_json=criteria_json, content_json=content_json,
            status=status,
            content_hash=hashlib.sha256(f"{title}|{audience}|{criteria_json}|{content_json}|{status}".encode()).hexdigest(),
            created_by=actor, change_reason=reason, created_at=datetime.now(tz=timezone.utc),
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return item

    def _json(self, value: dict) -> str:
        return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


recommendation_service = RecommendationService()

from __future__ import annotations

from datetime import datetime, timezone
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.alerts.models import OfficialAlertModel
from app.modules.catalog.models import SourceModel
from app.modules.ingestion.models import ObservationModel
from app.modules.recommendations.models import RecommendationRevisionModel


PUBLIC_CLASSIFICATIONS = {"public", "public_aggregate"}


class PublicPublicationService:
    """Builds safe public projections; internal records stay in their source modules."""

    def now(self) -> datetime:
        return datetime.now(tz=timezone.utc)

    def active_alerts(self, db: Session, organization_id: str, now: datetime | None = None) -> list[OfficialAlertModel]:
        reference = now or self.now()
        candidates = db.scalars(
            select(OfficialAlertModel)
            .where(
                OfficialAlertModel.organization_id == organization_id,
                OfficialAlertModel.status == "active",
            )
            .order_by(OfficialAlertModel.valid_to_utc.asc())
        ).all()
        return [item for item in candidates if self._is_current(item.valid_from_utc, item.valid_to_utc, reference)]

    def public_sources(self, db: Session, organization_id: str) -> list[SourceModel]:
        candidates = db.scalars(
            select(SourceModel)
            .where(SourceModel.organization_id == organization_id)
            .order_by(SourceModel.institution_name.asc(), SourceModel.source_name.asc())
        ).all()
        return [item for item in candidates if self.is_public_source(item)]

    def public_recommendations(
        self, db: Session, organization_id: str, now: datetime | None = None
    ) -> list[tuple[RecommendationRevisionModel, dict, datetime | None, datetime | None]]:
        reference = now or self.now()
        revisions = db.scalars(
            select(RecommendationRevisionModel)
            .where(RecommendationRevisionModel.organization_id == organization_id)
            .order_by(RecommendationRevisionModel.recommendation_family_id.asc(), RecommendationRevisionModel.revision_number.desc())
        ).all()
        latest_by_family: dict[str, RecommendationRevisionModel] = {}
        for revision in revisions:
            latest_by_family.setdefault(revision.recommendation_family_id, revision)

        published: list[tuple[RecommendationRevisionModel, dict, datetime | None, datetime | None]] = []
        for revision in latest_by_family.values():
            if revision.status != "published":
                continue
            criteria = self._json_dict(revision.criteria_json)
            valid_from = self._as_datetime(criteria.get("valid_from_utc"))
            valid_to = self._as_datetime(criteria.get("valid_to_utc"))
            if not self._is_current(valid_from, valid_to, reference, allow_open_start=True, allow_open_end=True):
                continue
            published.append((revision, self._json_dict(revision.content_json), valid_from, valid_to))
        return sorted(published, key=lambda item: item[0].created_at, reverse=True)

    def public_observations(
        self,
        db: Session,
        organization_id: str,
        *,
        variable_code: str | None = None,
        station_id: str | None = None,
    ) -> list[tuple[ObservationModel, SourceModel]]:
        sources = self.public_sources(db, organization_id)
        source_ids = [source.source_id for source in sources]
        if not source_ids:
            return []
        stmt = (
            select(ObservationModel, SourceModel)
            .join(SourceModel, SourceModel.source_id == ObservationModel.source_id)
            .where(
                ObservationModel.organization_id == organization_id,
                ObservationModel.source_id.in_(source_ids),
                ObservationModel.quality_status == "valid",
            )
            .order_by(ObservationModel.observed_at_utc.desc(), ObservationModel.observation_id.desc())
        )
        if variable_code:
            stmt = stmt.where(ObservationModel.variable_code == variable_code)
        if station_id:
            stmt = stmt.where(ObservationModel.station_id == station_id)
        return list(db.execute(stmt).all())

    def is_public_source(self, source: SourceModel) -> bool:
        if source.status not in {"active", "degraded"}:
            return False
        config = self._json_dict(source.connector_config_json)
        return str(config.get("classification", "")).strip().lower() in PUBLIC_CLASSIFICATIONS

    def source_state(self, source: SourceModel, now: datetime | None = None) -> str:
        if source.status == "degraded":
            return "degraded"
        if source.status != "active":
            return "unavailable"
        if source.last_success_at is None:
            return "waiting_first_collection"
        reference = now or self.now()
        age_minutes = (reference - self._utc(source.last_success_at)).total_seconds() / 60
        if age_minutes > max(source.expected_frequency_minutes * 2, 30):
            return "stale"
        return "operational"

    def data_kind(self, source: SourceModel) -> str:
        config = self._json_dict(source.connector_config_json)
        explicit = config.get("data_kind")
        if isinstance(explicit, str) and explicit.strip():
            return explicit.strip().lower()
        if "model" in source.source_type:
            return "model_estimate_or_forecast"
        if "forecast" in source.source_type:
            return "forecast"
        return "observation"

    def _json_dict(self, value: str | None) -> dict:
        if not value:
            return {}
        try:
            decoded = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return {}
        return decoded if isinstance(decoded, dict) else {}

    def _as_datetime(self, value: object) -> datetime | None:
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return self._utc(parsed)

    def _utc(self, value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

    def _is_current(
        self,
        valid_from: datetime | None,
        valid_to: datetime | None,
        reference: datetime,
        *,
        allow_open_start: bool = False,
        allow_open_end: bool = False,
    ) -> bool:
        if valid_from is None and not allow_open_start:
            return False
        if valid_to is None and not allow_open_end:
            return False
        return (valid_from is None or self._utc(valid_from) <= reference) and (
            valid_to is None or reference <= self._utc(valid_to)
        )


public_publication_service = PublicPublicationService()

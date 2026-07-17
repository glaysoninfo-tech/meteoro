from __future__ import annotations

from datetime import datetime, timezone
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.alerts.models import OfficialAlertModel, ProtocolActivationModel
from app.modules.catalog.models import SourceModel
from app.modules.data_quality.models import QualityIssueModel
from app.modules.geospatial.models import StationModel, TerritoryModel
from app.modules.incidents.models import IncidentReportModel


class OperationsService:
    def map(self, db: Session, organization_id: str) -> dict:
        now = datetime.now(tz=timezone.utc)
        territories = db.scalars(
            select(TerritoryModel).where(TerritoryModel.organization_id == organization_id, TerritoryModel.status == "active")
        ).all()
        stations = db.scalars(
            select(StationModel).where(StationModel.organization_id == organization_id)
        ).all()
        alerts = db.scalars(
            select(OfficialAlertModel).where(
                OfficialAlertModel.organization_id == organization_id, OfficialAlertModel.status == "active"
            )
        ).all()
        incidents = db.scalars(
            select(IncidentReportModel)
            .where(IncidentReportModel.organization_id == organization_id)
            .order_by(IncidentReportModel.reported_at_utc.desc())
            .limit(500)
        ).all()

        return {
            "generated_at_utc": now,
            "territories": self._collection(
                (self._geometry(item.geometry_geojson), {"territory_id": item.territory_id, "code": item.territory_code, "name": item.territory_name, "type": item.territory_type})
                for item in territories
            ),
            "stations": self._collection(
                (self._geometry(item.location_geojson), {"station_id": item.station_id, "code": item.station_code, "name": item.station_name, "type": item.station_type, "status": item.status, "territory_id": item.territory_id})
                for item in stations
            ),
            "alerts": self._collection(
                (self._geometry(item.geometry_geojson), {"alert_id": item.official_alert_id, "code": item.alert_code, "title": item.title, "severity": item.severity, "valid_to_utc": item.valid_to_utc.isoformat()})
                for item in alerts
                if self._is_current(item.valid_from_utc, item.valid_to_utc, now)
            ),
            "incidents": self._collection(
                (self._geometry(item.location_geojson), {"report_id": item.report_id, "category": item.category_code, "severity": item.severity, "triage_status": item.triage_status, "reported_at_utc": item.reported_at_utc.isoformat(), "location_code": item.location_code})
                for item in incidents
            ),
            "notices": [
                "Ocorrências sem coordenada fornecida pela origem permanecem na fila, mas não recebem marcador estimado no mapa.",
                "A geometria de alerta indica área de cobertura; não confirma ocorrência em todo o território coberto.",
            ],
        }

    def situation(self, db: Session, organization_id: str) -> dict:
        now = datetime.now(tz=timezone.utc)
        sources = db.scalars(select(SourceModel).where(SourceModel.organization_id == organization_id)).all()
        stations = db.scalars(select(StationModel).where(StationModel.organization_id == organization_id)).all()
        alerts = db.scalars(select(OfficialAlertModel).where(OfficialAlertModel.organization_id == organization_id, OfficialAlertModel.status == "active")).all()
        pending_quality = db.scalars(select(QualityIssueModel).where(QualityIssueModel.organization_id == organization_id, QualityIssueModel.review_status == "pending")).all()
        pending_incidents = db.scalars(select(IncidentReportModel).where(IncidentReportModel.organization_id == organization_id, IncidentReportModel.triage_status == "pending")).all()
        pending_protocols = db.scalars(select(ProtocolActivationModel).where(ProtocolActivationModel.organization_id == organization_id, ProtocolActivationModel.status == "pending_approval")).all()
        degraded_sources = [item for item in sources if item.status == "degraded"]
        stale_sources = [item for item in sources if self._source_is_stale(item, now)]
        active_alerts = [item for item in alerts if self._is_current(item.valid_from_utc, item.valid_to_utc, now)]
        degraded_stations = [item for item in stations if item.status in {"degraded", "inactive", "maintenance"}]
        has_attention = bool(degraded_sources or stale_sources or pending_quality or pending_protocols)
        return {
            "generated_at_utc": now,
            "platform_state": "attention" if has_attention else "operational",
            "active_alerts": len(active_alerts), "stations_total": len(stations), "stations_degraded": len(degraded_stations),
            "pending_quality_issues": len(pending_quality), "pending_incidents": len(pending_incidents),
            "pending_protocol_approvals": len(pending_protocols), "connectors_degraded": len(degraded_sources), "connectors_stale": len(stale_sources),
            "notices": ["Indicadores operacionais não são alertas públicos.", "O painel exibe somente dados disponíveis para o perfil autenticado."],
        }

    def _source_is_stale(self, source: SourceModel, now: datetime) -> bool:
        if source.status != "active" or source.last_success_at is None:
            return source.status == "active"
        value = self._utc(source.last_success_at)
        return (now - value).total_seconds() / 60 > max(source.expected_frequency_minutes * 2, 30)

    def _geometry(self, value: str | None) -> dict | None:
        if not value:
            return None
        try:
            parsed = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return None
        return parsed if isinstance(parsed, dict) and parsed.get("type") and parsed.get("coordinates") is not None else None

    def _collection(self, entries) -> dict:
        return {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": geometry, "properties": properties} for geometry, properties in entries if geometry is not None]}

    def _is_current(self, valid_from: datetime, valid_to: datetime, now: datetime) -> bool:
        return self._utc(valid_from) <= now <= self._utc(valid_to)

    def _utc(self, value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


operations_service = OperationsService()

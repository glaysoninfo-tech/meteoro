from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.incidents.models import IncidentReportModel
from app.modules.incidents.schemas import IncidentTriageRequest


class IncidentsService:
    def list_reports(
        self,
        db: Session,
        organization_id: str,
        source_id: str | None,
        triage_status: str | None,
        limit: int,
    ) -> list[IncidentReportModel]:
        stmt = select(IncidentReportModel).where(
            IncidentReportModel.organization_id == organization_id
        )
        if source_id is not None:
            stmt = stmt.where(IncidentReportModel.source_id == source_id)
        if triage_status is not None:
            stmt = stmt.where(IncidentReportModel.triage_status == triage_status.strip().lower())
        stmt = stmt.order_by(IncidentReportModel.reported_at_utc.desc()).limit(limit)
        return list(db.scalars(stmt).all())

    def triage_report(
        self,
        db: Session,
        report_id: str,
        organization_id: str,
        triaged_by: str,
        payload: IncidentTriageRequest,
    ) -> IncidentReportModel:
        report = db.get(IncidentReportModel, report_id)
        if report is None:
            raise KeyError(f"report_id '{report_id}' não encontrado.")
        if report.organization_id != organization_id:
            raise PermissionError("Acesso negado para este registro.")

        report.triage_status = payload.triage_status
        report.triaged_by = triaged_by
        report.triage_notes = payload.triage_notes
        db.commit()
        db.refresh(report)
        return report


incidents_service = IncidentsService()

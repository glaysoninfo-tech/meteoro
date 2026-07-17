import csv
import io
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.audit.service import audit_service
from app.modules.identity.dependencies import require_roles
from app.modules.identity.schemas import CurrentUser
from app.modules.planning.pdf import build_simple_pdf
from app.modules.planning.schemas import CommitteeClimateReport, StationAvailabilityReport
from app.modules.planning.service import planning_service

router = APIRouter()


@router.get("/committee/climate-report", response_model=CommitteeClimateReport)
def committee_climate_report(
    period_start_utc: datetime | None = Query(default=None),
    period_end_utc: datetime | None = Query(default=None),
    source_ids: list[str] | None = Query(default=None),
    max_alerts: int = Query(default=100, ge=1, le=500),
    current_user: CurrentUser = Depends(
        require_roles("admin_general", "operator", "analyst", "auditor")
    ),
    db: Session = Depends(get_db),
) -> CommitteeClimateReport:
    end_utc = period_end_utc or datetime.now(tz=timezone.utc)
    start_utc = period_start_utc or (end_utc - timedelta(days=7))

    try:
        report = planning_service.generate_committee_climate_report(
            db=db,
            organization_id=current_user.organization_id,
            period_start_utc=start_utc,
            period_end_utc=end_utc,
            source_ids=source_ids,
            max_alerts=max_alerts,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    audit_service.create_event(
        db=db,
        module="planning",
        action="committee.report_generated",
        actor=current_user.email,
        organization_id=current_user.organization_id,
        resource_type="committee_report",
        resource_id=f"{report.period_start_utc.isoformat()}::{report.period_end_utc.isoformat()}",
    )
    return report


@router.get("/committee/climate-report.pdf")
def committee_climate_report_pdf(
    period_start_utc: datetime | None = Query(default=None),
    period_end_utc: datetime | None = Query(default=None),
    source_ids: list[str] | None = Query(default=None),
    max_alerts: int = Query(default=100, ge=1, le=500),
    current_user: CurrentUser = Depends(require_roles("admin_general", "operator", "analyst", "auditor")),
    db: Session = Depends(get_db),
) -> Response:
    end_utc = period_end_utc or datetime.now(tz=timezone.utc)
    start_utc = period_start_utc or (end_utc - timedelta(days=7))
    try:
        report = planning_service.generate_committee_climate_report(
            db=db, organization_id=current_user.organization_id, period_start_utc=start_utc,
            period_end_utc=end_utc, source_ids=source_ids, max_alerts=max_alerts,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.create_event(
        db=db, module="planning", action="committee.report_pdf_generated", actor=current_user.email,
        organization_id=current_user.organization_id, resource_type="committee_report",
        resource_id=f"pdf::{report.period_start_utc.isoformat()}::{report.period_end_utc.isoformat()}",
    )
    pdf = build_simple_pdf(title="METEORO - Relatorio Climatico do Comite", sections=[
        ("Periodo", [f"Inicio: {report.period_start_utc.isoformat()}", f"Fim: {report.period_end_utc.isoformat()}", report.executive_summary]),
        ("Qualidade", [f"Validos: {report.quality_distribution.valid}", f"Suspeitos: {report.quality_distribution.suspect}", f"Rejeitados: {report.quality_distribution.rejected}"]),
        ("Tendencias", [f"{item.variable_code}: {item.trend_direction}; amostras validas {item.valid_sample_count}; media {item.average_value}" for item in report.trend_summaries]),
        ("Alertas por limiar", [f"[{item.severity}] {item.description} ({item.value} {item.unit})" for item in report.alerts] or ["Nenhum alerta por limiar no periodo."]),
    ])
    return Response(content=pdf, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=meteoro-relatorio-comite.pdf"})


@router.get("/committee/climate-report.csv")
def committee_climate_report_csv(
    period_start_utc: datetime | None = Query(default=None),
    period_end_utc: datetime | None = Query(default=None),
    source_ids: list[str] | None = Query(default=None),
    current_user: CurrentUser = Depends(require_roles("admin_general", "operator", "analyst", "auditor")),
    db: Session = Depends(get_db),
) -> Response:
    end_utc = period_end_utc or datetime.now(tz=timezone.utc)
    start_utc = period_start_utc or (end_utc - timedelta(days=7))
    try:
        report = planning_service.generate_committee_climate_report(
            db=db, organization_id=current_user.organization_id, period_start_utc=start_utc,
            period_end_utc=end_utc, source_ids=source_ids, max_alerts=500,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.create_event(
        db=db, module="planning", action="committee.report_csv_generated", actor=current_user.email,
        organization_id=current_user.organization_id, resource_type="committee_report",
        resource_id=f"csv::{report.period_start_utc.isoformat()}::{report.period_end_utc.isoformat()}",
    )
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=["record_type", "variable_code", "unit", "sample_count", "valid_sample_count", "min_value", "max_value", "average_value", "first_value", "last_value", "trend_delta", "trend_direction", "severity", "description"])
    writer.writeheader()
    for item in report.trend_summaries:
        writer.writerow({"record_type": "trend", **item.model_dump(), "severity": "", "description": ""})
    for item in report.alerts:
        writer.writerow({"record_type": "threshold_alert", "variable_code": item.variable_code, "unit": item.unit, "sample_count": "", "valid_sample_count": "", "min_value": "", "max_value": "", "average_value": "", "first_value": "", "last_value": item.value, "trend_delta": "", "trend_direction": "", "severity": item.severity, "description": item.description})
    return Response(content=stream.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=meteoro-relatorio-comite.csv"})


@router.get("/stations/availability", response_model=StationAvailabilityReport)
def station_availability_report(
    period_start_utc: datetime | None = Query(default=None),
    period_end_utc: datetime | None = Query(default=None),
    current_user: CurrentUser = Depends(require_roles("admin_general", "operator", "analyst", "auditor")),
    db: Session = Depends(get_db),
) -> StationAvailabilityReport:
    end_utc = period_end_utc or datetime.now(tz=timezone.utc)
    start_utc = period_start_utc or (end_utc - timedelta(days=30))
    try:
        report = planning_service.generate_station_availability_report(
            db=db, organization_id=current_user.organization_id, period_start_utc=start_utc, period_end_utc=end_utc,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.create_event(
        db=db, module="planning", action="station_availability.report_generated", actor=current_user.email,
        organization_id=current_user.organization_id, resource_type="station_availability_report",
        resource_id=f"{report.period_start_utc.isoformat()}::{report.period_end_utc.isoformat()}",
    )
    return report


@router.get("/stations/availability.csv")
def station_availability_csv(
    period_start_utc: datetime | None = Query(default=None),
    period_end_utc: datetime | None = Query(default=None),
    current_user: CurrentUser = Depends(require_roles("admin_general", "operator", "analyst", "auditor")),
    db: Session = Depends(get_db),
) -> Response:
    report = station_availability_report(period_start_utc, period_end_utc, current_user, db)
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=["station_code", "station_name", "station_type", "station_status", "health_status", "sensor_count", "observation_count", "valid_observation_count", "suspect_observation_count", "rejected_observation_count", "expected_observation_count", "completeness_percent", "last_observed_at_utc", "variables"])
    writer.writeheader()
    for item in report.stations:
        row = item.model_dump(mode="json")
        writer.writerow({key: ", ".join(row[key]) if key == "variables" else row.get(key) for key in writer.fieldnames})
    return Response(content=stream.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=meteoro-disponibilidade-estacoes.csv"})


@router.get("/stations/availability.pdf")
def station_availability_pdf(
    period_start_utc: datetime | None = Query(default=None),
    period_end_utc: datetime | None = Query(default=None),
    current_user: CurrentUser = Depends(require_roles("admin_general", "operator", "analyst", "auditor")),
    db: Session = Depends(get_db),
) -> Response:
    report = station_availability_report(period_start_utc, period_end_utc, current_user, db)
    pdf = build_simple_pdf(title="METEORO - Disponibilidade de Estacoes", sections=[
        ("Resumo", [report.summary]),
        ("Estacoes", [f"{item.station_code} | {item.health_status} | completude {item.completeness_percent if item.completeness_percent is not None else 'n/d'}% | ultima observacao {item.last_observed_at_utc.isoformat() if item.last_observed_at_utc else 'n/d'}" for item in report.stations] or ["Nenhuma estacao cadastrada no periodo."]),
    ])
    return Response(content=pdf, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=meteoro-disponibilidade-estacoes.pdf"})

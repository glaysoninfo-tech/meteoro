from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from urllib.error import HTTPError, URLError

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.settings import settings
from app.modules.alerts.models import OfficialAlertModel
from app.modules.alerts.parsers import (
    ParsedOfficialAlert,
    parse_official_alert_payload,
    source_is_official_alert_profile,
)
from app.modules.catalog.models import SourceModel
from app.modules.data_quality.models import QualityIssueModel
from app.modules.incidents.models import IncidentReportModel
from app.modules.incidents.parsers import (
    ParsedIncidentReport,
    parse_incident_payload,
    source_is_incident_profile,
)
from app.modules.ingestion.connectors import SourcePayload, collect_from_source
from app.modules.ingestion.models import (
    IngestionJobModel,
    IngestionRunModel,
    ObservationModel,
    RawAssetModel,
)
from app.modules.ingestion.parsers import ParsedObservation, parse_source_payload
from app.modules.ingestion.quality_rules import evaluate_observation_quality
from app.modules.ingestion.schemas import (
    ConnectorHealth,
    IngestionBatchResult,
    IngestionBatchSummary,
    ReprocessRequest,
)

try:
    from botocore.exceptions import BotoCoreError, ClientError

    BOTOCORE_ERRORS: tuple[type[Exception], ...] = (BotoCoreError, ClientError)
except ModuleNotFoundError:
    BOTOCORE_ERRORS = ()

KNOWN_INGESTION_ERRORS: tuple[type[Exception], ...] = (
    HTTPError,
    URLError,
    RuntimeError,
    ValueError,
    OSError,
    UnicodeDecodeError,
    json.JSONDecodeError,
) + BOTOCORE_ERRORS


@dataclass(slots=True)
class IngestionExecutionError(Exception):
    run_id: str
    detail: str

    def __str__(self) -> str:
        return f"Execução de ingestão falhou (run_id={self.run_id}): {self.detail}"


class IngestionService:
    def get_latest_runs(self, db: Session, organization_id: str) -> list[IngestionRunModel]:
        stmt = (
            select(IngestionRunModel)
            .where(IngestionRunModel.organization_id == organization_id)
            .order_by(IngestionRunModel.started_at.desc())
            .limit(50)
        )
        return list(db.scalars(stmt).all())

    def get_latest_observations(
        self,
        db: Session,
        organization_id: str,
        source_id: str | None,
        limit: int,
    ) -> list[ObservationModel]:
        stmt = select(ObservationModel).where(ObservationModel.organization_id == organization_id)
        if source_id is not None:
            stmt = stmt.where(ObservationModel.source_id == source_id)

        stmt = stmt.order_by(ObservationModel.observed_at_utc.desc()).limit(limit)
        return list(db.scalars(stmt).all())

    def request_reprocess(
        self,
        db: Session,
        payload: ReprocessRequest,
        organization_id: str,
    ) -> IngestionRunModel:
        period_start = self._as_utc(payload.period_start_utc)
        period_end = self._as_utc(payload.period_end_utc)
        if period_start >= period_end:
            raise ValueError("period_start_utc deve ser anterior a period_end_utc.")

        metadata_json = json.dumps(
            {
                "period_start_utc": period_start.isoformat(),
                "period_end_utc": period_end.isoformat(),
            },
            ensure_ascii=True,
        )
        return self.collect_source(
            db=db,
            source_id=payload.source_id,
            organization_id=organization_id,
            trigger_type="reprocess",
            run_metadata_json=metadata_json,
            raise_on_failure=True,
        )

    def collect_source(
        self,
        db: Session,
        source_id: str,
        organization_id: str,
        trigger_type: str,
        run_metadata_json: str | None,
        raise_on_failure: bool,
    ) -> IngestionRunModel:
        source = self._get_owned_source(db=db, source_id=source_id, organization_id=organization_id)
        if source is None:
            raise ValueError(f"source_id '{source_id}' não encontrada.")
        if source.status != "active":
            raise ValueError(f"Fonte '{source_id}' está com status '{source.status}'.")
        if source.access_method == "manual_file":
            raise ValueError(
                f"Fonte '{source_id}' exige importação de arquivo. Use o endpoint de upload."
            )

        run = IngestionRunModel(
            organization_id=organization_id,
            source_id=source.source_id,
            status="running",
            trigger_type=trigger_type,
            started_at=datetime.now(tz=timezone.utc),
            finished_at=None,
            records_received=0,
            records_accepted=0,
            records_rejected=0,
            records_deduplicated=0,
            error_summary=None,
            run_metadata_json=run_metadata_json,
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        try:
            payload = collect_from_source(
                source=source,
                collection_context=self._collection_context_from_metadata(
                    trigger_type=trigger_type,
                    run_metadata_json=run_metadata_json,
                ),
            )
            self._finalize_successful_run(
                db=db,
                run=run,
                source=source,
                payload=payload,
            )
            return run
        except KNOWN_INGESTION_ERRORS as exc:
            self._finalize_failed_run(db=db, run=run, source=source, error_detail=str(exc))
            if raise_on_failure:
                raise IngestionExecutionError(run_id=run.ingestion_run_id, detail=str(exc)) from exc
            return run

    def import_uploaded_file(
        self,
        db: Session,
        organization_id: str,
        source_id: str,
        file_name: str,
        file_content_type: str,
        file_bytes: bytes,
    ) -> IngestionRunModel:
        source = self._get_owned_source(db=db, source_id=source_id, organization_id=organization_id)
        if source is None:
            raise ValueError(f"source_id '{source_id}' não encontrada.")
        if source.status != "active":
            raise ValueError(f"Fonte '{source_id}' está com status '{source.status}'.")
        if source.access_method != "manual_file":
            raise ValueError(
                f"Fonte '{source_id}' não está configurada para importação manual de arquivo."
            )

        metadata_json = json.dumps({"uploaded_file_name": file_name}, ensure_ascii=True)
        run = IngestionRunModel(
            organization_id=organization_id,
            source_id=source.source_id,
            status="running",
            trigger_type="manual_import",
            started_at=datetime.now(tz=timezone.utc),
            finished_at=None,
            records_received=0,
            records_accepted=0,
            records_rejected=0,
            records_deduplicated=0,
            error_summary=None,
            run_metadata_json=metadata_json,
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        payload = SourcePayload(
            content_bytes=file_bytes,
            content_type=file_content_type or "application/octet-stream",
            source_timestamp=datetime.now(tz=timezone.utc),
            metadata_json=metadata_json,
        )
        try:
            self._finalize_successful_run(
                db=db,
                run=run,
                source=source,
                payload=payload,
            )
            return run
        except KNOWN_INGESTION_ERRORS as exc:
            self._finalize_failed_run(db=db, run=run, source=source, error_detail=str(exc))
            raise IngestionExecutionError(run_id=run.ingestion_run_id, detail=str(exc)) from exc

    def collect_sources_batch(
        self,
        db: Session,
        organization_id: str,
        only_due: bool,
    ) -> IngestionBatchSummary:
        sources = self._list_active_collectable_sources(db=db, organization_id=organization_id)
        now = datetime.now(tz=timezone.utc)
        if only_due:
            sources = [source for source in sources if self._source_is_due(source=source, now=now)]
            trigger_type = "scheduled"
        else:
            trigger_type = "refresh"

        return self._collect_sources(
            db=db,
            sources=sources,
            trigger_type=trigger_type,
        )

    def collect_due_sources_global(self, db: Session) -> IngestionBatchSummary:
        now = datetime.now(tz=timezone.utc)
        sources = self._list_active_collectable_sources_global(db=db)
        due_sources = [source for source in sources if self._source_is_due(source=source, now=now)]
        return self._collect_sources(
            db=db,
            sources=due_sources,
            trigger_type="scheduled",
        )

    def _collect_sources(
        self,
        db: Session,
        sources: list[SourceModel],
        trigger_type: str,
    ) -> IngestionBatchSummary:
        results: list[IngestionBatchResult] = []
        collected_successfully = 0
        failed = 0
        for source in sources:
            run = self.collect_source(
                db=db,
                source_id=source.source_id,
                organization_id=source.organization_id,
                trigger_type=trigger_type,
                run_metadata_json=None,
                raise_on_failure=False,
            )
            if run.status == "completed":
                collected_successfully += 1
                results.append(
                    IngestionBatchResult(
                        organization_id=source.organization_id,
                        source_id=source.source_id,
                        source_name=source.source_name,
                        status=run.status,
                        run_id=run.ingestion_run_id,
                        detail=None,
                    )
                )
                continue

            failed += 1
            results.append(
                IngestionBatchResult(
                    organization_id=source.organization_id,
                    source_id=source.source_id,
                    source_name=source.source_name,
                    status=run.status,
                    run_id=run.ingestion_run_id,
                    detail=run.error_summary,
                )
            )

        return IngestionBatchSummary(
            total_sources=len(results),
            collected_successfully=collected_successfully,
            failed=failed,
            results=results,
        )

    def get_connectors_health(self, db: Session, organization_id: str) -> list[ConnectorHealth]:
        stmt = (
            select(SourceModel)
            .where(SourceModel.organization_id == organization_id)
            .order_by(SourceModel.created_at.desc())
        )
        sources = list(db.scalars(stmt).all())
        now = datetime.now(tz=timezone.utc)
        health_items: list[ConnectorHealth] = []

        for source in sources:
            last_success_at = self._as_utc(source.last_success_at)
            last_collection_at = self._as_utc(source.last_collection_at)
            delay_minutes: int | None = None
            if last_success_at is not None:
                delay_minutes = int((now - last_success_at).total_seconds() // 60)

            state = self._resolve_source_state(
                source=source,
                delay_minutes=delay_minutes,
            )
            health_items.append(
                ConnectorHealth(
                    source_id=source.source_id,
                    source_name=source.source_name,
                    access_method=source.access_method,
                    status=source.status,
                    state=state,
                    expected_frequency_minutes=source.expected_frequency_minutes,
                    delay_minutes=delay_minutes,
                    last_collection_at=last_collection_at,
                    last_success_at=last_success_at,
                    last_error=source.last_error,
                )
            )
        return health_items

    def _finalize_successful_run(
        self,
        db: Session,
        run: IngestionRunModel,
        source: SourceModel,
        payload: SourcePayload,
    ) -> None:
        now = datetime.now(tz=timezone.utc)
        raw_asset = self._store_raw_asset(db=db, run=run, source=source, payload=payload, collected_at=now)
        db.flush()
        db.refresh(raw_asset)

        try:
            if source_is_official_alert_profile(source=source):
                parsed_alerts = parse_official_alert_payload(source=source, payload=payload)
                records_received = len(parsed_alerts)
                records_accepted, records_rejected, records_deduplicated = self._persist_official_alerts(
                    db=db,
                    source=source,
                    run=run,
                    raw_asset=raw_asset,
                    alerts=parsed_alerts,
                )
            elif source_is_incident_profile(source=source):
                parsed_incidents = parse_incident_payload(source=source, payload=payload)
                records_received = len(parsed_incidents)
                records_accepted, records_rejected, records_deduplicated = self._persist_incident_reports(
                    db=db,
                    source=source,
                    run=run,
                    raw_asset=raw_asset,
                    incidents=parsed_incidents,
                )
            else:
                parsed_observations = parse_source_payload(source=source, payload=payload)
                records_received = len(parsed_observations)
                records_accepted, records_rejected, records_deduplicated = self._persist_observations(
                    db=db,
                    source=source,
                    run=run,
                    raw_asset=raw_asset,
                    observations=parsed_observations,
                )
            raw_asset.parser_status = self._resolve_parser_status(
                accepted=records_accepted,
                rejected=records_rejected,
                deduplicated=records_deduplicated,
            )
        except KNOWN_INGESTION_ERRORS as exc:
            raw_asset.parser_status = "failed"
            raw_asset.metadata_json = self._merge_metadata_json(
                raw_asset.metadata_json,
                {"parser_error": str(exc)},
            )
            raise

        run.status = "completed"
        run.finished_at = now
        run.records_received = records_received
        run.records_accepted = records_accepted
        run.records_rejected = records_rejected
        run.records_deduplicated = records_deduplicated
        run.error_summary = None
        source.last_collection_at = now
        source.last_success_at = now
        source.last_error = None

        db.commit()
        db.refresh(run)

    def _persist_observations(
        self,
        db: Session,
        source: SourceModel,
        run: IngestionRunModel,
        raw_asset: RawAssetModel,
        observations: list[ParsedObservation],
    ) -> tuple[int, int, int]:
        created_at = datetime.now(tz=timezone.utc)
        accepted = 0
        rejected = 0
        deduplicated = 0

        for parsed in observations:
            quality = evaluate_observation_quality(
                variable_code=parsed.variable_code,
                value_canonical=parsed.value_canonical,
                observed_at_utc=parsed.observed_at_utc,
            )
            observation = ObservationModel(
                    organization_id=source.organization_id,
                    station_id=source.station_id,
                    sensor_id=source.sensor_id,
                    source_id=source.source_id,
                    ingestion_run_id=run.ingestion_run_id,
                    raw_asset_id=raw_asset.raw_asset_id,
                    observed_at_utc=parsed.observed_at_utc,
                    variable_code=parsed.variable_code,
                    value_original=parsed.value_original,
                    unit_original=parsed.unit_original,
                    value_canonical=parsed.value_canonical,
                    unit_canonical=parsed.unit_canonical,
                    quality_status=quality.status,
                    quality_score=quality.score,
                    quality_flag_code=quality.flag_code,
                    quality_description=quality.description,
                    location_code=parsed.location_code,
                    record_fingerprint=self._observation_fingerprint(source=source, parsed=parsed),
                    created_at=created_at,
                )
            if not self._add_if_new(db=db, entity=observation):
                deduplicated += 1
                continue

            if quality.status == "rejected":
                rejected += 1
            else:
                accepted += 1

            if quality.flag_code is not None and quality.description is not None:
                db.add(
                    QualityIssueModel(
                        organization_id=source.organization_id,
                        source_id=source.source_id,
                        variable_code=parsed.variable_code,
                        flag_code=quality.flag_code,
                        severity=self._resolve_quality_severity(quality.status),
                        description=quality.description,
                        detected_at_utc=created_at,
                        review_status="pending",
                        reviewed_by=None,
                        review_decision=None,
                        review_reason=None,
                    )
                )

        return accepted, rejected, deduplicated

    def _persist_official_alerts(
        self,
        db: Session,
        source: SourceModel,
        run: IngestionRunModel,
        raw_asset: RawAssetModel,
        alerts: list[ParsedOfficialAlert],
    ) -> tuple[int, int, int]:
        created_at = datetime.now(tz=timezone.utc)
        accepted = 0
        rejected = 0
        deduplicated = 0

        for parsed in alerts:
            flag_code, description = self._validate_official_alert(parsed=parsed, now_utc=created_at)
            status = (
                self._resolve_official_alert_status(valid_to_utc=parsed.valid_to_utc, now_utc=created_at)
                if flag_code is None
                else "invalid"
            )
            alert = OfficialAlertModel(
                    organization_id=source.organization_id,
                    source_id=source.source_id,
                    ingestion_run_id=run.ingestion_run_id,
                    raw_asset_id=raw_asset.raw_asset_id,
                    external_alert_id=parsed.external_alert_id,
                    issuer=parsed.issuer,
                    alert_code=parsed.alert_code,
                    severity=parsed.severity,
                    status=status,
                    issued_at_utc=parsed.issued_at_utc,
                    valid_from_utc=parsed.valid_from_utc,
                    valid_to_utc=parsed.valid_to_utc,
                    title=parsed.title,
                    message=parsed.message,
                    territory_codes_json=json.dumps(parsed.territory_codes, ensure_ascii=True),
                    geometry_geojson=parsed.geometry_geojson,
                    original_payload_json=parsed.original_payload_json,
                    record_fingerprint=self._official_alert_fingerprint(source=source, parsed=parsed),
                    created_at=created_at,
                    closed_at_utc=None,
                    closed_reason=None,
                )
            if not self._add_if_new(db=db, entity=alert):
                deduplicated += 1
                continue

            if flag_code is None:
                accepted += 1
            else:
                rejected += 1

            if flag_code is not None and description is not None:
                db.add(
                    QualityIssueModel(
                        organization_id=source.organization_id,
                        source_id=source.source_id,
                        variable_code="official_alert",
                        flag_code=flag_code,
                        severity=self._resolve_official_alert_issue_severity(flag_code=flag_code),
                        description=description,
                        detected_at_utc=created_at,
                        review_status="pending",
                        reviewed_by=None,
                        review_decision=None,
                        review_reason=None,
                    )
                )

        return accepted, rejected, deduplicated

    def _validate_official_alert(
        self,
        parsed: ParsedOfficialAlert,
        now_utc: datetime,
    ) -> tuple[str | None, str | None]:
        if parsed.valid_from_utc > parsed.valid_to_utc:
            return (
                "official_alert_invalid_range",
                "Período de vigência inválido: valid_from_utc maior que valid_to_utc.",
            )

        if parsed.issued_at_utc > now_utc + timedelta(minutes=5):
            return (
                "official_alert_future_issue_time",
                "Data de emissão do alerta está no futuro.",
            )

        if parsed.issuer.strip() == "":
            return (
                "official_alert_missing_issuer",
                "Órgão emissor ausente no alerta oficial.",
            )

        if parsed.title.strip() == "" or parsed.message.strip() == "":
            return (
                "official_alert_missing_text",
                "Título ou mensagem do alerta oficial ausente.",
            )

        allowed_severity = {"low", "medium", "high", "critical"}
        if parsed.severity not in allowed_severity:
            allowed = ", ".join(sorted(allowed_severity))
            return (
                "official_alert_invalid_severity",
                f"Severidade inválida: '{parsed.severity}'. Permitidas: {allowed}.",
            )

        return (None, None)

    def _resolve_official_alert_status(self, valid_to_utc: datetime, now_utc: datetime) -> str:
        if valid_to_utc < now_utc:
            return "expired"
        return "active"

    def _resolve_official_alert_issue_severity(self, flag_code: str) -> str:
        high_flags = {
            "official_alert_invalid_range",
            "official_alert_future_issue_time",
        }
        if flag_code in high_flags:
            return "high"
        return "medium"

    def _persist_incident_reports(
        self,
        db: Session,
        source: SourceModel,
        run: IngestionRunModel,
        raw_asset: RawAssetModel,
        incidents: list[ParsedIncidentReport],
    ) -> tuple[int, int, int]:
        created_at = datetime.now(tz=timezone.utc)
        accepted = 0
        rejected = 0
        deduplicated = 0

        for parsed in incidents:
            flag_code, description = self._validate_incident_report(parsed=parsed, now_utc=created_at)
            triage_status = "pending" if flag_code is None else "invalid"
            incident = IncidentReportModel(
                    organization_id=source.organization_id,
                    source_id=source.source_id,
                    ingestion_run_id=run.ingestion_run_id,
                    raw_asset_id=raw_asset.raw_asset_id,
                    reported_at_utc=parsed.reported_at_utc,
                    report_origin=parsed.report_origin,
                    category_code=parsed.category_code,
                    severity=parsed.severity,
                    description=parsed.description,
                    location_code=parsed.location_code,
                    location_geojson=parsed.location_geojson,
                    address_text=parsed.address_text,
                    reporter_name=parsed.reporter_name,
                    reporter_contact=parsed.reporter_contact,
                    external_protocol=parsed.external_protocol,
                    triage_status=triage_status,
                    triaged_by=None,
                    triage_notes=None,
                    record_fingerprint=self._incident_fingerprint(source=source, parsed=parsed),
                    created_at=created_at,
                )
            if not self._add_if_new(db=db, entity=incident):
                deduplicated += 1
                continue

            if flag_code is None:
                accepted += 1
            else:
                rejected += 1

            if flag_code is not None and description is not None:
                db.add(
                    QualityIssueModel(
                        organization_id=source.organization_id,
                        source_id=source.source_id,
                        variable_code="incident_report",
                        flag_code=flag_code,
                        severity=self._resolve_incident_quality_severity(flag_code=flag_code),
                        description=description,
                        detected_at_utc=created_at,
                        review_status="pending",
                        reviewed_by=None,
                        review_decision=None,
                        review_reason=None,
                    )
                )

        return accepted, rejected, deduplicated

    def _validate_incident_report(
        self,
        parsed: ParsedIncidentReport,
        now_utc: datetime,
    ) -> tuple[str | None, str | None]:
        if parsed.description is None:
            return (
                "incident_missing_description",
                "Descrição do incidente ausente no arquivo de origem.",
            )

        allowed_origins = {"inspection", "citizen"}
        if parsed.report_origin not in allowed_origins:
            allowed = ", ".join(sorted(allowed_origins))
            return (
                "incident_invalid_origin",
                f"Origem do incidente inválida: '{parsed.report_origin}'. Permitidas: {allowed}.",
            )

        allowed_severities = {"low", "medium", "high", "critical"}
        if parsed.severity not in allowed_severities:
            allowed = ", ".join(sorted(allowed_severities))
            return (
                "incident_invalid_severity",
                f"Severidade inválida: '{parsed.severity}'. Permitidas: {allowed}.",
            )

        if parsed.reported_at_utc > now_utc + timedelta(minutes=5):
            return (
                "incident_future_timestamp",
                "Timestamp de ocorrência está no futuro.",
            )

        return (None, None)

    def _resolve_incident_quality_severity(self, flag_code: str) -> str:
        high_flags = {
            "incident_missing_description",
            "incident_future_timestamp",
        }
        if flag_code in high_flags:
            return "high"
        return "medium"

    def _resolve_quality_severity(self, quality_status: str) -> str:
        if quality_status == "rejected":
            return "high"
        if quality_status == "suspect":
            return "medium"
        return "low"

    def _resolve_parser_status(self, accepted: int, rejected: int, deduplicated: int) -> str:
        if accepted > 0 and rejected > 0:
            return "partial"
        if accepted > 0:
            return "parsed"
        if rejected > 0:
            return "rejected"
        if deduplicated > 0:
            return "deduplicated"
        return "empty"

    def _collection_context_from_metadata(
        self,
        trigger_type: str,
        run_metadata_json: str | None,
    ) -> dict[str, str] | None:
        if trigger_type != "reprocess":
            return None
        if run_metadata_json is None:
            raise ValueError("Reprocessamento exige período de coleta configurado.")
        try:
            metadata = json.loads(run_metadata_json)
        except json.JSONDecodeError as exc:
            raise ValueError("Metadados do reprocessamento são inválidos.") from exc
        if not isinstance(metadata, dict):
            raise ValueError("Metadados do reprocessamento devem ser um objeto JSON.")
        period_start = metadata.get("period_start_utc")
        period_end = metadata.get("period_end_utc")
        if not isinstance(period_start, str) or not isinstance(period_end, str):
            raise ValueError("Reprocessamento exige period_start_utc e period_end_utc.")
        return {"period_start_utc": period_start, "period_end_utc": period_end}

    def _add_if_new(self, db: Session, entity: object) -> bool:
        try:
            with db.begin_nested():
                db.add(entity)
                db.flush()
        except IntegrityError:
            return False
        return True

    def _observation_fingerprint(self, source: SourceModel, parsed: ParsedObservation) -> str:
        return self._record_fingerprint(
            source_id=source.source_id,
            record_type="observation",
            payload={
                "observed_at_utc": self._as_utc(parsed.observed_at_utc).isoformat(),
                "variable_code": parsed.variable_code,
                "value_canonical": parsed.value_canonical,
                "unit_canonical": parsed.unit_canonical,
                "location_code": parsed.location_code or "",
            },
        )

    def create_collection_job(
        self,
        db: Session,
        organization_id: str,
        source_id: str,
        trigger_type: str,
        run_metadata_json: str | None,
        requested_by: str | None,
    ) -> tuple[IngestionJobModel, bool]:
        source = self._get_owned_source(db=db, source_id=source_id, organization_id=organization_id)
        if source is None:
            raise ValueError(f"source_id '{source_id}' não encontrada.")
        if source.status != "active":
            raise ValueError(f"Fonte '{source_id}' está com status '{source.status}'.")
        if source.access_method == "manual_file":
            raise ValueError("Fontes manual_file não podem ser coletadas pelo worker.")
        if trigger_type not in {"scheduled", "manual_collect", "reprocess", "profile_install"}:
            raise ValueError(f"trigger_type de job inválido: '{trigger_type}'.")
        if trigger_type == "reprocess":
            self._collection_context_from_metadata(
                trigger_type=trigger_type,
                run_metadata_json=run_metadata_json,
            )

        existing = db.scalar(
            select(IngestionJobModel)
            .where(
                IngestionJobModel.source_id == source_id,
                IngestionJobModel.status.in_(("queued", "processing")),
            )
            .order_by(IngestionJobModel.created_at.asc())
        )
        if existing is not None:
            return existing, False

        job = IngestionJobModel(
            organization_id=organization_id,
            source_id=source_id,
            trigger_type=trigger_type,
            status="queued",
            run_metadata_json=run_metadata_json,
            requested_by=requested_by,
            ingestion_run_id=None,
            attempts=0,
            error_summary=None,
            created_at=datetime.now(tz=timezone.utc),
            started_at=None,
            finished_at=None,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return job, True

    def list_due_sources_global(self, db: Session) -> list[SourceModel]:
        now = datetime.now(tz=timezone.utc)
        sources = self._list_active_collectable_sources_global(db=db)
        return [source for source in sources if self._source_is_due(source=source, now=now)]

    def get_job(
        self,
        db: Session,
        job_id: str,
        organization_id: str,
    ) -> IngestionJobModel | None:
        return db.scalar(
            select(IngestionJobModel).where(
                IngestionJobModel.job_id == job_id,
                IngestionJobModel.organization_id == organization_id,
            )
        )

    def _official_alert_fingerprint(self, source: SourceModel, parsed: ParsedOfficialAlert) -> str:
        return self._record_fingerprint(
            source_id=source.source_id,
            record_type="official_alert",
            payload={
                "external_alert_id": parsed.external_alert_id or "",
                "issuer": parsed.issuer,
                "alert_code": parsed.alert_code,
                "issued_at_utc": self._as_utc(parsed.issued_at_utc).isoformat(),
                "valid_to_utc": self._as_utc(parsed.valid_to_utc).isoformat(),
                "message": parsed.message,
            },
        )

    def _incident_fingerprint(self, source: SourceModel, parsed: ParsedIncidentReport) -> str:
        return self._record_fingerprint(
            source_id=source.source_id,
            record_type="incident_report",
            payload={
                "external_protocol": parsed.external_protocol or "",
                "reported_at_utc": self._as_utc(parsed.reported_at_utc).isoformat(),
                "category_code": parsed.category_code,
                "description": parsed.description or "",
                "location_code": parsed.location_code or "",
                "location_geojson": parsed.location_geojson or "",
            },
        )

    def _record_fingerprint(
        self,
        source_id: str,
        record_type: str,
        payload: dict[str, object],
    ) -> str:
        canonical = json.dumps(
            {"source_id": source_id, "record_type": record_type, **payload},
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _merge_metadata_json(self, metadata_json: str | None, extra: dict[str, str]) -> str:
        metadata: dict[str, str] = {}
        if metadata_json:
            decoded = json.loads(metadata_json)
            if not isinstance(decoded, dict):
                raise ValueError("metadata_json da coleta deve conter objeto JSON.")
            metadata = {str(key): str(value) for key, value in decoded.items()}
        metadata.update(extra)
        return json.dumps(metadata, ensure_ascii=True)

    def _finalize_failed_run(
        self,
        db: Session,
        run: IngestionRunModel,
        source: SourceModel,
        error_detail: str,
    ) -> None:
        now = datetime.now(tz=timezone.utc)
        run.status = "failed"
        run.finished_at = now
        run.error_summary = error_detail
        source.last_collection_at = now
        source.last_error = error_detail
        db.commit()
        db.refresh(run)

    def _store_raw_asset(
        self,
        db: Session,
        run: IngestionRunModel,
        source: SourceModel,
        payload: SourcePayload,
        collected_at: datetime,
    ) -> RawAssetModel:
        storage_root = Path(settings.ingestion_storage_path)
        if not storage_root.is_absolute():
            storage_root = (Path.cwd() / storage_root).resolve()

        source_folder = storage_root / source.source_id / collected_at.strftime("%Y%m%d")
        source_folder.mkdir(parents=True, exist_ok=True)

        file_extension = self._resolve_extension(
            content_type=payload.content_type,
            endpoint_reference=source.endpoint_reference,
        )
        file_name = f"{run.ingestion_run_id}{file_extension}"
        file_path = source_folder / file_name
        file_path.write_bytes(payload.content_bytes)

        payload_hash = hashlib.sha256(payload.content_bytes).hexdigest()
        raw_asset = RawAssetModel(
            organization_id=source.organization_id,
            source_id=source.source_id,
            ingestion_run_id=run.ingestion_run_id,
            object_uri=str(file_path),
            content_type=payload.content_type,
            size_bytes=len(payload.content_bytes),
            payload_hash=payload_hash,
            source_timestamp=payload.source_timestamp,
            collected_at=collected_at,
            parser_status="stored",
            metadata_json=payload.metadata_json,
        )
        db.add(raw_asset)
        return raw_asset

    def _resolve_extension(self, content_type: str, endpoint_reference: str) -> str:
        endpoint_lower = endpoint_reference.lower()
        content_type_lower = content_type.lower()
        if endpoint_lower.endswith(".json") or "json" in content_type_lower:
            return ".json"
        if endpoint_lower.endswith(".csv") or "csv" in content_type_lower:
            return ".csv"
        if endpoint_lower.endswith(".xml") or "xml" in content_type_lower:
            return ".xml"
        return ".bin"

    def _get_owned_source(
        self,
        db: Session,
        source_id: str,
        organization_id: str,
    ) -> SourceModel | None:
        stmt = select(SourceModel).where(
            SourceModel.source_id == source_id,
            SourceModel.organization_id == organization_id,
        )
        return db.scalar(stmt)

    def _list_active_collectable_sources(self, db: Session, organization_id: str) -> list[SourceModel]:
        stmt = (
            select(SourceModel)
            .where(
                SourceModel.organization_id == organization_id,
                SourceModel.status == "active",
                SourceModel.access_method.in_(("http", "s3", "mqtt", "opcua")),
            )
            .order_by(SourceModel.source_name.asc())
        )
        return list(db.scalars(stmt).all())

    def _list_active_collectable_sources_global(self, db: Session) -> list[SourceModel]:
        stmt = (
            select(SourceModel)
            .where(
                SourceModel.status == "active",
                SourceModel.access_method.in_(("http", "s3", "mqtt", "opcua")),
            )
            .order_by(SourceModel.organization_id.asc(), SourceModel.source_name.asc())
        )
        return list(db.scalars(stmt).all())

    def _source_is_due(self, source: SourceModel, now: datetime) -> bool:
        last_success_at = self._as_utc(source.last_success_at)
        if self._schedule_is_disabled(source):
            return False
        scheduled_slot = self._scheduled_slot(source=source, now=now)
        if scheduled_slot is not None:
            return last_success_at is None or last_success_at < scheduled_slot
        if last_success_at is None:
            return True
        elapsed_minutes = int((now - last_success_at).total_seconds() // 60)
        return elapsed_minutes >= source.expected_frequency_minutes

    def _schedule_is_disabled(self, source: SourceModel) -> bool:
        try:
            config = json.loads(source.connector_config_json or "{}")
        except json.JSONDecodeError:
            return False
        schedule = config.get("schedule")
        return isinstance(schedule, dict) and schedule.get("enabled") is False

    def _scheduled_slot(self, source: SourceModel, now: datetime) -> datetime | None:
        """Return the current deterministic UTC slot when the source opts in.

        `expected_frequency_minutes` remains the cadence.  The optional
        `schedule.minute_utc` configuration makes a hourly source run at a
        predictable minute (for example, :05) instead of one hour after an
        arbitrary successful collection.  It also works for larger cadences.
        """
        try:
            config = json.loads(source.connector_config_json or "{}")
        except json.JSONDecodeError:
            return None
        schedule = config.get("schedule")
        if not isinstance(schedule, dict):
            return None
        minute = schedule.get("minute_utc")
        if not isinstance(minute, int) or isinstance(minute, bool) or not 0 <= minute <= 59:
            return None

        utc_now = self._as_utc(now) or datetime.now(tz=timezone.utc)
        day_anchor = utc_now.replace(hour=0, minute=minute, second=0, microsecond=0)
        cadence = timedelta(minutes=source.expected_frequency_minutes)
        elapsed_seconds = (utc_now - day_anchor).total_seconds()
        if elapsed_seconds < 0:
            return None
        slot_count = int(elapsed_seconds // cadence.total_seconds())
        return day_anchor + cadence * slot_count

    def _resolve_source_state(
        self,
        source: SourceModel,
        delay_minutes: int | None,
    ) -> str:
        last_collection_at = self._as_utc(source.last_collection_at)
        last_success_at = self._as_utc(source.last_success_at)

        if source.status != "active":
            return "suspended"

        if last_collection_at and source.last_error:
            if last_success_at is None or last_collection_at >= last_success_at:
                return "error"

        if last_success_at is None:
            return "never_run"

        if delay_minutes is None:
            return "unknown"

        if delay_minutes <= int(source.expected_frequency_minutes * 1.5):
            return "healthy"
        if delay_minutes <= int(source.expected_frequency_minutes * 3):
            return "degraded"
        return "critical"

    def _as_utc(self, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


ingestion_service = IngestionService()

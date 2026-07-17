from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.alerts.models import (
    OfficialAlertModel,
    ProtocolActivationModel,
    ProtocolTemplateModel,
)
from app.modules.alerts.schemas import (
    CoverageSummaryItem,
    OfficialAlertCreateRequest,
    ProtocolActivateRequest,
    ProtocolApprovalRequest,
    ProtocolCloseRequest,
    ProtocolTemplateCreateRequest,
    ProtocolTemplateUpdateRequest,
)
from app.modules.catalog.models import SourceModel


class AlertsService:
    def list_official_alerts(
        self,
        db: Session,
        organization_id: str,
        status: str | None,
        severity: str | None,
        source_id: str | None,
        include_expired: bool,
    ) -> list[OfficialAlertModel]:
        self.close_expired_alerts(db=db, organization_id=organization_id)

        stmt = select(OfficialAlertModel).where(
            OfficialAlertModel.organization_id == organization_id
        )
        if source_id is not None:
            stmt = stmt.where(OfficialAlertModel.source_id == source_id)
        if status is not None:
            stmt = stmt.where(OfficialAlertModel.status == status.strip().lower())
        if severity is not None:
            stmt = stmt.where(OfficialAlertModel.severity == severity.strip().lower())
        if not include_expired:
            stmt = stmt.where(OfficialAlertModel.status != "expired")
        stmt = stmt.order_by(OfficialAlertModel.valid_from_utc.desc())
        return list(db.scalars(stmt).all())

    def create_official_alert(
        self,
        db: Session,
        organization_id: str,
        payload: OfficialAlertCreateRequest,
    ) -> OfficialAlertModel:
        source = self._get_source(db=db, source_id=payload.source_id, organization_id=organization_id)
        if source is None:
            raise LookupError(f"source_id '{payload.source_id}' não encontrada.")
        if payload.valid_from_utc > payload.valid_to_utc:
            raise ValueError("valid_from_utc deve ser menor ou igual a valid_to_utc.")

        now = datetime.now(tz=timezone.utc)
        fingerprint = self._official_alert_fingerprint(payload)
        existing = db.scalar(
            select(OfficialAlertModel).where(
                OfficialAlertModel.source_id == payload.source_id,
                OfficialAlertModel.record_fingerprint == fingerprint,
            )
        )
        if existing is not None:
            return existing
        alert = OfficialAlertModel(
            organization_id=organization_id,
            source_id=payload.source_id,
            ingestion_run_id=None,
            raw_asset_id=None,
            external_alert_id=payload.external_alert_id,
            issuer=payload.issuer,
            alert_code=payload.alert_code,
            severity=payload.severity,
            status=self._resolve_alert_status(valid_to_utc=payload.valid_to_utc, now_utc=now),
            issued_at_utc=self._as_utc(payload.issued_at_utc),
            valid_from_utc=self._as_utc(payload.valid_from_utc),
            valid_to_utc=self._as_utc(payload.valid_to_utc),
            title=payload.title,
            message=payload.message,
            territory_codes_json=self._encode_territory_codes(payload.territory_codes),
            geometry_geojson=payload.geometry_geojson,
            original_payload_json=payload.original_payload_json,
            record_fingerprint=fingerprint,
            created_at=now,
            closed_at_utc=None,
            closed_reason=None,
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)
        return alert

    def close_expired_alerts(self, db: Session, organization_id: str) -> int:
        now = datetime.now(tz=timezone.utc)
        stmt = select(OfficialAlertModel).where(
            OfficialAlertModel.organization_id == organization_id,
            OfficialAlertModel.status == "active",
            OfficialAlertModel.valid_to_utc < now,
        )
        alerts = list(db.scalars(stmt).all())
        for alert in alerts:
            alert.status = "expired"
            alert.closed_at_utc = now
            alert.closed_reason = "expired_automatic"
        if alerts:
            db.commit()
        return len(alerts)

    def close_official_alert(
        self,
        db: Session,
        organization_id: str,
        official_alert_id: str,
        closure_reason: str,
    ) -> OfficialAlertModel:
        alert = db.get(OfficialAlertModel, official_alert_id)
        if alert is None:
            raise LookupError(f"official_alert_id '{official_alert_id}' não encontrado.")
        if alert.organization_id != organization_id:
            raise PermissionError("Acesso negado para este alerta.")
        if alert.status == "closed":
            raise ValueError("Alerta já está encerrado.")

        alert.status = "closed"
        alert.closed_at_utc = datetime.now(tz=timezone.utc)
        alert.closed_reason = closure_reason
        db.commit()
        db.refresh(alert)
        return alert

    def list_coverage_summary(self, db: Session, organization_id: str) -> list[CoverageSummaryItem]:
        self.close_expired_alerts(db=db, organization_id=organization_id)
        stmt = select(OfficialAlertModel).where(
            OfficialAlertModel.organization_id == organization_id,
            OfficialAlertModel.status == "active",
        )
        alerts = list(db.scalars(stmt).all())
        if not alerts:
            return []

        summary_map: dict[str, CoverageSummaryItem] = {}
        for alert in alerts:
            territories = self._decode_territory_codes(alert.territory_codes_json)
            if not territories:
                territories = ["UNSPECIFIED"]
            for code in territories:
                existing = summary_map.get(code)
                if existing is None:
                    summary_map[code] = CoverageSummaryItem(
                        territory_code=code,
                        active_alerts=1,
                        highest_severity=alert.severity,
                        latest_valid_to_utc=alert.valid_to_utc,
                    )
                    continue

                existing.active_alerts += 1
                if self._severity_rank(alert.severity) > self._severity_rank(existing.highest_severity):
                    existing.highest_severity = alert.severity
                if (
                    existing.latest_valid_to_utc is None
                    or alert.valid_to_utc > existing.latest_valid_to_utc
                ):
                    existing.latest_valid_to_utc = alert.valid_to_utc

        summary = list(summary_map.values())
        summary.sort(
            key=lambda item: (
                self._severity_rank(item.highest_severity),
                item.active_alerts,
            ),
            reverse=True,
        )
        return summary

    def list_protocol_templates(self, db: Session, organization_id: str) -> list[ProtocolTemplateModel]:
        stmt = (
            select(ProtocolTemplateModel)
            .where(ProtocolTemplateModel.organization_id == organization_id)
            .order_by(ProtocolTemplateModel.updated_at.desc())
        )
        return list(db.scalars(stmt).all())

    def create_protocol_template(
        self,
        db: Session,
        organization_id: str,
        payload: ProtocolTemplateCreateRequest,
        created_by: str,
    ) -> ProtocolTemplateModel:
        self._validate_protocol_status(payload.status)
        self._validate_json_text(payload.action_steps_json, expected_kind="list", field_name="action_steps_json")
        if payload.trigger_config_json is not None:
            self._validate_json_text(
                payload.trigger_config_json,
                expected_kind="object",
                field_name="trigger_config_json",
            )
        now = datetime.now(tz=timezone.utc)
        protocol = ProtocolTemplateModel(
            organization_id=organization_id,
            protocol_family_id=str(uuid4()),
            revision_number=1,
            supersedes_protocol_id=None,
            content_hash=self._protocol_content_hash(
                protocol_name=payload.protocol_name,
                version=payload.version,
                status=payload.status,
                trigger_type=payload.trigger_type,
                trigger_config_json=payload.trigger_config_json,
                action_steps_json=payload.action_steps_json,
                requires_authority_approval=payload.requires_authority_approval,
            ),
            created_by=created_by,
            change_reason=payload.change_reason,
            protocol_name=payload.protocol_name,
            version=payload.version,
            status=payload.status.strip().lower(),
            trigger_type=payload.trigger_type.strip().lower(),
            trigger_config_json=payload.trigger_config_json,
            action_steps_json=payload.action_steps_json,
            requires_authority_approval=payload.requires_authority_approval,
            created_at=now,
            updated_at=now,
        )
        db.add(protocol)
        db.commit()
        db.refresh(protocol)
        return protocol

    def update_protocol_template(
        self,
        db: Session,
        organization_id: str,
        protocol_id: str,
        payload: ProtocolTemplateUpdateRequest,
        created_by: str,
    ) -> ProtocolTemplateModel:
        protocol = db.get(ProtocolTemplateModel, protocol_id)
        if protocol is None:
            raise LookupError(f"protocol_id '{protocol_id}' não encontrado.")
        if protocol.organization_id != organization_id:
            raise PermissionError("Acesso negado para este protocolo.")

        values = payload.model_dump(exclude_unset=True)
        change_reason = values.pop("change_reason")
        if "status" in values and values["status"] is not None:
            self._validate_protocol_status(values["status"])
            values["status"] = values["status"].strip().lower()
        if "trigger_type" in values and values["trigger_type"] is not None:
            values["trigger_type"] = values["trigger_type"].strip().lower()
        if "action_steps_json" in values and values["action_steps_json"] is not None:
            self._validate_json_text(
                values["action_steps_json"],
                expected_kind="list",
                field_name="action_steps_json",
            )
        if "trigger_config_json" in values and values["trigger_config_json"] is not None:
            self._validate_json_text(
                values["trigger_config_json"],
                expected_kind="object",
                field_name="trigger_config_json",
            )

        now = datetime.now(tz=timezone.utc)
        next_values = {
            "protocol_name": values.get("protocol_name", protocol.protocol_name),
            "version": values.get("version", protocol.version),
            "status": values.get("status", "draft"),
            "trigger_type": values.get("trigger_type", protocol.trigger_type),
            "trigger_config_json": values.get("trigger_config_json", protocol.trigger_config_json),
            "action_steps_json": values.get("action_steps_json", protocol.action_steps_json),
            "requires_authority_approval": values.get(
                "requires_authority_approval", protocol.requires_authority_approval
            ),
        }
        protocol.status = "superseded"
        protocol.updated_at = now
        replacement = ProtocolTemplateModel(
            organization_id=organization_id,
            protocol_family_id=protocol.protocol_family_id,
            revision_number=protocol.revision_number + 1,
            supersedes_protocol_id=protocol.protocol_id,
            content_hash=self._protocol_content_hash(**next_values),
            created_by=created_by,
            change_reason=change_reason,
            created_at=now,
            updated_at=now,
            **next_values,
        )
        db.add(replacement)
        db.commit()
        db.refresh(replacement)
        return replacement

    def list_protocol_activations(
        self,
        db: Session,
        organization_id: str,
        status: str | None,
    ) -> list[ProtocolActivationModel]:
        stmt = select(ProtocolActivationModel).where(
            ProtocolActivationModel.organization_id == organization_id
        )
        if status is not None:
            stmt = stmt.where(ProtocolActivationModel.status == status.strip().lower())
        stmt = stmt.order_by(ProtocolActivationModel.started_at_utc.desc())
        return list(db.scalars(stmt).all())

    def activate_protocol(
        self,
        db: Session,
        organization_id: str,
        protocol_id: str,
        payload: ProtocolActivateRequest,
        initiated_by: str,
    ) -> ProtocolActivationModel:
        protocol = db.get(ProtocolTemplateModel, protocol_id)
        if protocol is None:
            raise LookupError(f"protocol_id '{protocol_id}' não encontrado.")
        if protocol.organization_id != organization_id:
            raise PermissionError("Acesso negado para este protocolo.")
        if protocol.status != "active":
            raise ValueError(f"Protocolo '{protocol_id}' está com status '{protocol.status}'.")

        if payload.official_alert_id is not None:
            alert = db.get(OfficialAlertModel, payload.official_alert_id)
            if alert is None:
                raise LookupError(f"official_alert_id '{payload.official_alert_id}' não encontrado.")
            if alert.organization_id != organization_id:
                raise PermissionError("Acesso negado para o alerta informado.")

        if payload.action_log_json is not None:
            self._validate_json_text(
                payload.action_log_json,
                expected_kind="list_or_object",
                field_name="action_log_json",
            )

        now = datetime.now(tz=timezone.utc)
        activation_status = "active"
        approved_by: str | None = initiated_by
        approved_at: datetime | None = now
        if protocol.requires_authority_approval or payload.severity in {"high", "critical"}:
            activation_status = "pending_approval"
            approved_by = None
            approved_at = None

        activation = ProtocolActivationModel(
            organization_id=organization_id,
            protocol_id=protocol.protocol_id,
            official_alert_id=payload.official_alert_id,
            status=activation_status,
            severity=payload.severity,
            trigger_reason=payload.trigger_reason,
            initiated_by=initiated_by,
            approved_by=approved_by,
            closed_by=None,
            started_at_utc=now,
            approved_at_utc=approved_at,
            closed_at_utc=None,
            closure_notes=None,
            action_log_json=payload.action_log_json,
        )
        db.add(activation)
        db.commit()
        db.refresh(activation)
        return activation

    def approve_protocol_activation(
        self,
        db: Session,
        organization_id: str,
        activation_id: str,
        approved_by: str,
        payload: ProtocolApprovalRequest,
    ) -> ProtocolActivationModel:
        activation = db.get(ProtocolActivationModel, activation_id)
        if activation is None:
            raise LookupError(f"activation_id '{activation_id}' não encontrado.")
        if activation.organization_id != organization_id:
            raise PermissionError("Acesso negado para esta ativação.")
        if activation.status != "pending_approval":
            raise ValueError("Apenas ativações pendentes podem ser aprovadas.")
        if activation.initiated_by.strip().lower() == approved_by.strip().lower():
            raise PermissionError(
                "A autoridade aprovadora não pode aprovar uma ativação iniciada por ela mesma."
            )

        if payload.action_log_json is not None:
            self._validate_json_text(
                payload.action_log_json,
                expected_kind="list_or_object",
                field_name="action_log_json",
            )
            activation.action_log_json = payload.action_log_json

        activation.status = "active"
        activation.approved_by = approved_by
        activation.approved_at_utc = datetime.now(tz=timezone.utc)
        db.commit()
        db.refresh(activation)
        return activation

    def close_protocol_activation(
        self,
        db: Session,
        organization_id: str,
        activation_id: str,
        closed_by: str,
        payload: ProtocolCloseRequest,
    ) -> ProtocolActivationModel:
        activation = db.get(ProtocolActivationModel, activation_id)
        if activation is None:
            raise LookupError(f"activation_id '{activation_id}' não encontrado.")
        if activation.organization_id != organization_id:
            raise PermissionError("Acesso negado para esta ativação.")
        if activation.status in {"closed", "cancelled"}:
            raise ValueError("Ativação já encerrada.")

        if payload.action_log_json is not None:
            self._validate_json_text(
                payload.action_log_json,
                expected_kind="list_or_object",
                field_name="action_log_json",
            )
            activation.action_log_json = payload.action_log_json

        activation.status = "closed"
        activation.closed_by = closed_by
        activation.closed_at_utc = datetime.now(tz=timezone.utc)
        activation.closure_notes = payload.closure_notes
        db.commit()
        db.refresh(activation)
        return activation

    def _get_source(self, db: Session, source_id: str, organization_id: str) -> SourceModel | None:
        stmt = select(SourceModel).where(
            SourceModel.source_id == source_id,
            SourceModel.organization_id == organization_id,
        )
        return db.scalar(stmt)

    def _resolve_alert_status(self, valid_to_utc: datetime, now_utc: datetime) -> str:
        if self._as_utc(valid_to_utc) < now_utc:
            return "expired"
        return "active"

    def _severity_rank(self, severity: str) -> int:
        ranks = {"low": 1, "medium": 2, "high": 3, "critical": 4}
        return ranks.get(severity, 0)

    def _encode_territory_codes(self, territory_codes: list[str] | None) -> str | None:
        if territory_codes is None:
            return None
        cleaned = [item.strip() for item in territory_codes if item.strip() != ""]
        return json.dumps(cleaned, ensure_ascii=True)

    def _decode_territory_codes(self, territory_codes_json: str | None) -> list[str]:
        if territory_codes_json is None:
            return []
        parsed = json.loads(territory_codes_json)
        if not isinstance(parsed, list):
            raise ValueError("territory_codes_json inválido: deve ser lista JSON.")
        result: list[str] = []
        for item in parsed:
            text = str(item).strip()
            if text != "":
                result.append(text)
        return result

    def _validate_protocol_status(self, value: str) -> None:
        normalized = value.strip().lower()
        allowed = {"draft", "active", "inactive"}
        if normalized not in allowed:
            allowed_values = ", ".join(sorted(allowed))
            raise ValueError(f"status de protocolo inválido '{value}'. Permitidos: {allowed_values}.")

    def _protocol_content_hash(
        self,
        *,
        protocol_name: str,
        version: str,
        status: str,
        trigger_type: str,
        trigger_config_json: str | None,
        action_steps_json: str,
        requires_authority_approval: bool,
    ) -> str:
        canonical = json.dumps(
            {
                "protocol_name": protocol_name.strip(),
                "version": version.strip(),
                "status": status.strip().lower(),
                "trigger_type": trigger_type.strip().lower(),
                "trigger_config_json": trigger_config_json,
                "action_steps_json": action_steps_json,
                "requires_authority_approval": requires_authority_approval,
            },
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _official_alert_fingerprint(self, payload: OfficialAlertCreateRequest) -> str:
        canonical = json.dumps(
            {
                "external_alert_id": payload.external_alert_id,
                "issuer": payload.issuer.strip(),
                "alert_code": payload.alert_code.strip(),
                "issued_at_utc": self._as_utc(payload.issued_at_utc).isoformat(),
                "valid_from_utc": self._as_utc(payload.valid_from_utc).isoformat(),
                "valid_to_utc": self._as_utc(payload.valid_to_utc).isoformat(),
                "title": payload.title.strip(),
                "message": payload.message.strip(),
                "territory_codes": sorted(payload.territory_codes or []),
                "geometry_geojson": payload.geometry_geojson,
            },
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _validate_json_text(self, value: str, expected_kind: str, field_name: str) -> None:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{field_name} deve ser JSON válido.") from exc

        if expected_kind == "object" and not isinstance(parsed, dict):
            raise ValueError(f"{field_name} deve conter objeto JSON.")
        if expected_kind == "list" and not isinstance(parsed, list):
            raise ValueError(f"{field_name} deve conter lista JSON.")
        if expected_kind == "list_or_object" and not isinstance(parsed, (list, dict)):
            raise ValueError(f"{field_name} deve conter lista ou objeto JSON.")

    def _as_utc(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


alerts_service = AlertsService()

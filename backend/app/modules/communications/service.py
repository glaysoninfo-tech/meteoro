from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.alerts.models import OfficialAlertModel
from app.modules.communications.models import (
    BulletinDeliveryModel,
    BulletinDispatchModel,
    CommunicationRecipientModel,
)
from app.modules.communications.schemas import (
    ALLOWED_CONSENT_STATUS,
    ALLOWED_DISPATCH_STATUS,
    ALLOWED_CHANNEL_TYPES,
    BulletinDispatchCreateRequest,
    CommunicationRecipientConsentUpdateRequest,
    CommunicationRecipientCreateRequest,
    DailyBulletinGenerateRequest,
)
from app.modules.planning.service import planning_service


@dataclass(slots=True)
class DispatchExecution:
    dispatch: BulletinDispatchModel
    sent_count: int
    skipped_count: int
    failed_count: int


@dataclass(slots=True)
class DailyBulletinExecution:
    execution: DispatchExecution
    period_start_utc: datetime
    period_end_utc: datetime
    executive_summary: str
    active_official_alerts: int


class CommunicationsService:
    def list_recipients(
        self,
        db: Session,
        organization_id: str,
        channel_type: str | None,
        consent_status: str | None,
        include_inactive: bool,
    ) -> list[CommunicationRecipientModel]:
        stmt = select(CommunicationRecipientModel).where(
            CommunicationRecipientModel.organization_id == organization_id
        )
        if not include_inactive:
            stmt = stmt.where(CommunicationRecipientModel.is_active.is_(True))
        if channel_type is not None:
            normalized_channel = channel_type.strip().lower()
            if normalized_channel not in ALLOWED_CHANNEL_TYPES:
                allowed_values = ", ".join(sorted(ALLOWED_CHANNEL_TYPES))
                raise ValueError(
                    f"channel_type inválido '{channel_type}'. Permitidos: {allowed_values}."
                )
            stmt = stmt.where(CommunicationRecipientModel.channel_type == normalized_channel)
        if consent_status is not None:
            normalized_consent = consent_status.strip().lower()
            if normalized_consent not in ALLOWED_CONSENT_STATUS:
                allowed_values = ", ".join(sorted(ALLOWED_CONSENT_STATUS))
                raise ValueError(
                    f"consent_status inválido '{consent_status}'. Permitidos: {allowed_values}."
                )
            stmt = stmt.where(CommunicationRecipientModel.consent_status == normalized_consent)

        stmt = stmt.order_by(
            CommunicationRecipientModel.is_active.desc(),
            CommunicationRecipientModel.updated_at.desc(),
        )
        return list(db.scalars(stmt).all())

    def create_recipient(
        self,
        db: Session,
        organization_id: str,
        payload: CommunicationRecipientCreateRequest,
    ) -> CommunicationRecipientModel:
        now = datetime.now(tz=timezone.utc)
        destination = self._normalize_destination(
            channel_type=payload.channel_type,
            destination=payload.destination,
        )
        recipient = CommunicationRecipientModel(
            organization_id=organization_id,
            full_name=payload.full_name.strip(),
            channel_type=payload.channel_type,
            destination=destination,
            consent_status=payload.consent_status,
            consent_reason=payload.consent_reason,
            consent_updated_at=now,
            is_active=True,
            tags_json=payload.tags_json,
            created_at=now,
            updated_at=now,
        )
        db.add(recipient)
        db.commit()
        db.refresh(recipient)
        return recipient

    def update_recipient_consent(
        self,
        db: Session,
        organization_id: str,
        recipient_id: str,
        payload: CommunicationRecipientConsentUpdateRequest,
    ) -> CommunicationRecipientModel:
        recipient = db.get(CommunicationRecipientModel, recipient_id)
        if recipient is None:
            raise LookupError(f"recipient_id '{recipient_id}' não encontrado.")
        if recipient.organization_id != organization_id:
            raise PermissionError("Acesso negado para este destinatário.")

        now = datetime.now(tz=timezone.utc)
        recipient.consent_status = payload.consent_status
        recipient.consent_reason = payload.consent_reason
        recipient.consent_updated_at = now
        recipient.updated_at = now
        db.commit()
        db.refresh(recipient)
        return recipient

    def list_dispatches(
        self,
        db: Session,
        organization_id: str,
        status: str | None,
        bulletin_type: str | None,
        limit: int,
    ) -> list[BulletinDispatchModel]:
        stmt = select(BulletinDispatchModel).where(
            BulletinDispatchModel.organization_id == organization_id
        )
        if status is not None:
            normalized_status = status.strip().lower()
            if normalized_status not in ALLOWED_DISPATCH_STATUS:
                allowed_values = ", ".join(sorted(ALLOWED_DISPATCH_STATUS))
                raise ValueError(f"status inválido '{status}'. Permitidos: {allowed_values}.")
            stmt = stmt.where(BulletinDispatchModel.status == normalized_status)
        if bulletin_type is not None:
            stmt = stmt.where(BulletinDispatchModel.bulletin_type == bulletin_type.strip().lower())
        stmt = stmt.order_by(BulletinDispatchModel.created_at.desc()).limit(limit)
        return list(db.scalars(stmt).all())

    def list_dispatch_deliveries(
        self,
        db: Session,
        organization_id: str,
        dispatch_id: str,
    ) -> list[BulletinDeliveryModel]:
        dispatch = db.get(BulletinDispatchModel, dispatch_id)
        if dispatch is None:
            raise LookupError(f"dispatch_id '{dispatch_id}' não encontrado.")
        if dispatch.organization_id != organization_id:
            raise PermissionError("Acesso negado para este despacho.")

        stmt = (
            select(BulletinDeliveryModel)
            .where(BulletinDeliveryModel.dispatch_id == dispatch_id)
            .order_by(BulletinDeliveryModel.attempted_at_utc.desc())
        )
        return list(db.scalars(stmt).all())

    def create_dispatch(
        self,
        db: Session,
        organization_id: str,
        requested_by: str,
        payload: BulletinDispatchCreateRequest,
    ) -> DispatchExecution:
        dispatch = self._create_dispatch_record(
            db=db,
            organization_id=organization_id,
            bulletin_type=payload.bulletin_type,
            title=payload.title,
            content_text=payload.content_text,
            requested_by=requested_by,
            channel_scope=payload.channel_scope,
            report_snapshot=None,
        )
        if payload.send_immediately:
            return self.send_dispatch(
                db=db,
                organization_id=organization_id,
                dispatch_id=dispatch.dispatch_id,
            )
        return DispatchExecution(
            dispatch=dispatch,
            sent_count=0,
            skipped_count=0,
            failed_count=0,
        )

    def generate_daily_bulletin(
        self,
        db: Session,
        organization_id: str,
        requested_by: str,
        payload: DailyBulletinGenerateRequest,
    ) -> DailyBulletinExecution:
        period_end_utc = datetime.now(tz=timezone.utc)
        period_start_utc = period_end_utc - timedelta(hours=payload.period_hours)

        report = planning_service.generate_committee_climate_report(
            db=db,
            organization_id=organization_id,
            period_start_utc=period_start_utc,
            period_end_utc=period_end_utc,
            source_ids=None,
            max_alerts=payload.max_alerts,
        )
        active_alerts = list(
            db.scalars(
                select(OfficialAlertModel)
                .where(
                    OfficialAlertModel.organization_id == organization_id,
                    OfficialAlertModel.status == "active",
                )
                .order_by(OfficialAlertModel.valid_to_utc.asc())
                .limit(payload.max_alerts)
            ).all()
        )
        title, content = self._build_daily_bulletin_text(
            title_override=payload.title,
            report_executive_summary=report.executive_summary,
            active_alerts=active_alerts,
        )
        snapshot = {
            "period_start_utc": period_start_utc.isoformat(),
            "period_end_utc": period_end_utc.isoformat(),
            "observations_considered": report.observations_considered,
            "source_scope": report.source_scope,
            "active_official_alerts": len(active_alerts),
        }
        dispatch = self._create_dispatch_record(
            db=db,
            organization_id=organization_id,
            bulletin_type="daily_operational",
            title=title,
            content_text=content,
            requested_by=requested_by,
            channel_scope=payload.channel_scope,
            report_snapshot=snapshot,
        )
        if payload.send_immediately:
            execution = self.send_dispatch(
                db=db,
                organization_id=organization_id,
                dispatch_id=dispatch.dispatch_id,
            )
        else:
            execution = DispatchExecution(
                dispatch=dispatch,
                sent_count=0,
                skipped_count=0,
                failed_count=0,
            )
        return DailyBulletinExecution(
            execution=execution,
            period_start_utc=period_start_utc,
            period_end_utc=period_end_utc,
            executive_summary=report.executive_summary,
            active_official_alerts=len(active_alerts),
        )

    def send_dispatch(
        self,
        db: Session,
        organization_id: str,
        dispatch_id: str,
    ) -> DispatchExecution:
        dispatch = db.get(BulletinDispatchModel, dispatch_id)
        if dispatch is None:
            raise LookupError(f"dispatch_id '{dispatch_id}' não encontrado.")
        if dispatch.organization_id != organization_id:
            raise PermissionError("Acesso negado para este despacho.")
        if dispatch.status != "draft":
            raise ValueError("Somente despachos em status 'draft' podem ser enviados.")

        recipients = list(
            db.scalars(
                select(CommunicationRecipientModel).where(
                    CommunicationRecipientModel.organization_id == organization_id,
                    CommunicationRecipientModel.is_active.is_(True),
                )
            ).all()
        )
        if not recipients:
            raise ValueError("Nenhum destinatário ativo cadastrado para envio.")

        channel_scope = self._decode_channel_scope(dispatch.channel_scope_json)
        if channel_scope is not None:
            recipients = [item for item in recipients if item.channel_type in channel_scope]
        if not recipients:
            raise ValueError("Nenhum destinatário corresponde ao channel_scope configurado.")

        attempted_at = datetime.now(tz=timezone.utc)
        sent_count = 0
        skipped_count = 0
        failed_count = 0
        for recipient in recipients:
            if recipient.consent_status != "opt_in":
                delivery_status = "skipped_opt_out"
                detail = f"consent_status={recipient.consent_status}"
                delivered_at = None
                skipped_count += 1
            else:
                delivery_status = "sent"
                detail = "simulated_delivery"
                delivered_at = attempted_at
                sent_count += 1

            db.add(
                BulletinDeliveryModel(
                    organization_id=organization_id,
                    dispatch_id=dispatch.dispatch_id,
                    recipient_id=recipient.recipient_id,
                    channel_type=recipient.channel_type,
                    destination=recipient.destination,
                    delivery_status=delivery_status,
                    detail=detail,
                    attempted_at_utc=attempted_at,
                    delivered_at_utc=delivered_at,
                )
            )

        dispatch.status = self._resolve_dispatch_status(
            sent_count=sent_count,
            skipped_count=skipped_count,
        )
        dispatch.sent_at_utc = attempted_at if sent_count > 0 else None
        db.commit()
        db.refresh(dispatch)
        return DispatchExecution(
            dispatch=dispatch,
            sent_count=sent_count,
            skipped_count=skipped_count,
            failed_count=failed_count,
        )

    def _create_dispatch_record(
        self,
        db: Session,
        organization_id: str,
        bulletin_type: str,
        title: str,
        content_text: str,
        requested_by: str,
        channel_scope: list[str] | None,
        report_snapshot: dict[str, object] | None,
    ) -> BulletinDispatchModel:
        created_at = datetime.now(tz=timezone.utc)
        dispatch = BulletinDispatchModel(
            organization_id=organization_id,
            bulletin_type=bulletin_type.strip().lower(),
            status="draft",
            title=title.strip(),
            content_text=content_text.strip(),
            requested_by=requested_by,
            channel_scope_json=self._encode_channel_scope(channel_scope=channel_scope),
            report_snapshot_json=(
                json.dumps(report_snapshot, ensure_ascii=True) if report_snapshot is not None else None
            ),
            created_at=created_at,
            sent_at_utc=None,
        )
        db.add(dispatch)
        db.commit()
        db.refresh(dispatch)
        return dispatch

    def _build_daily_bulletin_text(
        self,
        title_override: str | None,
        report_executive_summary: str,
        active_alerts: list[OfficialAlertModel],
    ) -> tuple[str, str]:
        issued_at = datetime.now(tz=timezone.utc)
        title = title_override
        if title is None:
            title = f"Boletim operacional {issued_at.strftime('%Y-%m-%d %H:%M UTC')}"

        critical_or_high = sum(1 for alert in active_alerts if alert.severity in {"high", "critical"})
        lines = [
            f"{title}",
            "",
            f"Resumo executivo: {report_executive_summary}",
            f"Alertas oficiais ativos: {len(active_alerts)} (alto/critico: {critical_or_high}).",
        ]
        if active_alerts:
            lines.append("Alertas ativos prioritários:")
            for alert in active_alerts[:5]:
                lines.append(
                    f"- [{alert.severity}] {alert.title} (validade até {alert.valid_to_utc.isoformat()})"
                )
        return title, "\n".join(lines)

    def _normalize_destination(self, channel_type: str, destination: str) -> str:
        cleaned = destination.strip()
        if cleaned == "":
            raise ValueError("destination não pode ser vazio.")

        if channel_type == "email":
            lowered = cleaned.lower()
            if "@" not in lowered or lowered.startswith("@") or lowered.endswith("@"):
                raise ValueError("destination inválido para canal email.")
            local, domain = lowered.split("@", 1)
            if "." not in domain or local.strip() == "":
                raise ValueError("destination inválido para canal email.")
            return lowered

        if channel_type == "webhook":
            lowered = cleaned.lower()
            if not (lowered.startswith("https://") or lowered.startswith("http://")):
                raise ValueError("destination de webhook deve iniciar com http:// ou https://.")
            return cleaned

        if channel_type in {"sms", "whatsapp"}:
            compact = (
                cleaned.replace(" ", "")
                .replace("-", "")
                .replace("(", "")
                .replace(")", "")
            )
            if compact.startswith("+"):
                digits = compact[1:]
                prefix = "+"
            else:
                digits = compact
                prefix = ""
            if not digits.isdigit() or len(digits) < 8 or len(digits) > 20:
                raise ValueError(f"destination inválido para canal {channel_type}.")
            return f"{prefix}{digits}"

        raise ValueError(f"channel_type '{channel_type}' não suportado.")

    def _encode_channel_scope(self, channel_scope: list[str] | None) -> str | None:
        if channel_scope is None:
            return None
        return json.dumps(channel_scope, ensure_ascii=True)

    def _decode_channel_scope(self, channel_scope_json: str | None) -> set[str] | None:
        if channel_scope_json is None:
            return None
        parsed = json.loads(channel_scope_json)
        if not isinstance(parsed, list):
            raise ValueError("channel_scope_json inválido no despacho.")
        result: set[str] = set()
        for item in parsed:
            channel = str(item).strip().lower()
            if channel not in ALLOWED_CHANNEL_TYPES:
                raise ValueError(f"channel_scope contém canal inválido '{channel}'.")
            result.add(channel)
        return result

    def _resolve_dispatch_status(self, sent_count: int, skipped_count: int) -> str:
        if sent_count > 0 and skipped_count == 0:
            return "sent"
        if sent_count > 0 and skipped_count > 0:
            return "partial"
        return "cancelled"


communications_service = CommunicationsService()

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MitigationActionModel(Base):
    """Ação estruturante de mitigação/adaptação climática do município."""

    __tablename__ = "mitigation_actions"

    action_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.organization_id"), nullable=False
    )
    risk_theme: Mapped[str] = mapped_column(String(40), nullable=False)
    territory: Mapped[str] = mapped_column(String(160), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    responsible_role: Mapped[str] = mapped_column(String(160), nullable=False)
    action_type: Mapped[str] = mapped_column(String(20), nullable=False, default="mitigacao")
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="media")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="planejada")
    progress_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deadline_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    estimated_cost_brl: Mapped[float | None] = mapped_column(Float, nullable=True)
    indicator: Mapped[str | None] = mapped_column(String(300), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CabinetDecisionModel(Base):
    __tablename__ = "cabinet_decisions"

    decision_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.organization_id"), nullable=False
    )
    risk_key: Mapped[str] = mapped_column(String(240), nullable=False)
    territory: Mapped[str] = mapped_column(String(160), nullable=False)
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    responsible_action: Mapped[str] = mapped_column(String(500), nullable=False)
    responsible_role: Mapped[str] = mapped_column(String(160), nullable=False)
    deadline_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

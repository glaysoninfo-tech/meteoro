"""Populate the local demonstration database with strictly fictional data.

The script is intentionally idempotent and must never be used against a
production database. It lets a reviewer see public, operational and Cabinet
views without configuring a third-party connector.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from app.db.session import SessionLocal
from app.modules.alerts.models import OfficialAlertModel, ProtocolActivationModel, ProtocolTemplateModel
from app.modules.alerts.schemas import (
    OfficialAlertCreateRequest,
    ProtocolActivateRequest,
    ProtocolTemplateCreateRequest,
)
from app.modules.alerts.service import alerts_service
from app.modules.audit.service import audit_service
from app.modules.catalog.models import SourceModel
from app.modules.catalog.schemas import SourceCreate
from app.modules.catalog.service import catalog_service
from app.modules.geospatial.models import SensorModel, StationModel, TerritoryModel
from app.modules.geospatial.schemas import SensorCreate, StationCreate, TerritoryCreate
from app.modules.geospatial.service import geospatial_service
from app.modules.identity.models import UserModel
from app.modules.identity.schemas import BootstrapAdminRequest
from app.modules.identity.service import identity_service
from app.modules.incidents.models import IncidentReportModel
from app.modules.ingestion.models import IngestionRunModel, RawAssetModel
from app.modules.ingestion.service import ingestion_service
from app.modules.recommendations.models import RecommendationRevisionModel
from app.modules.recommendations.schemas import RecommendationCreate
from app.modules.recommendations.service import recommendation_service

DEMO_EMAIL = "admin@example.org"
DEMO_PASSWORD = "senha-forte-123"


def _first_or_create(db, statement, factory):
    existing = db.scalar(statement)
    return existing if existing is not None else factory()


def main() -> None:
    db = SessionLocal()
    try:
        admin = db.scalar(select(UserModel).where(UserModel.email == DEMO_EMAIL))
        if admin is None:
            admin = identity_service.bootstrap_admin(
                db,
                BootstrapAdminRequest(
                    name="Administrador da demonstração",
                    email=DEMO_EMAIL,
                    password=DEMO_PASSWORD,
                    organization_name="Prefeitura Demonstrativa de Meteoro",
                ),
            )
        organization_id = admin.organization_id

        territory = _first_or_create(
            db,
            select(TerritoryModel).where(
                TerritoryModel.organization_id == organization_id,
                TerritoryModel.territory_code == "CENTRO",
            ),
            lambda: geospatial_service.create_territory(
                db,
                organization_id,
                TerritoryCreate(
                    territory_code="CENTRO",
                    territory_name="Centro (demonstração)",
                    territory_type="bairro",
                    # Retângulo demonstrativo sobre a região central de Betim/MG.
                    geometry_geojson={
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [-44.225, -19.995],
                                [-44.170, -19.995],
                                [-44.170, -19.945],
                                [-44.225, -19.945],
                                [-44.225, -19.995],
                            ]
                        ],
                    },
                ),
            ),
        )
        station = _first_or_create(
            db,
            select(StationModel).where(
                StationModel.organization_id == organization_id,
                StationModel.station_code == "EST-CENTRO-01",
            ),
            lambda: geospatial_service.create_station(
                db,
                organization_id,
                StationCreate(
                    territory_id=territory.territory_id,
                    station_code="EST-CENTRO-01",
                    station_name="Estação Centro 01 (demonstração)",
                    station_type="meteorologica",
                    location_geojson={"type": "Point", "coordinates": [-44.198, -19.968]},
                    elevation_meters=831,
                    installed_on=date.today(),
                ),
            ),
        )
        sensor = _first_or_create(
            db,
            select(SensorModel).where(
                SensorModel.organization_id == organization_id,
                SensorModel.sensor_code == "SEN-TEMP-01",
            ),
            lambda: geospatial_service.create_sensor(
                db,
                organization_id,
                SensorCreate(
                    station_id=station.station_id,
                    sensor_code="SEN-TEMP-01",
                    sensor_name="Termômetro da estação Centro",
                    variable_code="temperature_c",
                    unit_canonical="c",
                ),
            ),
        )
        source = _first_or_create(
            db,
            select(SourceModel).where(
                SourceModel.organization_id == organization_id,
                SourceModel.source_name == "Leituras da estação Centro (demonstração)",
            ),
            lambda: catalog_service.create_source(
                db,
                SourceCreate(
                    institution_name="Prefeitura Demonstrativa",
                    source_name="Leituras da estação Centro (demonstração)",
                    source_type="meteorologia",
                    station_id=station.station_id,
                    sensor_id=sensor.sensor_id,
                    access_method="manual_file",
                    authentication_type="none",
                    endpoint_reference="manual://demo/centro-observacoes.json",
                    expected_frequency_minutes=15,
                    criticality="high",
                ),
                organization_id,
            ),
        )

        raw_asset = db.scalar(
            select(RawAssetModel)
            .where(RawAssetModel.source_id == source.source_id)
            .order_by(RawAssetModel.collected_at.desc())
        )
        if raw_asset is None:
            collected_at = datetime.now(tz=timezone.utc)
            readings = [
                {
                    "observed_at": (collected_at - timedelta(minutes=30)).isoformat(),
                    "location": "CENTRO",
                    "temperature": 36.8,
                    "temperature_unit": "c",
                },
                {
                    "observed_at": (collected_at - timedelta(minutes=15)).isoformat(),
                    "location": "CENTRO",
                    "rainfall": 68.0,
                    "rainfall_unit": "mm",
                },
                {
                    "observed_at": collected_at.isoformat(),
                    "location": "CENTRO",
                    "humidity": 2.0,
                    "humidity_unit": "%",
                },
            ]
            ingestion_service.import_uploaded_file(
                db,
                organization_id,
                source.source_id,
                "leituras-centro-demo.json",
                "application/json",
                json.dumps(readings).encode("utf-8"),
            )
            raw_asset = db.scalar(
                select(RawAssetModel)
                .where(RawAssetModel.source_id == source.source_id)
                .order_by(RawAssetModel.collected_at.desc())
            )

        now = datetime.now(tz=timezone.utc)
        alert = _first_or_create(
            db,
            select(OfficialAlertModel).where(
                OfficialAlertModel.organization_id == organization_id,
                OfficialAlertModel.alert_code == "DEMO-CALOR-01",
            ),
            lambda: alerts_service.create_official_alert(
                db,
                organization_id,
                OfficialAlertCreateRequest(
                    source_id=source.source_id,
                    external_alert_id="demo-calor-01",
                    issuer="Defesa Civil Demonstrativa",
                    alert_code="DEMO-CALOR-01",
                    severity="high",
                    issued_at_utc=now,
                    valid_from_utc=now,
                    valid_to_utc=now + timedelta(hours=12),
                    title="Calor intenso no Centro",
                    message="Cenário demonstrativo: risco de estresse térmico, com atenção prioritária a pessoas vulneráveis.",
                    territory_codes=["CENTRO"],
                    geometry_geojson=territory.geometry_geojson,
                    original_payload_json=json.dumps({"demo": True, "source": "seed_demo"}),
                ),
            ),
        )
        if alert.raw_asset_id is None and raw_asset is not None:
            alert.raw_asset_id = raw_asset.raw_asset_id
            db.commit()

        protocol = _first_or_create(
            db,
            select(ProtocolTemplateModel).where(
                ProtocolTemplateModel.organization_id == organization_id,
                ProtocolTemplateModel.protocol_name == "Resposta a calor intenso (demonstração)",
                ProtocolTemplateModel.status == "active",
            ),
            lambda: alerts_service.create_protocol_template(
                db,
                organization_id,
                ProtocolTemplateCreateRequest(
                    protocol_name="Resposta a calor intenso (demonstração)",
                    version="1.0-demo",
                    status="active",
                    trigger_type="official_alert",
                    trigger_config_json=json.dumps({"severity": ["high", "critical"]}),
                    action_steps_json=json.dumps(
                        [
                            {"step": "Acionar vigilância em saúde"},
                            {"step": "Publicar recomendações de hidratação"},
                        ]
                    ),
                    requires_authority_approval=True,
                    change_reason="Criação da demonstração local",
                ),
                admin.email,
            ),
        )
        pending_activation = db.scalar(
            select(ProtocolActivationModel).where(
                ProtocolActivationModel.organization_id == organization_id,
                ProtocolActivationModel.official_alert_id == alert.official_alert_id,
                ProtocolActivationModel.status == "pending_approval",
            )
        )
        if pending_activation is None:
            alerts_service.activate_protocol(
                db,
                organization_id,
                protocol.protocol_id,
                ProtocolActivateRequest(
                    official_alert_id=alert.official_alert_id,
                    severity="high",
                    trigger_reason="Demonstração de decisão pendente",
                ),
                admin.email,
            )

        recommendation = db.scalar(
            select(RecommendationRevisionModel).where(
                RecommendationRevisionModel.organization_id == organization_id,
                RecommendationRevisionModel.title == "Cuidados durante calor intenso",
                RecommendationRevisionModel.status == "active",
            )
        )
        if recommendation is None:
            recommendation_service.create(
                db,
                organization_id,
                RecommendationCreate(
                    title="Cuidados durante calor intenso",
                    audience="populacao",
                    criteria={"alert_severity": ["high", "critical"]},
                    content={
                        "summary": "Hidrate-se, evite exposição prolongada ao sol e procure a rede de saúde diante de mal-estar.",
                        "actions": [
                            "Beber água regularmente",
                            "Priorizar locais ventilados",
                            "Acompanhar alertas oficiais",
                        ],
                    },
                    status="active",
                    change_reason="Conteúdo da demonstração local",
                ),
                admin.email,
            )

        incident = db.scalar(
            select(IncidentReportModel).where(
                IncidentReportModel.organization_id == organization_id,
                IncidentReportModel.external_protocol == "DEMO-INC-01",
            )
        )
        if incident is None and raw_asset is not None:
            run = db.get(IngestionRunModel, raw_asset.ingestion_run_id)
            if run is None:
                raise RuntimeError("Ativo bruto da demonstração sem execução de ingestão.")
            db.add(
                IncidentReportModel(
                    organization_id=organization_id,
                    source_id=source.source_id,
                    ingestion_run_id=run.ingestion_run_id,
                    raw_asset_id=raw_asset.raw_asset_id,
                    reported_at_utc=now,
                    report_origin="citizen",
                    category_code="heat_exposure",
                    severity="medium",
                    description="Ocorrência demonstrativa para triagem operacional.",
                    location_code="CENTRO",
                    address_text=None,
                    reporter_name=None,
                    reporter_contact=None,
                    external_protocol="DEMO-INC-01",
                    triage_status="pending",
                    triaged_by=None,
                    triage_notes=None,
                    record_fingerprint=hashlib.sha256(b"demo-incident-centro-01").hexdigest(),
                    created_at=now,
                )
            )
            db.commit()

        audit_service.create_event(
            db,
            module="alerts",
            action="demo.portal_ready",
            actor=admin.email,
            organization_id=organization_id,
            resource_type="demo",
            resource_id="portal-local",
            reason="Dados fictícios para visualização local",
        )
        print(f"DEMO_ORGANIZATION_ID={organization_id}")
        print(f"DEMO_LOGIN={DEMO_EMAIL}")
        print(f"DEMO_PASSWORD={DEMO_PASSWORD}")
    finally:
        db.close()


if __name__ == "__main__":
    main()

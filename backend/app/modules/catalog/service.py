from datetime import datetime, timezone
import json
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.network_security import validate_connector_endpoint
from app.modules.catalog.models import SourceModel
from app.modules.catalog.regional_context import (
    ana_hidroweb_profiles,
    betim_open_meteo_profiles,
    redemet_aviation_profiles,
    redemet_imagery_profiles,
    regional_context_profiles,
)
from app.modules.catalog.schemas import SourceCreate, SourceUpdate
from app.modules.geospatial.models import SensorModel, StationModel


class CatalogService:
    def list_sources(self, db: Session, organization_id: str) -> list[SourceModel]:
        stmt = (
            select(SourceModel)
            .where(SourceModel.organization_id == organization_id)
            .order_by(SourceModel.created_at.desc())
        )
        return list(db.scalars(stmt).all())

    def create_source(
        self,
        db: Session,
        payload: SourceCreate,
        organization_id: str,
    ) -> SourceModel:
        self._validate_source_configuration(
            access_method=payload.access_method,
            authentication_type=payload.authentication_type,
            endpoint_reference=payload.endpoint_reference,
            connector_config_json=payload.connector_config_json,
        )
        self._validate_station_ownership(
            db=db,
            organization_id=organization_id,
            station_id=payload.station_id,
        )
        self._validate_sensor_ownership(
            db=db,
            organization_id=organization_id,
            station_id=payload.station_id,
            sensor_id=payload.sensor_id,
        )
        source = SourceModel(
            organization_id=organization_id,
            station_id=payload.station_id,
            sensor_id=payload.sensor_id,
            institution_name=payload.institution_name,
            source_name=payload.source_name,
            source_type=payload.source_type,
            access_method=payload.access_method,
            authentication_type=payload.authentication_type,
            endpoint_reference=payload.endpoint_reference,
            connector_config_json=payload.connector_config_json,
            status=payload.status,
            expected_frequency_minutes=payload.expected_frequency_minutes,
            criticality=payload.criticality,
            created_at=datetime.now(tz=timezone.utc),
        )
        db.add(source)
        db.commit()
        db.refresh(source)
        return source

    def install_regional_context_profiles(
        self,
        db: Session,
        organization_id: str,
    ) -> list[SourceModel]:
        """Install the regional model points once, without duplicating records."""
        return self._install_profiles(
            db=db,
            organization_id=organization_id,
            profiles=regional_context_profiles(),
        )

    def install_betim_open_meteo_profiles(
        self,
        db: Session,
        organization_id: str,
    ) -> list[SourceModel]:
        return self._install_profiles(
            db=db,
            organization_id=organization_id,
            profiles=betim_open_meteo_profiles(),
        )

    def install_redemet_aviation_profiles(
        self,
        db: Session,
        organization_id: str,
    ) -> list[SourceModel]:
        return self._install_profiles(
            db=db,
            organization_id=organization_id,
            profiles=redemet_aviation_profiles(),
        )

    def install_redemet_imagery_profiles(
        self,
        db: Session,
        organization_id: str,
    ) -> list[SourceModel]:
        return self._install_profiles(
            db=db,
            organization_id=organization_id,
            profiles=redemet_imagery_profiles(),
        )

    def install_ana_hidroweb_profiles(
        self,
        db: Session,
        organization_id: str,
        station_codes: list[str],
    ) -> list[SourceModel]:
        return self._install_profiles(
            db=db,
            organization_id=organization_id,
            profiles=ana_hidroweb_profiles(station_codes),
        )

    def _install_profiles(
        self,
        db: Session,
        organization_id: str,
        profiles: list[SourceCreate],
    ) -> list[SourceModel]:
        """Install named source profiles once, returning existing records when present."""
        names = [profile.source_name for profile in profiles]
        existing = {
            source.source_name: source
            for source in db.scalars(
                select(SourceModel).where(
                    SourceModel.organization_id == organization_id,
                    SourceModel.source_name.in_(names),
                )
            ).all()
        }
        installed: list[SourceModel] = []
        for profile in profiles:
            source = existing.get(profile.source_name)
            if source is None:
                source = self.create_source(
                    db=db,
                    payload=profile,
                    organization_id=organization_id,
                )
            installed.append(source)
        return installed

    def get_source(
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

    def update_source(
        self,
        db: Session,
        source_id: str,
        organization_id: str,
        payload: SourceUpdate,
    ) -> SourceModel:
        source = self.get_source(db=db, source_id=source_id, organization_id=organization_id)
        if source is None:
            raise LookupError(f"Fonte '{source_id}' não encontrada.")

        values = payload.model_dump(exclude_unset=True)
        access_method = values.get("access_method", source.access_method)
        authentication_type = values.get("authentication_type", source.authentication_type)
        connector_config_json = values.get("connector_config_json", source.connector_config_json)
        endpoint_reference = values.get("endpoint_reference", source.endpoint_reference)
        self._validate_source_configuration(
            access_method=access_method,
            authentication_type=authentication_type,
            endpoint_reference=endpoint_reference,
            connector_config_json=connector_config_json,
        )
        self._validate_station_ownership(
            db=db,
            organization_id=organization_id,
            station_id=values.get("station_id", source.station_id),
        )
        self._validate_sensor_ownership(
            db=db,
            organization_id=organization_id,
            station_id=values.get("station_id", source.station_id),
            sensor_id=values.get("sensor_id", source.sensor_id),
        )

        for field_name, field_value in values.items():
            setattr(source, field_name, field_value)

        db.commit()
        db.refresh(source)
        return source

    def _validate_source_configuration(
        self,
        access_method: str,
        authentication_type: str,
        endpoint_reference: str,
        connector_config_json: str | None,
    ) -> None:
        allowed_access_methods = {"http", "s3", "manual_file", "mqtt", "opcua"}
        if access_method not in allowed_access_methods:
            allowed = ", ".join(sorted(allowed_access_methods))
            raise ValueError(f"access_method inválido '{access_method}'. Permitidos: {allowed}.")

        allowed_auth_types = {
            "none",
            "api_key_env",
            "bearer_env",
            "aws_env",
            "mqtt_userpass_env",
            "opcua_userpass_env",
        }
        if authentication_type not in allowed_auth_types:
            allowed = ", ".join(sorted(allowed_auth_types))
            raise ValueError(
                f"authentication_type inválido '{authentication_type}'. Permitidos: {allowed}."
            )

        if access_method == "manual_file" and authentication_type != "none":
            raise ValueError("Fontes manual_file devem usar authentication_type='none'.")

        if access_method == "s3" and authentication_type not in {"none", "aws_env"}:
            raise ValueError("Fontes s3 devem usar authentication_type='none' ou 'aws_env'.")

        if access_method == "http" and authentication_type not in {
            "none",
            "api_key_env",
            "bearer_env",
        }:
            raise ValueError(
                "Fontes http devem usar authentication_type='none', 'api_key_env' ou 'bearer_env'."
            )

        if access_method == "mqtt" and authentication_type not in {"none", "mqtt_userpass_env"}:
            raise ValueError(
                "Fontes mqtt devem usar authentication_type='none' ou 'mqtt_userpass_env'."
            )

        if access_method == "opcua" and authentication_type not in {"none", "opcua_userpass_env"}:
            raise ValueError(
                "Fontes opcua devem usar authentication_type='none' ou 'opcua_userpass_env'."
            )

        connector_config = self._parse_connector_config(connector_config_json)

        if access_method == "mqtt":
            parsed_endpoint = urlparse(endpoint_reference)
            if parsed_endpoint.scheme != "mqtt":
                raise ValueError("endpoint_reference de fonte mqtt deve iniciar com mqtt://.")
            if parsed_endpoint.path.strip("/") == "":
                raise ValueError("endpoint_reference de fonte mqtt deve informar o tópico no path.")

        if access_method == "opcua":
            parsed_endpoint = urlparse(endpoint_reference)
            if parsed_endpoint.scheme != "opc.tcp":
                raise ValueError("endpoint_reference de fonte opcua deve iniciar com opc.tcp://.")
            nodes = connector_config.get("nodes")
            if not isinstance(nodes, list) or not nodes:
                raise ValueError("Fontes opcua exigem connector_config_json.nodes com ao menos um item.")

        validate_connector_endpoint(
            access_method=access_method,
            endpoint_reference=endpoint_reference,
        )

        if authentication_type == "mqtt_userpass_env":
            self._require_env_credentials(connector_config=connector_config, connector_name="mqtt")
        if authentication_type == "opcua_userpass_env":
            self._require_env_credentials(connector_config=connector_config, connector_name="opcua")

    def _parse_connector_config(self, connector_config_json: str | None) -> dict:
        if connector_config_json is None:
            return {}
        try:
            parsed = json.loads(connector_config_json)
        except json.JSONDecodeError as exc:
            raise ValueError("connector_config_json deve ser JSON válido.") from exc
        if not isinstance(parsed, dict):
            raise ValueError("connector_config_json deve conter um objeto JSON.")
        return parsed

    def _require_env_credentials(self, connector_config: dict, connector_name: str) -> None:
        username_env = connector_config.get("username_env_var")
        password_env = connector_config.get("password_env_var")
        if not isinstance(username_env, str) or username_env.strip() == "":
            raise ValueError(
                f"Fonte {connector_name} com autenticação por usuário exige username_env_var."
            )
        if not isinstance(password_env, str) or password_env.strip() == "":
            raise ValueError(
                f"Fonte {connector_name} com autenticação por usuário exige password_env_var."
            )

    def _validate_station_ownership(
        self,
        db: Session,
        organization_id: str,
        station_id: str | None,
    ) -> None:
        if station_id is None:
            return
        station = db.scalar(
            select(StationModel).where(
                StationModel.station_id == station_id,
                StationModel.organization_id == organization_id,
            )
        )
        if station is None:
            raise ValueError(f"station_id '{station_id}' não pertence à organização.")

    def _validate_sensor_ownership(
        self,
        db: Session,
        organization_id: str,
        station_id: str | None,
        sensor_id: str | None,
    ) -> None:
        if sensor_id is None:
            return
        sensor = db.scalar(
            select(SensorModel).where(
                SensorModel.sensor_id == sensor_id,
                SensorModel.organization_id == organization_id,
            )
        )
        if sensor is None:
            raise ValueError(f"sensor_id '{sensor_id}' não pertence à organização.")
        if station_id != sensor.station_id:
            raise ValueError("sensor_id deve pertencer à station_id informada na fonte.")


catalog_service = CatalogService()

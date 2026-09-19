from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.catalog.models import SourceModel
from app.modules.ingestion.models import ObservationModel, RawAssetModel
from app.modules.meteorology.schemas import (
    AviationCondition,
    AviationConditionsResponse,
    LightningEvent,
    MapImageLayer,
    OperationalMapResponse,
    ForecastPoint,
    ForecastSeries,
    RequestedForecastResponse,
)


# Envelope regional operacional de Betim. Uma fonte de raios pode substituí-lo
# por connector_config_json.interest_bounds após homologação territorial.
BETIM_REGIONAL_BOUNDS = {"south": -20.35, "west": -44.75, "north": -19.65, "east": -43.70}


class MeteorologyService:
    def get_operational_map_layers(
        self,
        db: Session,
        organization_id: str,
    ) -> OperationalMapResponse:
        sources = list(db.scalars(select(SourceModel).where(
            SourceModel.organization_id == organization_id,
        )).all())
        satellite: MapImageLayer | None = None
        radar: MapImageLayer | None = None
        lightning_events: list[LightningEvent] = []
        lightning_configured = False
        for source in sources:
            config = self._connector_config(source.connector_config_json)
            parser = config.get("parser")
            if parser not in {"redemet_imagery", "lightning_geojson"}:
                continue
            if parser == "lightning_geojson":
                lightning_configured = True
            raw_asset = db.scalar(select(RawAssetModel).where(
                RawAssetModel.source_id == source.source_id,
                RawAssetModel.organization_id == organization_id,
            ).order_by(RawAssetModel.collected_at.desc()))
            if raw_asset is None:
                continue
            payload = self._read_json_payload(raw_asset=raw_asset)
            if parser == "lightning_geojson":
                bounds = config.get("interest_bounds")
                selected_bounds = bounds if isinstance(bounds, dict) else BETIM_REGIONAL_BOUNDS
                lightning_events.extend(
                    item for item in self._extract_lightning_events(payload=payload)
                    if self._within_bounds(item=item, bounds=selected_bounds)
                )
                continue
            layer = self._extract_imagery_layer(
                payload=payload,
                config=config,
                source=source,
                collected_at=raw_asset.collected_at,
            )
            if layer is None:
                continue
            if layer.kind == "satellite":
                satellite = layer
            elif layer.kind == "radar":
                radar = layer
        now = datetime.now(tz=timezone.utc)
        recent_events = [
            item for item in lightning_events
            if item.occurred_at_utc is None or item.occurred_at_utc >= now - timedelta(hours=1)
        ]
        return OperationalMapResponse(
            generated_at_utc=now,
            satellite=satellite,
            radar=radar,
            lightning_available=lightning_configured and bool(lightning_events),
            lightning_count_last_60m=len(recent_events) if lightning_configured and lightning_events else None,
            lightning_events=recent_events,
            disclaimer=(
                "Radar e satélite são imagens de sensoriamento remoto e devem ser interpretados "
                "como contexto. Um eco de radar não confirma chuva no solo em Betim. O contador "
                "de raios é exibido somente com feed georreferenciado oficial configurado."
            ),
        )

    def _extract_imagery_layer(
        self,
        payload: object | None,
        config: dict[str, object],
        source: SourceModel,
        collected_at: datetime,
    ) -> MapImageLayer | None:
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
            return None
        data = payload["data"]
        kind = str(config.get("image_kind", ""))
        item: dict[str, object] | None = None
        bounds_data: dict[str, object] | None = None
        if kind == "satellite":
            images = data.get("satelite")
            if isinstance(images, list) and images:
                item = images[-1] if isinstance(images[-1], dict) else None
            bounds_data = data.get("lat_lon") if isinstance(data.get("lat_lon"), dict) else None
        elif kind == "radar":
            rows = data.get("radar")
            # The documented response is a nested list. Accept a flat list too.
            flattened: list[dict[str, object]] = []
            if isinstance(rows, list):
                flattened = []
                for group in rows:
                    if isinstance(group, list):
                        flattened.extend(entry for entry in group if isinstance(entry, dict))
                    elif isinstance(group, dict):
                        flattened.append(group)
                desired_area = str(config.get("radar_area", ""))
                matches = [entry for entry in flattened if str(entry.get("localidade", "")) == desired_area and entry.get("path")]
                item = (matches or [entry for entry in flattened if entry.get("path")])[-1] if any(entry.get("path") for entry in flattened) else None
                bounds_data = item
        if not item or not isinstance(item.get("path"), str):
            return None
        bounds = self._bounds_from_data(bounds_data)
        return MapImageLayer(
            kind=kind,
            product=str(config.get("product", "")),
            image_url=item["path"],
            captured_at_utc=self._parse_remote_datetime(item.get("data")) or collected_at,
            bounds=bounds,
            source_state=source.status,
            source_note=self._source_note(source),
        )

    def _bounds_from_data(self, data: dict[str, object] | None) -> list[list[float]] | None:
        if not data:
            return None
        try:
            south, north = float(data["lat_min"]), float(data["lat_max"])
            west, east = float(data["lon_min"]), float(data["lon_max"])
        except (KeyError, TypeError, ValueError):
            return None
        return [[south, west], [north, east]]

    def _parse_remote_datetime(self, value: object) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)

    def _extract_lightning_events(self, payload: object | None) -> list[LightningEvent]:
        if not isinstance(payload, dict) or not isinstance(payload.get("features"), list):
            return []
        events: list[LightningEvent] = []
        for feature in payload["features"]:
            if not isinstance(feature, dict):
                continue
            geometry, properties = feature.get("geometry"), feature.get("properties")
            if not isinstance(geometry, dict) or geometry.get("type") != "Point" or not isinstance(geometry.get("coordinates"), list):
                continue
            coords = geometry["coordinates"]
            if len(coords) < 2:
                continue
            try:
                longitude, latitude = float(coords[0]), float(coords[1])
            except (TypeError, ValueError):
                continue
            props = properties if isinstance(properties, dict) else {}
            occurred = self._parse_remote_datetime(props.get("timestamp") or props.get("occurred_at") or props.get("data_hora"))
            try:
                intensity = float(props.get("intensity", 1.0))
            except (TypeError, ValueError):
                intensity = 1.0
            events.append(LightningEvent(latitude=latitude, longitude=longitude, occurred_at_utc=occurred, intensity=max(0.1, intensity)))
        return events

    def _within_bounds(self, item: LightningEvent, bounds: dict[str, object]) -> bool:
        try:
            return (
                float(bounds["south"]) <= item.latitude <= float(bounds["north"])
                and float(bounds["west"]) <= item.longitude <= float(bounds["east"])
            )
        except (KeyError, TypeError, ValueError):
            # Invalid optional bounds must not silently widen the regional count.
            return False

    def get_aviation_conditions(
        self,
        db: Session,
        organization_id: str,
    ) -> AviationConditionsResponse:
        sources = list(db.scalars(select(SourceModel).where(
            SourceModel.organization_id == organization_id,
            SourceModel.institution_name == "REDEMET / DECEA",
        )).all())
        by_airport: dict[str, dict[str, object]] = {}
        for source in sources:
            config = self._connector_config(source.connector_config_json)
            parser = config.get("parser")
            icao = config.get("icao")
            if parser not in {"redemet_status", "redemet_metar"} or not isinstance(icao, str):
                continue
            airport = by_airport.setdefault(icao, {
                "airport_name": config.get("airport_name") or icao,
                "latitude": config.get("latitude"),
                "longitude": config.get("longitude"),
                "source_state": source.status,
                "source_note": "Sem coleta concluída para esta fonte.",
            })
            raw_asset = db.scalar(select(RawAssetModel).where(
                RawAssetModel.source_id == source.source_id,
                RawAssetModel.organization_id == organization_id,
            ).order_by(RawAssetModel.collected_at.desc()))
            if raw_asset is None:
                continue
            payload = self._read_json_payload(raw_asset=raw_asset)
            airport["source_state"] = source.status
            airport["source_note"] = self._source_note(source=source)
            if parser == "redemet_status":
                category = self._extract_redemet_category(payload=payload, icao=icao)
                if category:
                    airport["flight_category"] = category
                    airport["status_collected_at_utc"] = raw_asset.collected_at
            else:
                metar, valid_at = self._extract_latest_metar(payload=payload, icao=icao)
                if metar:
                    airport["metar"] = metar
                    airport["metar_valid_at_utc"] = valid_at or raw_asset.collected_at

        conditions = [
            AviationCondition(
                icao=icao,
                airport_name=str(item["airport_name"]),
                latitude=float(item["latitude"]),
                longitude=float(item["longitude"]),
                flight_category=item.get("flight_category"),
                status_collected_at_utc=item.get("status_collected_at_utc"),
                metar=item.get("metar"),
                metar_valid_at_utc=item.get("metar_valid_at_utc"),
                source_state=str(item["source_state"]),
                source_note=str(item["source_note"]),
            )
            for icao, item in sorted(by_airport.items())
            if item.get("latitude") is not None and item.get("longitude") is not None
        ]
        return AviationConditionsResponse(
            generated_at_utc=datetime.now(tz=timezone.utc),
            conditions=conditions,
            disclaimer=(
                "Condições aeronáuticas regionais da REDEMET/DECEA. As categorias g/y/r "
                "derivam de visibilidade e teto no aeródromo e não constituem alerta municipal "
                "nem observação direta em Betim."
            ),
        )

    def _connector_config(self, value: str | None) -> dict[str, object]:
        if not value:
            return {}
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return decoded if isinstance(decoded, dict) else {}

    def _read_json_payload(self, raw_asset: RawAssetModel) -> object | None:
        path = Path(raw_asset.object_uri)
        if raw_asset.size_bytes > 1_048_576 or not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None

    def _extract_redemet_category(self, payload: object | None, icao: str) -> str | None:
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            return None
        for row in payload["data"]:
            if isinstance(row, list) and len(row) >= 5 and str(row[0]).upper() == icao:
                value = str(row[4]).lower()
                return value if value in {"g", "y", "r"} else None
            if isinstance(row, dict) and str(row.get("icao", row.get("id_localidade", ""))).upper() == icao:
                value = str(row.get("status", "")).lower()
                return value if value in {"g", "y", "r"} else None
        return None

    def _extract_latest_metar(self, payload: object | None, icao: str) -> tuple[str | None, datetime | None]:
        if not isinstance(payload, dict):
            return None, None
        envelope = payload.get("data")
        records = envelope.get("data") if isinstance(envelope, dict) else None
        if not isinstance(records, list):
            return None, None
        matching = [item for item in records if isinstance(item, dict) and str(item.get("id_localidade", "")).upper() == icao]
        if not matching:
            return None, None
        item = matching[-1]
        message = item.get("mens")
        raw_time = item.get("validade_inicial")
        try:
            valid_at = datetime.fromisoformat(str(raw_time)).replace(tzinfo=timezone.utc) if raw_time else None
        except ValueError:
            valid_at = None
        return (str(message) if message else None, valid_at)

    def _source_note(self, source: SourceModel) -> str:
        if source.last_error:
            return "Fonte degradada: " + source.last_error[:160]
        if source.last_success_at is None:
            return "Coleta ainda não concluída."
        return "Fonte atualizada conforme última coleta registrada."

    def generate_requested_forecast(
        self,
        db: Session,
        organization_id: str,
        issued_at_utc: datetime,
        horizon_hours: int,
        step_hours: int,
        base_window_hours: int,
        source_ids: list[str] | None,
    ) -> RequestedForecastResponse:
        issued = self._as_utc(issued_at_utc)
        if step_hours > horizon_hours:
            raise ValueError("step_hours não pode ser maior que horizon_hours.")

        window_start = issued - timedelta(hours=base_window_hours)
        tracked = _forecast_variable_settings()

        stmt = select(ObservationModel).where(
            ObservationModel.organization_id == organization_id,
            ObservationModel.observed_at_utc >= window_start,
            ObservationModel.observed_at_utc <= issued,
            ObservationModel.variable_code.in_(tuple(tracked.keys())),
        )
        if source_ids:
            stmt = stmt.where(ObservationModel.source_id.in_(tuple(source_ids)))
        stmt = stmt.order_by(ObservationModel.observed_at_utc.asc())

        observations = list(db.scalars(stmt).all())
        usable = [item for item in observations if item.quality_status != "rejected"]
        if not usable:
            raise ValueError("Não há observações válidas no período solicitado para gerar previsão.")

        grouped: dict[str, list[ObservationModel]] = {}
        for item in usable:
            grouped.setdefault(item.variable_code, []).append(item)

        series_list: list[ForecastSeries] = []
        for variable_code, settings in tracked.items():
            samples = grouped.get(variable_code, [])
            if not samples:
                continue

            base_value = self._compute_base_value(samples=samples)
            trend_per_hour = self._compute_trend_per_hour(samples=samples)
            points = self._build_points(
                variable_code=variable_code,
                samples=samples,
                issued_at=issued,
                horizon_hours=horizon_hours,
                step_hours=step_hours,
                base_value=base_value,
                trend_per_hour=trend_per_hour,
                min_value=float(settings["min_value"]),
                max_value=float(settings["max_value"]),
            )

            series_list.append(
                ForecastSeries(
                    variable_code=variable_code,
                    unit=str(settings["unit"]),
                    sample_count=len(samples),
                    base_value=base_value,
                    trend_per_hour=trend_per_hour,
                    points=points,
                )
            )

        if not series_list:
            raise ValueError("Não foi possível montar séries de previsão para o período solicitado.")

        source_scope = sorted({item.source_id for item in usable})
        summary = self._build_summary(series=series_list)
        return RequestedForecastResponse(
            generated_at_utc=datetime.now(tz=timezone.utc),
            organization_id=organization_id,
            issued_at_utc=issued,
            horizon_hours=horizon_hours,
            step_hours=step_hours,
            source_scope=source_scope,
            model_name="statistical_trend_forecast",
            model_version="v1",
            series=series_list,
            summary=summary,
        )

    def _compute_base_value(self, samples: list[ObservationModel]) -> float:
        latest = samples[-3:] if len(samples) >= 3 else samples
        return sum(item.value_canonical for item in latest) / len(latest)

    def _compute_trend_per_hour(self, samples: list[ObservationModel]) -> float:
        if len(samples) < 2:
            return 0.0
        first = samples[0]
        last = samples[-1]
        elapsed = (self._as_utc(last.observed_at_utc) - self._as_utc(first.observed_at_utc)).total_seconds() / 3600.0
        if elapsed <= 0:
            return 0.0
        return (last.value_canonical - first.value_canonical) / elapsed

    def _build_points(
        self,
        variable_code: str,
        samples: list[ObservationModel],
        issued_at: datetime,
        horizon_hours: int,
        step_hours: int,
        base_value: float,
        trend_per_hour: float,
        min_value: float,
        max_value: float,
    ) -> list[ForecastPoint]:
        points: list[ForecastPoint] = []
        latest_observation_at = self._as_utc(samples[-1].observed_at_utc)
        age_hours = max(0.0, (issued_at - latest_observation_at).total_seconds() / 3600.0)

        for offset in range(step_hours, horizon_hours + 1, step_hours):
            projected = base_value + (trend_per_hour * offset)
            clipped = max(min_value, min(max_value, projected))
            risk = self._resolve_risk_level(variable_code=variable_code, value=clipped)

            confidence = 75
            confidence += min(20, len(samples) * 3)
            confidence -= min(35, int(age_hours * 2))
            confidence -= int(offset * 0.5)
            confidence_score = max(15, min(100, confidence))

            points.append(
                ForecastPoint(
                    valid_at_utc=issued_at + timedelta(hours=offset),
                    predicted_value=clipped,
                    risk_level=risk,
                    confidence_score=confidence_score,
                )
            )
        return points

    def _resolve_risk_level(self, variable_code: str, value: float) -> str:
        if variable_code == "temperature_c":
            if value >= 40.0:
                return "critical"
            if value >= 35.0:
                return "high"
            if value >= 32.0:
                return "attention"
            return "normal"

        if variable_code == "humidity_pct":
            if value <= 20.0:
                return "high"
            if value <= 30.0:
                return "attention"
            return "normal"

        if variable_code == "rainfall_mm_1h":
            if value >= 50.0:
                return "high"
            if value >= 30.0:
                return "attention"
            return "normal"

        if variable_code == "wind_speed_mps":
            if value >= 25.0:
                return "high"
            if value >= 17.0:
                return "attention"
            return "normal"

        if variable_code == "river_level_m":
            if value >= 6.0:
                return "critical"
            if value >= 4.0:
                return "high"
            if value >= 3.0:
                return "attention"
            return "normal"

        if variable_code == "river_flow_m3s":
            if value >= 3000.0:
                return "high"
            if value >= 1500.0:
                return "attention"
            return "normal"

        return "normal"

    def _build_summary(self, series: list[ForecastSeries]) -> str:
        total_points = sum(len(item.points) for item in series)
        high_risk = sum(
            1 for item in series for point in item.points if point.risk_level in {"high", "critical"}
        )
        return (
            f"Previsão estatística gerada para {len(series)} variáveis, "
            f"totalizando {total_points} pontos previstos. "
            f"Pontos em risco alto/crítico: {high_risk}."
        )

    def _as_utc(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    # ------------------- Pontos de monitoramento -------------------

    _MONITORING_EXCLUDED_PARSERS = {
        "redemet_imagery", "lightning_geojson", "redemet_status", "redemet_metar",
    }

    def get_monitoring_points(
        self,
        db: Session,
        organization_id: str,
        public_only: bool = False,
    ) -> dict:
        """Últimas leituras por estação: valores, acumulados de chuva
        (1/6/24/72 h) e tendência de nível d'água — a visão estratégica do mapa.
        """
        from app.modules.public.service import public_publication_service

        now = datetime.now(tz=timezone.utc)
        since = now - timedelta(hours=72)
        sources = list(db.scalars(select(SourceModel).where(
            SourceModel.organization_id == organization_id,
            SourceModel.status == "active",
        )).all())

        points: list[dict] = []
        for source in sources:
            config = self._connector_config(source.connector_config_json)
            parser = config.get("parser")
            if parser in self._MONITORING_EXCLUDED_PARSERS:
                continue
            station_code = config.get("station_code") or source.source_name
            if public_only and not public_publication_service.is_public_source(source):
                continue

            observations = list(db.scalars(select(ObservationModel).where(
                ObservationModel.organization_id == organization_id,
                ObservationModel.source_id == source.source_id,
                ObservationModel.observed_at_utc >= since,
            ).order_by(ObservationModel.observed_at_utc.asc())).all())
            if not observations:
                continue

            latest: dict[str, ObservationModel] = {}
            rain_series: list[tuple[datetime, float]] = []
            level_series: list[tuple[datetime, float]] = []
            for observation in observations:
                if observation.quality_status == "rejected":
                    continue
                latest[observation.variable_code] = observation
                when = self._as_utc(observation.observed_at_utc)
                value = float(observation.value_canonical)
                if observation.variable_code == "rainfall_mm_1h":
                    rain_series.append((when, value))
                elif observation.variable_code == "river_level_m":
                    level_series.append((when, value))
            if not latest:
                continue

            def _rain_sum(hours: int) -> float:
                cutoff = now - timedelta(hours=hours)
                return round(sum(v for t, v in rain_series if t >= cutoff), 1)

            rainfall_accumulation = (
                {"1h": _rain_sum(1), "6h": _rain_sum(6), "24h": _rain_sum(24), "72h": _rain_sum(72)}
                if rain_series
                else None
            )

            river_level = None
            if level_series:
                current_time, current_value = level_series[-1]
                river_level = {
                    "value_m": round(current_value, 2),
                    "observed_at_utc": current_time.isoformat(),
                    "trend": "estavel",
                    "rate_cm_h": 0.0,
                }
                reference = next(
                    (
                        (t, v)
                        for t, v in reversed(level_series[:-1])
                        if (current_time - t).total_seconds() >= 1800
                    ),
                    None,
                )
                if reference is not None:
                    hours_delta = (current_time - reference[0]).total_seconds() / 3600
                    rate_cm_h = (current_value - reference[1]) * 100.0 / hours_delta
                    river_level["rate_cm_h"] = round(rate_cm_h, 1)
                    if rate_cm_h >= 2.0:
                        river_level["trend"] = "subindo"
                    elif rate_cm_h <= -2.0:
                        river_level["trend"] = "descendo"

            latitude, longitude = self._resolve_coordinates(
                db=db, source=source, config=config, parser=parser
            )
            if latitude is None or longitude is None:
                continue

            if parser == "ana_hidroweb":
                kind = "fluviometrica"
            elif parser == "open_meteo":
                kind = "modelo"
            else:
                kind = "meteorologica"

            fog = self._fog_risk(latest)
            points.append({
                "fog_risk": fog,
                "source_id": source.source_id,
                "source_name": source.source_name,
                "station_code": station_code,
                "institution": source.institution_name,
                "kind": kind,
                "criticality": source.criticality,
                "latitude": latitude,
                "longitude": longitude,
                "observed_at_utc": max(
                    self._as_utc(item.observed_at_utc) for item in latest.values()
                ).isoformat(),
                "variables": {
                    code: {
                        "value": round(float(item.value_canonical), 1),
                        "unit": item.unit_canonical,
                        "observed_at_utc": self._as_utc(item.observed_at_utc).isoformat(),
                    }
                    for code, item in latest.items()
                },
                "rainfall_accumulation_mm": rainfall_accumulation,
                "river_level": river_level,
            })

        return {"generated_at_utc": now.isoformat(), "points": points}

    # Coordenada e altitude de Betim (centro) para a interpolação.
    _BETIM_POINT = (-19.9676, -44.1983, 831.0)

    def interpolated_betim_conditions(self, db: Session, organization_id: str) -> dict:
        """Estimativa das condições em Betim por interpolação IDW das estações.

        Combina, por Inverse Distance Weighting (peso = 1/distância²), as
        observações mais recentes das estações e pontos com coordenada
        conhecida. A temperatura recebe correção de altitude pela taxa de
        lapso (~6,5 °C/km). É estimativa espacial, não medição no ponto —
        rotulada como tal.
        """
        import math

        now = datetime.now(tz=timezone.utc)
        since = now - timedelta(hours=3)
        lat0, lon0, alt0 = self._BETIM_POINT
        variaveis = ("temperature_c", "humidity_pct", "wind_speed_mps", "rainfall_mm_1h")

        sources = list(db.scalars(select(SourceModel).where(
            SourceModel.organization_id == organization_id,
            SourceModel.status == "active",
        )).all())

        # Última leitura por (fonte, variável), com posição e altitude da fonte.
        pontos: list[dict] = []
        for source in sources:
            config = self._connector_config(source.connector_config_json)
            lat, lon = self._resolve_coordinates(db=db, source=source, config=config, parser=config.get("parser"))
            if lat is None or lon is None:
                continue
            altitude = config.get("altitude_m")
            observacoes = list(db.scalars(select(ObservationModel).where(
                ObservationModel.organization_id == organization_id,
                ObservationModel.source_id == source.source_id,
                ObservationModel.observed_at_utc >= since,
                ObservationModel.quality_status != "rejected",
                ObservationModel.variable_code.in_(variaveis),
            ).order_by(ObservationModel.observed_at_utc.asc())).all())
            if not observacoes:
                continue
            recentes: dict[str, float] = {}
            for obs in observacoes:
                recentes[obs.variable_code] = float(obs.value_canonical)
            pontos.append({
                "source_name": source.source_name,
                "lat": lat, "lon": lon,
                "altitude": float(altitude) if altitude is not None else None,
                "values": recentes,
            })

        def distancia_km(lat: float, lon: float) -> float:
            # Haversine.
            r = 6371.0
            dlat = math.radians(lat - lat0)
            dlon = math.radians(lon - lon0)
            a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat0)) * math.cos(math.radians(lat)) * math.sin(dlon / 2) ** 2
            return 2 * r * math.asin(math.sqrt(a))

        resultado: dict[str, dict] = {}
        for variavel in variaveis:
            soma_peso = 0.0
            soma_valor = 0.0
            usados = 0
            for ponto in pontos:
                if variavel not in ponto["values"]:
                    continue
                d = max(distancia_km(ponto["lat"], ponto["lon"]), 0.5)
                peso = 1.0 / (d * d)
                valor = ponto["values"][variavel]
                # Correção de altitude para temperatura (lapso de 6,5 °C/km).
                if variavel == "temperature_c" and ponto["altitude"] is not None:
                    valor += (ponto["altitude"] - alt0) * 0.0065
                soma_peso += peso
                soma_valor += peso * valor
                usados += 1
            if soma_peso > 0 and usados > 0:
                resultado[variavel] = {
                    "value": round(soma_valor / soma_peso, 1),
                    "stations_used": usados,
                }

        return {
            "generated_at_utc": now.isoformat(),
            "location": {"name": "Betim/MG", "latitude": lat0, "longitude": lon0},
            "method": "idw_inverse_distance_weighting",
            "variables": resultado,
            "stations_available": len(pontos),
            "disclaimer": (
                "Estimativa espacial por interpolação das estações e pontos com "
                "dado recente; não é medição no local. Enquanto Betim não dispõe "
                "de estação automática própria, esta é a melhor aproximação "
                "observacional das condições."
            ),
        }

    def _fog_risk(self, latest: dict) -> dict | None:
        """Risco de nevoeiro por resfriamento radiativo (meteorologia aplicada).

        Nevoeiro raso é invisível no satélite infravermelho — por isso é
        estimado a partir das condições que o produzem: pouca diferença entre
        temperatura e ponto de orvalho (ar saturando), umidade alta, vento
        fraco (sem mistura) e céu limpo (perda radiativa noturna). Critérios
        alinhados à prática operacional aeronáutica.
        """

        def value_of(code: str) -> float | None:
            observation = latest.get(code)
            return float(observation.value_canonical) if observation is not None else None

        temperature = value_of("temperature_c")
        dew_point = value_of("dew_point_c")
        humidity = value_of("humidity_pct")
        wind = value_of("wind_speed_mps")
        clouds = value_of("cloud_cover_pct")
        visibility = value_of("visibility_m")

        if temperature is None or (dew_point is None and humidity is None):
            return None

        spread = None
        if dew_point is not None:
            spread = round(temperature - dew_point, 1)

        score = 0
        motivos: list[str] = []
        if spread is not None:
            if spread <= 1.0:
                score += 3
                motivos.append(f"ar praticamente saturado (T−Td {spread} °C)")
            elif spread <= 2.5:
                score += 2
                motivos.append(f"pouca margem para saturação (T−Td {spread} °C)")
            elif spread <= 4.0:
                score += 1
        if humidity is not None:
            if humidity >= 95:
                score += 2
                motivos.append(f"umidade muito alta ({humidity:.0f}%)")
            elif humidity >= 90:
                score += 1
        if wind is not None and wind <= 2.0:
            score += 1
            motivos.append("vento fraco, sem mistura do ar")
        if clouds is not None and clouds <= 25:
            score += 1
            motivos.append("céu limpo favorecendo resfriamento noturno")
        if visibility is not None and visibility <= 1000:
            score += 3
            motivos.append(f"visibilidade já reduzida ({visibility:.0f} m)")

        if score >= 6:
            level, label = "alto", "Alto risco de nevoeiro"
        elif score >= 4:
            level, label = "moderado", "Risco moderado de nevoeiro"
        elif score >= 2:
            level, label = "baixo", "Baixo risco de nevoeiro"
        else:
            return None

        return {
            "level": level,
            "label": label,
            "score": score,
            "dew_point_spread_c": spread,
            "reasons": motivos,
            "note": (
                "Estimativa calculada a partir de temperatura, ponto de orvalho, "
                "umidade, vento e nebulosidade; não é observação direta de visibilidade."
            ),
        }

    def _resolve_coordinates(
        self,
        db: Session,
        source: SourceModel,
        config: dict,
        parser: str | None,
    ) -> tuple[float | None, float | None]:
        """Descobre a posição da estação por várias vias, na ordem de confiança."""
        # 1) Declarada no próprio conector.
        latitude, longitude = config.get("latitude"), config.get("longitude")
        if latitude is not None and longitude is not None:
            return (float(latitude), float(longitude))

        # 2) Parâmetros da URL (Open-Meteo e similares).
        from urllib.parse import parse_qs, urlparse

        query = parse_qs(urlparse(source.endpoint_reference or "").query)
        raw_lat = (query.get("latitude") or query.get("lat") or [None])[0]
        raw_lon = (query.get("longitude") or query.get("lon") or [None])[0]
        if raw_lat and raw_lon:
            try:
                return (float(raw_lat), float(raw_lon))
            except ValueError:
                pass

        # 3) Estação cadastrada e vinculada à fonte.
        if source.station_id:
            from app.modules.geospatial.models import StationModel

            station = db.get(StationModel, source.station_id)
            if station is not None and station.location_geojson:
                try:
                    coordinates = json.loads(station.location_geojson)["coordinates"]
                    return (float(coordinates[1]), float(coordinates[0]))
                except (ValueError, KeyError, IndexError, TypeError):
                    pass

        # 4) Payload bruto (INMET e Open-Meteo trazem a posição na resposta).
        latitude, longitude = self._latlon_from_latest_raw(db, source)
        if latitude is not None and longitude is not None:
            return (latitude, longitude)

        # 5) Camada oficial de réguas da ANA, cruzando pelo código da estação.
        if parser == "ana_hidroweb":
            return self._latlon_from_ana_layer(config.get("station_code"))
        return (None, None)

    def _latlon_from_ana_layer(self, station_code: str | None) -> tuple[float | None, float | None]:
        if not station_code:
            return (None, None)
        code = str(station_code).replace("ANA_", "").strip()
        try:
            from app.modules.geospatial.official_layers import official_layers

            layers = official_layers()
        except Exception:
            return (None, None)
        for feature in (layers.get("river_gauges") or {}).get("features", []):
            properties = feature.get("properties") or {}
            if str(properties.get("Codigo") or "").strip() != code:
                continue
            coordinates = (feature.get("geometry") or {}).get("coordinates")
            if isinstance(coordinates, list) and len(coordinates) >= 2:
                return (float(coordinates[1]), float(coordinates[0]))
        return (None, None)

    def _latlon_from_latest_raw(
        self, db: Session, source: SourceModel
    ) -> tuple[float | None, float | None]:
        """Extrai VL_LATITUDE/VL_LONGITUDE do payload bruto mais recente (INMET)."""
        raw_asset = db.scalar(select(RawAssetModel).where(
            RawAssetModel.source_id == source.source_id,
        ).order_by(RawAssetModel.collected_at.desc()))
        if raw_asset is None:
            return (None, None)
        try:
            payload = self._read_json_payload(raw_asset=raw_asset)
        except Exception:
            return (None, None)
        # Open-Meteo devolve latitude/longitude na raiz do JSON.
        if isinstance(payload, dict):
            raw_lat, raw_lon = payload.get("latitude"), payload.get("longitude")
            try:
                if raw_lat is not None and raw_lon is not None:
                    return (float(raw_lat), float(raw_lon))
            except (TypeError, ValueError):
                pass
        records = payload if isinstance(payload, list) else payload.get("data", []) if isinstance(payload, dict) else []
        for record in records:
            if not isinstance(record, dict):
                continue
            raw_lat = record.get("VL_LATITUDE") or record.get("latitude")
            raw_lon = record.get("VL_LONGITUDE") or record.get("longitude")
            try:
                if raw_lat is not None and raw_lon is not None:
                    return (float(raw_lat), float(raw_lon))
            except (TypeError, ValueError):
                continue
        return (None, None)


def _forecast_variable_settings() -> dict[str, dict[str, float | str]]:
    return {
        "temperature_c": {"unit": "c", "min_value": -30.0, "max_value": 55.0},
        "humidity_pct": {"unit": "%", "min_value": 0.0, "max_value": 100.0},
        "rainfall_mm_1h": {"unit": "mm", "min_value": 0.0, "max_value": 300.0},
        "wind_speed_mps": {"unit": "m/s", "min_value": 0.0, "max_value": 90.0},
        "river_level_m": {"unit": "m", "min_value": 0.0, "max_value": 30.0},
        "river_flow_m3s": {"unit": "m3/s", "min_value": 0.0, "max_value": 25000.0},
    }


meteorology_service = MeteorologyService()

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.ingestion.models import ObservationModel
from app.modules.catalog.models import SourceModel
from app.modules.geospatial.models import SensorModel, StationModel
from app.modules.planning.schemas import (
    ClimateAlert,
    CommitteeClimateReport,
    QualityDistribution,
    SourceCoverageSummary,
    StationAvailabilityItem,
    StationAvailabilityReport,
    VariableTrendSummary,
)


class PlanningService:
    def generate_station_availability_report(
        self,
        db: Session,
        organization_id: str,
        period_start_utc: datetime,
        period_end_utc: datetime,
    ) -> StationAvailabilityReport:
        start_utc = self._as_utc(period_start_utc)
        end_utc = self._as_utc(period_end_utc)
        if start_utc >= end_utc:
            raise ValueError("period_start_utc deve ser anterior a period_end_utc.")

        stations = list(
            db.scalars(
                select(StationModel)
                .where(StationModel.organization_id == organization_id)
                .order_by(StationModel.station_name.asc())
            ).all()
        )
        sensors = list(db.scalars(select(SensorModel).where(SensorModel.organization_id == organization_id)).all())
        sources = list(db.scalars(select(SourceModel).where(SourceModel.organization_id == organization_id)).all())
        observations = list(
            db.scalars(
                select(ObservationModel).where(
                    ObservationModel.organization_id == organization_id,
                    ObservationModel.observed_at_utc >= start_utc,
                    ObservationModel.observed_at_utc <= end_utc,
                )
            ).all()
        )
        sensors_by_station: dict[str, list[SensorModel]] = {}
        for sensor in sensors:
            sensors_by_station.setdefault(sensor.station_id, []).append(sensor)
        sources_by_station: dict[str, list[SourceModel]] = {}
        for source in sources:
            if source.station_id:
                sources_by_station.setdefault(source.station_id, []).append(source)
        observations_by_station: dict[str, list[ObservationModel]] = {}
        for observation in observations:
            if observation.station_id:
                observations_by_station.setdefault(observation.station_id, []).append(observation)

        period_minutes = max(1, int((end_utc - start_utc).total_seconds() / 60))
        report_items: list[StationAvailabilityItem] = []
        for station in stations:
            station_sensors = sensors_by_station.get(station.station_id, [])
            station_observations = observations_by_station.get(station.station_id, [])
            valid = sum(item.quality_status == "valid" for item in station_observations)
            suspect = sum(item.quality_status == "suspect" for item in station_observations)
            rejected = len(station_observations) - valid - suspect
            frequencies = [source.expected_frequency_minutes for source in sources_by_station.get(station.station_id, []) if source.expected_frequency_minutes > 0]
            expected = None
            if frequencies and station_sensors:
                expected = max(1, int(period_minutes / min(frequencies)) * len(station_sensors))
            completeness = None if expected is None else round(min(100.0, (valid / expected) * 100), 2)
            last_seen = max((self._as_utc(item.observed_at_utc) for item in station_observations), default=None)
            health = self._station_health(
                station_status=station.status,
                last_seen=last_seen,
                expected_frequency_minutes=min(frequencies) if frequencies else None,
                now_utc=end_utc,
            )
            report_items.append(
                StationAvailabilityItem(
                    station_id=station.station_id,
                    station_code=station.station_code,
                    station_name=station.station_name,
                    station_type=station.station_type,
                    station_status=station.status,
                    sensor_count=len(station_sensors),
                    observation_count=len(station_observations),
                    valid_observation_count=valid,
                    suspect_observation_count=suspect,
                    rejected_observation_count=rejected,
                    expected_observation_count=expected,
                    completeness_percent=completeness,
                    last_observed_at_utc=last_seen,
                    health_status=health,
                    variables=sorted({sensor.variable_code for sensor in station_sensors}),
                )
            )
        degraded = sum(item.health_status == "degraded" for item in report_items)
        summary = f"{len(report_items)} estações analisadas; {degraded} degradadas; período de {start_utc.isoformat()} a {end_utc.isoformat()}."
        return StationAvailabilityReport(
            generated_at_utc=datetime.now(tz=timezone.utc),
            organization_id=organization_id,
            period_start_utc=start_utc,
            period_end_utc=end_utc,
            stations=report_items,
            summary=summary,
        )

    def _station_health(
        self,
        *,
        station_status: str,
        last_seen: datetime | None,
        expected_frequency_minutes: int | None,
        now_utc: datetime,
    ) -> str:
        if station_status != "active":
            return station_status
        if last_seen is None:
            return "unknown"
        if expected_frequency_minutes is None:
            return "observed"
        age_minutes = (now_utc - last_seen).total_seconds() / 60
        return "degraded" if age_minutes > expected_frequency_minutes * 2 else "operational"

    def generate_committee_climate_report(
        self,
        db: Session,
        organization_id: str,
        period_start_utc: datetime,
        period_end_utc: datetime,
        source_ids: list[str] | None,
        max_alerts: int,
    ) -> CommitteeClimateReport:
        start_utc = self._as_utc(period_start_utc)
        end_utc = self._as_utc(period_end_utc)
        if start_utc >= end_utc:
            raise ValueError("period_start_utc deve ser anterior a period_end_utc.")

        tracked_variables = _tracked_variables()
        stmt = select(ObservationModel).where(
            ObservationModel.organization_id == organization_id,
            ObservationModel.observed_at_utc >= start_utc,
            ObservationModel.observed_at_utc <= end_utc,
            ObservationModel.variable_code.in_(tuple(tracked_variables.keys())),
        )
        if source_ids:
            stmt = stmt.where(ObservationModel.source_id.in_(tuple(source_ids)))
        stmt = stmt.order_by(ObservationModel.observed_at_utc.asc())
        observations = list(db.scalars(stmt).all())

        quality_distribution = self._build_quality_distribution(observations=observations)
        trend_summaries = self._build_trend_summaries(
            observations=observations,
            tracked_variables=tracked_variables,
        )
        alerts = self._build_alerts(observations=observations, max_alerts=max_alerts)
        source_coverage = self._build_source_coverage(observations=observations)
        source_scope = sorted({item.source_id for item in observations})
        executive_summary = self._build_executive_summary(
            trend_summaries=trend_summaries,
            alerts=alerts,
            quality_distribution=quality_distribution,
            observations_considered=len(observations),
        )

        return CommitteeClimateReport(
            generated_at_utc=datetime.now(tz=timezone.utc),
            organization_id=organization_id,
            period_start_utc=start_utc,
            period_end_utc=end_utc,
            source_scope=source_scope,
            observations_considered=len(observations),
            quality_distribution=quality_distribution,
            source_coverage=source_coverage,
            trend_summaries=trend_summaries,
            alerts=alerts,
            executive_summary=executive_summary,
        )

    def _build_quality_distribution(self, observations: list[ObservationModel]) -> QualityDistribution:
        valid = 0
        suspect = 0
        rejected = 0
        for observation in observations:
            if observation.quality_status == "valid":
                valid += 1
            elif observation.quality_status == "suspect":
                suspect += 1
            else:
                rejected += 1
        return QualityDistribution(valid=valid, suspect=suspect, rejected=rejected)

    def _build_source_coverage(self, observations: list[ObservationModel]) -> list[SourceCoverageSummary]:
        counts_by_source: dict[str, int] = {}
        last_seen_by_source: dict[str, datetime] = {}
        for observation in observations:
            counts_by_source[observation.source_id] = counts_by_source.get(observation.source_id, 0) + 1
            previous = last_seen_by_source.get(observation.source_id)
            if previous is None or observation.observed_at_utc > previous:
                last_seen_by_source[observation.source_id] = observation.observed_at_utc

        summaries: list[SourceCoverageSummary] = []
        for source_id, sample_count in counts_by_source.items():
            summaries.append(
                SourceCoverageSummary(
                    source_id=source_id,
                    sample_count=sample_count,
                    last_observed_at_utc=last_seen_by_source.get(source_id),
                )
            )
        summaries.sort(key=lambda item: item.sample_count, reverse=True)
        return summaries

    def _build_trend_summaries(
        self,
        observations: list[ObservationModel],
        tracked_variables: dict[str, dict[str, float | str]],
    ) -> list[VariableTrendSummary]:
        grouped: dict[str, list[ObservationModel]] = {}
        for observation in observations:
            grouped.setdefault(observation.variable_code, []).append(observation)

        summaries: list[VariableTrendSummary] = []
        for variable_code, config in tracked_variables.items():
            all_samples = grouped.get(variable_code, [])
            usable_samples = [sample for sample in all_samples if sample.quality_status != "rejected"]
            values = [sample.value_canonical for sample in usable_samples]

            if values:
                min_value = min(values)
                max_value = max(values)
                average_value = sum(values) / len(values)
                first_value = values[0]
                last_value = values[-1]
                if len(values) >= 2:
                    trend_delta = last_value - first_value
                    trend_direction = self._resolve_trend_direction(
                        variable_code=variable_code,
                        trend_delta=trend_delta,
                    )
                else:
                    trend_delta = None
                    trend_direction = "insufficient"
            else:
                min_value = None
                max_value = None
                average_value = None
                first_value = None
                last_value = None
                trend_delta = None
                trend_direction = "insufficient"

            summaries.append(
                VariableTrendSummary(
                    variable_code=variable_code,
                    unit=str(config["unit"]),
                    sample_count=len(all_samples),
                    valid_sample_count=len(usable_samples),
                    min_value=min_value,
                    max_value=max_value,
                    average_value=average_value,
                    first_value=first_value,
                    last_value=last_value,
                    trend_delta=trend_delta,
                    trend_direction=trend_direction,
                )
            )
        return summaries

    def _resolve_trend_direction(self, variable_code: str, trend_delta: float) -> str:
        epsilon = _tracked_variables().get(variable_code, {}).get("trend_epsilon", 0.5)
        if not isinstance(epsilon, (int, float)):
            epsilon = 0.5
        threshold = float(epsilon)

        if trend_delta > threshold:
            return "rising"
        if trend_delta < -threshold:
            return "falling"
        return "stable"

    def _build_alerts(self, observations: list[ObservationModel], max_alerts: int) -> list[ClimateAlert]:
        candidates: list[ClimateAlert] = []
        for observation in observations:
            alert = self._evaluate_alert(observation=observation)
            if alert is not None:
                candidates.append(alert)

        severity_rank = {"critical": 4, "high": 3, "medium": 2, "low": 1}
        candidates.sort(
            key=lambda item: (
                item.observed_at_utc,
                severity_rank.get(item.severity, 0),
            ),
            reverse=True,
        )
        return candidates[:max_alerts]

    def _evaluate_alert(self, observation: ObservationModel) -> ClimateAlert | None:
        if observation.quality_status == "rejected":
            return None

        variable_code = observation.variable_code
        value = observation.value_canonical

        if variable_code == "temperature_c":
            if value >= 40.0:
                return self._build_alert(
                    alert_code="temperature_extreme",
                    severity="critical",
                    observation=observation,
                    threshold=40.0,
                    description="Temperatura extrema observada acima de 40C.",
                )
            if value >= 35.0:
                return self._build_alert(
                    alert_code="temperature_high",
                    severity="high",
                    observation=observation,
                    threshold=35.0,
                    description="Temperatura elevada observada acima de 35C.",
                )

        if variable_code == "humidity_pct":
            if value <= 20.0:
                return self._build_alert(
                    alert_code="humidity_critical_low",
                    severity="high",
                    observation=observation,
                    threshold=20.0,
                    description="Umidade relativa crítica em patamar igual ou abaixo de 20%.",
                )
            if value <= 30.0:
                return self._build_alert(
                    alert_code="humidity_low",
                    severity="medium",
                    observation=observation,
                    threshold=30.0,
                    description="Umidade relativa baixa em patamar igual ou abaixo de 30%.",
                )
            if value >= 95.0:
                return self._build_alert(
                    alert_code="humidity_very_high",
                    severity="medium",
                    observation=observation,
                    threshold=95.0,
                    description="Umidade relativa muito alta, potencialmente favorável a tempestades.",
                )

        if variable_code == "rainfall_mm_1h":
            if value >= 50.0:
                return self._build_alert(
                    alert_code="storm_heavy_rain",
                    severity="high",
                    observation=observation,
                    threshold=50.0,
                    description="Chuva intensa acima de 50 mm/h com risco de tempestade.",
                )
            if value >= 30.0:
                return self._build_alert(
                    alert_code="storm_rain_watch",
                    severity="medium",
                    observation=observation,
                    threshold=30.0,
                    description="Chuva forte acima de 30 mm/h em monitoramento.",
                )

        if variable_code == "wind_speed_mps":
            if value >= 25.0:
                return self._build_alert(
                    alert_code="storm_wind_gust",
                    severity="high",
                    observation=observation,
                    threshold=25.0,
                    description="Rajada intensa de vento acima de 25 m/s com potencial de dano.",
                )
            if value >= 17.0:
                return self._build_alert(
                    alert_code="storm_wind_watch",
                    severity="medium",
                    observation=observation,
                    threshold=17.0,
                    description="Vento forte acima de 17 m/s, condição de atenção.",
                )

        if variable_code == "river_level_m":
            if value >= 6.0:
                return self._build_alert(
                    alert_code="river_level_critical",
                    severity="critical",
                    observation=observation,
                    threshold=6.0,
                    description="Nível do rio em cota crítica igual ou acima de 6 m.",
                )
            if value >= 4.0:
                return self._build_alert(
                    alert_code="river_level_high",
                    severity="high",
                    observation=observation,
                    threshold=4.0,
                    description="Nível do rio acima de 4 m com risco de transbordamento.",
                )

        if variable_code == "river_flow_m3s":
            if value >= 3000.0:
                return self._build_alert(
                    alert_code="river_flow_critical",
                    severity="high",
                    observation=observation,
                    threshold=3000.0,
                    description="Vazão do rio em patamar crítico acima de 3000 m3/s.",
                )
            if value >= 1500.0:
                return self._build_alert(
                    alert_code="river_flow_high",
                    severity="medium",
                    observation=observation,
                    threshold=1500.0,
                    description="Vazão do rio acima de 1500 m3/s em monitoramento.",
                )

        return None

    def _build_alert(
        self,
        alert_code: str,
        severity: str,
        observation: ObservationModel,
        threshold: float,
        description: str,
    ) -> ClimateAlert:
        return ClimateAlert(
            alert_code=alert_code,
            severity=severity,
            variable_code=observation.variable_code,
            source_id=observation.source_id,
            observed_at_utc=observation.observed_at_utc,
            location_code=observation.location_code,
            value=observation.value_canonical,
            unit=observation.unit_canonical,
            threshold=threshold,
            description=description,
        )

    def _build_executive_summary(
        self,
        trend_summaries: list[VariableTrendSummary],
        alerts: list[ClimateAlert],
        quality_distribution: QualityDistribution,
        observations_considered: int,
    ) -> str:
        trend_map = {item.variable_code: item.trend_direction for item in trend_summaries}
        critical_or_high_alerts = sum(1 for alert in alerts if alert.severity in {"critical", "high"})
        return (
            "Relatorio com "
            f"{observations_considered} observacoes (validas={quality_distribution.valid}, "
            f"suspeitas={quality_distribution.suspect}, rejeitadas={quality_distribution.rejected}). "
            f"Tendencias: temperatura={trend_map.get('temperature_c', 'insufficient')}, "
            f"umidade={trend_map.get('humidity_pct', 'insufficient')}, "
            f"nivel_rio={trend_map.get('river_level_m', 'insufficient')}. "
            f"Alertas criticos/altos no periodo: {critical_or_high_alerts}."
        )

    def _as_utc(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


def _tracked_variables() -> dict[str, dict[str, float | str]]:
    return {
        "temperature_c": {"unit": "c", "trend_epsilon": 0.5},
        "humidity_pct": {"unit": "%", "trend_epsilon": 2.0},
        "rainfall_mm_1h": {"unit": "mm", "trend_epsilon": 5.0},
        "wind_speed_mps": {"unit": "m/s", "trend_epsilon": 1.5},
        "river_level_m": {"unit": "m", "trend_epsilon": 0.2},
        "river_flow_m3s": {"unit": "m3/s", "trend_epsilon": 100.0},
    }


planning_service = PlanningService()

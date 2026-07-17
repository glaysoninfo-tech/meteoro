from datetime import datetime, timezone
from types import SimpleNamespace

from app.modules.ingestion.service import ingestion_service


def _source(last_success_at: datetime | None) -> SimpleNamespace:
    return SimpleNamespace(
        expected_frequency_minutes=60,
        last_success_at=last_success_at,
        connector_config_json='{"schedule":{"minute_utc":5}}',
    )


def test_hourly_source_runs_on_utc_minute_offset_after_the_slot() -> None:
    source = _source(datetime(2026, 7, 15, 11, 5, tzinfo=timezone.utc))

    assert ingestion_service._source_is_due(source, datetime(2026, 7, 15, 12, 4, tzinfo=timezone.utc)) is False
    assert ingestion_service._source_is_due(source, datetime(2026, 7, 15, 12, 5, tzinfo=timezone.utc)) is True


def test_hourly_source_is_not_requeued_in_the_same_slot() -> None:
    source = _source(datetime(2026, 7, 15, 12, 5, 10, tzinfo=timezone.utc))

    assert ingestion_service._source_is_due(source, datetime(2026, 7, 15, 12, 50, tzinfo=timezone.utc)) is False


def test_reprocessing_profile_is_excluded_from_automatic_schedule() -> None:
    source = _source(None)
    source.connector_config_json = '{"schedule":{"enabled":false}}'

    assert ingestion_service._source_is_due(source, datetime(2026, 7, 15, 12, 5, tzinfo=timezone.utc)) is False

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from app.core.settings import settings


def test_alembic_upgrade_creates_idempotency_and_authority_schema(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'migration.sqlite'}"
    monkeypatch.setattr(settings, "database_url", database_url)
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))

    command.upgrade(config, "head")

    engine = create_engine(database_url)
    inspector = inspect(engine)
    assert "records_deduplicated" in {
        column["name"] for column in inspector.get_columns("ingestion_runs")
    }
    for table_name in ("observations", "official_alerts", "incident_reports"):
        assert "record_fingerprint" in {
            column["name"] for column in inspector.get_columns(table_name)
        }
    assert {"territories", "stations", "sensors"}.issubset(set(inspector.get_table_names()))
    assert {"station_id", "sensor_id"}.issubset(
        {column["name"] for column in inspector.get_columns("observations")}
    )
    with engine.connect() as connection:
        role_count = connection.execute(
            text("SELECT COUNT(*) FROM roles WHERE name = 'authority_approver'")
        ).scalar_one()
    assert role_count == 1
    engine.dispose()

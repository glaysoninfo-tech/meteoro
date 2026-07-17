"""Add territories, stations, sensors and PostGIS geometry columns.

Revision ID: 20260714_0009
Revises: 20260714_0008
Create Date: 2026-07-14 21:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260714_0009"
down_revision: Union[str, Sequence[str], None] = "20260714_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "territories",
        sa.Column("territory_id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("territory_code", sa.String(length=80), nullable=False),
        sa.Column("territory_name", sa.String(length=160), nullable=False),
        sa.Column("territory_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("geometry_geojson", sa.Text(), nullable=False),
        # Converted to geometry(GEOMETRY, 4326) below on PostgreSQL.
        sa.Column("geometry", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.organization_id"],
            name="fk_territories_organization_id_organizations",
        ),
        sa.UniqueConstraint("organization_id", "territory_code", name="uq_territory_org_code"),
    )
    op.create_index("ix_territories_org_type", "territories", ["organization_id", "territory_type"])

    op.create_table(
        "stations",
        sa.Column("station_id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("territory_id", sa.String(length=36), nullable=True),
        sa.Column("station_code", sa.String(length=80), nullable=False),
        sa.Column("station_name", sa.String(length=160), nullable=False),
        sa.Column("station_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("location_geojson", sa.Text(), nullable=False),
        # Converted to geometry(POINT, 4326) below on PostgreSQL.
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("elevation_meters", sa.Float(), nullable=True),
        sa.Column("installed_on", sa.Date(), nullable=True),
        sa.Column("decommissioned_on", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.organization_id"],
            name="fk_stations_organization_id_organizations",
        ),
        sa.ForeignKeyConstraint(
            ["territory_id"],
            ["territories.territory_id"],
            name="fk_stations_territory_id_territories",
        ),
        sa.UniqueConstraint("organization_id", "station_code", name="uq_station_org_code"),
    )
    op.create_index("ix_stations_org_status", "stations", ["organization_id", "status"])
    op.create_index("ix_stations_territory", "stations", ["territory_id"])

    op.create_table(
        "sensors",
        sa.Column("sensor_id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("station_id", sa.String(length=36), nullable=False),
        sa.Column("sensor_code", sa.String(length=80), nullable=False),
        sa.Column("sensor_name", sa.String(length=160), nullable=False),
        sa.Column("variable_code", sa.String(length=60), nullable=False),
        sa.Column("unit_canonical", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("manufacturer", sa.String(length=120), nullable=True),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("serial_number", sa.String(length=120), nullable=True),
        sa.Column("calibration_due_on", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.organization_id"],
            name="fk_sensors_organization_id_organizations",
        ),
        sa.ForeignKeyConstraint(
            ["station_id"],
            ["stations.station_id"],
            name="fk_sensors_station_id_stations",
        ),
        sa.UniqueConstraint("station_id", "sensor_code", name="uq_sensor_station_code"),
    )
    op.create_index("ix_sensors_org_status", "sensors", ["organization_id", "status"])
    op.create_index("ix_sensors_station", "sensors", ["station_id"])

    with op.batch_alter_table("sources") as batch_op:
        batch_op.add_column(sa.Column("station_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("sensor_id", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            "fk_sources_station_id_stations",
            "stations",
            ["station_id"],
            ["station_id"],
        )
        batch_op.create_foreign_key(
            "fk_sources_sensor_id_sensors",
            "sensors",
            ["sensor_id"],
            ["sensor_id"],
        )
    op.create_index("ix_sources_station", "sources", ["station_id"])
    op.create_index("ix_sources_sensor", "sources", ["sensor_id"])

    with op.batch_alter_table("observations") as batch_op:
        batch_op.add_column(sa.Column("station_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("sensor_id", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            "fk_observations_station_id_stations",
            "stations",
            ["station_id"],
            ["station_id"],
        )
        batch_op.create_foreign_key(
            "fk_observations_sensor_id_sensors",
            "sensors",
            ["sensor_id"],
            ["sensor_id"],
        )
    op.create_index(
        "ix_observations_station_time",
        "observations",
        ["organization_id", "station_id", "observed_at_utc"],
    )
    op.create_index("ix_observations_sensor_time", "observations", ["sensor_id", "observed_at_utc"])

    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
        op.execute(
            "ALTER TABLE territories ALTER COLUMN geometry "
            "TYPE geometry(GEOMETRY, 4326) "
            "USING CASE WHEN geometry_geojson IS NULL THEN NULL "
            "ELSE ST_SetSRID(ST_GeomFromGeoJSON(geometry_geojson), 4326) END"
        )
        op.execute(
            "ALTER TABLE stations ALTER COLUMN location "
            "TYPE geometry(POINT, 4326) "
            "USING CASE WHEN location_geojson IS NULL THEN NULL "
            "ELSE ST_SetSRID(ST_GeomFromGeoJSON(location_geojson), 4326) END"
        )
        op.execute("CREATE INDEX ix_territories_geometry_gist ON territories USING GIST (geometry)")
        op.execute("CREATE INDEX ix_stations_location_gist ON stations USING GIST (location)")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_stations_location_gist")
        op.execute("DROP INDEX IF EXISTS ix_territories_geometry_gist")

    op.drop_index("ix_observations_sensor_time", table_name="observations")
    op.drop_index("ix_observations_station_time", table_name="observations")
    with op.batch_alter_table("observations") as batch_op:
        batch_op.drop_constraint("fk_observations_sensor_id_sensors", type_="foreignkey")
        batch_op.drop_constraint("fk_observations_station_id_stations", type_="foreignkey")
        batch_op.drop_column("sensor_id")
        batch_op.drop_column("station_id")

    op.drop_index("ix_sources_sensor", table_name="sources")
    op.drop_index("ix_sources_station", table_name="sources")
    with op.batch_alter_table("sources") as batch_op:
        batch_op.drop_constraint("fk_sources_sensor_id_sensors", type_="foreignkey")
        batch_op.drop_constraint("fk_sources_station_id_stations", type_="foreignkey")
        batch_op.drop_column("sensor_id")
        batch_op.drop_column("station_id")

    op.drop_index("ix_sensors_station", table_name="sensors")
    op.drop_index("ix_sensors_org_status", table_name="sensors")
    op.drop_table("sensors")
    op.drop_index("ix_stations_territory", table_name="stations")
    op.drop_index("ix_stations_org_status", table_name="stations")
    op.drop_table("stations")
    op.drop_index("ix_territories_org_type", table_name="territories")
    op.drop_table("territories")

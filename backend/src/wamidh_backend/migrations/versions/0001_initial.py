"""Initial schema: telemetry, incidents and their audit log, with PostGIS (ADR 0002).

Revision ID: 0001
Revises:
Create Date: 2026-10-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geography

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.create_table(
        "telemetry",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("node_id", sa.Integer, nullable=False),
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("ts", sa.String(20), nullable=False),  # node clock, UTC
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("gas_ratio", sa.Float, nullable=False),
        sa.Column("temp_c", sa.Float, nullable=False),
        sa.Column("rh_pct", sa.Float, nullable=False),
        sa.Column("flame", sa.Boolean, nullable=False),
        sa.Column("fire_prob", sa.Float, nullable=False),
        sa.Column("battery_v", sa.Float, nullable=False),
    )
    op.create_index("ix_telemetry_node_id", "telemetry", ["node_id"])
    op.create_index("ix_telemetry_received_at", "telemetry", ["received_at"])

    op.create_table(
        "incident",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("first_node_id", sa.Integer, nullable=False),
        sa.Column("estimated_origin", sa.JSON, nullable=False),
        sa.Column("access_point", sa.JSON, nullable=True),
        sa.Column("node_ids", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assigned_crew", sa.Integer, nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("origin", Geography("POINT", srid=4326, spatial_index=False), nullable=True),
    )
    op.create_index("ix_incident_origin", "incident", ["origin"], postgresql_using="gist")

    op.create_table(
        "incident_event",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("incident_id", sa.Integer, sa.ForeignKey("incident.id"), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
    )
    op.create_index("ix_incident_event_incident_id", "incident_event", ["incident_id"])


def downgrade() -> None:
    op.drop_table("incident_event")
    op.drop_table("incident")
    op.drop_table("telemetry")

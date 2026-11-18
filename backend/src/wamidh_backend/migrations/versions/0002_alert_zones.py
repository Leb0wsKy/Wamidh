"""Alert zones, cell towers and public alerts (ADR 0003).

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geography

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "alert_zone",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(120), nullable=True),
        sa.Column("near", sa.String(120), nullable=True),
        sa.Column("population", sa.Integer, nullable=False),
        sa.Column("risk_level", sa.String(8), nullable=False),
        sa.Column("risk_percentile", sa.Float, nullable=True),
        sa.Column("building_count", sa.Integer, nullable=False),
        sa.Column("outline_json", sa.JSON, nullable=False),
        sa.Column(
            "outline", Geography("MULTIPOLYGON", srid=4326, spatial_index=False), nullable=False
        ),
    )
    op.create_index("ix_alert_zone_outline", "alert_zone", ["outline"], postgresql_using="gist")

    op.create_table(
        "cell_tower",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("radio", sa.String(8), nullable=False),
        sa.Column("net", sa.Integer, nullable=False),
        sa.Column("range_m", sa.Integer, nullable=False),
        sa.Column("samples", sa.Integer, nullable=False),
        sa.Column("lon", sa.Float, nullable=False),
        sa.Column("lat", sa.Float, nullable=False),
        sa.Column("location", Geography("POINT", srid=4326, spatial_index=False), nullable=False),
    )
    op.create_index("ix_cell_tower_location", "cell_tower", ["location"], postgresql_using="gist")

    op.create_table(
        "zone_tower",
        sa.Column("zone_id", sa.Integer, sa.ForeignKey("alert_zone.id"), primary_key=True),
        sa.Column("tower_id", sa.String(40), sa.ForeignKey("cell_tower.id"), primary_key=True),
    )

    op.create_table(
        "public_alert",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("incident_id", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_by", sa.String(80), nullable=False),
        sa.Column("zone_ids", sa.JSON, nullable=False),
        sa.Column("zone_labels", sa.JSON, nullable=False),
        sa.Column("tower_ids", sa.JSON, nullable=False),
        sa.Column("people", sa.Integer, nullable=False),
        sa.Column("message_ar", sa.Text, nullable=False),
        sa.Column("cap_xml", sa.Text, nullable=False),
        sa.Column("delivery", sa.String(40), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
    )
    op.create_index("ix_public_alert_incident_id", "public_alert", ["incident_id"])


def downgrade() -> None:
    op.drop_table("public_alert")
    op.drop_table("zone_tower")
    op.drop_table("cell_tower")
    op.drop_table("alert_zone")

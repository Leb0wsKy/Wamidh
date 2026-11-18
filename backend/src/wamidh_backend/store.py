"""Persistence (SQLAlchemy 2). SQLite for development; the same models run on PostgreSQL by
changing the URL (CLAUDE.md plans PostgreSQL + PostGIS for deployment)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from geoalchemy2 import Geography
from shapely.geometry import MultiPolygon, shape
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    func,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship

from wamidh_backend.core import Incident, IncidentEvent


class Base(DeclarativeBase):
    pass


class TelemetryRow(Base):
    __tablename__ = "telemetry"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    node_id: Mapped[int] = mapped_column(Integer, index=True)
    seq: Mapped[int] = mapped_column(Integer)
    ts: Mapped[str] = mapped_column(String(20))  # node clock, UTC
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    state: Mapped[str] = mapped_column(String(24))
    gas_ratio: Mapped[float] = mapped_column(Float)
    temp_c: Mapped[float] = mapped_column(Float)
    rh_pct: Mapped[float] = mapped_column(Float)
    flame: Mapped[bool] = mapped_column(Boolean)
    fire_prob: Mapped[float] = mapped_column(Float)
    battery_v: Mapped[float] = mapped_column(Float)


class IncidentRow(Base):
    __tablename__ = "incident"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(String(24))
    first_node_id: Mapped[int] = mapped_column(Integer)
    estimated_origin: Mapped[dict[str, Any]] = mapped_column(JSON)
    access_point: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    node_ids: Mapped[list[int]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    assigned_crew: Mapped[int | None] = mapped_column(Integer, nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Estimated origin as a WGS84 point (ADR 0002), for distance search over the history.
    # PostGIS geography on PostgreSQL; EWKT text on SQLite (unit tests), same code path.
    origin: Mapped[str | None] = mapped_column(
        Geography("POINT", srid=4326, spatial_index=False).with_variant(String, "sqlite"),
        nullable=True,
    )
    events: Mapped[list[IncidentEventRow]] = relationship(
        order_by="IncidentEventRow.id", cascade="all, delete-orphan"
    )


class IncidentEventRow(Base):
    """Audit log (CLAUDE.md: every step of an incident is kept)."""

    __tablename__ = "incident_event"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incident.id"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    type: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class AlertZoneRow(Base):
    """A population alert zone (ADR 0003), built offline by `zones/`."""

    __tablename__ = "alert_zone"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    near: Mapped[str | None] = mapped_column(String(120), nullable=True)
    population: Mapped[int] = mapped_column(Integer)
    risk_level: Mapped[str] = mapped_column(String(8))
    risk_percentile: Mapped[float | None] = mapped_column(Float, nullable=True)
    building_count: Mapped[int] = mapped_column(Integer)
    # GeoJSON for serving the map; geography for spatial queries (EWKT text on SQLite).
    outline_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    outline: Mapped[str] = mapped_column(
        Geography("MULTIPOLYGON", srid=4326, spatial_index=False).with_variant(String, "sqlite")
    )


class CellTowerRow(Base):
    """A cell tower from OpenCelliD (approximate, crowdsourced; ADR 0003)."""

    __tablename__ = "cell_tower"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)  # mcc-net-area-cell
    radio: Mapped[str] = mapped_column(String(8))
    net: Mapped[int] = mapped_column(Integer)
    range_m: Mapped[int] = mapped_column(Integer)
    samples: Mapped[int] = mapped_column(Integer)
    lon: Mapped[float] = mapped_column(Float)
    lat: Mapped[float] = mapped_column(Float)
    location: Mapped[str] = mapped_column(
        Geography("POINT", srid=4326, spatial_index=False).with_variant(String, "sqlite")
    )


class ZoneTowerRow(Base):
    __tablename__ = "zone_tower"
    zone_id: Mapped[int] = mapped_column(ForeignKey("alert_zone.id"), primary_key=True)
    tower_id: Mapped[str] = mapped_column(ForeignKey("cell_tower.id"), primary_key=True)


class PublicAlertRow(Base):
    """A public alert broadcast after the dispatcher confirmed it (ADR 0003)."""

    __tablename__ = "public_alert"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[int] = mapped_column(Integer, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    confirmed_by: Mapped[str] = mapped_column(String(80))
    zone_ids: Mapped[list[int]] = mapped_column(JSON)
    zone_labels: Mapped[list[str]] = mapped_column(JSON)  # Arabic names, as in the text
    tower_ids: Mapped[list[str]] = mapped_column(JSON)
    people: Mapped[int] = mapped_column(Integer)
    message_ar: Mapped[str] = mapped_column(Text)
    cap_xml: Mapped[str] = mapped_column(Text)
    delivery: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(16))  # CAP status: Exercise (simulated) or Actual


def _ewkt(point: dict[str, Any] | None) -> str | None:
    """EWKT of a {"lon", "lat"} point, or None when the point is missing or partial."""
    if not point or point.get("lon") is None or point.get("lat") is None:
        return None
    return f"SRID=4326;POINT({float(point['lon'])} {float(point['lat'])})"


def _utc(ts: datetime | None) -> datetime | None:
    # SQLite drops tzinfo; everything is stored as UTC.
    return ts.replace(tzinfo=UTC) if ts and ts.tzinfo is None else ts


class Store:
    def __init__(self, url: str) -> None:
        self._engine = create_engine(url, json_serializer=json.dumps)
        if self._engine.dialect.name == "postgresql":
            # Alembic owns the schema on PostgreSQL (ADR 0002): never create tables here.
            from wamidh_backend.db import schema_is_current

            if not schema_is_current(url):
                raise SystemExit(
                    "The database schema is not up to date. "
                    "Run: python -m wamidh_backend.db upgrade"
                )
        else:
            Base.metadata.create_all(self._engine)  # SQLite: unit tests, offline fallback

    def save_telemetry(self, t: dict[str, Any], received_at: datetime) -> None:
        fields = {
            k: t[k]
            for k in (
                "node_id",
                "seq",
                "ts",
                "state",
                "gas_ratio",
                "temp_c",
                "rh_pct",
                "flame",
                "fire_prob",
                "battery_v",
            )
        }
        with Session(self._engine) as s, s.begin():
            s.add(TelemetryRow(**fields, received_at=received_at))

    def telemetry_since(
        self, since: datetime, node_ids: list[int] | None = None
    ) -> dict[int, list[dict[str, Any]]]:
        """Readings received after `since`, per node, oldest first (server clock); only
        `node_ids` when given."""
        q = (
            select(TelemetryRow)
            .where(TelemetryRow.received_at >= since)
            .order_by(TelemetryRow.node_id, TelemetryRow.received_at, TelemetryRow.id)
        )
        if node_ids is not None:
            q = q.where(TelemetryRow.node_id.in_(node_ids))
        out: dict[int, list[dict[str, Any]]] = {}
        with Session(self._engine) as s:
            for r in s.scalars(q):
                at = _utc(r.received_at)
                assert at is not None
                out.setdefault(r.node_id, []).append(
                    {
                        "ts": at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "state": r.state,
                        "temp_c": r.temp_c,
                        "rh_pct": r.rh_pct,
                        "gas_ratio": r.gas_ratio,
                        "fire_prob": r.fire_prob,
                        "battery_v": r.battery_v,
                    }
                )
        return out

    def node_memory(self) -> dict[int, dict[str, Any]]:
        """Per node, from the telemetry table: last time in ALERT and in FIRE. Restores what
        the dashboard shows after a backend restart."""
        out: dict[int, dict[str, Any]] = {}
        with Session(self._engine) as s:
            times = (
                select(TelemetryRow.node_id, TelemetryRow.state, func.max(TelemetryRow.received_at))
                .where(TelemetryRow.state.in_(("ALERT", "FIRE")))
                .group_by(TelemetryRow.node_id, TelemetryRow.state)
            )
            for node_id, state, at in s.execute(times):
                out.setdefault(node_id, {})[state] = _utc(at)
        return out

    def incidents_near(self, lon: float, lat: float, radius_km: float) -> list[int]:
        """Ids of incidents whose origin is within `radius_km` of the point, nearest first."""
        if self._engine.dialect.name != "postgresql":
            raise NotImplementedError("distance search needs PostgreSQL + PostGIS (ADR 0002)")
        point = func.ST_GeogFromText(f"SRID=4326;POINT({float(lon)} {float(lat)})")
        q = (
            select(IncidentRow.id)
            .where(func.ST_DWithin(IncidentRow.origin, point, radius_km * 1000))
            .order_by(func.ST_Distance(IncidentRow.origin, point), IncidentRow.id)
        )
        with Session(self._engine) as s:
            return [int(i) for i in s.scalars(q)]

    def count_telemetry(self, node_id: int) -> int:
        with Session(self._engine) as s:
            q = (
                select(func.count())
                .select_from(TelemetryRow)
                .where(TelemetryRow.node_id == node_id)
            )
            return int(s.scalar(q) or 0)

    def save_incident(self, inc: Incident) -> None:
        with Session(self._engine) as s, s.begin():
            row = s.get(IncidentRow, inc.id)
            if row is None:
                row = IncidentRow(id=inc.id)
                s.add(row)
            row.status = inc.status
            row.first_node_id = inc.first_node_id
            row.estimated_origin = inc.estimated_origin
            row.origin = _ewkt(inc.estimated_origin)
            row.access_point = inc.access_point
            row.node_ids = sorted(inc.node_ids)
            row.created_at = inc.created_at
            row.acknowledged_at = inc.acknowledged_at
            row.assigned_crew = inc.assigned_crew
            for e in inc.events[len(row.events) :]:  # the audit log only grows
                row.events.append(IncidentEventRow(ts=e.ts, type=e.type, payload=e.payload))

    def load_incidents(self) -> list[Incident]:
        with Session(self._engine) as s:
            rows = s.scalars(select(IncidentRow).order_by(IncidentRow.id)).all()
            return [
                Incident(
                    id=r.id,
                    status=r.status,
                    first_node_id=r.first_node_id,
                    estimated_origin=r.estimated_origin,
                    created_at=_utc(r.created_at),  # type: ignore[arg-type]
                    access_point=r.access_point,
                    acknowledged_at=_utc(r.acknowledged_at),
                    node_ids=set(r.node_ids),
                    assigned_crew=r.assigned_crew,
                    events=[IncidentEvent(_utc(e.ts), e.type, e.payload) for e in r.events],  # type: ignore[arg-type]
                )
                for r in rows
            ]

    # --- alert zones and cell towers (ADR 0003) -------------------------------------------

    def replace_zones(self, zones: list[dict[str, Any]], towers: list[dict[str, Any]]) -> None:
        """Replace every zone and tower in one transaction (zones as GeoJSON-like dicts)."""
        with Session(self._engine) as s, s.begin():
            s.query(ZoneTowerRow).delete()
            s.query(AlertZoneRow).delete()
            s.query(CellTowerRow).delete()
            s.flush()
            for t in towers:
                lon, lat = t["geometry"]["coordinates"][:2]
                s.add(
                    CellTowerRow(
                        id=str(t["id"]),
                        radio=str(t["radio"]),
                        net=int(t["net"]),
                        range_m=int(t["range_m"]),
                        samples=int(t["samples"]),
                        lon=float(lon),
                        lat=float(lat),
                        location=f"SRID=4326;POINT({float(lon)} {float(lat)})",
                    )
                )
            s.flush()
            for z in zones:
                geom = shape(z["geometry"])
                if geom.geom_type == "Polygon":
                    geom = MultiPolygon([geom])
                s.add(
                    AlertZoneRow(
                        id=int(z["id"]),
                        name=z.get("name") or None,
                        near=z.get("near") or None,
                        population=int(z["population"]),
                        risk_level=str(z["risk_level"]),
                        risk_percentile=z.get("risk_percentile"),
                        building_count=int(z["building_count"]),
                        outline_json=geom.__geo_interface__,
                        outline=f"SRID=4326;{geom.wkt}",
                    )
                )
            s.flush()
            for z in zones:
                for tid in z.get("tower_ids") or []:
                    s.add(ZoneTowerRow(zone_id=int(z["id"]), tower_id=str(tid)))

    def _towers_by_zone(self, s: Session) -> dict[int, list[str]]:
        out: dict[int, list[str]] = {}
        for zt in s.scalars(select(ZoneTowerRow).order_by(ZoneTowerRow.tower_id)):
            out.setdefault(zt.zone_id, []).append(zt.tower_id)
        return out

    def zones_geojson(self) -> dict[str, Any]:
        with Session(self._engine) as s:
            towers = self._towers_by_zone(s)
            features = [
                {
                    "type": "Feature",
                    "geometry": z.outline_json,
                    "properties": {
                        "id": z.id,
                        "name": z.name,
                        "near": z.near,
                        "population": z.population,
                        "risk_level": z.risk_level,
                        "risk_percentile": z.risk_percentile,
                        "building_count": z.building_count,
                        "tower_ids": towers.get(z.id, []),
                    },
                }
                for z in s.scalars(select(AlertZoneRow).order_by(AlertZoneRow.id))
            ]
        return {"type": "FeatureCollection", "features": features}

    def towers_geojson(self) -> dict[str, Any]:
        with Session(self._engine) as s:
            features = [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [t.lon, t.lat]},
                    "properties": {
                        "id": t.id,
                        "radio": t.radio,
                        "net": t.net,
                        "range_m": t.range_m,
                        "samples": t.samples,
                    },
                }
                for t in s.scalars(select(CellTowerRow).order_by(CellTowerRow.id))
            ]
        return {"type": "FeatureCollection", "features": features}

    def zones_near(self, lon: float, lat: float, radius_km: float) -> list[dict[str, Any]]:
        """Zones whose outline is within `radius_km` of the point, nearest edge first."""
        if self._engine.dialect.name != "postgresql":
            raise NotImplementedError("zone search needs PostgreSQL + PostGIS (ADR 0002)")
        point = func.ST_GeogFromText(f"SRID=4326;POINT({float(lon)} {float(lat)})")
        distance = func.ST_Distance(AlertZoneRow.outline, point)
        q = (
            select(AlertZoneRow, distance)
            .where(func.ST_DWithin(AlertZoneRow.outline, point, radius_km * 1000))
            .order_by(distance, AlertZoneRow.id)
        )
        with Session(self._engine) as s:
            towers = self._towers_by_zone(s)
            return [
                {
                    "id": z.id,
                    "name": z.name,
                    "near": z.near,
                    "population": z.population,
                    "risk_level": z.risk_level,
                    "distance_km": round(float(d) / 1000, 2),
                    "tower_ids": towers.get(z.id, []),
                    "outline": z.outline_json,
                }
                for z, d in s.execute(q)
            ]

    # --- public alerts ---------------------------------------------------------------------

    def save_public_alert(self, alert: dict[str, Any]) -> int:
        with Session(self._engine) as s, s.begin():
            row = PublicAlertRow(**alert)
            s.add(row)
            s.flush()
            return int(row.id)

    def list_public_alerts(self) -> list[dict[str, Any]]:
        cols = [c.name for c in PublicAlertRow.__table__.columns]
        with Session(self._engine) as s:
            rows = s.scalars(select(PublicAlertRow).order_by(PublicAlertRow.id.desc())).all()
            return [
                {c: (_utc(getattr(r, c)) if c == "created_at" else getattr(r, c)) for c in cols}
                for r in rows
            ]

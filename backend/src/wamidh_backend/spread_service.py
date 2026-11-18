"""Fire spread forecasts for incidents (ADR 0004): one ensemble run per incident, fed from its
audit log and from the sensors still calm. Advisory only: nothing here triggers an action."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime, timedelta
from typing import Any, Protocol

from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry
from wamidh_spread.run import NodeRef, SpreadRun, Wind

from wamidh_backend.core import CLOSED, Incident, NodeInfo
from wamidh_backend.weather import WeatherService

log = logging.getLogger("wamidh.spread")
EVENT_KIND = {"node_fire": "FIRE", "fire_spread": "FIRE", "node_lost": "LOST"}


class Engine(Protocol):
    def start(
        self,
        first: NodeRef,
        t0: datetime,
        wind: Wind,
        nodes: list[NodeRef],
        time_scale: float,
    ) -> SpreadRun: ...


class _Fire:
    def __init__(self, run: SpreadRun, wind: dict[str, Any]) -> None:
        self.run = run
        self.wind = wind
        self.fed: set[tuple[int, str]] = set()
        self.last: dict[str, Any] | None = None
        self.last_at: datetime | None = None


class SpreadService:
    def __init__(
        self,
        engine: Engine,
        weather: WeatherService,
        nodes: Iterable[NodeInfo],
        time_scale: float = 1.0,
        zones: Callable[[], dict[str, Any]] | None = None,
        min_interval_s: float = 2.0,
    ) -> None:
        self.engine = engine
        self.weather = weather
        self.nodes = {n.node_id: n for n in nodes}
        self.time_scale = time_scale
        self.zones = zones
        self.min_interval = timedelta(seconds=min_interval_s)
        self._fires: dict[int, _Fire] = {}
        self._zone_shapes: list[tuple[dict[str, Any], BaseGeometry]] | None = None
        self._lock = threading.Lock()

    def forecast(
        self, inc: Incident, node_states: Mapping[int, str], now: datetime
    ) -> dict[str, Any] | None:
        """The current forecast for `inc` (None when it cannot be computed). Thread-safe: the
        refresh loop and HTTP requests may ask at the same time."""
        with self._lock:
            try:
                return self._forecast(inc, node_states, now)
            except Exception:
                log.exception("spread forecast failed for incident %s", inc.id)
                return None

    def _forecast(
        self, inc: Incident, node_states: Mapping[int, str], now: datetime
    ) -> dict[str, Any] | None:
        fire = self._fires.get(inc.id) or self._start(inc)
        if fire is None:
            return None
        closed = inc.status in CLOSED
        if closed:
            # Frozen at the end of the incident: what the model said when it was closed.
            now = max((e.ts for e in inc.events), default=inc.created_at)
            if fire.last is not None:
                return fire.last
        new = False
        for e in sorted(inc.events, key=lambda e: e.ts):
            kind = EVENT_KIND.get(e.type)
            node_id = e.payload.get("node_id")
            if kind is None or node_id is None or (int(node_id), kind) in fire.fed:
                continue
            fire.fed.add((int(node_id), kind))
            if e.type != "node_fire" or int(node_id) != inc.first_node_id:
                fire.run.observe(int(node_id), kind, e.ts)
            new = True
        if (
            fire.last is not None
            and not new
            and fire.last_at is not None
            and now - fire.last_at < self.min_interval
        ):
            return fire.last
        calm = {nid for nid, state in node_states.items() if state == "NORMAL"}
        fc = fire.run.forecast(now, calm)
        out = fc.to_json()
        out |= {
            "incident_id": inc.id,
            "wind_reading": fire.wind,
            "advisory": True,
            "closed": closed,
            "threatened_zones": self._threatened(out["horizons"]),
        }
        fire.last, fire.last_at = out, now
        return out

    def _start(self, inc: Incident) -> _Fire | None:
        first = self.nodes.get(inc.first_node_id)
        if first is None:
            return None
        t0 = next((e.ts for e in inc.events if e.type == "node_fire"), inc.created_at)
        reading = self.weather.wind(first.lat, first.lon, t0)
        wind = Wind(reading.from_deg, reading.speed_ms, reading.source)
        refs = [NodeRef(n.node_id, n.lon, n.lat) for n in self.nodes.values()]
        run = self.engine.start(
            NodeRef(first.node_id, first.lon, first.lat), t0, wind, refs, self.time_scale
        )
        fire = _Fire(run, reading.to_json())
        self._fires[inc.id] = fire
        log.info(
            "incident %s: spread ensemble started (wind %s from %.0f deg, %.1f m/s)",
            inc.id,
            reading.source,
            reading.from_deg,
            reading.speed_ms,
        )
        return fire

    def _threatened(self, horizons: Mapping[str, Any]) -> list[dict[str, Any]]:
        """Population zones touched by a probability contour: the earliest horizon reaching
        them, and the highest probability band at that horizon (20, 50 or 80 %)."""
        if self.zones is None:
            return []
        if self._zone_shapes is None:
            self._zone_shapes = [
                (f["properties"], shape(f["geometry"])) for f in self.zones()["features"]
            ]
        out: dict[int, dict[str, Any]] = {}
        for h in sorted(horizons, key=int):
            bands = [(f["properties"]["p"], shape(f["geometry"])) for f in horizons[h]["features"]]
            for props, geom in self._zone_shapes:
                zid = int(props["id"])
                hits = [p for p, area in bands if area.intersects(geom)]
                if zid not in out and hits:
                    out[zid] = {
                        "id": zid,
                        "name": props.get("name"),
                        "near": props.get("near"),
                        "population": props.get("population"),
                        "risk_level": props.get("risk_level"),
                        "horizon_min": int(h),
                        "p": max(hits),
                    }
        return sorted(out.values(), key=lambda z: (z["horizon_min"], -(z["population"] or 0)))

    def forget(self, incident_ids: Iterable[int]) -> None:
        with self._lock:
            for i in incident_ids:
                self._fires.pop(i, None)

"""FastAPI app: REST + WebSocket API (contracts/api.md), MQTT bridge, watchdog loop."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import math
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

import aiomqtt
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from wamidh_contracts import NODE_WILDCARD, parse_node_topic, station_cmd_topic

from wamidh_backend.alerts import AlertsConfig, cap_xml, propose
from wamidh_backend.broadcast import BroadcastProvider, SimulatedBroadcast
from wamidh_backend.core import CLOSED, Core, LiveEvent, iso
from wamidh_backend.history import thin
from wamidh_backend.routing import RoadGraph
from wamidh_backend.spread_service import SpreadService
from wamidh_backend.store import Store
from wamidh_backend.weather import WeatherService

log = logging.getLogger("wamidh.app")


def utcnow() -> datetime:
    return datetime.now(UTC)


class Hub:
    """Open dashboard connections; every live event goes to all of them."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()

    async def join(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.add(ws)

    def leave(self, ws: WebSocket) -> None:
        self._clients.discard(ws)

    async def broadcast(self, events: Iterable[LiveEvent]) -> None:
        for event in events:
            for ws in list(self._clients):
                try:
                    await ws.send_json(event)
                except Exception:  # noqa: BLE001 - a dead socket must not stop the others
                    self.leave(ws)


@dataclass
class MqttSettings:
    host: str
    port: int
    station_id: int = 1


class Runtime:
    """Background work: MQTT ingest, siren commands, watchdog. Absent in HTTP-only tests."""

    def __init__(self, core: Core, store: Store, hub: Hub, mqtt: MqttSettings, tick_s: float):
        self.core, self.store, self.hub, self.mqtt, self.tick_s = core, store, hub, mqtt, tick_s
        self.sirens: asyncio.Queue[tuple[str, int]] = asyncio.Queue()
        self.connected = False

    def siren(self, command: str, incident_id: int) -> None:
        self.sirens.put_nowait((command, incident_id))

    def persist(self, events: list[LiveEvent]) -> None:
        for e in events:
            if e["kind"] == "incident":
                inc = next(i for i in self.core.list_incidents() if i.id == e["incident"]["id"])
                self.store.save_incident(inc)

    async def _ingest(self, client: aiomqtt.Client) -> None:
        await client.subscribe(NODE_WILDCARD, qos=1)
        async for message in client.messages:
            topic = str(message.topic)
            raw = message.payload if isinstance(message.payload, bytes) else b""
            now = utcnow()
            events = self.core.handle(topic, raw, now)
            parsed = parse_node_topic(topic)
            if events and parsed and parsed[1] == "telemetry":
                self.store.save_telemetry(json.loads(raw), received_at=now)
            self.persist(events)
            await self.hub.broadcast(events)

    async def _send_sirens(self, client: aiomqtt.Client) -> None:
        while True:
            command, incident_id = await self.sirens.get()
            payload = {
                "siren": command,
                "incident_id": incident_id,
                "ts": utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            await client.publish(
                station_cmd_topic(self.mqtt.station_id), json.dumps(payload), qos=1
            )
            log.warning(
                "station %s: siren %s (incident %s)", self.mqtt.station_id, command, incident_id
            )

    async def mqtt_forever(self) -> None:
        while True:
            try:
                async with aiomqtt.Client(
                    self.mqtt.host, self.mqtt.port, identifier="wamidh-backend"
                ) as client:
                    self.connected = True
                    log.info("MQTT connected to %s:%s", self.mqtt.host, self.mqtt.port)
                    await asyncio.gather(self._ingest(client), self._send_sirens(client))
            except aiomqtt.MqttError as e:
                self.connected = False
                log.error("MQTT broker unreachable (%s), retrying in 3 s", e)
                await asyncio.sleep(3)

    async def watchdog_forever(self) -> None:
        while True:
            events = self.core.watchdog(utcnow())
            self.persist(events)
            await self.hub.broadcast(events)
            await asyncio.sleep(self.tick_s)


class StatusBody(BaseModel):
    status: str
    crew_id: int | None = None


class AssignBody(BaseModel):
    crew_id: int


class AlertBody(BaseModel):
    confirmed_by: str = Field(min_length=1, max_length=80, pattern=r"\S")


class ZoneSource(Protocol):
    """Alert zones and cell towers (the Store on PostgreSQL; a fake in HTTP tests)."""

    def zones_near(self, lon: float, lat: float, radius_km: float) -> list[dict[str, Any]]: ...
    def zones_geojson(self) -> dict[str, Any]: ...
    def towers_geojson(self) -> dict[str, Any]: ...


ALERTS_CONFIG = Path(__file__).resolve().parents[2] / "config" / "alerts.yaml"


def load_alerts_config(path: Path = ALERTS_CONFIG) -> AlertsConfig:
    import yaml

    return AlertsConfig.from_dict(yaml.safe_load(path.read_text(encoding="utf-8")))


def _metres(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance between two (lon, lat) points; fine for the last few hundred metres."""
    (lon1, lat1), (lon2, lat2) = map(lambda p: (math.radians(p[0]), math.radians(p[1])), (a, b))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * 6_371_000 * math.asin(math.sqrt(h))


def _parse_lat_lon(text: str) -> tuple[float, float]:
    """'lat,lon' -> (lon, lat)."""
    try:
        lat, lon = (float(v) for v in text.split(","))
    except ValueError as e:
        raise HTTPException(422, "from must be 'lat,lon'") from e
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise HTTPException(422, "from is out of range")
    return lon, lat


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def create_app(
    core: Core,
    store: Store,
    placement_dir: Path,
    mqtt: MqttSettings | None,
    watchdog_tick_s: float = 2.0,
    crews: list[dict[str, Any]] | None = None,
    stations: list[dict[str, Any]] | None = None,
    coverage_radius_m: float = 500,
    router: RoadGraph | None = None,
    history_max_points: int = 120,
    zones_store: ZoneSource | None = None,
    broadcast: BroadcastProvider | None = None,
    alerts_cfg: AlertsConfig | None = None,
    weather: WeatherService | None = None,
    spread: SpreadService | None = None,
    spread_refresh_s: float = 0,
) -> FastAPI:
    crews = crews or []
    zones: ZoneSource = zones_store or store
    radio: BroadcastProvider = broadcast or SimulatedBroadcast()
    alerts = alerts_cfg or load_alerts_config()
    stations = stations or []
    hub = Hub()
    core.restore(store.load_incidents())
    core.restore_memory(store.node_memory())
    runtime = Runtime(core, store, hub, mqtt, watchdog_tick_s) if mqtt else None
    if runtime:
        core.attach_siren(runtime.siren)

    def node_states() -> dict[int, str]:
        return {n.info.node_id: n.state for n in core.list_nodes()}

    async def spread_forever() -> None:
        """Refresh the forecast of every burning incident, then tell the dashboards: the
        calm sensors keep informing the model even when nothing new is detected."""
        assert spread is not None
        while True:
            for inc in [i for i in core.list_incidents() if i.status not in CLOSED]:
                fc = await asyncio.to_thread(spread.forecast, inc, node_states(), utcnow())
                if fc is not None:
                    await hub.broadcast(
                        [
                            {
                                "kind": "forecast",
                                "incident_id": inc.id,
                                "computed_at": fc["computed_at"],
                            }
                        ]
                    )
            await asyncio.sleep(spread_refresh_s)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        tasks = (
            [
                asyncio.create_task(runtime.mqtt_forever()),
                asyncio.create_task(runtime.watchdog_forever()),
            ]
            if runtime
            else []
        )
        if spread is not None and spread_refresh_s > 0:
            tasks.append(asyncio.create_task(spread_forever()))
        yield
        for t in tasks:
            t.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await t

    app = FastAPI(title="Wamidh API", version="1.0", lifespan=lifespan)
    gateways = [
        {
            "id": f["properties"]["gateway_id"],
            "lon": f["geometry"]["coordinates"][0],
            "lat": f["geometry"]["coordinates"][1],
            "elevation_m": f["properties"]["elevation_m"],
            "nodes_assigned": f["properties"]["nodes_assigned"],
        }
        for f in _read_json(placement_dir / "gateways.geojson")["features"]
    ]
    risk: dict[str, Any] = _read_json(placement_dir / "risk.json")

    def incident_or_404(incident_id: int) -> None:
        if incident_id not in {i.id for i in core.list_incidents()}:
            raise HTTPException(404, f"incident {incident_id} not found")

    @app.get("/api/v1/health")
    def health() -> dict[str, Any]:
        return {
            "mqtt_connected": runtime.connected if runtime else None,
            "nodes": len(core.list_nodes()),
        }

    @app.get("/api/v1/nodes")
    def nodes() -> list[dict[str, Any]]:
        return [
            {
                **n.to_json(),
                "link": core.stats(n.info.node_id),
                "coverage_radius_m": coverage_radius_m,
            }
            for n in core.list_nodes()
        ]

    @app.get("/api/v1/gateways")
    def list_gateways() -> list[dict[str, Any]]:
        return gateways

    @app.get("/api/v1/risk-map")
    def risk_map() -> dict[str, Any]:
        return risk

    @app.get("/api/v1/history")
    def history(
        minutes: int = Query(60, ge=1, le=24 * 60),
        nodes: str | None = Query(None, pattern=r"^\d+(,\d+)*$"),
    ) -> dict[str, Any]:
        """Recent readings of the installed sensors (all, or `nodes=1,2,3`), for the trends.
        With 200 sensors the dashboard asks only for the ones on screen."""
        now = utcnow()
        since = now - timedelta(minutes=minutes)
        wanted = [int(n) for n in nodes.split(",")] if nodes else None
        recent = store.telemetry_since(since, wanted)
        return {
            "since": iso(since),
            "now": iso(now),
            # Gaps longer than this mean the sensor was silent (the timeline shows them grey).
            "silent_after_s": dict(core.silent_after_s),
            "nodes": [
                {
                    "node_id": n.info.node_id,
                    "points": thin(recent.get(n.info.node_id, []), history_max_points),
                }
                for n in core.list_nodes()
                if wanted is None or n.info.node_id in wanted
            ],
        }

    @app.get("/api/v1/crews")
    def list_crews() -> list[dict[str, Any]]:
        return crews

    @app.get("/api/v1/stations")
    def list_stations() -> list[dict[str, Any]]:
        return stations

    @app.get("/api/v1/incidents")
    def incidents(
        near: str | None = None,
        radius_km: float = Query(5, gt=0, le=100),
    ) -> list[dict[str, Any]]:
        """All incidents; with `near=lat,lon`, only those within `radius_km`, nearest first."""
        if near is None:
            return [i.to_json() for i in core.list_incidents()]
        lon, lat = _parse_lat_lon(near)
        try:
            ids = store.incidents_near(lon, lat, radius_km)
        except NotImplementedError as e:
            raise HTTPException(501, str(e)) from e
        by_id = {i.id: i for i in core.list_incidents()}
        return [by_id[i].to_json() for i in ids if i in by_id]

    async def publish(incident_id: int) -> dict[str, Any]:
        inc = next(i for i in core.list_incidents() if i.id == incident_id)
        store.save_incident(inc)
        event = {"kind": "incident", "incident": inc.to_json()}
        await hub.broadcast([event])
        return inc.to_json()

    @app.post("/api/v1/incidents/{incident_id}/ack")
    async def acknowledge(incident_id: int) -> dict[str, Any]:
        incident_or_404(incident_id)
        try:
            core.acknowledge(incident_id, utcnow())
        except ValueError as e:
            raise HTTPException(409, str(e)) from e
        return await publish(incident_id)

    @app.post("/api/v1/incidents/{incident_id}/status")
    async def set_status(incident_id: int, body: StatusBody) -> dict[str, Any]:
        incident_or_404(incident_id)
        try:
            core.set_status(incident_id, body.status, utcnow(), crew_id=body.crew_id)
        except ValueError as e:
            raise HTTPException(409, str(e)) from e
        return await publish(incident_id)

    @app.post("/api/v1/incidents/{incident_id}/assign")
    async def assign(incident_id: int, body: AssignBody) -> dict[str, Any]:
        incident_or_404(incident_id)
        if body.crew_id not in {c["id"] for c in crews}:
            raise HTTPException(404, f"crew {body.crew_id} not found")
        try:
            core.assign(incident_id, body.crew_id, utcnow())
        except ValueError as e:
            raise HTTPException(409, str(e)) from e
        return await publish(incident_id)

    @app.get("/api/v1/incidents/{incident_id}/route")
    def route(
        incident_id: int,
        from_: str | None = Query(None, alias="from"),
        crew_id: int | None = None,
    ) -> dict[str, Any]:
        """Drive from the crew (live GPS, else its station) to the access point, then walk."""
        incident_or_404(incident_id)
        if router is None:
            raise HTTPException(503, "routing is not configured (road network not loaded)")
        inc = next(i for i in core.list_incidents() if i.id == incident_id)
        node = next(n for n in core.list_nodes() if n.info.node_id == inc.first_node_id)
        target = (node.info.lon, node.info.lat)
        if from_ is not None:
            origin, source = _parse_lat_lon(from_), "gps"
        else:
            crew = next((c for c in crews if c["id"] == crew_id), None)
            station_id = crew["station_id"] if crew else None
            station = next((s for s in stations if s["id"] == station_id), None)
            station = station or (stations[0] if stations else None)
            if station is None:
                raise HTTPException(422, "no origin: pass from=lat,lon or configure a station")
            origin, source = (station["lon"], station["lat"]), "station"
        ap = inc.access_point
        end = (ap["lon"], ap["lat"]) if ap else target
        drive = router.route(origin, end)
        if drive is None:
            raise HTTPException(404, "no road route found")
        # The last metres from the road to the node are on foot (nodes sit in the forest).
        walk_from = (drive.geometry[-1][0], drive.geometry[-1][1])
        return {
            "incident_id": incident_id,
            "origin": {"lon": origin[0], "lat": origin[1], "source": source},
            "target": {"node_id": node.info.node_id, "lon": target[0], "lat": target[1]},
            "drive": drive.to_json(),
            "walk": {
                "geometry": [list(walk_from), list(target)],
                "distance_m": round(_metres(walk_from, target), 1),
            },
        }

    # --- fire spread forecast (ADR 0004) ----------------------------------------------------

    @app.get("/api/v1/incidents/{incident_id}/forecast")
    async def forecast(incident_id: int) -> dict[str, Any]:
        """Where the fire is likely to be within 15/30/60/120 min. Advisory only."""
        incident_or_404(incident_id)
        if spread is None:
            raise HTTPException(503, "the spread engine is not configured")
        inc = next(i for i in core.list_incidents() if i.id == incident_id)
        fc = await asyncio.to_thread(spread.forecast, inc, node_states(), utcnow())
        if fc is None:
            raise HTTPException(503, f"no forecast for incident {incident_id} (see the log)")
        return fc

    @app.get("/api/v1/weather")
    async def wind_now(
        lat: float = Query(ge=-90, le=90), lon: float = Query(ge=-180, le=180)
    ) -> dict[str, Any]:
        """Wind now at a point (OpenWeatherMap, else last known, else the default)."""
        if weather is None:
            raise HTTPException(503, "weather is not configured")
        reading = await asyncio.to_thread(weather.wind, lat, lon, utcnow())
        return reading.to_json()

    # --- population alerts (ADR 0003) ------------------------------------------------------

    @app.get("/api/v1/zones")
    def list_zones() -> dict[str, Any]:
        return zones.zones_geojson()

    @app.get("/api/v1/towers")
    def list_towers() -> dict[str, Any]:
        return zones.towers_geojson()

    def proposal_for(incident_id: int) -> Any:
        incident_or_404(incident_id)
        inc = next(i for i in core.list_incidents() if i.id == incident_id)
        origin = inc.estimated_origin
        try:
            near = zones.zones_near(origin["lon"], origin["lat"], alerts.concern_radius_km)
        except NotImplementedError as e:
            raise HTTPException(501, str(e)) from e
        return inc, propose(inc.to_json(), near, alerts)

    @app.get("/api/v1/incidents/{incident_id}/alert-proposal")
    def alert_proposal(incident_id: int) -> dict[str, Any]:
        """Who a public alert would reach. Nothing is sent from here."""
        return dict(proposal_for(incident_id)[1].to_json())

    @app.post("/api/v1/incidents/{incident_id}/alert")
    async def send_alert(incident_id: int, body: AlertBody) -> dict[str, Any]:
        """Broadcast the public alert. Only on a dispatcher's confirmation, after the
        acknowledgement: the backend never alerts the population on its own."""
        inc, proposal = proposal_for(incident_id)
        if inc.status in ("NEW", "STATION_NOTIFIED"):
            raise HTTPException(409, f"acknowledge incident {incident_id} before alerting")
        if inc.status in CLOSED:
            raise HTTPException(409, f"incident {incident_id} is {inc.status}")
        if not proposal.zones:
            raise HTTPException(409, "no population zone near this incident")
        now = utcnow()
        xml = cap_xml(proposal, now, exercise=radio.exercise, cfg=alerts)
        delivery = radio.send(xml, proposal.tower_ids)
        record = {
            "incident_id": incident_id,
            "created_at": now,
            "confirmed_by": body.confirmed_by.strip(),
            "zone_ids": [z["id"] for z in proposal.zones],
            "zone_labels": [z["label"] for z in proposal.zones],
            "tower_ids": proposal.tower_ids,
            "people": proposal.people,
            "message_ar": proposal.message_ar,
            "cap_xml": xml,
            "delivery": delivery,
            "status": "Exercise" if radio.exercise else "Actual",
        }
        alert_id = store.save_public_alert(record)
        audit = ("zone_ids", "people", "confirmed_by", "delivery")
        core.record(
            incident_id, "public_alert", {"alert_id": alert_id} | {k: record[k] for k in audit}, now
        )
        await publish(incident_id)
        return {**record, "id": alert_id, "created_at": iso(now)}

    @app.get("/api/v1/alerts")
    def public_alerts(active: bool = False) -> list[dict[str, Any]]:
        """Public alerts as residents received them: no sensor data, no dispatcher name."""
        status = {i.id: i.status for i in core.list_incidents()}
        out = []
        for a in store.list_public_alerts():
            live = status.get(a["incident_id"]) not in CLOSED | {None}
            if active and not live:
                continue
            out.append(
                {
                    "id": a["id"],
                    "incident_id": a["incident_id"],
                    "created_at": iso(a["created_at"]),
                    "zones": [
                        {"id": i, "label": label}
                        for i, label in zip(a["zone_ids"], a["zone_labels"], strict=True)
                    ],
                    "people": a["people"],
                    "headline": a["message_ar"].split("\n", 1)[0],
                    "message_ar": a["message_ar"],
                    "status": a["status"],
                    "delivery": a["delivery"],
                    "active": live,
                }
            )
        return out

    @app.websocket("/api/v1/ws")
    async def ws(socket: WebSocket) -> None:
        await hub.join(socket)
        try:
            while True:
                await socket.receive_text()  # keep-alive; clients do not send commands here
        except WebSocketDisconnect:
            hub.leave(socket)

    return app

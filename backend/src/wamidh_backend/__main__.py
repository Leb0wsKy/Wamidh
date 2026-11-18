"""Run the backend.

python -m wamidh_backend [--config backend/config/dev.yaml]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import timedelta
from pathlib import Path
from typing import Any

import uvicorn
import yaml
from wamidh_spread.engine import SpreadEngine

from wamidh_backend.app import MqttSettings, create_app
from wamidh_backend.core import Core, NodeInfo
from wamidh_backend.db import check_reachable, database_url, is_postgres
from wamidh_backend.routing import RoadGraph
from wamidh_backend.spread_service import SpreadService
from wamidh_backend.store import Store
from wamidh_backend.weather import OpenWeatherMap, WeatherService, read_secret

REPO = Path(__file__).resolve().parents[3]
log = logging.getLogger("wamidh_backend")


def load_roads(cfg: dict, points: list[tuple[float, float]]) -> RoadGraph | None:  # type: ignore[type-arg]
    """Road graph around the nodes and stations, or None (Go then has no in-app route)."""
    r = cfg.get("routing")
    if not r:
        return None
    path = REPO / r["roads"]
    if not path.exists():
        log.warning("routing disabled: %s missing (run placement step 01)", path)
        return None
    pad = r["pad_deg"]
    lons, lats = [p[0] for p in points], [p[1] for p in points]
    bbox = (min(lons) - pad, min(lats) - pad, max(lons) + pad, max(lats) + pad)
    t = time.perf_counter()
    graph = RoadGraph.from_shapefile(path, bbox, r["speeds_kmh"])
    log.info("road graph %s vertices/edges built in %.1f s", graph.size, time.perf_counter() - t)
    return graph


def build_spread(
    cfg: dict[str, Any], nodes: list[NodeInfo], store: Store
) -> tuple[WeatherService, SpreadService | None]:
    """Wind (OpenWeatherMap, key from OPENWEATHER_API_KEY) and the spread engine (ADR 0004)."""
    w = cfg.get("weather", {})
    key = read_secret("OPENWEATHER_API_KEY", REPO, os.environ)
    provider = OpenWeatherMap(key, timeout_s=float(w.get("timeout_s", 4))) if key else None
    if provider is None:
        log.warning("weather: no OPENWEATHER_API_KEY, the configured default wind is used")
    weather = WeatherService(
        provider, float(w.get("cache_s", 600)), w.get("default", {}), w.get("demo_override")
    )
    if w.get("demo_override"):
        log.warning("weather: DEMO wind override %s in use", w["demo_override"])
    s = cfg.get("spread")
    if not s:
        return weather, None
    engine = SpreadEngine.from_config(REPO / s["config"])
    spread = SpreadService(
        engine,
        weather,
        nodes,
        time_scale=float(s.get("time_scale", 1)),
        zones=store.zones_geojson,
    )
    log.info("spread engine ready (time scale x%s)", s.get("time_scale", 1))
    return weather, spread


def main() -> None:
    parser = argparse.ArgumentParser(description="Wamidh backend")
    parser.add_argument("--config", type=Path, default=REPO / "backend" / "config" / "dev.yaml")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(name)s: %(message)s", datefmt="%H:%M:%S"
    )
    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))

    registry_path = REPO / cfg["registry"]
    if not registry_path.exists():
        raise SystemExit(f"{registry_path} missing: run `python -m wamidh_sim.provision`")
    nodes = [
        NodeInfo(
            n["node_id"],
            bytes.fromhex(n["key_hex"]),
            n["lon"],
            n["lat"],
            n.get("risk_percentile"),
            n.get("gateway_id"),
            n.get("access"),
        )
        for n in json.loads(registry_path.read_text(encoding="utf-8"))["nodes"]
    ]
    url = database_url(cfg, REPO, os.environ)
    if is_postgres(url):
        check_reachable(url)
    else:
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)

    inc = cfg["incidents"]
    core = Core(
        nodes,
        silent_after_s=cfg["silent_after_s"],
        siren=lambda *_: None,  # replaced by the MQTT runtime
        join_radius_km=inc["join_radius_km"],
        join_window=timedelta(minutes=inc["join_window_min"]),
    )
    stations = cfg.get("stations", [])
    router = load_roads(
        cfg,
        [(n.lon, n.lat) for n in nodes] + [(s["lon"], s["lat"]) for s in stations],
    )
    store = Store(url)
    weather, spread = build_spread(cfg, nodes, store)
    m = cfg["mqtt"]
    app = create_app(
        core=core,
        store=store,
        placement_dir=REPO / cfg["placement_dir"],
        mqtt=MqttSettings(m["host"], m["port"], m["station_id"]),
        watchdog_tick_s=cfg["watchdog_tick_s"],
        crews=cfg.get("crews", []),
        stations=stations,
        coverage_radius_m=cfg.get("coverage_radius_m", 500),
        router=router,
        history_max_points=cfg.get("history", {}).get("max_points", 120),
        weather=weather,
        spread=spread,
        spread_refresh_s=float(cfg.get("spread", {}).get("refresh_s", 0)),
    )
    server = uvicorn.Server(
        uvicorn.Config(app, host=cfg["http"]["host"], port=cfg["http"]["port"], loop="none")
    )
    # aiomqtt needs a selector event loop on Windows.
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    asyncio.run(server.serve(), loop_factory=loop_factory)


if __name__ == "__main__":
    main()

"""A closed-loop fire for the demo (CLAUDE.md section 10, ADR 0004).

    python -m wamidh_sim.scenario --node 187            # a fire starts next to sensor 187
    python -m wamidh_sim.scenario --at 36.80,8.66 --wind-from 270 --wind-speed 7
    python -m wamidh_sim.scenario --node 12 --speed 60 --burn-min 20

A hidden "true" fire spreads with the same physics as the backend's engine. Its wind is the
real wind now (asked from the backend, OpenWeatherMap) changed by a random offset the backend
never sees, unless given. When the fire comes within detection range of a sensor, smoke builds
at that sensor (its control port); some fire minutes after the fire reaches it, the sensor
loses power (burned). The backend has to work the fire out from the alerts alone.

Fire time runs `--speed` times faster than the clock (60: one fire minute per second). Stops by
itself once the incident is closed, restoring every sensor it touched.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from pyproj import Transformer
from wamidh_spread.engine import SpreadEngine
from wamidh_spread.landscape import Landscape
from wamidh_spread.physics import arrival_times

from wamidh_sim.ignite import call
from wamidh_sim.node import DEFAULT_CONFIG, REPO, load

TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:32632", always_xy=True)
TO_LONLAT = Transformer.from_crs("EPSG:32632", "EPSG:4326", always_xy=True)
SPREAD_CONFIG = REPO / "spread" / "config" / "kroumirie.yaml"


@dataclass(frozen=True)
class Step:
    fire_min: float  # since the first detection
    node_id: int
    action: str  # "ignite": smoke reaches the sensor; "burn": the fire destroys it


def plan(
    ls: Landscape,
    arrival: NDArray[np.float64],
    nodes: list[dict[str, Any]],
    detect_radius_m: float,
    burn_min: float,
    until_min: float,
) -> list[Step]:
    """What happens to each sensor, in fire minutes since the first detection."""
    steps: list[tuple[float, int, str]] = []
    for n in nodes:
        x, y = TO_UTM.transform(n["lon"], n["lat"])
        own = ls.cell_of(x, y)
        if own is None:
            continue
        detect = float(arrival[ls.cells_within(x, y, detect_radius_m)].min())
        if math.isfinite(detect):
            steps.append((detect, int(n["node_id"]), "ignite"))
        reach = float(arrival[own])
        if math.isfinite(reach):
            steps.append((reach + burn_min, int(n["node_id"]), "burn"))
    if not steps:
        return []
    start = min(t for t, _, a in steps if a == "ignite")
    return [
        Step(round(t - start, 2), nid, action)
        for t, nid, action in sorted(steps)
        if t - start <= until_min
    ]


def _backend_json(url: str) -> Any:
    with urllib.request.urlopen(url, timeout=5) as res:
        return json.loads(res.read())


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a closed-loop simulated fire")
    where = parser.add_mutually_exclusive_group(required=True)
    where.add_argument("--node", type=int, help="the fire starts next to this sensor")
    where.add_argument("--at", help="ignition point lat,lon")
    parser.add_argument("--wind-from", type=float, help="hidden true wind direction (deg)")
    parser.add_argument("--wind-speed", type=float, help="hidden true wind speed (m/s)")
    parser.add_argument("--speed", type=float, default=60, help="fire minutes per real minute")
    parser.add_argument(
        "--burn-min", type=float, default=20, help="fire minutes to destroy a sensor"
    )
    parser.add_argument("--until-min", type=float, default=180, help="fire minutes to simulate")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()

    cfg, registry = load(args.config)
    nodes = registry["nodes"]
    rng = random.Random(args.seed)
    if args.node is not None:
        first = next((n for n in nodes if n["node_id"] == args.node), None)
        if first is None:
            raise SystemExit(f"sensor {args.node} is not provisioned")
        lat, lon = first["lat"], first["lon"]
    else:
        lat, lon = (float(v) for v in args.at.split(","))

    # Hidden truth: the real wind now, shifted by an offset the backend never sees.
    if args.wind_from is None or args.wind_speed is None:
        try:
            w = _backend_json(f"{cfg['backend_url']}/api/v1/weather?lat={lat}&lon={lon}")
            base_from, base_speed = float(w["from_deg"]), float(w["speed_ms"])
        except OSError:
            base_from, base_speed = 270.0, 5.0
        wind_from = (
            args.wind_from if args.wind_from is not None else (base_from + rng.gauss(0, 15)) % 360
        )
        wind_ms = (
            args.wind_speed
            if args.wind_speed is not None
            else max(2.0, base_speed * rng.uniform(1.0, 1.6))
        )
    else:
        wind_from, wind_ms = args.wind_from, args.wind_speed

    engine = SpreadEngine.from_config(SPREAD_CONFIG)
    ls = engine.landscape_around(lon, lat)
    x, y = TO_UTM.transform(lon, lat)
    if args.node is not None:
        # The fire starts upwind of the sensor, 100-350 m away (its smoke drifts to it).
        d, az = rng.uniform(100, 350), math.radians(wind_from + rng.gauss(0, 30))
        x, y = x + d * math.sin(az), y + d * math.cos(az)
    cell = ls.cell_of(x, y)
    if cell is None or ls.ros.ravel()[cell] <= 0:
        raise SystemExit(
            "the ignition point does not burn (water, bare rock, village); pick another"
        )
    fuel = rng.uniform(0.85, 1.15)
    arrival = arrival_times(ls, cell, engine.physics, wind_from, wind_ms, fuel)
    detect = float(engine.cfg["observations"]["detect_radius_m"])
    steps = plan(ls, arrival, nodes, detect, args.burn_min, args.until_min)
    if not steps:
        raise SystemExit("the fire reaches no sensor within the horizon")

    ign_lon, ign_lat = TO_LONLAT.transform(*ls.centre_of(cell))
    print(
        f"HIDDEN TRUTH  ignition {ign_lat:.5f},{ign_lon:.5f} - wind from {wind_from:.0f} deg "
        f"at {wind_ms:.1f} m/s - fuel x{fuel:.2f} - time x{args.speed:g}"
    )
    for s in steps:
        print(f"  +{s.fire_min:6.1f} fire min  sensor {s.node_id:>3}  {s.action}")

    ports = {n["node_id"]: n["control_port"] for n in nodes}
    touched: set[int] = set()
    t_start = time.monotonic()
    try:
        for s in steps:
            wait = t_start + s.fire_min * 60 / args.speed - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            if s.action == "ignite":
                call(ports[s.node_id], "POST", "/ignite?ramp=3")
            else:
                call(ports[s.node_id], "POST", "/power?on=0")
            touched.add(s.node_id)
            print(f"[{s.fire_min:6.1f}] sensor {s.node_id}: {s.action}")
        print("fire schedule done; waiting for the incident to be closed (Ctrl+C to stop now)")
        first_id = steps[0].node_id
        seen_open = False  # the backend needs a few seconds to open the incident
        while True:
            time.sleep(3)
            try:
                incidents = _backend_json(f"{cfg['backend_url']}/api/v1/incidents")
            except OSError:
                continue
            burning = any(
                i["status"] not in ("CLOSED", "FALSE_ALARM") and first_id in i["node_ids"]
                for i in incidents
            )
            seen_open = seen_open or burning
            if seen_open and not burning:
                break
    except KeyboardInterrupt:
        pass
    finally:
        for nid in touched:
            try:
                call(ports[nid], "POST", "/power?on=1")
                call(ports[nid], "POST", "/extinguish")
            except OSError:
                pass
        print(f"restored {len(touched)} sensors")


if __name__ == "__main__":
    main()

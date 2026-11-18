"""Two studies for the Phase 1 report (ADR 0004), on the real Kroumirie terrain.

    python spread/scripts/report_studies.py            # -> docs/figures/fig_spread_*.png|svg,
                                                       #    fig_impact.png|svg, spread_studies.json

1. Validation. Hidden fires start near randomly chosen sensors with a "true" wind the model
   never sees; the model starts from a measured wind that is off. After 1, 2 and 3 sensor
   detections we compare its heading, wind, ignition point and 1-hour footprint with the truth,
   and with the same ensemble that ignores the alerts.
2. Impact. For the same kind of fire: how big is it when the first crew arrives, if detection
   is by Wamidh (the sensor's real detection time) or later (assumed delays)? Crew travel
   is the real road route from the Ain Draham station to the sensor's access point.

Every delay that is not computed is an ASSUMPTION, written in the output.
"""

from __future__ import annotations

import json
import math
import random
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import yaml  # noqa: E402
from pyproj import Transformer  # noqa: E402

from wamidh_spread.engine import REPO, SpreadEngine  # noqa: E402
from wamidh_spread.physics import arrival_times  # noqa: E402
from wamidh_spread.run import NodeRef, SpreadRun, Wind  # noqa: E402

TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:32632", always_xy=True)
FIG = REPO / "docs" / "figures"
EMBER, COMPARE, INK = "#B3261E", "#2A78D6", "#1A1A19"
SEED = 2026
N_FIRES = 30
DETECT_LAG_MIN = 2.0  # ASSUMPTION: smoke to confirmed FIRE at the sensor (simulator ramp)

# Impact timeline (minutes). ASSUMPTIONS: no Tunisian statistic of detection delays exists in
# the sources we found; we bracket today's detection (lookout, patrol, call) at 30, 60 and 120.
ALERT_ACK_MIN = 2.0  # siren to acknowledgement
DISPATCH_MIN = 3.0  # crew boards the truck
WALK_M_PER_MIN = 67.0  # 4 km/h on foot from the access point
BASELINE_DETECTION_MIN = (30, 60, 120)


def sensors() -> list[dict[str, Any]]:
    feats = json.loads((REPO / "web/public/placement/nodes.geojson").read_text("utf-8"))["features"]
    return [
        {
            "node_id": int(f["properties"]["node_id"]),
            "lon": f["geometry"]["coordinates"][0],
            "lat": f["geometry"]["coordinates"][1],
            "access": (f["properties"]["access_lon"], f["properties"]["access_lat"]),
            "dist_to_access_m": float(f["properties"]["dist_to_access_m"]),
        }
        for f in feats
    ]


def heading_err(a: float, b: float) -> float:
    return abs((a - b + 180) % 360 - 180)


def true_head(ls: Any, arrival: np.ndarray, ign: int, until: float) -> float:
    xs, ys = ls.centres()
    ix, iy = ls.centre_of(ign)
    burned = arrival <= until
    d = np.where(burned, np.hypot(xs - ix, ys - iy), -1)
    k = int(d.argmax())
    return (math.degrees(math.atan2(xs[k] - ix, ys[k] - iy)) + 360) % 360


def jaccard(a: np.ndarray, b: np.ndarray) -> float:
    union = np.logical_or(a, b).sum()
    return float(np.logical_and(a, b).sum() / union) if union else float("nan")


def hidden_fire(engine: SpreadEngine, node: dict[str, Any], rng: random.Random) -> dict[str, Any] | None:
    measured_from = rng.uniform(0, 360)
    measured_ms = rng.uniform(4, 9)
    true_from = (measured_from + rng.gauss(0, 20)) % 360
    true_ms = measured_ms * rng.uniform(0.8, 1.4)
    fuel = rng.uniform(0.85, 1.15)
    ls = engine.landscape_around(node["lon"], node["lat"])
    x, y = TO_UTM.transform(node["lon"], node["lat"])
    d, az = rng.uniform(100, 400), math.radians(true_from + rng.gauss(0, 30))
    ign = ls.cell_of(x + d * math.sin(az), y + d * math.cos(az))
    if ign is None or ls.ros.ravel()[ign] <= 0:
        return None
    arrival = arrival_times(ls, ign, engine.physics, true_from, true_ms, fuel)
    return {
        "ls": ls,
        "ign": ign,
        "arrival": arrival,
        "measured": Wind(measured_from, measured_ms, "measured"),
        "true_from": true_from,
        "true_ms": true_ms,
    }


def detections(fire: dict[str, Any], nodes: list[dict[str, Any]], radius: float) -> list[tuple[float, int]]:
    ls, arrival = fire["ls"], fire["arrival"]
    out = []
    for n in nodes:
        x, y = TO_UTM.transform(n["lon"], n["lat"])
        if ls.cell_of(x, y) is None:
            continue
        t = float(arrival[ls.cells_within(x, y, radius)].min())
        if math.isfinite(t) and t <= 360:
            out.append((t + DETECT_LAG_MIN, n["node_id"]))
    return sorted(out)


# --- study 1: validation ---------------------------------------------------------------------


def validation(engine: SpreadEngine, nodes: list[dict[str, Any]]) -> dict[str, Any]:
    rng = random.Random(SEED)
    radius = float(engine.cfg["observations"]["detect_radius_m"])
    refs = [NodeRef(n["node_id"], n["lon"], n["lat"]) for n in nodes]
    rows: list[dict[str, Any]] = []
    attempts = 0
    while len(rows) < N_FIRES and attempts < 400:
        attempts += 1
        fire = hidden_fire(engine, rng.choice(nodes), rng)
        if fire is None:
            continue
        det = detections(fire, nodes, radius)
        if len(det) < 3:
            continue  # the study is about learning from successive alerts
        t0_fire, first_id = det[0]
        t0 = datetime(2026, 7, 20, 13, 0, tzinfo=UTC)
        at = lambda m: t0 + timedelta(minutes=m - t0_fire)  # noqa: E731
        run = SpreadRun(fire["ls"], engine.physics, engine.cfg, refs[[r.node_id for r in refs].index(first_id)],
                        t0, fire["measured"], refs, 1.0)
        blind = SpreadRun(fire["ls"], engine.physics, engine.cfg, refs[[r.node_id for r in refs].index(first_id)],
                          t0, fire["measured"], refs, 1.0)
        ix, iy = fire["ls"].centre_of(fire["ign"])
        row: dict[str, Any] = {"first_node": first_id, "steps": []}
        for k in (1, 2, 3):
            t_now = det[k - 1][0] + 1
            if k > 1:
                run.observe(det[k - 1][1], "FIRE", at(det[k - 1][0]))
            seen = {nid for _, nid in det[:k]}
            calm = {r.node_id for r in refs} - seen - {nid for t, nid in det if t <= t_now}
            fc = run.forecast(at(t_now), calm)
            fb = blind.forecast(at(t_now), set())
            truth_60 = fire["arrival"] <= t_now + 60
            head_true = true_head(fire["ls"], fire["arrival"], fire["ign"], t_now + 60)
            step = {
                "k": k,
                "heading_err": heading_err(fc.heading_deg, head_true),
                "heading_err_blind": heading_err(fb.heading_deg, head_true),
                "wind_err": heading_err(fc.wind_from_deg, fire["true_from"]),
                "wind_err_measured": heading_err(fire["measured"].from_deg, fire["true_from"]),
                "ignition_err_m": math.dist(fc.ignition_xy, (ix, iy)),
                "jaccard_60": jaccard(fc.probabilities[60] >= 0.5, truth_60),
                "jaccard_60_blind": jaccard(fb.probabilities[60] >= 0.5, truth_60),
                "ess": fc.ess_ratio,
            }
            row["steps"].append(step)
        rows.append(row)
        print(f"fire {len(rows)}: " + " | ".join(
            f"k={s['k']} head {s['heading_err']:.0f} (blind {s['heading_err_blind']:.0f}) "
            f"J60 {s['jaccard_60']:.2f}/{s['jaccard_60_blind']:.2f}" for s in row["steps"]), flush=True)
    summary = {}
    for k in (1, 2, 3):
        steps = [r["steps"][k - 1] for r in rows]
        med = lambda key: float(np.nanmedian([s[key] for s in steps]))  # noqa: E731
        summary[str(k)] = {
            key: round(med(key), 3)
            for key in ("heading_err", "heading_err_blind", "wind_err", "wind_err_measured",
                        "ignition_err_m", "jaccard_60", "jaccard_60_blind", "ess")
        }
    return {"n_fires": len(rows), "median_by_detections": summary, "fires": rows}


def figure_validation(result: dict[str, Any]) -> None:
    s = result["median_by_detections"]
    ks = [1, 2, 3]
    fig, axes = plt.subplots(1, 2, figsize=(6.6, 2.6))
    ax = axes[0]
    ax.plot(ks, [s[str(k)]["heading_err_blind"] for k in ks], "o--", color=COMPARE, label="ensemble without the alerts")
    ax.plot(ks, [s[str(k)]["heading_err"] for k in ks], "o-", color=EMBER, label="Wamidh (alerts assimilated)")
    ax.set_xticks(ks)
    ax.set_xlabel("sensors that have detected the fire")
    ax.set_ylabel("heading error (deg, median)")
    ax.set_title("Where is the fire going?")
    ax.legend(loc="upper right")
    ax = axes[1]
    ax.plot(ks, [s[str(k)]["jaccard_60_blind"] for k in ks], "o--", color=COMPARE)
    ax.plot(ks, [s[str(k)]["jaccard_60"] for k in ks], "o-", color=EMBER)
    ax.set_xticks(ks)
    ax.set_ylim(0, 1)
    ax.set_xlabel("sensors that have detected the fire")
    ax.set_ylabel("Jaccard, 1-hour footprint (median)")
    ax.set_title("How well is the next hour predicted?")
    fig.tight_layout()
    for ext in ("png", "svg"):
        fig.savefig(FIG / f"fig_spread_validation.{ext}")
    plt.close(fig)


# --- study 2: impact -------------------------------------------------------------------------


def road_graph(nodes: list[dict[str, Any]], station: tuple[float, float]) -> Any:
    sys.path.insert(0, str(REPO / "backend" / "src"))
    from wamidh_backend.routing import RoadGraph

    cfg = yaml.safe_load((REPO / "backend/config/dev.yaml").read_text("utf-8"))
    r = cfg["routing"]
    lons = [n["lon"] for n in nodes] + [station[0]]
    lats = [n["lat"] for n in nodes] + [station[1]]
    pad = r["pad_deg"]
    bbox = (min(lons) - pad, min(lats) - pad, max(lons) + pad, max(lats) + pad)
    return RoadGraph.from_shapefile(REPO / r["roads"], bbox, r["speeds_kmh"])


def impact(engine: SpreadEngine, nodes: list[dict[str, Any]]) -> dict[str, Any]:
    cfg = yaml.safe_load((REPO / "backend/config/dev.yaml").read_text("utf-8"))
    st = cfg["stations"][0]
    station = (st["lon"], st["lat"])
    graph = road_graph(nodes, station)
    radius = float(engine.cfg["observations"]["detect_radius_m"])
    rng = random.Random(SEED + 1)
    cases = {"typical": (316.0, 1.9), "windy": (316.0, 8.0)}  # ERA5 summer mean; windy: ASSUMPTION
    out: dict[str, Any] = {}
    for name, (wind_from, wind_ms) in cases.items():
        rows = []
        sample = rng.sample(nodes, 60)
        for node in sample:
            route = graph.route(station, node["access"])
            if route is None:
                continue
            travel = route.duration_s / 60 + node["dist_to_access_m"] / WALK_M_PER_MIN
            ls = engine.landscape_around(node["lon"], node["lat"])
            x, y = TO_UTM.transform(node["lon"], node["lat"])
            d, az = rng.uniform(100, 400), math.radians(wind_from + rng.gauss(0, 30))
            ign = ls.cell_of(x + d * math.sin(az), y + d * math.cos(az))
            if ign is None or ls.ros.ravel()[ign] <= 0:
                continue
            arrival = arrival_times(ls, ign, engine.physics, wind_from, wind_ms, rng.uniform(0.85, 1.15))
            detect = float(arrival[ls.cells_within(x, y, radius)].min()) + DETECT_LAG_MIN
            if not math.isfinite(detect):
                continue
            ha = lambda t: float((arrival <= t).sum()) * ls.cell_m**2 / 1e4  # noqa: E731
            response = ALERT_ACK_MIN + DISPATCH_MIN + travel
            row = {
                "node": node["node_id"],
                "travel_min": travel,
                "detect_min": detect,
                "eg_arrival_min": detect + response,
                "eg_ha": ha(detect + response),
            }
            for b in BASELINE_DETECTION_MIN:
                row[f"base{b}_ha"] = ha(b + response)
            rows.append(row)
        med = lambda key: float(np.median([r[key] for r in rows]))  # noqa: E731
        under = lambda key, lim: float(np.mean([r[key] <= lim for r in rows]))  # noqa: E731
        out[name] = {
            "wind_from_deg": wind_from,
            "wind_ms": wind_ms,
            "n": len(rows),
            "median_travel_min": round(med("travel_min"), 1),
            "median_detect_min": round(med("detect_min"), 1),
            "median_eg_arrival_min": round(med("eg_arrival_min"), 1),
            "median_ha": {"wamidh": round(med("eg_ha"), 2),
                          **{f"detected_at_{b}min": round(med(f"base{b}_ha"), 2) for b in BASELINE_DETECTION_MIN}},
            "share_at_most_3ha": {"wamidh": round(under("eg_ha", 3), 2),
                                  **{f"detected_at_{b}min": round(under(f"base{b}_ha", 3), 2) for b in BASELINE_DETECTION_MIN}},
            "rows": rows,
        }
        print(name, {k: v for k, v in out[name].items() if k != "rows"}, flush=True)
    out["assumptions"] = {
        "detect_lag_min": DETECT_LAG_MIN,
        "alert_ack_min": ALERT_ACK_MIN,
        "dispatch_min": DISPATCH_MIN,
        "walk_m_per_min": WALK_M_PER_MIN,
        "baseline_detection_min": list(BASELINE_DETECTION_MIN),
        "ignition": "100-400 m upwind of a placed sensor",
        "station": st["name"],
    }
    return out


def figure_impact(result: dict[str, Any]) -> None:
    labels = ["Wamidh"] + [f"detected\nat {b} min" for b in BASELINE_DETECTION_MIN]
    keys = ["wamidh"] + [f"detected_at_{b}min" for b in BASELINE_DETECTION_MIN]
    fig, axes = plt.subplots(1, 2, figsize=(6.6, 2.7), sharey=False)
    for ax, case, title in zip(axes, ("typical", "windy"), ("Typical summer wind", "Windy day"), strict=True):
        r = result[case]
        vals = [r["median_ha"][k] for k in keys]
        bars = ax.bar(labels, vals, color=[EMBER] + [COMPARE] * len(BASELINE_DETECTION_MIN))
        for b, v in zip(bars, vals, strict=True):
            ax.annotate(f"{v:.1f} ha", (b.get_x() + b.get_width() / 2, v), ha="center", va="bottom", fontsize=7)
        ax.set_title(f"{title} ({r['wind_ms']:.0f} m/s)")
        ax.set_ylabel("area burning when the crew arrives\n(median, ha)")
        ax.tick_params(axis="x", labelsize=7)
    fig.tight_layout()
    for ext in ("png", "svg"):
        fig.savefig(FIG / f"fig_impact.{ext}")
    plt.close(fig)


def main() -> None:
    plt.style.use(str(FIG / "wamidh.mplstyle"))
    engine = SpreadEngine.from_config(REPO / "spread/config/kroumirie.yaml")
    nodes = sensors()
    val = validation(engine, nodes)
    figure_validation(val)
    imp = impact(engine, nodes)
    figure_impact(imp)
    (FIG / "spread_studies.json").write_text(
        json.dumps({"note": "Generated by spread/scripts/report_studies.py; do not edit by hand.",
                    "seed": SEED, "validation": val, "impact": imp}, indent=1, default=float),
        encoding="utf-8",
    )
    print("written", FIG / "spread_studies.json")


if __name__ == "__main__":
    main()

"""Build the alert zones (ADR 0003).

    python -m zones.pipeline --config zones/config/kroumirie.yaml [--download]

Outputs in `outputs` (default data/processed): zones.geojson, towers.geojson, zones_summary.json.
Without the OpenCelliD file the zones are still built, with "towers: not available".
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import yaml

from zones.clusters import cluster_buildings
from zones.names import name_zones
from zones.population import settled_cells, zone_population
from zones.risk import zone_risk
from zones.towers import empty_towers, link_towers, parse_towers

UTM = "EPSG:32632"
REPO = Path(__file__).resolve().parents[3]


def _path(repo: Path, p: str) -> Path:
    q = Path(p)
    return q if q.is_absolute() else repo / q


def run(cfg: dict[str, Any], repo: Path = REPO) -> dict[str, Any]:
    bbox = tuple(cfg["bbox"])
    inp = {k: _path(repo, v) for k, v in cfg["inputs"].items()}
    out_dir = _path(repo, cfg["outputs"])
    out_dir.mkdir(parents=True, exist_ok=True)

    c = cfg["clusters"]
    buildings = gpd.read_file(inp["buildings"], bbox=bbox).to_crs(UTM)
    elements = pd.concat(
        [
            gpd.GeoDataFrame(
                {"kind": ["building"] * len(buildings)}, geometry=buildings.geometry.values, crs=UTM
            ),
            settled_cells(inp["worldpop"], bbox, c["min_people_per_cell"]),
        ],
        ignore_index=True,
    )
    zones = cluster_buildings(
        gpd.GeoDataFrame(elements, geometry="geometry", crs=UTM),
        c["eps_m"],
        c["min_buildings"],
        c["buffer_m"],
        c["simplify_m"],
    )

    places = gpd.read_file(inp["places"], bbox=bbox)
    places = places[places["fclass"].isin(cfg["names"]["place_classes"])].to_crs(UTM)
    names = name_zones(zones, places, cfg["names"]["radius_m"])

    population = zone_population(zones, inp["worldpop"])
    r = cfg["risk"]
    risk = zone_risk(zones, inp["susceptibility"], r["ring_m"], r["high"], r["medium"])

    t = cfg["towers"]
    if inp["towers"].exists():
        towers = parse_towers(inp["towers"], bbox, t["pad_m"])
        links = link_towers(zones, towers.to_crs(UTM), t["min_range_m"], t["max_range_m"])
        towers_status = f"{len(towers)} towers"
    else:
        towers = empty_towers()
        links = [[] for _ in range(len(zones))]
        towers_status = "not available"

    zones = zones.assign(
        name=[n["name"] for n in names],
        near=[n["near"] for n in names],
        population=population,
        risk_level=[x[0] for x in risk],
        risk_percentile=[x[1] for x in risk],
        tower_ids=links,
    )
    # Most people first: zone 1 is the largest settlement.
    zones = zones.sort_values("population", ascending=False, kind="stable").reset_index(drop=True)
    zones.insert(0, "id", range(1, len(zones) + 1))
    zones.to_crs("EPSG:4326").to_file(out_dir / "zones.geojson", driver="GeoJSON")
    towers.to_file(out_dir / "towers.geojson", driver="GeoJSON")

    summary = {
        "zones": int(len(zones)),
        "people_estimate": int(zones["population"].sum()) if len(zones) else 0,
        "by_risk": zones["risk_level"].value_counts().to_dict() if len(zones) else {},
        "towers": towers_status,
        "zones_without_tower": int(sum(1 for x in links if not x)),
        "sources": {
            "buildings_places": "OpenStreetMap (Geofabrik), ODbL",
            "population": "WorldPop 2020 constrained 100 m, CC BY 4.0 (modelled estimate)",
            "towers": "OpenCelliD, CC BY-SA 4.0 (crowdsourced, approximate)",
            "risk": "Wamidh placement model, susceptibility percentile",
        },
    }
    (out_dir / "zones_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Wamidh alert zones")
    parser.add_argument("--config", type=Path, default=REPO / "zones" / "config" / "kroumirie.yaml")
    parser.add_argument(
        "--download", action="store_true", help="fetch WorldPop and OpenCelliD first"
    )
    args = parser.parse_args()
    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    if args.download:
        from zones.download import download_all

        download_all(cfg, REPO)
    summary = run(cfg)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

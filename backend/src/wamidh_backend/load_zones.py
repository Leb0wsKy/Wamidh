"""Load the alert zones and cell towers built by `zones/` into the database (ADR 0003).

    python -m wamidh_backend.load_zones          # reads data/processed/{zones,towers}.geojson

Replaces the previous set in one transaction. Run after `python -m zones.pipeline`.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from .db import REPO, check_reachable, database_url
from .store import Store


def _features(path: Path) -> list[dict[str, Any]]:
    collection = json.loads(path.read_text(encoding="utf-8"))
    return [{**f["properties"], "geometry": f["geometry"]} for f in collection["features"]]


def load(store: Store, folder: Path) -> dict[str, int]:
    """Read `zones.geojson` and `towers.geojson` from `folder` into `store`; return counts."""
    zones = _features(folder / "zones.geojson")
    towers_path = folder / "towers.geojson"
    towers = _features(towers_path) if towers_path.exists() else []
    known = {str(t["id"]) for t in towers}
    for z in zones:  # a link to a tower missing from the file would break the foreign key
        z["tower_ids"] = [t for t in z.get("tower_ids") or [] if str(t) in known]
    store.replace_zones(zones, towers)
    links = sum(len(z["tower_ids"]) for z in zones)
    return {"zones": len(zones), "towers": len(towers), "links": links}


def main() -> None:
    import yaml

    parser = argparse.ArgumentParser(description="Load alert zones and cell towers")
    parser.add_argument("--config", type=Path, default=REPO / "backend" / "config" / "dev.yaml")
    parser.add_argument("--folder", type=Path, default=REPO / "data" / "processed")
    args = parser.parse_args()
    url = database_url(yaml.safe_load(args.config.read_text(encoding="utf-8")), REPO, os.environ)
    check_reachable(url)
    counts = load(Store(url), args.folder)
    print(f"Loaded {counts['zones']} zones, {counts['towers']} towers, {counts['links']} links.")


if __name__ == "__main__":
    main()

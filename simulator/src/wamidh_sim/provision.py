"""Install virtual nodes: pick the top-ranked optimised sites and give each a secret key.

    python -m wamidh_sim.provision --count 200

Writes config/dev/registry.json (git-ignored: it holds the node keys). The backend reads the
same file to know which nodes exist and how to verify their signatures, exactly as a real
installation registers each node's key.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
DEFAULT_SITES = REPO / "web" / "public" / "placement" / "nodes.geojson"
DEFAULT_REGISTRY = REPO / "config" / "dev" / "registry.json"


def build_registry(
    sites: dict[str, Any],
    count: int,
    base_port: int,
    seed: int | None = None,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The `count` top-ranked sites. A node already in `existing` keeps its key: growing the
    installation must not invalidate the sensors already in the field."""
    rng = random.SystemRandom() if seed is None else random.Random(seed)
    keys = {n["node_id"]: n["key_hex"] for n in (existing or {}).get("nodes", [])}
    ranked = sorted(sites["features"], key=lambda f: f["properties"]["rank"])[:count]
    nodes = []
    for i, f in enumerate(ranked, start=1):
        p = f["properties"]
        lon, lat = f["geometry"]["coordinates"][:2]
        gw = p.get("gateway_id") or None
        nodes.append(
            {
                "node_id": int(p["node_id"]),
                "lon": lon,
                "lat": lat,
                "risk_percentile": p.get("risk_percentile"),
                "gateway_id": int(gw) if gw else None,
                "access": {
                    "lon": p["access_lon"],
                    "lat": p["access_lat"],
                    "road_type": p["access_type"],
                },
                "key_hex": keys.get(int(p["node_id"]))
                or "".join(rng.choice("0123456789abcdef") for _ in range(64)),
                "control_port": base_port + i,
            }
        )
    return {"nodes": nodes}


def main() -> None:
    parser = argparse.ArgumentParser(description="Provision virtual nodes")
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--sites", type=Path, default=DEFAULT_SITES)
    parser.add_argument("--out", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--base-port", type=int, default=8100)
    args = parser.parse_args()

    sites = json.loads(args.sites.read_text(encoding="utf-8"))
    existing = json.loads(args.out.read_text(encoding="utf-8")) if args.out.exists() else None
    registry = build_registry(sites, args.count, args.base_port, existing=existing)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(registry, indent=2), encoding="utf-8")
    kept = len(
        {n["node_id"] for n in (existing or {}).get("nodes", [])}
        & {n["node_id"] for n in registry["nodes"]}
    )
    print(f"provisioned {len(registry['nodes'])} nodes ({kept} keys kept) -> {args.out}")


if __name__ == "__main__":
    main()

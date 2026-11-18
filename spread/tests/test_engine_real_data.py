"""The engine on the real Kroumirie rasters (skipped when the data is not downloaded)."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from wamidh_spread.engine import REPO, SpreadEngine
from wamidh_spread.run import NodeRef, Wind

CONFIG = REPO / "spread" / "config" / "kroumirie.yaml"
NODES = REPO / "data" / "processed" / "nodes.geojson"
needs_data = pytest.mark.skipif(
    not (REPO / "data" / "raw" / "gee" / "kroumirie_terrain.tif").exists() or not NODES.exists(),
    reason="pilot-zone rasters not downloaded (data/README.md)",
)


def sensors() -> list[NodeRef]:
    feats = json.loads(NODES.read_text(encoding="utf-8"))["features"]
    return [
        NodeRef(int(f["properties"]["node_id"]), *f["geometry"]["coordinates"][:2]) for f in feats
    ]


@needs_data
def test_a_real_fire_start_is_fast_and_its_forecast_is_coherent() -> None:
    engine = SpreadEngine.from_config(CONFIG)
    nodes = sensors()
    t0 = datetime(2026, 7, 20, 14, 0, tzinfo=UTC)

    start = time.perf_counter()
    run = engine.start(nodes[0], t0, Wind(270, 6, "test"), nodes)
    started = time.perf_counter() - start
    fc = run.forecast(t0 + timedelta(minutes=2), calm={n.node_id for n in nodes[1:]})

    assert started < 15  # 200 arrival maps on the 12 x 12 km window
    assert run.ls.rows == run.ls.cols == 120
    assert (run.ls.ros > 0).mean() > 0.5  # mostly burnable forest and shrubland
    assert np.all(fc.probability(120) >= fc.probability(60) - 1e-9)
    assert fc.to_json()["horizons"]["60"]["features"]

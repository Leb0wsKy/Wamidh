"""Entry point: the spread engine for one zone, built from its configuration (CLAUDE.md 7.5).

engine = SpreadEngine.from_config("spread/config/kroumirie.yaml")
run = engine.start(first=NodeRef(12, lon, lat), t0=..., wind=Wind(270, 6), nodes=[...])
run.observe(13, "FIRE", t)
forecast = run.forecast(now, calm={14, 15}).to_json()
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from wamidh_spread.landscape import Landscape
from wamidh_spread.physics import Physics
from wamidh_spread.run import TO_UTM, NodeRef, SpreadRun, Wind

REPO = Path(__file__).resolve().parents[3]


class SpreadEngine:
    def __init__(self, cfg: Mapping[str, Any], repo: Path = REPO) -> None:
        self.cfg = cfg
        self.repo = repo
        self.fuels = yaml.safe_load((repo / cfg["fuels"]).read_text(encoding="utf-8"))
        p = cfg["physics"]
        self.physics = Physics(
            midflame_factor=float(p["midflame_factor"]),
            max_length_to_breadth=float(p["max_length_to_breadth"]),
            upslope_coeff=float(p["upslope_coeff"]),
            downslope_coeff=float(p["downslope_coeff"]),
            horizon_limit_min=float(p["horizon_limit_min"]),
            wind_exponent=float(p.get("wind_exponent", 1.0)),
        )

    @staticmethod
    def from_config(path: str | Path, repo: Path = REPO) -> SpreadEngine:
        p = Path(path)
        p = p if p.is_absolute() else repo / p
        return SpreadEngine(yaml.safe_load(p.read_text(encoding="utf-8")), repo)

    def landscape_around(self, lon: float, lat: float) -> Landscape:
        r, g = self.cfg["rasters"], self.cfg["grid"]
        return Landscape.from_rasters(
            self.repo / r["terrain"],
            self.repo / r["landcover"],
            self.repo / r["ndvi"],
            self.fuels,
            TO_UTM.transform(lon, lat),
            float(g["window_m"]),
            float(g["cell_m"]),
        )

    def start(
        self,
        first: NodeRef,
        t0: datetime,
        wind: Wind,
        nodes: Iterable[NodeRef],
        time_scale: float = 1.0,
        seed: int | None = None,
    ) -> SpreadRun:
        """A new fire first detected by `first` at `t0`. `nodes`: every installed sensor (those
        outside the window are ignored)."""
        cfg = dict(self.cfg)
        if seed is not None:
            cfg["ensemble"] = {**cfg["ensemble"], "seed": seed}
        ls = self.landscape_around(first.lon, first.lat)
        return SpreadRun(ls, self.physics, cfg, first, t0, wind, nodes, time_scale)

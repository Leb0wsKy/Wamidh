"""On-node camera (ADR 0001): the image is analysed on the node and only feeds its fire decision.

`CameraModel.look` is a RULE-BASED PLACEHOLDER for the TinyML vision model, which will be trained
on day and night images (ADR 0001, "Training data"). What it imitates:
- by day, smoke and flames are visible: the probability follows the smoke level at the node;
- at night, smoke is invisible and only flames are seen: it responds only to a nearby fire
  (high smoke level) or to flames, and ignores smoke alone.
ASSUMPTION: thresholds and noise chosen by hand to give that behaviour, not measured.
"""

from __future__ import annotations

import math
import random
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Vision:
    prob: float  # probability that a fire is visible, 0-1
    night: bool  # evaluated in night mode (flames only)


class CameraModel:
    def __init__(self, seed: int, daylight: tuple[time, time], tz: ZoneInfo) -> None:
        self._rng = random.Random(seed)
        self._daylight = daylight
        self._tz = tz

    def is_day(self, now: datetime) -> bool:
        local = now.astimezone(self._tz).time()
        start, end = self._daylight
        return start <= local < end

    def look(self, now: datetime, smoke: float, flame: bool) -> Vision:
        noise = self._rng.gauss(0, 0.02)
        if self.is_day(now):
            p = 1 / (1 + math.exp(-12 * (smoke - 0.35))) + noise
            return Vision(prob=round(min(max(p, 0.0), 1.0), 3), night=False)
        fire_light = flame or smoke >= 0.7
        p = (0.93 if fire_light else 0.03) + noise
        return Vision(prob=round(min(max(p, 0.0), 1.0), 3), night=True)


def camera_from_config(cfg: Mapping[str, Any], seed: int) -> CameraModel:
    """`cfg` is the `camera:` section of simulator/config/demo.yaml."""
    start, end = (time.fromisoformat(t) for t in cfg["daylight_local"])
    return CameraModel(seed=seed, daylight=(start, end), tz=ZoneInfo(cfg["timezone"]))

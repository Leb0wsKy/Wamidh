"""Virtual sensors: what an ESP32 node with a BME688 and an IR flame sensor would read.

The ambient model is a plausible summer day in Kroumirie, not measured data.
ASSUMPTION: daily temperature 24 +/- 8 degC (peak 15:00), humidity 55 -/+ 25 %, solar charging
from 06:00 to 20:00. Smoke (0 = clean air, 1 = fire at the node) lowers the gas resistance,
heats and dries the air; flames are visible from smoke >= 0.85.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Readings:
    gas_ratio: float  # gas resistance / local baseline; smoke lowers it
    temp_c: float
    rh_pct: float
    flame: bool
    battery_v: float


class SensorModel:
    def __init__(self, seed: int) -> None:
        self._rng = random.Random(seed)

    def read(self, now: datetime, smoke: float) -> Readings:
        smoke = min(max(smoke, 0.0), 1.0)
        hour = now.hour + now.minute / 60
        day = math.sin(2 * math.pi * (hour - 9) / 24)  # +1 at 15:00, -1 at 03:00
        noise = self._rng.gauss

        temp = 24 + 8 * day + noise(0, 0.3) + 30 * smoke
        rh = 55 - 25 * day + noise(0, 1.0) - 30 * smoke
        gas = 1.0 + noise(0, 0.02) - 0.7 * smoke
        sun = max(0.0, math.sin(math.pi * (hour - 6) / 14)) if 6 <= hour <= 20 else 0.0
        battery = 3.7 + 0.35 * sun + noise(0, 0.01)

        return Readings(
            gas_ratio=round(min(max(gas, 0.05), 2.0), 3),
            temp_c=round(temp, 1),
            rh_pct=round(min(max(rh, 3.0), 100.0), 1),
            flame=smoke >= 0.85,
            battery_v=round(min(max(battery, 3.3), 4.2), 2),
        )

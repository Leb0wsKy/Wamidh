"""On-node fire decision (CLAUDE.md section 6.3 of the report: edge intelligence).

`fire_probability` is a RULE-BASED PLACEHOLDER for the TinyML classifier, which will be trained
on controlled smoke tests with the prototype. ASSUMPTION: weights chosen by hand so that clean
air stays near 0, fog (humid, gas dip, cool, no flame) stays below the alert threshold, and
smoke with heat reaches FIRE.
"""

from __future__ import annotations

import math

from wamidh_contracts import NodeReportedState

from wamidh_sim.camera import Vision
from wamidh_sim.sensors import Readings


def fire_probability(r: Readings, vision: Vision | None = None) -> float:
    z = (
        8.0 * (1.0 - r.gas_ratio)  # smoke lowers gas resistance
        + 0.25 * max(0.0, r.temp_c - 35.0)  # heat beyond a hot afternoon
        + 4.0 * r.flame
        - 0.04 * max(0.0, r.rh_pct - 60.0)  # very humid air: fog, not fire
        - 3.5
    )
    if vision is not None:
        # ASSUMPTION: camera weight chosen by hand (ADR 0001). By day the camera can confirm or
        # contradict; at night it can only confirm (smoke is invisible in the dark).
        seen = vision.prob - 0.3
        z += 3.0 * (max(0.0, seen) if vision.night else seen)
    return 1.0 / (1.0 + math.exp(-z))


class NodeStateMachine:
    """NORMAL / ALERT / FIRE. Escalates at once; calms down only after `clear_readings`
    consecutive readings below the alert threshold, so a flickering fire stays reported."""

    def __init__(self, alert: float = 0.4, fire: float = 0.8, clear_readings: int = 3) -> None:
        self.alert, self.fire, self.clear_readings = alert, fire, clear_readings
        self.state: NodeReportedState = "NORMAL"
        self._calm = 0

    def update(self, prob: float, flame: bool) -> NodeReportedState:
        if flame or prob >= self.fire:
            self.state, self._calm = "FIRE", 0
        elif prob >= self.alert:
            self._calm = 0
            if self.state == "NORMAL":
                self.state = "ALERT"
        else:
            self._calm += 1
            if self.state != "NORMAL" and self._calm >= self.clear_readings:
                self.state = "NORMAL"
        return self.state

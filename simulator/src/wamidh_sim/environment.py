"""The air around a node. `ignite` makes smoke build up over time, like a fire taking hold."""

from __future__ import annotations

from datetime import datetime


class SmokeEnvironment:
    def __init__(self) -> None:
        self._start_level = 0.0
        self._target = 0.0
        self._t0: datetime | None = None
        self._ramp_s = 0.0

    def set_target(self, target: float, ramp_s: float, now: datetime) -> None:
        self._start_level = self.level(now) if self._t0 else 0.0
        self._target = min(max(target, 0.0), 1.0)
        self._t0 = now
        self._ramp_s = max(ramp_s, 0.0)

    def level(self, now: datetime) -> float:
        if self._t0 is None:
            return 0.0
        if self._ramp_s == 0:
            return self._target
        frac = min(max((now - self._t0).total_seconds() / self._ramp_s, 0.0), 1.0)
        return self._start_level + (self._target - self._start_level) * frac

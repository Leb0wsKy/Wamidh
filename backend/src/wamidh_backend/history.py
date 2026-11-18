"""Recent sensor history for the dashboard's trends and timeline (GET /api/v1/history)."""

from __future__ import annotations

from typing import Any

Point = dict[str, Any]


def thin(points: list[Point], max_points: int) -> list[Point]:
    """At most ~`max_points` readings, evenly sampled, always keeping both ends and every
    reading where the state changes (the timeline must show exactly when a sensor went into
    ALERT or FIRE, whatever the sampling)."""
    if len(points) <= max_points:
        return points
    changes = {i for i in range(1, len(points)) if points[i]["state"] != points[i - 1]["state"]}
    budget = max(2, max_points - len(changes))
    step = (len(points) - 1) / (budget - 1)
    sampled = {round(k * step) for k in range(budget)}
    return [points[i] for i in sorted(sampled | changes)]

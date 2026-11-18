"""Delivery of public alerts to a Cell Broadcast Centre (ADR 0003).

Only the simulated provider exists: a real one needs an agreement with the operators and the
Civil Protection. The backend never calls a provider on its own; a dispatcher confirms first.
"""

from __future__ import annotations

import logging
from typing import Protocol

log = logging.getLogger("wamidh.broadcast")


class BroadcastProvider(Protocol):
    # True when the provider does not reach real phones (the CAP status is then "Exercise").
    exercise: bool

    def send(self, cap_xml: str, tower_ids: list[str]) -> str:
        """Hand the CAP message to the operator for these cells; return the delivery label."""
        ...


class SimulatedBroadcast:
    """Logs the CAP message instead of sending it. Used in the demo and the tests."""

    exercise = True

    def send(self, cap_xml: str, tower_ids: list[str]) -> str:
        log.warning("SIMULATED cell broadcast to %d cells:\n%s", len(tower_ids), cap_xml)
        return "simulated"

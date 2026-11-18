"""Message models mirroring telemetry.schema.json and event.schema.json."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# States a node reports. OFFLINE and LOST_PROBABLY_BURNED are set by the backend watchdog.
NodeReportedState = Literal["NORMAL", "ALERT", "FIRE"]
NodeState = Literal["NORMAL", "ALERT", "FIRE", "OFFLINE", "LOST_PROBABLY_BURNED"]


class Telemetry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: int = Field(ge=1, le=65535)
    seq: int = Field(ge=0, le=65535)
    ts: str
    state: NodeReportedState
    gas_ratio: float = Field(ge=0, le=4)
    temp_c: float = Field(ge=-40, le=125)
    rh_pct: float = Field(ge=0, le=100)
    flame: bool
    fire_prob: float = Field(ge=0, le=1)
    battery_v: float = Field(ge=0, le=5)
    sig: str


class NodeEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: int = Field(ge=1, le=65535)
    seq: int = Field(ge=0, le=65535)
    ts: str
    from_state: NodeReportedState
    to_state: NodeReportedState
    fire_prob: float = Field(ge=0, le=1)
    flame: bool = False
    sig: str

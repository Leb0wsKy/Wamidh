# On-node camera and sensor popup: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** every node reports a visual fire probability computed on the node by day and by
night (`vision_prob`, `vision_night`), and clicking a sensor on the station map opens a popup
with its details.

**Architecture:** the contract gains two optional fields, implemented first. The simulator
gains a placeholder camera that wakes only in ALERT/FIRE and feeds the on-node fusion. The
backend stores the fields and keeps per node the last ALERT time, last FIRE time and latest
camera evaluation, restored from the telemetry table at startup. The web app renders a tested
`SensorDetails` component inside a Leaflet popup.

**Tech stack:** Python 3.11 (pydantic 2, FastAPI, SQLAlchemy 2, pytest, ruff, mypy), React 19 +
TypeScript strict, react-leaflet 5, i18next, vitest, Playwright (driving system Edge) for the
live check.

**Spec:** `docs/superpowers/specs/2026-10-05-node-camera-and-map-popup-design.md` (read it with
this plan). **Decision record:** `docs/adr/0001-on-node-camera-no-image-uplink.md`.

## Global constraints

- No personal names, school or Student Branch anywhere: code, comments, docs (CLAUDE.md §2).
- Every assumed value is marked `ASSUMPTION` in code or config, with a note.
- The simulated camera is a `PLACEHOLDER` for the trained model, and says so in its docstring.
- Images never leave the node: no image field, topic or endpoint is added anywhere.
- `vision_prob` is in 0–1 or `null`; `vision_night` is a boolean or `null`. Both are optional;
  absent means `null`.
- The LoRa packet is 20 bytes: 16 data bytes + a 4-byte truncated HMAC (`contracts/packet_format.md`).
- Thresholds and intervals live in YAML or `web/src/config.ts`, not inside components.
- UI text is in `fr`, `ar` (RTL) and `en`. No emoji in the interface; icons come from `web/src/components/iconPaths.ts`.
- Python: `ruff format`, `ruff check`, `mypy --strict` clean on `backend/`. Web: `npx prettier --check src`, `npx tsc -b`, `npx oxlint src` with no new warnings.
- Storage in UTC; the UI shows Africa/Tunis time.

## Review focus

1. **A node without a camera** (message has no `vision_*` keys) must still be accepted, and its popup must say the camera never evaluated. *Test in Task 3* (`test_telemetry_without_camera_fields_is_accepted`).
2. **A backend restart** must not lose "last alert", "last fire" or the last camera evaluation. *Test in Task 3* (`test_node_memory_survives_a_restart`).
3. **Day/night must use Africa/Tunis time, not UTC:** 05:45 UTC is 06:45 in Tunis, which is day. *Test in Task 2* (`test_daylight_uses_tunis_time_not_utc`).
4. **`vision_prob` present with `vision_night` missing** must be treated as a day evaluation, not crash. *Test in Task 3* (`test_vision_without_night_flag_counts_as_day`).
5. **The popup must stay open while live updates arrive** (markers must not remount), and must read right-to-left in Arabic. *Checked live in Task 6*; the RTL attribute is unit-tested in Task 4.

---

## File structure

| File | Responsibility |
|---|---|
| `contracts/telemetry.schema.json`, `contracts/python/src/wamidh_contracts/models.py` | the two new optional fields |
| `contracts/packet_format.md` (new) | the 20-byte LoRa layout |
| `simulator/src/wamidh_sim/camera.py` (new) | placeholder vision model, day/night |
| `simulator/src/wamidh_sim/classifier.py`, `firmware.py`, `node.py`, `config/demo.yaml` | fusion, camera wake-up, wiring, config |
| `backend/src/wamidh_backend/store.py`, `core.py`, `app.py` | storage, node memory, restore |
| `contracts/api.md` | Node JSON gains `vision`, `last_alert_at`, `last_fire_at`, `access_point` |
| `web/src/components/SensorDetails.tsx` (new) | popup content, presentational and tested |
| `web/src/components/StationMap.tsx`, `SensorLedger.tsx`, `pages/StationPage.tsx` | popup wiring, camera column |
| `web/src/domain/time.ts`, `status.ts` | date-time and "ago" formatting |

---

### Task 1: Contract: `vision_prob`, `vision_night`, 20-byte packet

**Files:**
- Modify: `contracts/telemetry.schema.json`
- Modify: `contracts/python/src/wamidh_contracts/models.py`
- Modify: `contracts/python/tests/test_contracts.py`
- Create: `contracts/packet_format.md`
- Modify: `contracts/mqtt_topics.md` (one line, see Step 6)

**Interfaces:**
- Produces: `Telemetry.vision_prob: float | None` (0–1, default `None`), `Telemetry.vision_night: bool | None` (default `None`).

- [ ] **Step 1: Write the failing tests.** In `contracts/python/tests/test_contracts.py`, replace `test_telemetry_model_matches_the_json_schema_fields` and add two tests:

```python
def test_telemetry_model_matches_the_json_schema_fields() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    assert set(Telemetry.model_fields) == set(schema["properties"])
    required = {name for name, f in Telemetry.model_fields.items() if f.is_required()}
    assert set(schema["required"]) == required


def test_camera_fields_are_optional_and_bounded() -> None:
    bare = Telemetry.model_validate({**TELEMETRY, "sig": "x"})
    assert bare.vision_prob is None and bare.vision_night is None

    night = Telemetry.model_validate(
        {**TELEMETRY, "vision_prob": 0.92, "vision_night": True, "sig": "x"}
    )
    assert night.vision_prob == 0.92 and night.vision_night is True

    asleep = Telemetry.model_validate(
        {**TELEMETRY, "vision_prob": None, "vision_night": None, "sig": "x"}
    )
    assert asleep.vision_prob is None

    with pytest.raises(ValidationError):
        Telemetry.model_validate({**TELEMETRY, "vision_prob": 1.2, "sig": "x"})


def test_signature_covers_the_camera_fields() -> None:
    body = {**TELEMETRY, "vision_prob": 0.1, "vision_night": False}
    msg = {**body, "sig": sign(body, KEY)}
    assert verify(msg, KEY)

    assert not verify({**msg, "vision_prob": 0.95}, KEY)  # a forged "fire visible"
```

- [ ] **Step 2: Run them to see them fail.**
  Run: `cd contracts/python && ../../.venv/Scripts/python -m pytest -q`
  Expected: FAIL. `vision_prob` is rejected as an extra field, and the schema has no such properties.

- [ ] **Step 3: Implement.**
  - In `models.py`, add to `class Telemetry` after `fire_prob`:

```python
    # On-node camera (ADR 0001): probability that a fire is visible, computed on the node.
    # None = not evaluated (camera asleep in NORMAL, or no camera). Images never leave the node.
    vision_prob: float | None = Field(default=None, ge=0, le=1)
    # True if evaluated in night mode, when only flames (not smoke) can be seen.
    vision_night: bool | None = None
```

  - In `telemetry.schema.json`:
    - change `"description"` to `"Periodic node reading. Mirrors the 20-byte LoRa packet (packet_format.md). Published on wamidh/v1/nodes/{node_id}/telemetry."`;
    - leave `"required"` unchanged;
    - add to `"properties"` after `"fire_prob"`:

```json
    "vision_prob": { "type": ["number", "null"], "minimum": 0, "maximum": 1, "description": "Probability that a fire is visible, from the on-node vision model (ADR 0001): smoke or flames by day, flames and glow at night. null or absent = not evaluated (camera asleep in NORMAL, or no camera)." },
    "vision_night": { "type": ["boolean", "null"], "description": "true if the camera evaluated in night mode (flames only); null when vision_prob is null." },
```

  - Add `"vision_prob": 0.83, "vision_night": false,` to the schema's example, after `"fire_prob"`.

- [ ] **Step 4: Run the tests.**
  Run: `cd contracts/python && ../../.venv/Scripts/python -m pytest -q`
  Expected: all pass.

- [ ] **Step 5: Create `contracts/packet_format.md`:**

```markdown
# LoRa packet (v1): 20 bytes

Binary form of the telemetry message (`telemetry.schema.json`) for the LoRa link
(nodes → gateway in the field; ESP-NOW carries the same bytes in the prototype). The gateway
decodes it to the JSON message before publishing on MQTT. All fields are little-endian.

| Bytes | Field | Encoding |
|---|---|---|
| 0–1 | `node_id` | uint16 |
| 2–3 | `seq` | uint16, wraps at 65535 |
| 4–7 | `ts` | uint32, Unix seconds UTC |
| 8 | flags | bits 0–1 state (0 NORMAL, 1 ALERT, 2 FIRE); bit 2 `flame`; bit 3 `vision_night`; bits 4–7 reserved (0) |
| 9 | `gas_ratio` | uint8, ratio × 100 (0.00–2.55; 255 means ≥ 2.55) |
| 10–11 | `temp_c` | int16, °C × 10 |
| 12 | `rh_pct` | uint8, % × 2 (0–100 %, 0.5 % steps) |
| 13 | `fire_prob` | uint8, probability × 254 (255 reserved) |
| 14 | `vision_prob` | uint8, probability × 254; **255 = null** (camera asleep or absent) |
| 15 | `battery_v` | uint8, (V − 2.00) × 100 (2.00–4.55 V) |
| 16–19 | `sig` | first 4 bytes of HMAC-SHA256 over bytes 0–15 with the node's key |

16 data bytes + 4-byte tag = **20 bytes**. Without the camera byte (14) it would be 19; ADR 0001
explains why the camera adds one byte and never an image.

Airtime (Semtech SX1276 formula, BW 125 kHz, CR 4/5): 57 ms at SF7, 185 ms at SF9, 1.3 s at SF12.

## Open point: tag length

The JSON path (prototype over Wi-Fi and MQTT, simulator) uses a 16-byte HMAC tag (`sig`). The
LoRa path uses 4 bytes to save airtime: a forged packet has a 2⁻³² chance per attempt, and `seq`
rejects replays. The firmware track must confirm this trade-off and how the gateway forwards the
4-byte tag to the backend for verification.
```

- [ ] **Step 6:** In `contracts/mqtt_topics.md`, find the line mentioning the 19-byte packet (`grep -n "19" contracts/mqtt_topics.md`). Change it to say 20 bytes and link `packet_format.md`. If no such line exists, add under the telemetry topic: `Binary LoRa form: 20 bytes, see packet_format.md.`

- [ ] **Step 7: Commit** (once the repository is initialised; the team handles `git init`):
  `git add contracts && git commit -m "feat(contracts): add on-node camera vision_prob/vision_night and 20-byte packet layout"`

---

### Task 2: Simulator: placeholder camera, day/night, fusion

**Files:**
- Create: `simulator/src/wamidh_sim/camera.py`
- Modify: `simulator/src/wamidh_sim/classifier.py`
- Modify: `simulator/src/wamidh_sim/firmware.py`
- Modify: `simulator/src/wamidh_sim/node.py:50-59`
- Modify: `simulator/config/demo.yaml`
- Modify: `simulator/pyproject.toml` (add `tzdata` on Windows)
- Test: `simulator/tests/test_camera.py` (new), `simulator/tests/test_node_logic.py`

**Interfaces:**
- Consumes: `Telemetry.vision_prob`, `Telemetry.vision_night` (Task 1).
- Produces:
  - `Vision(prob: float, night: bool)` (frozen dataclass);
  - `CameraModel(seed: int, daylight: tuple[time, time], tz: ZoneInfo)` with `.is_day(now) -> bool` and `.look(now, smoke, flame) -> Vision`;
  - `camera_from_config(cfg: Mapping, seed: int) -> CameraModel`;
  - `fire_probability(r: Readings, vision: Vision | None = None) -> float`;
  - `NodeFirmware(..., camera: CameraModel | None = None)`.
  - Telemetry always carries the keys `vision_prob` and `vision_night` (`null` when asleep).

- [ ] **Step 1: Write the failing tests.** Create `simulator/tests/test_camera.py`:

```python
from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

from wamidh_sim.camera import CameraModel, Vision, camera_from_config
from wamidh_sim.classifier import fire_probability
from wamidh_sim.sensors import Readings

TUNIS = ZoneInfo("Africa/Tunis")
DAY = datetime(2026, 7, 20, 14, 0, tzinfo=UTC)  # 15:00 in Tunis
NIGHT = datetime(2026, 7, 20, 1, 0, tzinfo=UTC)  # 02:00 in Tunis


def camera() -> CameraModel:
    return CameraModel(seed=1, daylight=(time(6, 30), time(19, 30)), tz=TUNIS)


def test_by_day_it_sees_smoke_but_not_clean_air() -> None:
    cam = camera()
    assert cam.look(DAY, smoke=0.0, flame=False).prob < 0.1
    seen = cam.look(DAY, smoke=0.6, flame=False)
    assert seen.prob > 0.8 and seen.night is False


def test_at_night_smoke_alone_is_invisible_but_a_nearby_fire_is_seen() -> None:
    cam = camera()
    smoke_only = cam.look(NIGHT, smoke=0.5, flame=False)
    assert smoke_only.prob < 0.1 and smoke_only.night is True
    assert cam.look(NIGHT, smoke=0.9, flame=False).prob > 0.8
    assert cam.look(NIGHT, smoke=0.2, flame=True).prob > 0.8


def test_daylight_uses_tunis_time_not_utc() -> None:
    cam = camera()
    assert cam.is_day(datetime(2026, 7, 20, 5, 45, tzinfo=UTC))  # 06:45 in Tunis
    assert not cam.is_day(datetime(2026, 7, 20, 18, 45, tzinfo=UTC))  # 19:45 in Tunis


def test_camera_from_config() -> None:
    cam = camera_from_config(
        {"timezone": "Africa/Tunis", "daylight_local": ["06:30", "19:30"]}, seed=3
    )
    assert cam.is_day(DAY) and not cam.is_day(NIGHT)


def test_visible_fire_raises_the_fire_probability_and_its_absence_by_day_lowers_it() -> None:
    r = Readings(gas_ratio=0.62, temp_c=36.0, rh_pct=30.0, flame=False, battery_v=4.0)
    alone = fire_probability(r)

    assert fire_probability(r, Vision(prob=0.95, night=False)) > alone
    assert fire_probability(r, Vision(prob=0.02, night=False)) < alone


def test_at_night_seeing_nothing_does_not_argue_against_a_fire() -> None:
    # Smoke is invisible at night: an empty night image is not evidence of "no fire".
    r = Readings(gas_ratio=0.62, temp_c=30.0, rh_pct=40.0, flame=False, battery_v=3.8)

    assert fire_probability(r, Vision(prob=0.02, night=True)) == fire_probability(r)
```

  Append to `simulator/tests/test_node_logic.py`:

```python
def test_the_camera_sleeps_in_normal_and_wakes_once_the_node_is_alarmed() -> None:
    from datetime import time
    from zoneinfo import ZoneInfo

    from wamidh_sim.camera import CameraModel

    fw = NodeFirmware(
        node_id=7,
        key=KEY,
        sensors=SensorModel(seed=3),
        state_machine=NodeStateMachine(),
        intervals_s={"NORMAL": 10, "ALERT": 5, "FIRE": 2},
        camera=CameraModel(seed=3, daylight=(time(6, 30), time(19, 30)), tz=ZoneInfo("Africa/Tunis")),
    )
    tele = lambda msgs: [p for t, p in msgs if parse_node_topic(t)[1] == "telemetry"][0]  # noqa: E731

    calm = tele(fw.step(T0, smoke=0.0))
    assert calm["vision_prob"] is None and calm["vision_night"] is None

    # The fire is detected this tick; the camera was asleep when it started.
    first = tele(fw.step(T0 + timedelta(seconds=1), smoke=1.0))
    assert first["state"] == "FIRE" and first["vision_prob"] is None

    # Next report: the camera is awake and sees the fire (14:00 UTC is daytime in Tunis).
    awake = tele(fw.step(T0 + timedelta(seconds=3), smoke=1.0))
    assert awake["vision_prob"] > 0.8 and awake["vision_night"] is False
    assert verify(awake, KEY)
```

- [ ] **Step 2: Run them to see them fail.**
  Run: `cd simulator && ../.venv/Scripts/python -m pytest -q`
  Expected: FAIL, `ModuleNotFoundError: wamidh_sim.camera`.

- [ ] **Step 3: Create `simulator/src/wamidh_sim/camera.py`:**

```python
"""On-node camera (ADR 0001): the image is analysed on the node; only a probability leaves it.

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
```

- [ ] **Step 4: Fusion in `classifier.py`.**
  - Add the import `from wamidh_sim.camera import Vision`.
  - Replace `fire_probability` with:

```python
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
```

- [ ] **Step 5: Firmware wake-up in `firmware.py`.**
  - Add the import `from wamidh_sim.camera import CameraModel, Vision`.
  - Add the parameter `camera: CameraModel | None = None` to `NodeFirmware.__init__` (after `intervals_s`) and store it as `self._camera = camera`.
  - In `step`, replace the first two lines (`r = ...`, `prob = ...`) with:

```python
        r = self._sensors.read(now, smoke)
        # Energy cascade (ADR 0001): the camera sleeps in NORMAL and wakes once the node is
        # already in ALERT or FIRE from an earlier reading.
        vision: Vision | None = None
        if self._camera is not None and self.state in ("ALERT", "FIRE"):
            vision = self._camera.look(now, smoke, r.flame)
        prob = fire_probability(r, vision)
```

  - In the telemetry payload, after `"fire_prob": round(prob, 3),` add:

```python
                            "vision_prob": vision.prob if vision else None,
                            "vision_night": vision.night if vision else None,
```

- [ ] **Step 6: Wiring.**
  - In `node.py`, add the import `from wamidh_sim.camera import camera_from_config` and the argument `camera=camera_from_config(cfg["camera"], seed=entry["node_id"]),` to the `NodeFirmware(...)` call (after `intervals_s=...`).
  - Append to `simulator/config/demo.yaml`:

```yaml

# Simulated on-node camera (ADR 0001). PLACEHOLDER for the vision model trained on day and
# night images. Sleeps in NORMAL; evaluates in ALERT and FIRE.
camera:
  timezone: Africa/Tunis
  daylight_local: ["06:30", "19:30"]   # ASSUMPTION: approximate summer day in Kroumirie
```

  - In `simulator/pyproject.toml`, change the dependencies to `["wamidh-contracts", "aiomqtt>=2.3", "pyyaml>=6.0", "tzdata>=2024.1; sys_platform == 'win32'"]` (Windows has no system time-zone database).

- [ ] **Step 7: Run the tests and the linter.**
  Run: `cd simulator && ../.venv/Scripts/python -m pytest -q && ../.venv/Scripts/ruff format src tests && ../.venv/Scripts/ruff check src tests`
  Expected: all pass (the existing `test_payload_matches_the_contract` also validates the new keys).

- [ ] **Step 8: Commit:** `git add simulator && git commit -m "feat(simulator): placeholder on-node camera, day/night, fused into fire_prob"`

---

### Task 3: Backend: store, node memory, restore, API

**Files:**
- Modify: `backend/src/wamidh_backend/store.py` (`TelemetryRow`, `save_telemetry`, new `node_memory`)
- Modify: `backend/src/wamidh_backend/core.py` (`NodeView`, `handle`, new `restore_memory`)
- Modify: `backend/src/wamidh_backend/app.py` (`create_app`: restore at startup)
- Modify: `contracts/api.md` (Node type)
- Test: `backend/tests/test_core.py`, `backend/tests/test_store.py`, `backend/tests/test_api.py`

**Interfaces:**
- Consumes: `Telemetry.vision_prob`, `Telemetry.vision_night` (Task 1).
- Produces (Node JSON, from `/api/v1/nodes` and the WebSocket `node` events):
  - `readings.vision_prob: number | null`, `readings.vision_night: boolean | null`;
  - `vision: {prob: number, night: boolean, at: ISO string} | null`, the latest non-null evaluation;
  - `last_alert_at: ISO string | null`, `last_fire_at: ISO string | null`;
  - `access_point: {lon, lat, road_type} | null` (from the registry).
- Produces (store): `Store.node_memory() -> dict[int, dict[str, Any]]` with optional keys `"ALERT"` and `"FIRE"` (datetime) and `"vision"` (`{"prob", "night", "at"}`).
- Produces (core): `Core.restore_memory(memory: Mapping[int, Mapping[str, Any]]) -> None`.

- [ ] **Step 1: Write the failing tests.**
  - In `backend/tests/test_core.py`, give the helper extra fields: change its signature to `def telemetry(node_id: int, seq: int, state: str = "NORMAL", key: bytes | None = None, **extra: Any) -> bytes:` and its body dict to `body = {..., "battery_v": 4.0, **extra}`. Add `from typing import Any` to the imports.
  - Append:

```python
def test_camera_evaluation_and_alarm_times_are_kept_per_node() -> None:
    core, _ = make_core()
    core.handle(node_topic(1, "telemetry"), telemetry(1, 0, "ALERT", vision_prob=0.87, vision_night=False), T0)
    later = T0 + timedelta(seconds=30)
    core.handle(node_topic(1, "telemetry"), telemetry(1, 1, "FIRE", vision_prob=None, vision_night=None), later)

    n = core.node(1).to_json()
    assert n["readings"]["vision_prob"] is None  # latest reading: camera did not evaluate
    assert n["vision"] == {"prob": 0.87, "night": False, "at": "2026-07-20T14:00:00Z"}
    assert n["last_alert_at"] == "2026-07-20T14:00:00Z"
    assert n["last_fire_at"] == "2026-07-20T14:00:30Z"


def test_telemetry_without_camera_fields_is_accepted() -> None:
    core, _ = make_core()
    core.handle(node_topic(1, "telemetry"), telemetry(1, 0), T0)

    n = core.node(1).to_json()
    assert n["state"] == "NORMAL" and n["vision"] is None
    assert n["last_alert_at"] is None and n["last_fire_at"] is None


def test_vision_without_night_flag_counts_as_day() -> None:
    core, _ = make_core()
    core.handle(node_topic(1, "telemetry"), telemetry(1, 0, "ALERT", vision_prob=0.4), T0)

    assert core.node(1).to_json()["vision"]["night"] is False


def test_restore_memory_after_a_restart() -> None:
    core, _ = make_core()
    core.restore_memory({1: {"ALERT": T0, "vision": {"prob": 0.9, "night": True, "at": T0}}})

    n = core.node(1).to_json()
    assert n["last_alert_at"] == "2026-07-20T14:00:00Z" and n["last_fire_at"] is None
    assert n["vision"] == {"prob": 0.9, "night": True, "at": "2026-07-20T14:00:00Z"}
```

  - These tests use the existing helper `make_core() -> tuple[Core, FakeSiren]` (nodes 1 and 2) and `Core.node(node_id) -> NodeView`.
  - Append to `backend/tests/test_store.py`:

```python
def test_node_memory_survives_a_restart(tmp_path) -> None:  # type: ignore[no-untyped-def]
    url = f"sqlite:///{tmp_path / 'eg.db'}"
    store = Store(url)
    base = {"seq": 0, "ts": "x", "gas_ratio": 1.0, "temp_c": 30.0, "rh_pct": 40.0, "flame": False, "fire_prob": 0.5, "battery_v": 4.0, "node_id": 1}
    store.save_telemetry({**base, "state": "ALERT", "vision_prob": 0.8, "vision_night": True}, T0)
    store.save_telemetry({**base, "state": "FIRE"}, T0 + timedelta(minutes=1))  # no camera fields
    store.save_telemetry({**base, "state": "NORMAL", "vision_prob": None}, T0 + timedelta(minutes=2))

    mem = Store(url).node_memory()  # a fresh Store, as after a restart

    assert mem[1]["ALERT"] == T0
    assert mem[1]["FIRE"] == T0 + timedelta(minutes=1)
    assert mem[1]["vision"] == {"prob": 0.8, "night": True, "at": T0}
```

  - Append to `backend/tests/test_api.py`:

```python
def test_nodes_expose_camera_history_and_access_point(tmp_path) -> None:  # type: ignore[no-untyped-def]
    c, core = client(tmp_path, access=ACCESS)
    core.handle(node_topic(1, "telemetry"), telemetry(1, 0, "ALERT", vision_prob=0.7, vision_night=False), T0)

    n = c.get("/api/v1/nodes").json()[0]
    assert n["vision"]["prob"] == 0.7 and n["last_alert_at"] == "2026-07-20T14:00:00Z"
    assert n["access_point"] == ACCESS
```

- [ ] **Step 2: Run them to see them fail.**
  Run: `cd backend && ../.venv/Scripts/python -m pytest -q`
  Expected: FAIL (`KeyError: 'vision'`, no attribute `node_memory`, and so on).

- [ ] **Step 3: Store (`store.py`).**
  - Add to `TelemetryRow`, after `battery_v`:

```python
    vision_prob: Mapped[float | None] = mapped_column(Float, nullable=True)
    vision_night: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
```

  - In `save_telemetry`, after the `fields = {...}` comprehension, add:

```python
        # Optional on-node camera fields (ADR 0001); absent for nodes without a camera.
        fields["vision_prob"] = t.get("vision_prob")
        fields["vision_night"] = t.get("vision_night")
```

  - Add after `telemetry_since`:

```python
    def node_memory(self) -> dict[int, dict[str, Any]]:
        """Per node, from the telemetry table: last time in ALERT and in FIRE, and the latest
        camera evaluation. Restores what the dashboard shows after a backend restart."""
        out: dict[int, dict[str, Any]] = {}
        with Session(self._engine) as s:
            times = (
                select(TelemetryRow.node_id, TelemetryRow.state, func.max(TelemetryRow.received_at))
                .where(TelemetryRow.state.in_(("ALERT", "FIRE")))
                .group_by(TelemetryRow.node_id, TelemetryRow.state)
            )
            for node_id, state, at in s.execute(times):
                out.setdefault(node_id, {})[state] = _utc(at)
            latest = (
                select(func.max(TelemetryRow.id))
                .where(TelemetryRow.vision_prob.is_not(None))
                .group_by(TelemetryRow.node_id)
            )
            for r in s.scalars(select(TelemetryRow).where(TelemetryRow.id.in_(latest))):
                out.setdefault(r.node_id, {})["vision"] = {
                    "prob": r.vision_prob,
                    "night": bool(r.vision_night),
                    "at": _utc(r.received_at),
                }
        return out
```

- [ ] **Step 4: Core (`core.py`).**
  - Add to `NodeView`, after `readings`:

```python
    last_alert_at: datetime | None = None
    last_fire_at: datetime | None = None
    # Latest non-null camera evaluation: {"prob": float, "night": bool, "at": datetime}.
    vision: dict[str, Any] | None = None
```

  - In `NodeView.to_json`, add after `"readings": self.readings,`:

```python
            "access_point": i.access,
            "last_alert_at": iso(self.last_alert_at),
            "last_fire_at": iso(self.last_fire_at),
            "vision": (
                {**self.vision, "at": iso(self.vision["at"])} if self.vision is not None else None
            ),
```

  - In `handle`, extend `node.readings = {...}` with `"vision_prob": model.vision_prob, "vision_night": model.vision_night,`, then right after that assignment add:

```python
            if model.vision_prob is not None:
                node.vision = {
                    "prob": model.vision_prob,
                    "night": bool(model.vision_night),  # missing flag = day evaluation
                    "at": now,
                }
```

  - Just before `out: list[LiveEvent] = ...` add:

```python
        if node.state == "ALERT":
            node.last_alert_at = now
        elif node.state == "FIRE":
            node.last_fire_at = now
```

  - Add a method next to `restore`:

```python
    def restore_memory(self, memory: Mapping[int, Mapping[str, Any]]) -> None:
        """Last alert / fire times and camera evaluation, from the store at startup."""
        for node_id, m in memory.items():
            node = self._nodes.get(node_id)
            if node is None:
                continue  # a node no longer installed
            node.last_alert_at = m.get("ALERT")
            node.last_fire_at = m.get("FIRE")
            node.vision = dict(m["vision"]) if m.get("vision") else None
```

- [ ] **Step 5: Restore at startup (`app.py`).** In `create_app`, after `core.restore(store.load_incidents())`, add `core.restore_memory(store.node_memory())`.

- [ ] **Step 6: Update `contracts/api.md`.** In the `interface Node` block, add after the readings:

```ts
  readings: { gas_ratio, temp_c, rh_pct, flame, fire_prob, vision_prob: number | null, vision_night: boolean | null };
  /** latest camera evaluation on the node (ADR 0001); null if the camera never evaluated */
  vision: { prob: number; night: boolean; at: string } | null;
  last_alert_at: string | null;   // last report in ALERT (UTC)
  last_fire_at: string | null;    // last report in FIRE (UTC)
  access_point: { lon: number; lat: number; road_type: string } | null;
```

  Keep the existing lines that already describe `readings`; merge rather than duplicate.

- [ ] **Step 7: Run everything.**
  Run: `cd backend && ../.venv/Scripts/ruff format src tests && ../.venv/Scripts/ruff check src tests && ../.venv/Scripts/mypy src && ../.venv/Scripts/python -m pytest -q`
  Expected: all checks pass.

- [ ] **Step 8: Commit:** `git add backend contracts/api.md && git commit -m "feat(backend): store camera evaluation, keep last alert/fire per node, restore at startup"`

---

### Task 4: Web: `SensorDetails` (the popup content)

**Files:**
- Modify: `web/src/api/types.ts` (`SensorNode`)
- Modify: `web/src/domain/time.ts` (+ `formatDateTime`), `web/src/domain/status.ts` (`shortAgo` gains hours and days)
- Modify: `web/src/components/iconPaths.ts` (+ `moon`)
- Modify: `web/src/i18n/locales/fr.json`, `ar.json`, `en.json` (+ `popup` section, + `ledger.camera`)
- Create: `web/src/components/SensorDetails.tsx`
- Test: `web/src/components/SensorDetails.test.tsx`, `web/src/domain/time.test.ts` (new), `web/src/domain/status.test.ts`

**Interfaces:**
- Consumes: the Node JSON fields from Task 3.
- Produces:
  - `SensorDetails({ node: SensorNode; now: number; onClose: () => void })`;
  - `formatDateTime(iso: string): string` (for example `05/10 13:02`, Africa/Tunis, Western digits in every language);
  - `shortAgo(ms)`: `"8 s"`, `"5 min"`, `"3 h"`, `"2 j"` (the day unit comes from i18n: see Step 3).

- [ ] **Step 1: Types.** In `SensorNode` (`types.ts`), add to `readings`: `vision_prob?: number | null` and `vision_night?: boolean | null`. Add these fields to the interface:

```ts
  /** latest camera evaluation on the node (ADR 0001); null if never */
  vision?: { prob: number; night: boolean; at: string } | null
  last_alert_at?: string | null
  last_fire_at?: string | null
  access_point?: (LonLat & { road_type: string }) | null
```

- [ ] **Step 2: Write the failing tests.**
  - Create `web/src/domain/time.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { formatDateTime } from './time'

describe('formatDateTime', () => {
  it('shows day/month and hour:minute in Tunisian time', () => {
    expect(formatDateTime('2026-10-05T12:02:00Z')).toBe('05/10 13:02')
    expect(formatDateTime('2026-10-05T23:30:00Z')).toBe('06/10 00:30')
  })
})
```

  - In `web/src/domain/status.test.ts`, replace the `shortAgo` block with:

```ts
describe('shortAgo', () => {
  it('says seconds, minutes, hours, then days', () => {
    expect(shortAgo(3_400)).toBe('3 s')
    expect(shortAgo(5 * 60_000)).toBe('5 min')
    expect(shortAgo(3 * 3_600_000)).toBe('3 h')
    expect(shortAgo(50 * 3_600_000, 'd')).toBe('2 d')
  })
})
```

  - Create `web/src/components/SensorDetails.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { SensorNode } from '../api/types'
import i18n from '../i18n'
import { SensorDetails } from './SensorDetails'

const NOW = Date.parse('2026-10-05T12:10:00Z')
const node: SensorNode = {
  id: 4,
  state: 'ALERT',
  lon: 8.601508,
  lat: 36.786972,
  last_seen: '2026-10-05T12:09:52Z',
  battery_v: 4.02,
  risk_percentile: 99.3,
  gateway_id: 33,
  readings: { temp_c: 41.3, rh_pct: 21, gas_ratio: 0.71, flame: false, fire_prob: 0.55, vision_prob: 0.87, vision_night: false },
  vision: { prob: 0.87, night: false, at: '2026-10-05T12:02:00Z' },
  last_alert_at: '2026-10-05T12:09:52Z',
  last_fire_at: null,
  access_point: { lon: 8.6036, lat: 36.7888, road_type: 'track' },
  link: { received: 900, lost: 3, rejected: 0 },
}

describe('SensorDetails', () => {
  it('shows state, readings, camera, location, history and health', () => {
    render(<SensorDetails node={node} now={NOW} onClose={() => {}} />)

    expect(screen.getByRole('heading', { name: /Sensor 4/ })).toBeInTheDocument()
    expect(screen.getByText('Alert')).toBeInTheDocument()
    expect(screen.getByText('41.3 °C')).toBeInTheDocument()
    expect(screen.getByText('Fire visible 87 % · 05/10 13:02')).toBeInTheDocument()
    expect(screen.getByText('36.78697, 8.60151')).toBeInTheDocument()
    expect(screen.getByText('Access: forest track')).toBeInTheDocument()
    expect(screen.getByText('Gateway 33')).toBeInTheDocument()
    expect(screen.getByText('Last fire').nextSibling).toHaveTextContent('never')
    expect(screen.getByText('Last alert').nextSibling).toHaveTextContent('05/10 13:09 · 8 s ago')
    expect(screen.getByText('4.02 V')).toBeInTheDocument()
    expect(screen.getByText('3 lost')).toBeInTheDocument()
    expect(screen.getByTitle('Contact')).toHaveTextContent('8 s ago') // last contact
  })

  it('says when the camera is asleep, and when it looked at night', () => {
    render(
      <SensorDetails
        node={{ ...node, state: 'NORMAL', vision: { prob: 0.92, night: true, at: '2026-10-05T01:14:00Z' } }}
        now={NOW}
        onClose={() => {}}
      />,
    )

    expect(screen.getByText('Asleep (wakes on alert)')).toBeInTheDocument()
    expect(screen.getByText('Last look: 92 % · 05/10 02:14 · night (flames only)')).toBeInTheDocument()
  })

  it('says when the camera never evaluated (node without camera, or never alarmed)', () => {
    render(<SensorDetails node={{ ...node, state: 'NORMAL', vision: null }} now={NOW} onClose={() => {}} />)

    expect(screen.getByText('Never evaluated')).toBeInTheDocument()
  })

  it('closes with the × button', async () => {
    const onClose = vi.fn()
    render(<SensorDetails node={node} now={NOW} onClose={onClose} />)

    await userEvent.click(screen.getByRole('button', { name: 'Close' }))

    expect(onClose).toHaveBeenCalledOnce()
  })

  it('reads right to left in Arabic, although it sits inside the left-to-right map', async () => {
    await i18n.changeLanguage('ar')
    const { container } = render(<SensorDetails node={node} now={NOW} onClose={() => {}} />)
    expect(container.firstElementChild).toHaveAttribute('dir', 'rtl')
    await i18n.changeLanguage('en')
  })
})
```

- [ ] **Step 3: Run them to see them fail.**
  Run: `cd web && npx vitest run src/components/SensorDetails.test.tsx src/domain/time.test.ts src/domain/status.test.ts`
  Expected: FAIL (module not found, `formatDateTime` not exported).

- [ ] **Step 4: Implement the helpers.**
  - In `time.ts`, append:

```ts
/** "05/10 13:02": day/month and time in Tunisian time, for events that may be days old.
 *  Same numeric layout and Western digits in every language, like the rest of the UI. */
export function formatDateTime(iso: string): string {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Africa/Tunis',
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(new Date(iso))
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? ''
  return `${get('day')}/${get('month')} ${get('hour')}:${get('minute')}`
}
```

  - In `status.ts`, replace `shortAgo` with:

```ts
/** "8 s", "5 min", "3 h", "2 d": how long ago, short. `dayUnit` comes from i18n ("j" in French). */
export function shortAgo(ms: number, dayUnit = 'd'): string {
  const s = Math.max(0, Math.round(ms / 1000))
  if (s < 120) return `${s} s`
  if (s < 120 * 60) return `${Math.round(s / 60)} min`
  if (s < 48 * 3600) return `${Math.round(s / 3600)} h`
  return `${Math.round(s / 86400)} ${dayUnit}`
}
```

  - In `iconPaths.ts`, add to `PATHS`: `moon: 'M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z',`.

- [ ] **Step 5: Text keys.** Add a `popup` section and `ledger.camera` to the three locale files:

```json
"popup": {
  "close": "Fermer", "readings": "Mesures", "flame": "Flamme (IR)", "yes": "Oui", "no": "Non",
  "camera": "Caméra (IA embarquée)", "visible": "Feu visible {{p}} % · {{t}}",
  "night": "nuit (flammes seulement)", "asleep": "En veille (se réveille en alerte)",
  "lastLook": "Dernière évaluation : {{p}} % · {{t}}", "neverLooked": "Jamais évaluée",
  "location": "Emplacement", "access": "Accès : {{road}}", "gateway": "Passerelle {{id}}",
  "history": "Historique", "lastAlert": "Dernière alerte", "lastFire": "Dernier feu",
  "never": "jamais", "ago": "il y a {{t}}", "health": "État technique", "dayUnit": "j",
  "temp": "Température"
}
```

  English: `"close": "Close", "readings": "Readings", "flame": "Flame (IR)", "yes": "Yes", "no": "No", "camera": "Camera (on-board AI)", "visible": "Fire visible {{p}} % · {{t}}", "night": "night (flames only)", "asleep": "Asleep (wakes on alert)", "lastLook": "Last look: {{p}} % · {{t}}", "neverLooked": "Never evaluated", "location": "Location", "access": "Access: {{road}}", "gateway": "Gateway {{id}}", "history": "History", "lastAlert": "Last alert", "lastFire": "Last fire", "never": "never", "ago": "{{t}} ago", "health": "Health", "dayUnit": "d", "temp": "Temperature"`.

  Arabic: `"close": "إغلاق", "readings": "القياسات", "flame": "اللهب (أشعة تحت الحمراء)", "yes": "نعم", "no": "لا", "camera": "الكاميرا (ذكاء اصطناعي مدمج)", "visible": "حريق مرئي {{p}} % · {{t}}", "night": "ليلًا (اللهب فقط)", "asleep": "في وضع السكون (تستيقظ عند الإنذار)", "lastLook": "آخر تقييم: {{p}} % · {{t}}", "neverLooked": "لم تُقيِّم بعد", "location": "الموقع", "access": "الوصول: {{road}}", "gateway": "البوابة {{id}}", "history": "السجل", "lastAlert": "آخر إنذار", "lastFire": "آخر حريق", "never": "أبدًا", "ago": "منذ {{t}}", "health": "الحالة التقنية", "dayUnit": "ي", "temp": "الحرارة"`.

  `ledger.camera`: fr `"Caméra"`, en `"Camera"`, ar `"الكاميرا"`. Keep each file's existing order; append the new keys.

- [ ] **Step 6: Create `web/src/components/SensorDetails.tsx`:**

```tsx
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import type { SensorNode } from '../api/types'
import { directionOf } from '../i18n'
import { nodeStyle } from '../domain/nodeState'
import { shortAgo } from '../domain/status'
import { formatDateTime } from '../domain/time'
import { BatteryGauge } from './BatteryGauge'
import { Icon } from './Icon'

interface Props {
  node: SensorNode
  now: number
  onClose: () => void
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <>
      <dt className="text-ink-2">{label}</dt>
      <dd className="text-end font-medium text-ink tabular-nums">{children}</dd>
    </>
  )
}

/** The popup for one sensor on the station map. */
export function SensorDetails({ node, now, onClose }: Props) {
  const { t, i18n } = useTranslation()
  const lang = i18n.language
  const s = nodeStyle(node.state)
  const r = node.readings ?? {}
  const ago = (iso: string) =>
    t('popup.ago', { t: shortAgo(now - Date.parse(iso), t('popup.dayUnit')) })
  const when = (iso: string | null | undefined) =>
    iso ? `${formatDateTime(iso)} · ${ago(iso)}` : t('popup.never')
  const v = node.vision ?? null
  const pct = (p: number) => Math.round(p * 100)
  // When and how the camera last looked, e.g. "05/10 02:14 · night (flames only)".
  const stamp = v ? `${formatDateTime(v.at)}${v.night ? ` · ${t('popup.night')}` : ''}` : ''
  // The camera is awake in ALERT and FIRE (ADR 0001), asleep otherwise.
  const awake = node.state === 'ALERT' || node.state === 'FIRE'

  return (
    // The map is always left-to-right; the popup follows the interface language.
    <div dir={directionOf(lang)} className="w-72 text-sm">
      <header
        className="flex items-center gap-2 border-b border-line px-3 py-2.5"
        style={{ borderTop: `3px solid ${s.color}` }}
      >
        <h3 className="text-base font-bold text-ink">
          {t('station.node')} {node.id}
        </h3>
        <span className="font-semibold" style={{ color: s.color }}>
          {t(s.labelKey)}
        </span>
        <button
          type="button"
          onClick={onClose}
          aria-label={t('popup.close')}
          className="ms-auto grid size-8 place-items-center rounded-md text-ink-2 hover:bg-paper hover:text-ink"
        >
          <Icon name="close" size={18} />
        </button>
      </header>

      <div className="flex flex-col gap-3 px-3 py-3">
        <section>
          <h4 className="eg-label mb-1">{t('popup.readings')}</h4>
          <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-0.5">
            <Row label={t('popup.temp')}>
              <span dir="ltr">{r.temp_c != null ? `${r.temp_c.toFixed(1)} °C` : '—'}</span>
            </Row>
            <Row label={t('card.humidity')}>
              <span dir="ltr">{r.rh_pct != null ? `${Math.round(r.rh_pct)} %` : '—'}</span>
            </Row>
            <Row label={t('card.gas')}>{r.gas_ratio != null ? r.gas_ratio.toFixed(2) : '—'}</Row>
            <Row label={t('popup.flame')}>{r.flame ? t('popup.yes') : t('popup.no')}</Row>
            <Row label={t('ledger.ai')}>
              <span dir="ltr">{r.fire_prob != null ? `${pct(r.fire_prob)} %` : '—'}</span>
            </Row>
          </dl>
        </section>

        <section>
          <h4 className="eg-label mb-1">{t('popup.camera')}</h4>
          {awake && v && (
            <p className="font-medium text-ink">
              {t('popup.visible', { p: pct(v.prob), t: stamp })}
            </p>
          )}
          {awake && !v && <p className="text-ink">{t('popup.neverLooked')}</p>}
          {!awake && (
            <>
              <p className="text-ink">{t('popup.asleep')}</p>
              <p className="text-xs text-ink-2">
                {v ? t('popup.lastLook', { p: pct(v.prob), t: stamp }) : t('popup.neverLooked')}
              </p>
            </>
          )}
        </section>

        <section>
          <h4 className="eg-label mb-1">{t('popup.location')}</h4>
          <p dir="ltr" className="text-start text-ink tabular-nums">
            {node.lat.toFixed(5)}, {node.lon.toFixed(5)}
          </p>
          {node.access_point && (
            <p className="text-ink-2">
              {t('popup.access', {
                road: t(`roadType.${node.access_point.road_type}`, {
                  defaultValue: node.access_point.road_type,
                }),
              })}
            </p>
          )}
          <p className="text-ink-2">
            {node.gateway_id !== null ? t('popup.gateway', { id: node.gateway_id }) : t('card.noLink')}
          </p>
        </section>

        <section>
          <h4 className="eg-label mb-1">{t('popup.history')}</h4>
          <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-0.5">
            <dt className="text-ink-2">{t('popup.lastAlert')}</dt>
            <dd className="text-end font-medium text-ink tabular-nums">{when(node.last_alert_at)}</dd>
            <dt className="text-ink-2">{t('popup.lastFire')}</dt>
            <dd className="text-end font-medium text-ink tabular-nums">{when(node.last_fire_at)}</dd>
          </dl>
        </section>

        <section className="flex items-center gap-3 border-t border-line pt-2.5 text-xs text-ink-2">
          <span className="eg-label">{t('popup.health')}</span>
          <BatteryGauge volts={node.battery_v} />
          {node.link && node.link.lost > 0 && <span>{t('card.lost', { n: node.link.lost })}</span>}
          <span className="ms-auto tabular-nums" title={t('ledger.contact')}>
            {node.last_seen ? ago(node.last_seen) : t('station.never')}
          </span>
        </section>
      </div>
    </div>
  )
}
```

  The strings the tests rely on (English):
  - **awake, evaluated:** `"Fire visible 87 % · 05/10 13:02"`, plus `" · night (flames only)"` for a night evaluation;
  - **asleep, evaluated before:** `"Asleep (wakes on alert)"`, then `"Last look: 92 % · 05/10 02:14 · night (flames only)"`;
  - **asleep, never evaluated:** `"Asleep (wakes on alert)"`, then `"Never evaluated"`.

- [ ] **Step 7: Run the tests.**
  Run: `cd web && npx prettier --write src && npx tsc -b && npx vitest run`
  Expected: all pass, including the i18n "keys used in the code exist" test.

- [ ] **Step 8: Commit:** `git add web && git commit -m "feat(web): sensor details popup content with camera, history and location"`

---

### Task 5: Web: open the popup from the map and the ledger; camera column

**Files:**
- Modify: `web/src/components/StationMap.tsx` (stable marker keys, `Popup`, refs, Escape, `now` prop)
- Modify: `web/src/pages/StationPage.tsx` (pass `now`)
- Modify: `web/src/components/SensorLedger.tsx` (+ camera column)
- Modify: `web/src/index.css` (+ popup frame style)
- Test: `web/src/components/SensorLedger.test.tsx`

**Interfaces:**
- Consumes: `SensorDetails` (Task 4); `MapFocus { nodeId, seq }` (exists).
- Produces: `StationMap` props gain `now: number`. A `focus` request now also opens that sensor's popup.

- [ ] **Step 1: Write the failing ledger test.** Append to `SensorLedger.test.tsx`:

```tsx
  it('shows the camera evaluation, with a mark for night ones', () => {
    render(
      <SensorLedger
        {...props}
        nodes={[
          node(1, { state: 'ALERT', readings: { temp_c: 40, rh_pct: 20, gas_ratio: 0.7, flame: false, fire_prob: 0.5, vision_prob: 0.87, vision_night: false } }),
          node(2, { state: 'FIRE', readings: { temp_c: 50, rh_pct: 10, gas_ratio: 0.4, flame: true, fire_prob: 0.9, vision_prob: 0.92, vision_night: true } }),
          node(3),
        ]}
      />,
    )

    const [fire, alert, calm] = screen.getAllByRole('button')
    expect(within(alert!).getByTestId('camera')).toHaveTextContent('87 %')
    expect(within(fire!).getByTestId('camera')).toHaveTextContent('92 %')
    expect(within(fire!).getByTestId('camera').querySelector('svg')).not.toBeNull() // moon
    expect(within(calm!).getByTestId('camera')).toHaveTextContent('—')
  })
```

- [ ] **Step 2: Run it to see it fail.**
  Run: `cd web && npx vitest run src/components/SensorLedger.test.tsx`
  Expected: FAIL, `Unable to find an element by: [data-testid="camera"]`.

- [ ] **Step 3: Camera column in `SensorLedger.tsx`.**
  - Change `COLS` to insert a `3.5rem` column after the AI column:
    `'grid grid-cols-[1.5rem_5rem_minmax(5.5rem,auto)_minmax(3rem,1fr)_3.25rem_3.5rem_4.75rem_5.5rem] items-center gap-x-3'`.
  - Add a header cell after `<span className="text-end">{t('ledger.ai')}</span>`: `<span className="text-end">{t('ledger.camera')}</span>`.
  - Add a row cell after the AI probability cell:

```tsx
            <span
              data-testid="camera"
              dir="ltr"
              className="flex items-center justify-end gap-1 text-ink tabular-nums"
              title={r.vision_night ? t('popup.night') : undefined}
            >
              {r.vision_night && <Icon name="moon" size={12} className="text-ink-2" />}
              {r.vision_prob != null ? `${Math.round(r.vision_prob * 100)} %` : '—'}
            </span>
```

- [ ] **Step 4: Popup wiring in `StationMap.tsx`.**
  - Imports: add `Popup` to the `react-leaflet` import; add `import { SensorDetails } from './SensorDetails'`.
  - Props: add `now: number` to `Props` and to the destructuring.
  - Refs and Escape, inside `StationMap` after the `zoom` state:

```tsx
  const markers = useRef(new Map<number, L.Marker>())
  // Escape closes the open sensor popup, wherever the keyboard focus is.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') map?.closePopup()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [map])
```

  - `FocusOn`: give it a prop `open: (nodeId: number) => void`. After `map.flyTo(...)`, add `map.once('moveend', () => open(n.id))`. Pass `open={(id) => markers.current.get(id)?.openPopup()}` where `<FocusOn>` is rendered.
  - Node `Marker`:
    - **Key:** use `key={n.id}`, so the marker is never remounted and an open popup stays open through live updates. react-leaflet updates `icon`, `zIndexOffset` and `position` in place.
    - **Ref:** add `ref={(m) => { if (m) markers.current.set(n.id, m); else markers.current.delete(n.id) }}`.
    - **Popup:** add, inside the marker after the data-tag `Tooltip`:

```tsx
                  <Popup closeButton={false} autoPanPadding={[24, 24]} className="eg-popup" maxWidth={320}>
                    <SensorDetails node={n} now={now} onClose={() => map?.closePopup()} />
                  </Popup>
```

  - In `StationPage.tsx`, pass `now={now}` to `<StationMap>`.

- [ ] **Step 5: Popup frame style.** Append to `web/src/index.css`:

```css
/* Sensor popup: the card is drawn by SensorDetails; Leaflet only provides the frame. */
.eg-popup .leaflet-popup-content-wrapper {
  padding: 0;
  overflow: hidden;
  border-radius: 8px;
  box-shadow: 0 4px 16px rgb(26 26 25 / 0.18);
}
.eg-popup .leaflet-popup-content {
  margin: 0;
  width: auto !important;
  font-family: var(--font-sans);
  line-height: 1.4;
}
```

- [ ] **Step 6: Run all web checks.**
  Run: `cd web && npx prettier --write src && npx tsc -b && npx oxlint src && npx vitest run && npm run build`
  Expected: all pass. oxlint shows only the two existing `NavigationPage` warnings.

- [ ] **Step 7: Commit:** `git add web && git commit -m "feat(web): open sensor popup from map and ledger; camera column in the ledger"`

---

### Task 6: Live check and restart

**Files:**
- Create (scratchpad, not in the repository): `popup.mjs`
- Modify: `web/README.md` (one row), `simulator/README.md` (one line)

- [ ] **Step 1: Restart the backend and the nodes** so they load the new code. Each runs in its own window, outside any tool time limit.
  1. Find the processes (PowerShell):
     - backend: `Get-NetTCPConnection -LocalPort 8000 -State Listen | Select OwningProcess`;
     - nodes: `Get-CimInstance Win32_Process | ? { $_.CommandLine -match 'wamidh_sim' }`.
  2. `Stop-Process` them.
  3. Start each with `Start-Process powershell -ArgumentList '-NoExit','-Command',"& '<repo>\.venv\Scripts\python.exe' -m wamidh_backend"` (and `-m wamidh_sim.run` for the nodes), working directory = repo root.
  4. Check `GET /api/v1/nodes`: every node has `vision`, `last_alert_at`, `last_fire_at` and `access_point` keys.

- [ ] **Step 2: Live check in Edge.** Create `popup.mjs` in the scratchpad:

```js
import { execFileSync } from 'node:child_process'
import { chromium } from 'file:///C:/Users/Admin/Desktop/sight-ceda/web/node_modules/playwright/index.mjs'
const out = process.argv[2], base = 'http://127.0.0.1:5173'
const py = 'C:/Users/Admin/Desktop/sight-ceda/.venv/Scripts/python.exe'
const ignite = (...a) => execFileSync(py, ['-m', 'wamidh_sim.ignite', ...a], { cwd: 'C:/Users/Admin/Desktop/sight-ceda' })
const browser = await chromium.launch({ channel: 'msedge' })
const errors = []
const p = await (await browser.newContext({ viewport: { width: 1440, height: 860 } })).newPage()
p.on('pageerror', (e) => errors.push(e.message))
await p.goto(`${base}/station`); await p.waitForTimeout(3500)
await p.getByRole('button', { name: /Capteur 2 ·/ }).click()          // ledger row -> popup
await p.waitForSelector('.eg-popup'); await p.waitForTimeout(800)
await p.screenshot({ path: `${out}/pop1_calm.png` })
ignite('2', '--ramp', '20')
await p.waitForFunction(() => document.querySelector('.eg-popup')?.textContent?.includes('Feu visible'), null, { timeout: 90000 })
console.log('popup still open during live updates:', await p.locator('.eg-popup').count())
await p.screenshot({ path: `${out}/pop2_fire.png` })
await p.getByRole('button', { name: 'Fermer' }).click()
console.log('closed by ×:', (await p.locator('.eg-popup').count()) === 0)
await p.locator('.eg-node[data-state="FIRE"]').click()                  // marker -> popup
await p.waitForSelector('.eg-popup'); await p.keyboard.press('Escape')
console.log('closed by Escape:', (await p.locator('.eg-popup').count()) === 0)
console.log(errors.length ? 'errors: ' + errors.join(' | ') : 'no page errors')
await browser.close()
ignite('2', '--out')
```

  Run: `node popup.mjs <scratchpad>/shots`
  Expected:
  - output: `popup still open during live updates: 1`, `closed by ×: true`, `closed by Escape: true`, `no page errors`;
  - `pop2_fire.png` shows the popup with "Feu visible … %" and "Dernière alerte" filled.

  If the camera line never shows "Feu visible", check that the run happens in Tunis daylight, or at night with the fire close enough. The placeholder needs smoke ≥ 0.7 or flames at night, so the 20 s ramp reaches it.

- [ ] **Step 3: Docs.**
  - In `web/README.md`, extend the `/station` row: "click a sensor (map or ledger) for its details: readings, on-node camera result, location, last alert/fire; close with × or Escape".
  - In `simulator/README.md`, add: "Each virtual node has a placeholder camera (ADR 0001): it sleeps in NORMAL and, in ALERT/FIRE, reports `vision_prob`. By day it sees smoke, at night only flames."

- [ ] **Step 4: Commit:** `git add web/README.md simulator/README.md && git commit -m "docs: sensor popup and simulated on-node camera"`

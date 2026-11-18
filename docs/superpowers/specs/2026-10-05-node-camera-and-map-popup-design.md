# On-node camera (`vision_prob`) and the sensor popup on the station map

- **Date:** 2026-10-05
- **Decision record:** [ADR 0001](../../adr/0001-on-node-camera-no-image-uplink.md) (why the camera stays on the node)
- **Scope:** contracts, simulator, backend, web. Firmware stays out of scope (CLAUDE.md §1).

> **Amendment (2026-10-05, after delivery):** the camera's result is **not transmitted** and not shown on the dashboard. `vision_prob`/`vision_night` were removed from the contract (packet back to 19 bytes), the backend no longer stores them, and the popup and ledger no longer show a camera line. The camera still feeds `fire_prob` on the node. The popup's readings became instrument tiles, and the 60-minute timeline was removed from the station page. Sections 2–6 below describe the first version.

## 1. Goal

1. Every node has a camera whose image is analysed **on the node**, by day and by night. Only
   the result, `vision_prob`, is transmitted, and it contributes to the fire decision.
2. On the station map, clicking a sensor (or its ledger row) opens a popup with that sensor's
   details. It closes with an **×** button, Escape or a click on the map.

## 2. Contract changes (implemented first)

### 2.1 Telemetry JSON (`contracts/telemetry.schema.json`, `wamidh_contracts.Telemetry`)

New fields:

| Field | Type | Meaning |
|---|---|---|
| `vision_prob` | number 0–1, or `null` | Probability that a fire is visible, from the on-node vision model: smoke or flames by day, flames and glow at night. `null` = not evaluated (camera asleep in `NORMAL`, or camera fault). |
| `vision_night` | boolean, or `null` | `true` if the evaluation was made in night mode, when only flames can be seen; `null` when `vision_prob` is `null`. |

- Both are **optional** in the schema. If absent, they mean `null`, so a node without a camera
  stays valid. When present, they're covered by `sig` like every other field.
- The schema description changes from "19-byte" to "20-byte LoRa packet".

The event message (`event.schema.json`) is unchanged.

### 2.2 Binary LoRa packet (new `contracts/packet_format.md`)

Written now because the byte count is part of the decision. All fields are little-endian.

| Bytes | Field | Encoding |
|---|---|---|
| 0–1 | `node_id` | uint16 |
| 2–3 | `seq` | uint16 |
| 4–7 | `ts` | uint32, Unix seconds UTC |
| 8 | flags | bits 0–1 state (0 NORMAL, 1 ALERT, 2 FIRE), bit 2 flame, bit 3 `vision_night`, bits 4–7 reserved (0) |
| 9 | `gas_ratio` | uint8, ratio × 100 (0.00–2.55; 255 means ≥ 2.55) |
| 10–11 | `temp_c` | int16, °C × 10 |
| 12 | `rh_pct` | uint8, % × 2 (0–100 %, 0.5 % steps) |
| 13 | `fire_prob` | uint8, probability × 254 (0–254; 255 reserved) |
| 14 | `vision_prob` | uint8, probability × 254 (0–254); **255 = null** (not evaluated) |
| 15 | `battery_v` | uint8, (V − 2.00) × 100 (2.00–4.55 V) |
| 16–19 | `sig` | first 4 bytes of HMAC-SHA256 over bytes 0–15 with the node's key |

That's 16 data bytes plus a 4-byte tag, so **20 bytes** (19 without `vision_prob`).

**Open point, recorded in the file:** the JSON path (prototype, simulator) uses a 16-byte HMAC
tag, while the LoRa path uses 4 bytes to save airtime. A 4-byte tag gives a 2⁻³² chance per
forgery attempt, and `seq` rejects replays. The firmware track must confirm this trade-off.

## 3. Simulator (`simulator/`)

- New `camera.py`, a **rule-based placeholder** for the trained vision model. It's labelled
  `PLACEHOLDER` in the code, like `classifier.py`.
  - It evaluates only when the node's state is `ALERT` or `FIRE`; in `NORMAL` it returns
    `None` (asleep).
  - Day or night comes from config: `camera.daylight_local: ["06:30", "19:30"]` in
    `Africa/Tunis` (**ASSUMPTION**, an approximate summer day).
  - **By day** it "sees" smoke as soon as the existing `SmokeEnvironment` smoke level becomes
    noticeable. **At night** it sees only flames: it responds only when the fire is close (high
    smoke level, or the IR flame sensor triggers) and ignores smoke alone.
  - Small noise comes from the seeded RNG. Fog (the `false_alarm_fog` case) produces nothing
    visible day or night, so the camera helps keep fog out of `FIRE`.
- **Fusion:** `fire_probability(readings, vision_prob)` adds a camera term when `vision_prob`
  isn't `None`. The weight is an **ASSUMPTION** (hand-chosen, documented next to the existing
  ones).
- **Firmware loop:** the camera is called *after* the state machine has reached `ALERT`, so the
  energy cascade is respected: one evaluation per report in `ALERT`/`FIRE`, none in `NORMAL`.
- `vision_prob` and `vision_night` are included in the signed telemetry.

## 4. Backend (`backend/`)

- **Storage:** `TelemetryRow.vision_prob` (nullable float) and `vision_night` (nullable boolean).
  The existing auto-migration adds the columns to the development database.
- **Node snapshot:**
  - `readings.vision_prob` and `readings.vision_night` (the latest values, possibly `null`);
  - `vision`: `{"prob": x, "night": bool, "at": ts}`, the latest non-null evaluation, so the
    popup can say when, and in which mode, the camera last looked.
- **`/api/v1/nodes`** gains, per node:
  - `last_alert_at`: the latest time the node reported `ALERT`;
  - `last_fire_at`: the same for `FIRE`;
  - both `null` if never. They're computed from the telemetry table (latest receive time per
    node and state) and restored correctly after a restart.
- `contracts/api.md` is updated to match.

## 5. Web: the sensor popup (`web/`)

- **Opening:** clicking a sensor's marker opens a Leaflet popup anchored to it. Clicking a ledger
  row does the same: the map flies to the sensor, then opens its popup.
- **Closing:** with the **×** button (Leaflet's close button, restyled to a 32 px target),
  Escape, or a click on the map. Only one popup is open at a time.
- **Contents** (French, Arabic, English):
  - **Header:** sensor number, state (coloured), last contact.
  - **Readings:** temperature, humidity, gas ratio, IR flame (yes/no), AI fire probability.
  - **Camera:**
    - the latest evaluation with its time and mode, e.g. "Feu visible 87 % · 13:02" by day, or
      "Feu visible 92 % · 02:14 · nuit (flammes seulement)" at night;
    - "En veille (se réveille en alerte)" in `NORMAL`, with the last evaluation underneath if
      there is one.
  - **Location:** latitude/longitude (5 decimals), the access point's road type, and the gateway
    it reports to (or "hors de portée radio").
  - **History:** last alert and last fire, as a time plus how long ago, or "jamais".
  - **Health:** battery gauge and voltage, lost packets.
- **Ledger:** gains a small camera column showing `vision_prob` %, with a moon mark for night
  evaluations, or "—".
- **Map data tag:** unchanged.

## 6. Tests

- **Contracts:** `vision_prob` and `vision_night` accepted as values, `null` or absent;
  out-of-range values rejected; the signature covers them.
- **Simulator:**
  - the camera returns `None` in `NORMAL`;
  - by day it returns a high value with smoke, and a low one in fog;
  - at night it ignores smoke alone but returns a high value for a nearby fire, with
    `vision_night = true`;
  - fusion raises `fire_prob` with visible smoke and lowers it without.
- **Backend:** `vision_prob` and `vision_night` stored and served; `last_alert_at`/`last_fire_at` correct, including
  after a restart.
- **Web:**
  - popup contents for a node in each case (asleep, day evaluation, night evaluation, never
    alerted);
  - the × button closes it;
  - a ledger click opens the right popup.
- **Live check in Edge:** ignite a sensor and watch the camera value and the popup during
  `ALERT` → `FIRE`.

## 7. Out of scope

- Images for humans, or a second image radio (see the ADR).
- Building the training dataset and training the real vision model (firmware track; the ADR
  lists what the dataset must contain).

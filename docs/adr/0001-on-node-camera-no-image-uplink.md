# ADR 0001: a camera on every node, analysed on the node, nothing transmitted

- **Status:** accepted (2026-10-05); amended the same day: the camera's own probability is not transmitted either (see *Decision*)
- **Affects:** `contracts/telemetry.schema.json`, `contracts/packet_format.md`, `contracts/python`, `simulator/`, `backend/`, `web/`, future `firmware/`

## Context

Each node detects fire with an infrared flame sensor and a BME688 (temperature, humidity and gas
resistance, reported as `gas_ratio`). These are cheap, low-power and run continuously, but they
can be fooled. Fog, dust or exhaust lower the gas ratio; heat raises the temperature. A camera
adds an independent kind of evidence: smoke or flames you can see.

Two constraints shape how a camera can be used:

1. **Radio.** Nodes talk to their gateway over LoRa. The telemetry packet is 19 bytes. If
   the EU868 rules apply in Tunisia (**ASSUMPTION**, to be checked against the national
   regulation), each node may transmit at most 1 % of the time: **36 s of airtime per hour**.
2. **Energy.** Nodes run on a small solar panel and battery. A camera module draws about
   250 mA while capturing (**ASSUMPTION**, typical OV2640 / ESP32-CAM datasheet figures, to be
   measured). The other sensors draw microamps to a few milliamps.

LoRa airtime, computed with the Semtech SX1276 formula (BW 125 kHz, CR 4/5, 8-symbol preamble,
explicit header, CRC on; largest payload allowed at each spreading factor):

| Spreading factor | One 19-byte packet | A 15 KB image (320×240 JPEG) | A 1 KB thumbnail |
|---|---|---|---|
| SF7 (short range) | 51 ms | 68 packets, **24 s** | 5 packets, 1.7 s |
| SF9 | 185 ms | 131 packets, **81 s** | 9 packets, 5.5 s |
| SF12 (long range, mountain terrain) | 1.3 s | 295 packets, **727 s** | 20 packets, 49 s |

A single image takes most of the hourly budget at SF7, and is impossible at SF9 or SF12. All
the nodes of a gateway also share its channel. Sending images with telemetry is therefore not
feasible, and transmitting them at all would drain the batteries the solar panels recharge.

## Decision

- Every node carries a camera (OV2640 class, on an ESP32-S3 with PSRAM so a small vision model
  can run on the node).
- **Nothing from the camera leaves the node.** A TinyML vision model on the node outputs the
  probability that a fire is visible, and that probability feeds the node's own fire decision
  (`fire_prob`). Neither the image nor the camera's probability is transmitted: the LoRa packet
  stays at **19 bytes** (`contracts/packet_format.md`). A first version of this decision sent the
  probability as one extra byte; it was dropped because the dispatcher acts on the node's
  verdict, not on each sensor separately, and every byte costs airtime and solar energy.
- **Energy cascade:** the camera sleeps in `NORMAL`. It wakes in `ALERT` and `FIRE`, when gas,
  temperature or IR already suspect a fire. It captures a few frames, runs the model, and sleeps
  again. In `NORMAL` the camera costs nothing.
- **Day and night.** The camera works in both, but sees different things:
  - by day, **smoke and flames**;
  - at night, **flames and their glow**, which are the brightest objects in a dark scene. Smoke
    is invisible at night, so the model must not rely on it then.
  The node captures in a night exposure mode after dark (longer exposure, higher gain).
- **One model trained on day and night images** (see *Training data* below).
- The on-node classifier's verdict `fire_prob` fuses gas, temperature, IR flame and, when the
  camera is awake, its probability. By day the camera can confirm or contradict the other
  sensors; at night it can only confirm, since smoke is invisible in the dark.

## Training data for the vision model

The model is only as good as its dataset. It needs, **in daylight and at night**:

| | Daylight | Night |
|---|---|---|
| **Fire (positives)** | smoke columns and plumes at several distances; flames through vegetation | flames, glowing embers, fire light on smoke and trees |
| **No fire (negatives)** | fog, low clouds, dust, haze, sun glare, orange sunsets, steam | vehicle headlights, torches, village and street lights, the moon, camera noise in total darkness |

The negatives matter as much as the positives: they're what keeps the camera from causing false
alarms. Candidate public datasets (**to be checked** for licence, image quality and how much
night content they really have, before use):
- **D-Fire** (smoke and fire images, with bounding boxes);
- **FLAME** (aerial images of controlled fires, from drones);
- **FIgLib** (HPWREN wildfire smoke sequences from fixed cameras, mostly daytime).

Night positives are rare in public data. They'll be completed with **our own captures**: the
prototype's camera filming controlled fire tests by day and by night, from node height, through
Mediterranean vegetation. The report must state how many images of each kind were used and
measure accuracy **separately for day and night**.

A cheap hardware option worth testing: the same OV2640 sensor **without an infrared-cut filter**
(sold as "NoIR"). Flames emit strongly in near-infrared, so such a module sees fire better at
night, at the cost of less natural colours by day.

## Alternatives considered

| Option | Why not |
|---|---|
| Send an image with every report | Over LoRa: 24 s to 12 min of airtime per image against a 36 s/hour budget (table above), plus the camera's energy every 15 min. |
| Send an image only on `FIRE` over LoRa | One image still uses most of an hour's budget at SF7 and is impossible at SF12. |
| Send a 1 KB thumbnail once on `FIRE` | Fits at SF7 (1.7 s) but not at SF12 (49 s), and costs camera and radio energy for a picture too small to judge from. Not worth it. |
| Second radio for images (Wi-Fi HaLow) | Doubles the radio hardware, cost and energy for a human-viewable picture the decision does not need. Kept as a possible future extension. |
| Cameras on the gateways only | Gateways have more power and a line of sight to their nodes, but are far from where a fire starts. Not chosen, so that every node has the camera evidence. |

## Consequences

- **Good:** the camera improves the fire decision (fewer false alarms from fog or dust) at no
  radio cost, and an energy cost only during alerts. It's an edge-AI design that keeps
  working on solar power.
- **Cost:** a camera module and a stronger microcontroller (ESP32-S3 with PSRAM) per node: the
  bill of materials must include them.
- **Limits:** no picture for the dispatcher; humans see the model's output, not the scene. At
  night the camera sees flames but not smoke, so it can confirm a fire but not detect early
  smoke; that remains the gas sensor's job. Lights near roads and villages are the main night
  false-alarm risk, and the training negatives must cover them.
- **Until firmware exists:** the simulator emulates the camera with a rule-based placeholder,
  labelled as such, in the same way as the fire classifier.
- **To measure on the hardware prototype:** the camera's current and capture time (day and
  night exposure), the vision model's latency on the ESP32-S3, its accuracy **by day and by
  night**, and the energy per alert.

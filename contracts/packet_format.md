# LoRa packet (v1): 19 bytes

Binary form of the telemetry message (`telemetry.schema.json`) for the LoRa link
(nodes → gateway in the field; ESP-NOW carries the same bytes in the prototype). The gateway
decodes it to the JSON message before publishing on MQTT. All fields are little-endian.

| Bytes | Field | Encoding |
|---|---|---|
| 0–1 | `node_id` | uint16 |
| 2–3 | `seq` | uint16, wraps at 65535 |
| 4–7 | `ts` | uint32, Unix seconds UTC |
| 8 | flags | bits 0–1 state (0 NORMAL, 1 ALERT, 2 FIRE); bit 2 `flame`; bits 3–7 reserved (0) |
| 9 | `gas_ratio` | uint8, ratio × 100 (0.00–2.55; 255 means ≥ 2.55) |
| 10–11 | `temp_c` | int16, °C × 10 |
| 12 | `rh_pct` | uint8, % × 2 (0–100 %, 0.5 % steps) |
| 13 | `fire_prob` | uint8, probability × 254 (255 reserved) |
| 14 | `battery_v` | uint8, (V − 2.00) × 100 (2.00–4.55 V) |
| 15–18 | `sig` | first 4 bytes of HMAC-SHA256 over bytes 0–14 with the node's key |

15 data bytes + 4-byte tag = **19 bytes**.

The on-node camera (ADR 0001) adds nothing to the packet: its result is fused into `fire_prob` on
the node, and neither the image nor the camera's own probability is transmitted.

Airtime (Semtech SX1276 formula, BW 125 kHz, CR 4/5, 8-symbol preamble, explicit header, CRC on,
low-data-rate optimisation at SF11–12): about 51 ms at SF7, 185 ms at SF9, 1.3 s at SF12.

## Open point: tag length

The JSON path (prototype over Wi-Fi and MQTT, simulator) uses a 16-byte HMAC tag (`sig`). The
LoRa path uses 4 bytes to save airtime: a forged packet has a 2⁻³² chance per attempt, and `seq`
rejects replays. The firmware track must confirm this trade-off and how the gateway forwards the
4-byte tag to the backend for verification.

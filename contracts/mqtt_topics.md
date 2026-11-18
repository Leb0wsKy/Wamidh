# MQTT topics (v1)

Single source of truth shared by firmware, gateway, simulator and backend. Any change here needs
an ADR in `docs/adr/` and a version bump in the topic prefix.

| Topic | Direction | QoS | Payload |
|---|---|---|---|
| `wamidh/v1/nodes/{node_id}/telemetry` | node → backend | 1 | `telemetry.schema.json` |
| `wamidh/v1/nodes/{node_id}/event` | node → backend | 1 | `event.schema.json` (state transitions, fire alerts) |
| `wamidh/v1/stations/{station_id}/cmd` | backend → station receiver | 1 | `{"siren": "on" \| "off", "incident_id": int, "ts": ISO-8601}` |
| `wamidh/v1/stations/{station_id}/ack` | station receiver → backend | 1 | `{"incident_id": int, "ts": ISO-8601}` |

- `node_id` and `station_id` are positive integers.
- Timestamps are UTC, ISO-8601 with `Z` (`2026-10-01T12:00:00Z`).
- Every node message carries `sig`, a truncated HMAC over the payload (see `telemetry.schema.json`).
  The backend **rejects** unsigned or invalid messages.
- Binary LoRa form of the telemetry: 19 bytes, see `packet_format.md`.
- Duplicates (QoS 1 redelivery) are detected by `(node_id, seq)`.

## Node states

| State | Trigger | Reporting interval (field) | Declared silent after | Backend state when silent |
|---|---|---|---|---|
| `NORMAL` | readings within local baseline | 15 min | 60 min | `OFFLINE` (maintenance ticket) |
| `ALERT` | anomaly, fire not confirmed | 2 min | 10 min | `OFFLINE` (maintenance ticket) |
| `FIRE` | classifier confirms fire | immediately, then continuous | 5 min | `LOST_PROBABLY_BURNED` (spread-engine evidence) |

Nodes only ever send `NORMAL`, `ALERT` or `FIRE`. `OFFLINE` and `LOST_PROBABLY_BURNED` are set by
the backend watchdog. The prototype reports every 2 min in all states; intervals are config values.

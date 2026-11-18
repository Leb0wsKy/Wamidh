# Backend

FastAPI service:
- MQTT ingest (signature check, duplicates, packet loss) and node state;
- incidents (siren command to the station over MQTT, audit log);
- watchdog (OFFLINE / LOST_PROBABLY_BURNED);
- REST + WebSocket API (`contracts/api.md`);
- population alerts: alert zones, cell towers, and Arabic CAP 1.2 Cell Broadcast messages that a
  dispatcher confirms ([ADR 0003](../docs/adr/0003-cell-broadcast-alert-zones.md)).

Data is stored in **PostgreSQL 16 + PostGIS** ([ADR 0002](../docs/adr/0002-postgresql-postgis-authority-hosted.md)).

```bash
# from the repo root (scripts/dev.ps1 does all of this for you)
docker compose up -d mqtt db                   # broker + database (127.0.0.1 only)
python -m wamidh_backend.db upgrade        # create / update the schema (Alembic)
python -m wamidh_backend                   # http://127.0.0.1:8000/docs
```

- **Database URL:** taken from `WAMIDH_DATABASE_URL` if set, otherwise from `database:` in `config/dev.yaml`.
  - **Development:** the compose file publishes PostgreSQL on **127.0.0.1:5433**, since 5432 is often taken by a PostgreSQL already installed on the PC. The password is the development-only value from `.env.example`.
  - **Deployment:** set the variable on the authorities' server; never commit it.
  - **Without Docker:** a `sqlite:///…` URL still works as an emergency fallback, but the distance search (`/incidents?near=`) needs PostgreSQL.
- **Migrations:** live in `src/wamidh_backend/migrations/`. Add a revision for every schema change; `python -m wamidh_backend.db upgrade` applies them.
- **Moving the old SQLite data (one time):** `python -m wamidh_backend.migrate_sqlite [--from data/dev/wamidh.db]`. It copies incidents, their logs and telemetry with their ids. It refuses a non-empty target unless `--force`, and never modifies the SQLite file.

## Fire spread forecast (ADR 0004)

- `GET /incidents/{id}/forecast`: probability contours per horizon, estimated ignition, heading
  and speed, threatened zones; recomputed every `spread.refresh_s` and announced over the
  WebSocket. Advisory: it never triggers anything.
- `GET /weather?lat=&lon=`: wind now, from OpenWeatherMap (`OPENWEATHER_API_KEY` in `.env`),
  cached 10 min, else the last value received, else `weather.default`.
- `spread.time_scale` tells the model how much faster than the clock simulated fires run (60
  in the demo, 1 in the field).
- Demo on a calm day: set `weather.demo_override` (e.g. `{from_deg: 210, speed_ms: 8}`), restart,
  then `python -m wamidh_sim.scenario --node 13`. The hidden fire uses that wind with a
  secret offset; the interface labels the measurement "demo".

## Population alerts

```bash
python -m zones.pipeline                     # build data/processed/zones.geojson (zones/README.md)
python -m wamidh_backend.load_zones      # load zones + towers into the database
```

- `GET /incidents/{id}/alert-proposal` lists the zones within `concern_radius_km` of the fire
  and drafts the Arabic message. It never sends anything.
- `POST /incidents/{id}/alert {confirmed_by}` broadcasts the alert. It needs an acknowledged,
  open incident and at least one zone; it writes a `public_alert` audit event.
- The texts and CAP fields are in `config/alerts.yaml`. They are a draft to validate with the
  Civil Protection.
- Delivery goes through `SimulatedBroadcast`, which logs the CAP message, and every message is
  marked `Exercise`. A real provider needs an agreement with the operators.
- The zone search uses PostGIS; on SQLite the proposal returns 501.

## Tests

```bash
python -m pytest                     # unit tests (SQLite, no Docker needed)
WAMIDH_TEST_DATABASE_URL=postgresql+psycopg://wamidh:wamidh-dev-only@127.0.0.1:5433/wamidh \
  python -m pytest                   # + integration tests against PostgreSQL + PostGIS
```

Each integration test runs in its own fresh schema, dropped afterwards, so the development data
is never touched. Without the variable they are skipped, with the reason shown.

Settings: `config/dev.yaml` (watchdog thresholds are demo timing, labelled).

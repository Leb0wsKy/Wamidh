# Move the backend store to PostgreSQL + PostGIS

- **Date:** 2026-10-05
- **Decision record:** [ADR 0002](../../adr/0002-postgresql-postgis-authority-hosted.md)
- **Scope:** `backend/`, `docker-compose.yml`, `scripts/dev.ps1`, `.env.example`, docs. No change to
  the API's existing responses, the dashboard, the simulator or the contracts.

## 1. Goal

The backend stores sensor readings, incidents and their audit log in PostgreSQL with PostGIS
instead of a SQLite file. The demo still runs offline on one laptop. Existing data is carried
over. The incident history can be searched by distance.

## 2. Infrastructure

- **`docker-compose.yml`** gains a `db` service:
  - **Image:** `postgis/postgis:16-3.4`.
  - **Data:** a named volume `wamidh-pgdata`, so it survives restarts.
  - **Port:** published on `127.0.0.1:5432` only, so it can't be reached from the network.
  - **Health check:** `pg_isready`.
  - **Credentials:** database `wamidh`, user `wamidh`; the password comes from
    `POSTGRES_PASSWORD`, read from `.env`.
- **`.env.example`** (new):

  ```
  POSTGRES_PASSWORD=wamidh-dev-only
  WAMIDH_DATABASE_URL=postgresql+psycopg://wamidh:wamidh-dev-only@127.0.0.1:5432/wamidh
  ```

  The real `.env` is git-ignored.
- **`scripts/dev.ps1`:**
  - starts `docker compose up -d mqtt db`;
  - waits for the `db` health check, with a 60 s timeout and a clear message if it fails;
  - runs the schema migrations (`alembic upgrade head`);
  - then starts the backend as today.

## 3. Configuration

- **Database URL:** the backend reads it from the `WAMIDH_DATABASE_URL` environment variable
  if set, else from `database:` in `backend/config/dev.yaml`.
- **`dev.yaml`'s value** becomes the PostgreSQL URL with the development password, labelled
  "development only". A `sqlite:///` URL is still accepted, so the stack can run without Docker
  in an emergency.

## 4. Database layer (`backend/`)

- **New dependencies:** `psycopg[binary]>=3.2`, `alembic>=1.13`, `geoalchemy2>=0.15`. All are free,
  with no account or key.
- **Alembic** (`backend/alembic.ini`, `backend/migrations/`):
  - **Revision 0001:** `CREATE EXTENSION IF NOT EXISTS postgis`; the current tables `telemetry`,
    `incident`, `incident_event` with their indexes; and the column
    `incident.origin geography(Point, 4326)` with a GiST index.
  - **The migration environment** takes the URL from the same configuration as the backend.
- **`Store`:**
  - **On PostgreSQL**, it doesn't create tables itself (Alembic owns the schema) and checks at
    startup that the schema is at the latest revision. If not, it stops with "run
    `alembic upgrade head`".
  - **On SQLite** (unit tests), it keeps `create_all`. The old `_add_missing_columns` shortcut is
    removed.
  - **`save_incident`** also writes `origin` from `estimated_origin` (lon/lat) when it has one.
    On SQLite the column holds the WKT text, so the same code runs.
  - **`incidents_near(lon, lat, radius_km) -> list[int]`** returns the ids of incidents whose
    origin is within the radius, nearest first. It uses `ST_DWithin`/`ST_Distance` on geography.
    It is available on PostgreSQL only; on SQLite it raises a clear `NotImplementedError`.
- **API:** `GET /api/v1/incidents` accepts optional `near=lat,lon&radius_km=…` (0 < radius ≤ 100)
  and then returns only the matching incidents, nearest first. The parameters are validated
  (422 on bad input). `contracts/api.md` is updated.

## 5. Data migration (one time)

- **`python -m wamidh_backend.migrate_sqlite [--from data/dev/wamidh.db]`:**
  - copies every telemetry row (in batches of 5,000) and every incident with its full event log
    into PostgreSQL;
  - keeps the incident ids, and moves the id sequences past them so new incidents don't collide.
- **Safeguards:**
  - it refuses to run if the target already holds incidents or telemetry, unless `--force` is
    given;
  - it prints the counts copied;
  - it never modifies the SQLite file.

## 6. Tests

- **Unit tests stay on SQLite:** the existing 47 backend tests, plus new ones for:
  - the URL selection (environment variable before YAML);
  - `origin` written by `save_incident`;
  - `incidents_near` raising on SQLite;
  - the `near` parameter validation.
- **Integration tests** (`backend/tests/integration/`, marker `postgres`):
  - **When they run:** only if `WAMIDH_TEST_DATABASE_URL` is set and reachable, otherwise
    skipped with a reason. Each test runs in its own fresh schema.
  - **What they cover:**
    - the schema migrates up from empty;
    - incidents and logs survive a new `Store`;
    - telemetry history;
    - `incidents_near` returns the right incidents in distance order (a known set of points 1,
      4 and 9 km away);
    - the `/incidents?near=` endpoint;
    - the SQLite-to-PostgreSQL migration (counts, ids, sequences, refusal to run twice).
- **Live check:**
  1. `dev.ps1` brings up the database;
  2. the migration copies the current data;
  3. the dashboard shows the same 35 incidents and the sensor trends;
  4. a test fire creates incident #36.

## 7. Documentation

- **ADR 0002** (written).
- **Updated:** `backend/README.md` (how to start, migrate, run the integration tests), `data/README.md`
  (the SQLite file is now a legacy backup), and the root README's quickstart if it mentions the
  database.

## 8. Out of scope

- The telemetry retention job, the encrypted backup scripts, and the CI service container (ADR
  0002, "To do later").
- Storing nodes, stations or access points in the database (they still come from the registry
  and the config).
- Any dashboard change.

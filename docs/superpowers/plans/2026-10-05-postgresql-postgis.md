# PostgreSQL + PostGIS store: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** the backend stores telemetry, incidents and their audit log in PostgreSQL + PostGIS
(Docker), with versioned migrations, the existing SQLite data carried over, and a distance
search over the incident history.

**Architecture:**
- **One URL decides the database.** `WAMIDH_DATABASE_URL` is used first, else `backend/config/dev.yaml`.
- **On PostgreSQL**, Alembic owns the schema and `Store` refuses to start on an outdated one.
- **On SQLite** (unit tests), `Store` still calls `create_all`.
- **Incident origins** are stored as `geography(Point, 4326)`. On SQLite the same column holds
  EWKT text, so one code path serves both.
- **The live incident logic** (`Core`) stays in memory (ADR 0002).

**Tech stack:** PostgreSQL 16 + PostGIS 3.4 (`postgis/postgis:16-3.4`), SQLAlchemy 2, psycopg 3,
Alembic, GeoAlchemy2, pytest.

**Spec:** `docs/superpowers/specs/2026-10-05-postgresql-postgis-design.md`. **ADR:** `docs/adr/0002-postgresql-postgis-authority-hosted.md`.

## Global constraints

- **Network:** the database port is published on `127.0.0.1` only.
- **Secrets:** no password in committed files except the development-only value in
  `.env.example` and `backend/config/dev.yaml`, labelled as such. The real `.env` is git-ignored.
- **Coordinates:** stored as WGS84 (EPSG:4326). Distances are in metres on geography; the API takes km.
- **API compatibility:** the existing responses keep their shape; only the optional
  `near`/`radius_km` filter is new (0 < radius ≤ 100).
- **Migration safety:** the migration never modifies the SQLite file, and refuses a non-empty
  target unless `--force` is given.
- **Python quality:** ruff and `mypy --strict` must be clean on `backend/`.

## Review focus

1. **PostgreSQL not running at startup:** the backend must stop with a clear message, not a traceback. Test: `test_unreachable_database_gives_a_clear_message`.
2. **Schema not migrated (empty database):** the backend must say "run the migration", not crash on a missing table. Test: `test_store_refuses_an_unmigrated_schema` (integration).
3. **Incidents created after the data migration** must not reuse migrated ids, and log entries must not collide. Test: `test_new_rows_after_migration_get_fresh_ids` (integration).
4. **An incident without an origin** (`estimated_origin` missing or partial) must still save, with no origin. Test: `test_incident_without_origin_saves`.
5. **`near` with bad input** (`near=abc`, a radius of 0 or 500) must give a 422, and `near` on SQLite must give a 501, not a 500. Test: `test_near_validation` and `test_near_needs_postgresql`.

---

### Task 1: Database URL, origin column, `incidents_near` (SQLite unit level)

**Files:**
- Create: `backend/src/wamidh_backend/db.py`
- Modify: `backend/src/wamidh_backend/store.py`, `backend/src/wamidh_backend/__main__.py`, `backend/src/wamidh_backend/app.py`, `backend/pyproject.toml`, `backend/config/dev.yaml`
- Test: `backend/tests/test_db.py` (new), `backend/tests/test_store.py`, `backend/tests/test_api.py`

**Interfaces:**
- Produces:
  - `db.database_url(cfg: Mapping[str, Any], repo: Path, env: Mapping[str, str]) -> str`;
  - `db.check_reachable(url: str) -> None`, which raises `SystemExit` with a clear message;
  - `Store.incidents_near(lon: float, lat: float, radius_km: float) -> list[int]`;
  - `IncidentRow.origin` (EWKT `SRID=4326;POINT(lon lat)` or `None`).
- API: `GET /api/v1/incidents?near=lat,lon&radius_km=r`. It returns 422 on bad input and 501 on SQLite.

- [ ] **Step 1: Failing tests.** In `test_db.py`:
  - `database_url`: the environment variable wins; a relative `sqlite:///` path is resolved under the repo; a PostgreSQL URL passes through.
  - `check_reachable`: an unreachable PostgreSQL URL (port 1) raises `SystemExit` whose message names the URL host and says to start Docker.

  In `test_store.py`:
  - `save_incident` writes `origin = "SRID=4326;POINT(8.625 36.709)"`;
  - an incident with `estimated_origin={}` saves with `origin None` (`test_incident_without_origin_saves`);
  - `incidents_near` raises `NotImplementedError` on SQLite.

  In `test_api.py`:
  - `test_near_validation`: `near=abc`, a radius of 0 and a radius of 500 give 422;
  - `test_near_needs_postgresql`: a valid query on SQLite gives 501.
- [ ] **Step 2: Watch them fail.** `cd backend && ../.venv/Scripts/python -m pytest -q`
- [ ] **Step 3: Implement.**
  - **Dependencies:** add `psycopg[binary]>=3.2`, `alembic>=1.13`, `geoalchemy2>=0.15` to `pyproject.toml` and install them into `.venv`.
  - **`db.py`:** `database_url` resolves as described. `check_reachable` connects with a 5 s timeout and turns `OperationalError` into `SystemExit("Cannot reach the database at <host>:<port> — is Docker running? Start it with: docker compose up -d db")`.
  - **`store.py`:**
    - add `origin = mapped_column(Geography("POINT", 4326, spatial_index=False).with_variant(String, "sqlite"), nullable=True)`;
    - in `save_incident`, set `row.origin` to the EWKT when `estimated_origin` has both `lon` and `lat`, else `None`;
    - `incidents_near` raises `NotImplementedError("distance search needs PostgreSQL + PostGIS")` unless the dialect is postgresql. On PostgreSQL it runs `ST_DWithin(origin, ST_GeogFromText(:p), :m)` ordered by `ST_Distance` and returns the ids;
    - remove `_add_missing_columns`.
  - **`app.py`:** `incidents()` gets `near: str | None = None, radius_km: float = Query(5, gt=0, le=100)`. It parses `near` with the existing `_parse_lat_lon` (422 on error), maps `NotImplementedError` to 501, and returns the incidents for the ids in order.
  - **`__main__.py`:** use `database_url(cfg, REPO, os.environ)`, then `check_reachable(url)` for PostgreSQL URLs.
  - **`dev.yaml`:** `database: postgresql+psycopg://wamidh:wamidh-dev-only@127.0.0.1:5432/wamidh   # development only; deployment sets WAMIDH_DATABASE_URL`.
- [ ] **Step 4: Run** pytest, ruff and mypy: all green.

### Task 2: Alembic migrations, the schema check, Docker, `dev.ps1`

**Files:**
- Create: `backend/src/wamidh_backend/migrations/env.py`, `migrations/script.py.mako`, `migrations/versions/0001_initial.py`, `backend/alembic.ini`, `.env.example`
- Modify: `backend/src/wamidh_backend/db.py` (+ `upgrade(url)`, `schema_is_current(url)`, CLI `python -m wamidh_backend.db upgrade`), `store.py` (refuses an outdated schema on PostgreSQL), `docker-compose.yml`, `scripts/dev.ps1`
- Test: `backend/tests/integration/conftest.py`, `backend/tests/integration/test_postgres.py`

**Interfaces:**
- Produces:
  - `db.upgrade(url: str) -> None`;
  - `db.schema_is_current(url: str) -> bool`;
  - the fixture `pg_url` (a fresh schema per test, dropped afterwards) for the integration tests.
- [ ] **Step 1: Failing integration tests** (marker `postgres`; skipped unless `WAMIDH_TEST_DATABASE_URL` is set and reachable):
  - `test_store_refuses_an_unmigrated_schema`: `Store(pg_url)` on an empty schema raises `SystemExit` mentioning "upgrade".
  - `test_migrations_create_the_schema_with_postgis`: after `upgrade`, the tables `telemetry`, `incident`, `incident_event` exist, `incident.origin` is of type geography, and a GiST index covers it.
  - `test_incidents_and_logs_survive_a_new_store`: save an incident with 3 events; a new `Store` loads it equal.
  - `test_telemetry_history`: `telemetry_since` and `node_memory` behave as on SQLite.
  - `test_incidents_near_in_distance_order`: incidents at about 1, 4 and 9 km from a point; a 5 km radius returns `[1 km id, 4 km id]` in that order.
  - `test_api_near_on_postgres`: `/incidents?near=…&radius_km=5` returns the same two, in order.
- [ ] **Step 2: Start PostgreSQL and watch the tests fail.**
  - Add the `db` service to `docker-compose.yml`:
    - image `postgis/postgis:16-3.4`;
    - `POSTGRES_DB`/`POSTGRES_USER=wamidh`, `POSTGRES_PASSWORD` from `${POSTGRES_PASSWORD:-wamidh-dev-only}`;
    - ports `127.0.0.1:5432:5432`;
    - volume `wamidh-pgdata`;
    - health check `pg_isready -U wamidh -d wamidh`;
    - `restart: unless-stopped`.
  - Create `.env.example` (spec §2).
  - Run `docker compose up -d db`, then set `WAMIDH_TEST_DATABASE_URL` to the development URL.
- [ ] **Step 3: Implement.**
  - **`0001_initial.py`:** creates the extension and the three tables exactly as the models define them (including the existing indexes `ix_telemetry_node_id`, `ix_telemetry_received_at`, `ix_incident_event_incident_id`), plus `incident.origin geography(Point,4326)` and the index `ix_incident_origin` (GiST).
  - **`env.py`:** takes the URL from `config.get_main_option("sqlalchemy.url")` (set by `db.upgrade`) or from `database_url(...)` for the CLI.
  - **`db.upgrade`:** builds an Alembic `Config` programmatically (`script_location` = the package's `migrations` folder) and runs `command.upgrade(cfg, "head")`.
  - **`schema_is_current`:** compares the `MigrationContext` current revision with the script head.
  - **`Store.__init__`:** on postgresql, if the schema isn't current, raise `SystemExit("The database schema is not up to date. Run: python -m wamidh_backend.db upgrade")`; on sqlite, `create_all` as before.
  - **`dev.ps1`:**
    1. `docker compose up -d mqtt db`;
    2. wait for health with `docker inspect --format '{{.State.Health.Status}}'`, up to 60 s, failing with a clear message;
    3. `python -m wamidh_backend.db upgrade`;
    4. then the existing steps.
- [ ] **Step 4: Run** the integration tests (all pass) and the unit tests (still green).

### Task 3: One-time SQLite → PostgreSQL data migration

**Files:**
- Create: `backend/src/wamidh_backend/migrate_sqlite.py`
- Test: `backend/tests/integration/test_migrate_sqlite.py`

**Interfaces:**
- Produces: `migrate(source_url: str, target_url: str, force: bool = False, batch: int = 5000) -> dict[str, int]` (counts per table), plus a CLI `python -m wamidh_backend.migrate_sqlite [--from PATH] [--force]`.
- [ ] **Step 1: Failing tests** (integration):
  - `test_copies_incidents_logs_and_telemetry`: a SQLite source with 2 incidents (3 + 2 events) and 7 telemetry rows → the target has the same counts, the same ids, the same `load_incidents()`, and origins set.
  - `test_refuses_a_non_empty_target_unless_forced`.
  - `test_new_rows_after_migration_get_fresh_ids`: after migrating, saving a new telemetry row and a new incident event gives ids above the migrated maxima.
  - `test_source_file_is_not_modified`: the file's hash is unchanged.
- [ ] **Step 2: Watch them fail.**
- [ ] **Step 3: Implement.**
  - Read the source with the model tables (only mapped columns, so old extra columns are ignored), then copy in batches with Core `insert`.
  - Convert naive timestamps to UTC and compute `origin` for incidents.
  - Afterwards run `SELECT setval(pg_get_serial_sequence(t, 'id'), max(id))` for each non-empty table.
  - With `force`, `TRUNCATE incident_event, incident, telemetry RESTART IDENTITY` first.
- [ ] **Step 4: Run** the integration tests: all green.

### Task 4: Switch the live stack, migrate the real data, docs

- [ ] **Step 1:** `docker compose up -d db`, then `python -m wamidh_backend.db upgrade`.
- [ ] **Step 2:** `python -m wamidh_backend.migrate_sqlite --from data/dev/wamidh.db`. The counts must match the SQLite file: 35 incidents and the telemetry total.
- [ ] **Step 3:** restart the backend and the sensors in their own windows. Check:
  - `/api/v1/incidents` returns 35;
  - `/history` has points;
  - a test fire creates incident #36;
  - a near query returns incidents.
  - Take an Edge screenshot of the Incidents tab.
- [ ] **Step 4: Docs.**
  - `backend/README.md`: start, migrate, integration tests;
  - `data/README.md`: the SQLite file is a legacy backup;
  - `contracts/api.md`: the `near` and `radius_km` parameters;
  - the root README's quickstart, if it mentions the database.

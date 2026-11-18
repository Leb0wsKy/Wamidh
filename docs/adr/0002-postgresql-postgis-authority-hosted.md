# ADR 0002: PostgreSQL + PostGIS, hosted by the authorities

- **Status:** accepted (2026-10-05)
- **Affects:** `backend/`, `docker-compose.yml`, `scripts/dev.ps1`, deployment

## Context

The backend has stored everything (sensor readings, incidents and their audit log) in a single
SQLite file since the first prototype. That was the right tool to get started, but it has three
limits for what Wamidh must become:

1. **Concurrency.** A station screen, several crew phones and the sensor ingest write at the
   same time. SQLite locks the whole file for each write.
2. **Geography.** Fires, sensors, roads and villages are places. SQLite cannot answer "which past
   fires were within 5 km of this sensor?" without loading everything into Python.
3. **Deployment.** A Civil Protection service needs a server database with accounts, encrypted
   connections, backups and versioned schema changes.

The question was also raised whether a hosted cloud database (Firebase) would be simpler.

## Decision

- **PostgreSQL 16 with the PostGIS 3 extension** stores all backend data, run from the official
  `postgis/postgis` container image.
  - In development and in the demo, it runs on the same laptop next to the MQTT broker, so the
    whole system still works **offline** (CLAUDE.md §11).
  - In deployment, it runs on a **server operated by the authorities**, ideally hosted in
    Tunisia.
- **Schema changes are versioned with Alembic.** The first migration creates the current tables
  and enables PostGIS.
- **Geography is stored as geography.** Incident origins are WGS84 points (EPSG:4326, as CLAUDE.md
  §4 requires) with a spatial index, so the history can be searched by distance.
- **Automated tests** keep a fast SQLite path for unit tests, plus integration tests against
  the real PostgreSQL.
- **Existing data is migrated once** from the SQLite file, which is kept as a backup.

## Privacy and security (deployment)

- **Data residency.** Incident logs, crew movements and residents' subscriptions stay on a server
  the authorities control, not with a foreign cloud provider.
- **Access.**
  - The database accepts connections only from the backend: it is never exposed to the internet
    or to the dashboard.
  - Connections use TLS.
  - The backend uses its own account with only the rights it needs.
- **Secrets.** The database password comes from the environment (`WAMIDH_DATABASE_URL`) and
  is never committed. `.env.example` holds a development-only value.
- **Backups.** A nightly `pg_dump`, encrypted before it leaves the server, with restore tested
  regularly.
- **Personal data.** Residents' phone numbers are stored encrypted, with a hash for lookups
  (CLAUDE.md §8); consent and revocation are recorded.

## Retention

| Data | Kept | Why |
|---|---|---|
| Incidents and their event log | forever | the audit trail: who knew what, and when |
| Raw sensor telemetry | 90 days (**ASSUMPTION**, to be agreed with the authorities) | trends, investigations after a fire |
| Telemetry older than that | hourly averages, forever | long-term sensor health and the report's statistics |

Size, for scale: 200 nodes reporting every 15 minutes in `NORMAL` produce about 19,000 readings a
day, roughly 7 million a year. That's comfortable for PostgreSQL on a modest server. The
retention job itself is a later step; this ADR fixes the rule.

## Alternatives considered

| Option | Why not |
|---|---|
| **Stay on SQLite** | Single-writer locking, no spatial queries, not a deployment database. |
| **Firebase (Firestore)** | Needs internet (breaks the offline demo); needs a Google account and key; stores Civil Protection data on servers abroad; no spatial queries; would duplicate or bypass the backend's signature checks, audit log and live feed. Worth reconsidering only for push notifications to phones, where the free Web Push standard is used instead. |
| **PostgreSQL without PostGIS, add it later** | Saves almost nothing (same image size, one extension), and would mean a second data migration. |
| **Move the live incident join (3 km) into the database** | It only ever looks at the few open incidents the backend keeps in memory; a database round-trip would add latency to an alarm and tie the incident logic to PostgreSQL. PostGIS is used for the history instead. |

## Consequences

- **Good:**
  - concurrent writes;
  - spatial search over the whole history;
  - versioned schema;
  - a credible deployment and privacy story;
  - still free and offline.
- **Cost:**
  - Docker must be running for the full stack;
  - two more Python dependencies (`psycopg`, `GeoAlchemy2`);
  - a one-time data migration.
- **To do later:**
  - the retention job;
  - encrypted backup scripts for the server;
  - a CI service container for the integration tests.

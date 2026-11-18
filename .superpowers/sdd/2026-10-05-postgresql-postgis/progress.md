# SDD ledger — plan: docs/superpowers/plans/2026-10-05-postgresql-postgis.md
Spec: docs/superpowers/specs/2026-10-05-postgresql-postgis-design.md
Setup: Ruling: no git repository — no worktree or commits; ledger by hand — cost if wrong: team commits after git init.
Pre-flight: T1→T2 db.py extended (upgrade, schema_is_current); T1→T3 Store models/origin used by migrate: consistent.
Task 1: Ruling: removed test_an_older_database_gets_the_new_columns — it tested the add-missing-column shortcut the spec removes in favour of Alembic — cost if wrong: none.
Task 1: complete (no commits: no git; tests: backend pytest → 55 passed; ruff + mypy clean)
Task 2: Ruling: host port 5433 instead of 5432 — a PostgreSQL already installed on this PC listens on 5432 and must not be touched — cost if wrong: one port number in compose, dev.yaml and .env.example.
Task 2: Ruling: host port 5433 instead of 5432 — a PostgreSQL already installed on this PC listens on 5432 and must not be touched — cost if wrong: one port number in compose, dev.yaml and .env.example.
Task 2: Ruling: dev.ps1 runs 'python -m wamidh_backend.db upgrade' rather than the alembic CLI — same rules for the URL as the backend, clear message when the DB is unreachable — cost if wrong: none.
Task 2: Ruling: dev.ps1 finds the db container with 'docker compose ps -q db', not by name — the name depends on the folder, which will be renamed — cost if wrong: none.
Task 2: complete (no commits: no git; tests: backend pytest with WAMIDH_TEST_DATABASE_URL → 61 passed; without → 55 passed, 6 skipped; ruff + mypy clean)
Task 3: complete (no commits: no git; tests: backend pytest with PostgreSQL → 65 passed, 1 warning in 11.37s; migrate_sqlite opens the source read-only)
Task 4: Ruling: /incidents?status=open in api.md was never implemented; documented the real behaviour (all incidents) next to the new near filter — cost if wrong: doc only.
Task 4: complete (live: 35 incidents, 240 events, 22,687 readings copied and matching; backend and sensors on PostgreSQL; test fire created #36 with a PostGIS origin; near search returns 33 within 3 km of sensor 2)
Final review: self-review (no reviewer agent dispatched — the user did not ask for one); checked URL resolution, unreachable/unmigrated messages, read-only source, sequences, secrets, API compatibility. No findings.
Final: minor (deferred): Store opens a second short-lived engine at startup to check the schema revision.
Final: INCIDENT: integration tests used schema t_xxx with search_path t_xxx,public; once the real data was migrated into public, tests fell through to the real tables and one --force test truncated them. Cause found by systematic debugging after 10 failures in the final run.
Final: fixed test isolation — tests now use a separate database <name>_test (public holds only PostGIS), refuse the development database name; guard test test_isolated_from_development_data RED→GREEN; suite 66/66.
Final: restored development data from the read-only SQLite backup (migrate_sqlite --force): 35 incidents, 240 events, 22,687 readings, verified identical; lost: test incident #36 and readings received between the first migration and the restore (minutes).
Final: verified isolation live: full suite run while the stack ran; real data unchanged (35/240/max id 35), no test schemas left.

# SDD ledger — plan: docs/superpowers/plans/2026-10-05-alert-zones-cell-broadcast.md
Spec: docs/superpowers/specs/2026-10-05-alert-zones-cell-broadcast-design.md
Setup: Ruling: no git — no worktree/commits; ledger by hand; user pre-approved straight-through execution — cost if wrong: team commits after git init.
Setup: Ruling: OpenCelliD download format implemented from its published bulk format (docs return HTTP 403 to tools); verified on first real download — cost if wrong: parser adjustment.
Task 1: Ruling: zones built from OSM buildings + settled WorldPop cells (spec said OSM buildings only) — OSM maps ~11% of the population here; with cells, 143 zones cover ~131,000 of ~145,000 people (90%) — cost if wrong: zone outlines include cells WorldPop marks as built.
Task 1: Ruling: zone names are the OSM 'name' (Arabic in Geofabrik extracts; no Latin field available) and 'near' for douars — cost if wrong: Latin names need another source.
Task 1: complete (no commits: no git; tests: zones pytest -> 10 passed; real run: 143 zones, ~131,110 people, towers pending the OpenCelliD key)
Task 2: complete (store models, migration 0002, load_zones; tests: backend pytest with PG -> 73 passed)
Task 3: Ruling: public_alert gains zone_labels (JSON) so /alerts shows the Arabic names as sent, edited into migration 0002 (not yet applied to the dev DB) — cost if wrong: one column
Task 3: Ruling: zone search goes through a ZoneSource protocol (Store on PostgreSQL, fake in SQLite HTTP tests); alerts also refused on closed incidents; at most 3 zones named in the text (Cell Broadcast page length) — cost if wrong: config change
Task 3: complete (alerts.py, broadcast.py, config/alerts.yaml, 5 endpoints, contracts/api.md; tests: backend pytest with PG -> 88 passed, ruff + mypy --strict clean)
Task 4: Ruling: confirmed_by is the role 'dispatcher' (config ALERTS.confirmedBy) — no login exists yet — cost if wrong: audit names a role, not a person, until auth lands
Task 4: Ruling: Population section rendered inside IncidentDetail (children slot) before the timeline; Residents sidebar moves alerts above the map on phones when an alert is active — cost if wrong: layout tweak
Task 4: complete (Residents page, ZonesMap, ZonePanel, PhoneAlertCard, PopulationAlert, queries/types/i18n; tests: web vitest -> 120 passed, typecheck + oxlint clean)
Task 5: complete (migration 0002 applied to dev DB; 143 zones loaded, 0 towers pending key; backend+simulator restarted (duplicate stale windows stopped); live Edge check: Arabic default on /residents, zone panel, proposal, confirm, broadcast, phone card fr/ar, no page errors; test incident #41 closed as false alarm; docs: zones/README, backend/README, data/README, CLAUDE.md pointer, dev.ps1 loads zones)
Final review: self-review (no subagent: user asked not to spawn agents)
Final: minor (deferred): the pulse class on an alerted zone is set only when the polygon is first drawn (Leaflet ignores className in setStyle); the dashed ember outline does update
Final: minor (deferred): 'Diffuser une mise à jour' stays disabled briefly after sending, while the incident and alert lists refresh
Final: Ruling: workspace ledger kept (not deleted) — no git history exists yet to replace it as the record — cost if wrong: one stray git-ignored folder
Change (user request 2026-10-06): broadcast control moved from the incident view to the Residents tab ('Feux en cours' card, FireAlertPanel); map shows fire origin, concern radius and concerned zones; Incidents keeps the audit line only. Tests: web 123 passed.

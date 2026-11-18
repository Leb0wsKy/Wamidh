# ADR 0005: the project is named Wamidh

- **Status:** accepted, 2026-11-18
- **Scope:** whole repository, including the shared contract (`contracts/`)

## Context

The project started under the placeholder name "EmberGuard". The Phase 1 report was submitted as
**Wamidh**, so the code, the documentation and the report must use the same name.

## Decision

Rename everything at once, before any hardware exists:

| What | Before | After |
|---|---|---|
| MQTT topic prefix (contract) | `emberguard/v1/...` | `wamidh/v1/...` |
| Python packages | `emberguard_backend`, `emberguard_contracts`, `emberguard_sim`, `emberguard_spread` | `wamidh_*` |
| Environment variables | `EMBERGUARD_DATABASE_URL`, `EMBERGUARD_TEST_DATABASE_URL` | `WAMIDH_*` |
| Development database (Docker) | user and database `emberguard`, volume `emberguard-pgdata` | `wamidh`, `wamidh-pgdata` |
| Figure style | `docs/figures/emberguard.mplstyle` | `docs/figures/wamidh.mplstyle` |

The contract version stays `v1`: only the prefix changes, the topic layout and the payloads are the
same, and no deployed node or firmware uses the old prefix.

## Consequences

- Every component must be updated together; the simulator and the backend already are.
- The development database starts empty in a new Docker volume. The old volume is left untouched
  and can be deleted by hand once it is no longer needed.
- Earth Engine exports now go to the Drive folder `wamidh_gee`; rasters already downloaded to
  `data/raw/gee/` are unaffected.

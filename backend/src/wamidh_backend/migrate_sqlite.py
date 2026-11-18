"""One-time copy of the development SQLite database into PostgreSQL (ADR 0002).

    python -m wamidh_backend.migrate_sqlite [--from data/dev/wamidh.db] [--force]

Copies every incident with its full event log and every telemetry reading, keeping the ids.
Refuses a target that already holds data unless --force (which replaces it). Never writes to
the SQLite file: it stays as a backup.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import Engine, Table, create_engine, func, insert, select, text

from wamidh_backend.db import REPO, check_reachable, database_url, is_postgres
from wamidh_backend.store import IncidentEventRow, IncidentRow, TelemetryRow, _ewkt

TABLES: list[Table] = [
    IncidentRow.__table__,  # type: ignore[list-item]
    IncidentEventRow.__table__,  # type: ignore[list-item]
    TelemetryRow.__table__,  # type: ignore[list-item]
]


def _utc(v: Any) -> Any:
    # SQLite returns naive datetimes; everything was stored as UTC.
    return v.replace(tzinfo=UTC) if isinstance(v, datetime) and v.tzinfo is None else v


def _read_only(sqlite_url: str) -> Engine:
    """Open the SQLite file read-only: the migration can never modify the backup."""
    path = Path(sqlite_url.removeprefix("sqlite:///")).resolve()
    uri = f"file:{path.as_posix()}?mode=ro"
    return create_engine("sqlite://", creator=lambda: sqlite3.connect(uri, uri=True))


def _copy(src: Engine, dst: Engine, table: Table, batch: int) -> int:
    # Only the columns the old file has: `incident.origin` is new and computed here instead.
    columns = [c for c in table.c if c.name != "origin"]
    copied = 0
    with src.connect() as s, dst.begin() as d:
        result = s.execution_options(yield_per=batch).execute(select(*columns).order_by(table.c.id))
        for chunk in result.partitions(batch):
            rows = [{k: _utc(v) for k, v in r._mapping.items()} for r in chunk]
            if table.name == "incident":
                for r in rows:
                    r["origin"] = _ewkt(r["estimated_origin"])
            d.execute(insert(table), rows)
            copied += len(rows)
    return copied


def migrate(
    source_url: str, target_url: str, force: bool = False, batch: int = 5000
) -> dict[str, int]:
    """Copy incidents, their logs and telemetry; return the number of rows copied per table."""
    src = _read_only(source_url)
    dst = create_engine(target_url)
    try:
        with dst.connect() as d:
            held = {
                t.name: int(d.execute(select(func.count()).select_from(t)).scalar() or 0)
                for t in TABLES
            }
        if any(held.values()) and not force:
            raise SystemExit(
                f"The target already holds {held['incident']} incidents and {held['telemetry']} "
                "readings. Run with --force to replace them."
            )
        if force:
            with dst.begin() as d:
                d.execute(
                    text("TRUNCATE incident_event, incident, telemetry RESTART IDENTITY CASCADE")
                )
        counts = {t.name: _copy(src, dst, t, batch) for t in TABLES}
        # New rows must not reuse copied ids: move each id sequence past the copied maximum.
        with dst.begin() as d:
            for t in TABLES:
                if counts[t.name]:
                    d.execute(
                        text(
                            f"SELECT setval(pg_get_serial_sequence('{t.name}', 'id'), "
                            f"(SELECT max(id) FROM {t.name}))"
                        )
                    )
        return counts
    finally:
        src.dispose()
        dst.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Copy the SQLite database into PostgreSQL")
    parser.add_argument(
        "--from", dest="source", type=Path, default=REPO / "data" / "dev" / "wamidh.db"
    )
    parser.add_argument("--config", type=Path, default=REPO / "backend" / "config" / "dev.yaml")
    parser.add_argument("--force", action="store_true", help="replace data already in the target")
    args = parser.parse_args()
    if not args.source.exists():
        raise SystemExit(f"{args.source} not found")
    target = database_url(yaml.safe_load(args.config.read_text(encoding="utf-8")), REPO, os.environ)
    if not is_postgres(target):
        raise SystemExit(
            "The target database (WAMIDH_DATABASE_URL or dev.yaml) is not PostgreSQL."
        )
    check_reachable(target)
    counts = migrate(f"sqlite:///{args.source.resolve()}", target, force=args.force)
    print("Copied: " + ", ".join(f"{n} {name}" for name, n in counts.items()))
    print(f"The SQLite file {args.source} was not modified; keep it as a backup.")


if __name__ == "__main__":
    main()

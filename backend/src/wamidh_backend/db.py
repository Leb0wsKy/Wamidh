"""Which database the backend uses, and how its schema is kept up to date (ADR 0002).

    python -m wamidh_backend.db upgrade     # apply the Alembic migrations

The URL comes from the WAMIDH_DATABASE_URL environment variable (deployment: set by the
authorities' server, never committed), else from `database:` in backend/config/dev.yaml.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

ENV_VAR = "WAMIDH_DATABASE_URL"
MIGRATIONS = Path(__file__).resolve().parent / "migrations"
REPO = Path(__file__).resolve().parents[3]


def database_url(cfg: Mapping[str, Any], repo: Path, env: Mapping[str, str]) -> str:
    url = env.get(ENV_VAR) or str(cfg["database"])
    # A relative SQLite path (development fallback) is relative to the repository root.
    if url.startswith("sqlite:///") and not url.startswith("sqlite:////"):
        path = Path(url.removeprefix("sqlite:///"))
        if not path.is_absolute():
            path = repo / path
        url = f"sqlite:///{path}"
    return url


def is_postgres(url: str) -> bool:
    return make_url(url).get_backend_name() == "postgresql"


def check_reachable(url: str) -> None:
    """Stop with a clear message, not a traceback, when PostgreSQL is not running."""
    u = make_url(url)
    engine = create_engine(url, connect_args={"connect_timeout": 5})
    try:
        with engine.connect():
            pass
    except OperationalError as e:
        raise SystemExit(
            f"Cannot reach the database at {u.host}:{u.port} — is Docker running? "
            "Start it with: docker compose up -d db"
        ) from e
    finally:
        engine.dispose()


def _alembic_config(url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    # Alembic's config parser treats % as interpolation: escape it (URL-encoded options).
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


def upgrade(url: str) -> None:
    """Bring the schema to the latest revision (creates it on an empty database)."""
    command.upgrade(_alembic_config(url), "head")


def schema_is_current(url: str) -> bool:
    head = ScriptDirectory.from_config(_alembic_config(url)).get_current_head()
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            return MigrationContext.configure(connection).get_current_revision() == head
    finally:
        engine.dispose()


def main() -> None:
    import yaml

    parser = argparse.ArgumentParser(description="Wamidh database schema")
    parser.add_argument("action", choices=["upgrade"])
    parser.add_argument("--config", type=Path, default=REPO / "backend" / "config" / "dev.yaml")
    args = parser.parse_args()
    url = database_url(yaml.safe_load(args.config.read_text(encoding="utf-8")), REPO, os.environ)
    if not is_postgres(url):
        raise SystemExit("Migrations are for PostgreSQL; SQLite databases create their tables.")
    check_reachable(url)
    upgrade(url)
    print(f"Database schema at the latest revision ({make_url(url).host}:{make_url(url).port}).")


if __name__ == "__main__":
    main()

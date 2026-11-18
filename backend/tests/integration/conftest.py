"""Integration tests against a real PostgreSQL + PostGIS (ADR 0002).

They run only when WAMIDH_TEST_DATABASE_URL points at a reachable server, e.g. the
development container (docker compose up -d db). The tests never use that database itself: they
create a separate database `<name>_test` on the same server, whose `public` schema holds only
PostGIS, and give each test a fresh schema in it, dropped afterwards. Real tables are therefore
never on a test's search path (an earlier version that used the real database's `public` let
tests fall through to the development tables).
"""

from __future__ import annotations

import os
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

BASE_URL = os.environ.get("WAMIDH_TEST_DATABASE_URL")
# Shared helpers live next to the unit tests (e.g. test_zones_store.zone).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _reachable(url: str) -> bool:
    try:
        with create_engine(url, connect_args={"connect_timeout": 3}).connect():
            return True
    except OperationalError:
        return False


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    reason = (
        "set WAMIDH_TEST_DATABASE_URL to a reachable PostgreSQL + PostGIS"
        if not BASE_URL
        else None
        if _reachable(BASE_URL)
        else f"PostgreSQL not reachable at {make_url(BASE_URL).host}:{make_url(BASE_URL).port}"
    )
    for item in items:
        if "integration" in str(item.fspath):
            item.add_marker(pytest.mark.postgres)
            if reason:
                item.add_marker(pytest.mark.skip(reason=reason))


def _test_database_url() -> str:
    """URL of `<name>_test` on the same server, created (with PostGIS) on first use."""
    assert BASE_URL
    base = make_url(BASE_URL)
    name = f"{base.database}_test"
    if name == base.database:
        raise RuntimeError("refusing to run integration tests in the development database")
    admin = create_engine(BASE_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        exists = c.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": name}
        ).scalar()
        if not exists:
            c.execute(text(f'CREATE DATABASE "{name}"'))
    admin.dispose()
    url = base.set(database=name).render_as_string(hide_password=False)
    engine = create_engine(url)
    with engine.begin() as c:
        c.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    engine.dispose()
    return url


@pytest.fixture
def pg_url() -> Iterator[str]:
    """A fresh, empty schema in the test database (PostGIS stays visible via public)."""
    test_db = _test_database_url()
    schema = f"t_{uuid.uuid4().hex[:12]}"
    admin = create_engine(test_db)
    with admin.begin() as c:
        c.execute(text(f'CREATE SCHEMA "{schema}"'))
    url = make_url(test_db).update_query_dict({"options": f"-csearch_path={schema},public"})
    try:
        yield url.render_as_string(hide_password=False)
    finally:
        with admin.begin() as c:
            c.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()

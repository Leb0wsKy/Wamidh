from pathlib import Path

import pytest

from wamidh_backend.db import check_reachable, database_url

REPO = Path("C:/repo")
PG = "postgresql+psycopg://wamidh:pw@127.0.0.1:5432/wamidh"


def test_the_environment_variable_wins_over_the_config_file() -> None:
    url = database_url(
        {"database": "sqlite:///data/dev/x.db"}, REPO, {"WAMIDH_DATABASE_URL": PG}
    )

    assert url == PG


def test_a_relative_sqlite_path_is_resolved_under_the_repository() -> None:
    url = database_url({"database": "sqlite:///data/dev/x.db"}, REPO, {})

    assert url == f"sqlite:///{REPO / 'data/dev/x.db'}"


def test_a_postgresql_url_from_the_config_passes_through() -> None:
    assert database_url({"database": PG}, REPO, {}) == PG


def test_unreachable_database_gives_a_clear_message() -> None:
    with pytest.raises(SystemExit) as e:
        check_reachable("postgresql+psycopg://wamidh:pw@127.0.0.1:1/wamidh")

    assert "127.0.0.1:1" in str(e.value) and "docker compose up -d db" in str(e.value)

"""Alembic environment: the URL is set by wamidh_backend.db (same rules as the backend)."""

from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine

from wamidh_backend.store import Base

config = context.config
target_metadata = Base.metadata


def run_migrations_online() -> None:
    url = config.get_main_option("sqlalchemy.url")
    assert url, "wamidh_backend.db sets sqlalchemy.url"
    engine = create_engine(url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


run_migrations_online()

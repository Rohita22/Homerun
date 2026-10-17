"""SQLAlchemy declarative base and engine/session factory.

SQLite is run in WAL mode per PRD section 9 ("Use SQLite WAL mode for hackathon; PostgreSQL
optional"). The engine is created from ``Settings.homerun_database_url`` so swapping to Postgres
in production is a single environment variable change.
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()

_connect_args = {"check_same_thread": False} if settings.is_sqlite else {}
engine = create_engine(settings.homerun_database_url, connect_args=_connect_args, future=True)


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:  # noqa: ANN001
    if not settings.is_sqlite:
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    """Create all tables if they do not exist. Hackathon-speed substitute for Alembic
    migrations; the schema version is still recorded via ``recommendation_runs.model_version``
    and the ML artifact metadata (PRD section 9: "Persist ... schema version")."""
    from app.db import models  # noqa: F401 (ensure models are registered on Base.metadata)

    Base.metadata.create_all(bind=engine)


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

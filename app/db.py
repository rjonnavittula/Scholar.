"""Database engine + session helpers.

Defaults to SQLite for zero-config local runs; point HIVE_DATABASE_URL at
Postgres for the self-hosted / H.I.V.E. deployment.
"""
import os

from sqlmodel import Session, SQLModel, create_engine

DATABASE_URL = os.getenv("HIVE_DATABASE_URL", "sqlite:///./hive.db")

# check_same_thread is a SQLite-only quirk; harmless to omit for Postgres.
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, echo=False, connect_args=_connect_args)


def init_db() -> None:
    """Create tables. Fine for v0 — swap for Alembic migrations before prod."""
    # Importing models here guarantees they're registered on metadata.
    from app import models  # noqa: F401

    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session

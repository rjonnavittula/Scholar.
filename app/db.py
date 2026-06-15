"""DB engine/session + schema bootstrap.

Bootstrap strategy (v4a):
  - On first boot, create_all() builds the current schema and we `stamp` it to
    the Alembic baseline (0001). 
  - On later boots, `alembic upgrade head` applies any new migrations.
  - To evolve the schema later: edit models, then
        docker compose exec hive-api alembic revision --autogenerate -m "msg"
        docker compose exec hive-api alembic upgrade head
    No more `docker compose down -v`.
"""
import os

from sqlmodel import Session, SQLModel, create_engine, select

DATABASE_URL = os.getenv("HIVE_DATABASE_URL", "sqlite:///./hive.db")
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, echo=False, connect_args=_connect_args)


def _alembic_cfg():
    from alembic.config import Config
    cfg = Config("alembic.ini")
    cfg.set_main_option("script_location", "alembic")
    cfg.set_main_option("sqlalchemy.url", DATABASE_URL)
    return cfg


def init_db() -> None:
    from app import models
    from sqlalchemy import inspect

    insp = inspect(engine)
    fresh = not insp.has_table("task")

    if fresh:
        SQLModel.metadata.create_all(engine)

    # Alembic bookkeeping: stamp baseline on a fresh DB, else upgrade to head.
    try:
        from alembic import command
        cfg = _alembic_cfg()
        if fresh and not insp.has_table("alembic_version"):
            command.stamp(cfg, "0001_baseline")
        else:
            command.upgrade(cfg, "head")
    except Exception as e:  # never block boot on migration tooling
        print(f"[alembic] skipped ({e})")

    _seed()


def _seed() -> None:
    from app import models
    with Session(engine) as s:
        if not s.get(models.Settings, 1):
            s.add(models.Settings(id=1))
        if not s.exec(select(models.AwakeTime)).first():
            for wd in range(7):
                s.add(models.AwakeTime(weekday=wd, start_min=480, end_min=1410))
        s.commit()


def get_session():
    with Session(engine) as session:
        yield session

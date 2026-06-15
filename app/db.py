"""DB engine/session + first-boot seeding."""
import os

from sqlmodel import Session, SQLModel, create_engine, select

DATABASE_URL = os.getenv("HIVE_DATABASE_URL", "sqlite:///./hive.db")
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, echo=False, connect_args=_connect_args)


def init_db() -> None:
    from app import models

    SQLModel.metadata.create_all(engine)
    # seed defaults once
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

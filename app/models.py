"""HIVE Scholar v2 models.

Shovel-style anatomy: awake windows define where study time can exist,
activities and planned blocks consume it, the engine computes what's left,
and the cushion answers whether what's left covers what's due.

Times-of-day are stored as minutes since midnight (0..1440) to keep the
engine integer-pure. Datetimes are naive local (single-user, self-hosted).
"""
from __future__ import annotations

import enum
from datetime import date, datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class TaskStatus(str, enum.Enum):
    todo = "todo"
    done = "done"


class Source(str, enum.Enum):
    manual = "manual"
    canvas = "canvas"
    api = "api"


class Course(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    color: str = "#8A7F73"
    source: Source = Source.manual
    external_id: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=datetime.now)


class Task(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    notes: str = ""
    course_id: Optional[int] = Field(default=None, foreign_key="course.id", index=True)
    category: str = ""                      # Homework / Quiz / Reading / ...
    due_at: Optional[datetime] = Field(default=None, index=True)
    start_date: Optional[date] = None       # "start ahead" anchor
    time_needed_min: int = 60
    time_spent_min: int = 0
    priority_flag: bool = False
    status: TaskStatus = TaskStatus.todo
    source: Source = Source.manual
    external_id: Optional[str] = Field(default=None, index=True)
    due_tz: Optional[str] = None          # IANA zone the due time was set in
    completed_at: Optional[datetime] = None   # UTC instant the task was marked done
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    @property
    def remaining_min(self) -> int:
        if self.status == TaskStatus.done:
            return 0
        return max(0, self.time_needed_min - self.time_spent_min)


class AwakeTime(SQLModel, table=True):
    """One row per weekday (0=Mon..6=Sun). Study time only exists inside."""
    id: Optional[int] = Field(default=None, primary_key=True)
    weekday: int = Field(index=True)
    start_min: int = 480     # 08:00
    end_min: int = 1410      # 23:30


class Activity(SQLModel, table=True):
    """Recurring weekly block (lecture, lunch, workout...). Consumes time."""
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    color: str = "#5A5348"
    weekday: int = Field(index=True)
    start_min: int
    end_min: int
    tz: Optional[str] = None          # IANA zone; None = use home_tz
    course_id: Optional[int] = Field(default=None, foreign_key="course.id")


class PlannedBlock(SQLModel, table=True):
    """A DO date: this task, planned into this slot on the calendar."""
    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: int = Field(foreign_key="task.id", index=True)
    start_at: datetime = Field(index=True)
    end_at: datetime
    completed: bool = False


class Term(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = "Term"
    classes_start: Optional[date] = None
    classes_end: Optional[date] = None
    exam_end: Optional[date] = None


class Holiday(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    day: date = Field(index=True)
    name: str = ""


class Settings(SQLModel, table=True):
    """Single row (id=1)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    min_block_min: int = 30
    start_ahead_days: int = 3
    yellow_threshold_pct: int = 40
    day_start_min: int = 480          # calendar scroll-to
    home_tz: str = "America/New_York"     # your current physical zone
    school_tz: str = "America/New_York"   # where due dates are anchored
    week_start: int = 6                   # 0=Mon .. 6=Sun (calendar week start)
    country: str = "US"                   # ISO-3166 for the location->tz picker
    onboarded: bool = False
    theme: str = "dark"
    accent: str = "#8A7F73"
    density: float = 1.0
    fontscale: float = 1.0
    default_view: str = "week"
    canvas_base_url: str = ""
    canvas_token: str = ""


class TimeLog(SQLModel, table=True):
    """A logged chunk of work on a task (manual or from a completed block)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: int = Field(foreign_key="task.id", index=True)
    minutes: int
    logged_at: datetime = Field(default_factory=datetime.now, index=True)  # UTC
    source: str = "manual"   # manual | block | timer


class ApiKey(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    label: str
    hashed_key: str = Field(index=True)
    created_at: datetime = Field(default_factory=datetime.now)
    revoked: bool = False

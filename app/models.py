"""Data models for the HIVE Tasks API (the 'Scholar' planning service).

Kept intentionally flat (FK ints, no lazy relationships) to keep the v0
surface small and the Cushion engine easy to reason about.
"""
from __future__ import annotations

import enum
from datetime import datetime, time
from typing import Optional

from sqlmodel import Field, SQLModel


class TaskStatus(str, enum.Enum):
    todo = "todo"
    in_progress = "in_progress"
    done = "done"


class TaskSource(str, enum.Enum):
    manual = "manual"
    canvas = "canvas"
    syllabus = "syllabus"
    api = "api"


# --------------------------------------------------------------------------- #
# Core entities
# --------------------------------------------------------------------------- #
class Course(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    code: Optional[str] = None
    color: Optional[str] = None  # hex, defaults to H.I.V.E. amber in UI
    # External mapping so re-imports update instead of duplicate.
    external_id: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Task(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    notes: str = ""
    course_id: Optional[int] = Field(default=None, foreign_key="course.id", index=True)

    due_at: Optional[datetime] = Field(default=None, index=True)
    # The two numbers Shovel cares about: how long it NEEDS vs how long you've SPENT.
    time_needed_min: int = 0
    time_spent_min: int = 0

    status: TaskStatus = TaskStatus.todo
    priority: int = 0  # 0 = none, higher = more urgent (for tie-breaks)
    source: TaskSource = TaskSource.manual
    external_id: Optional[str] = Field(default=None, index=True)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    @property
    def remaining_min(self) -> int:
        if self.status == TaskStatus.done:
            return 0
        return max(0, self.time_needed_min - self.time_spent_min)


class Commitment(SQLModel, table=True):
    """Recurring weekly busy block — classes, work, standing meetings.

    These subtract from your available study time, every week.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    weekday: int  # 0 = Monday ... 6 = Sunday (matches Python date.weekday())
    start: time
    end: time


class Event(SQLModel, table=True):
    """One-off calendar event that blocks study time on a specific day."""
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    start_at: datetime
    end_at: datetime


class ApiKey(SQLModel, table=True):
    """Hashed API keys. The plaintext is shown once at creation, never stored."""
    id: Optional[int] = Field(default=None, primary_key=True)
    label: str
    hashed_key: str = Field(index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    revoked: bool = False

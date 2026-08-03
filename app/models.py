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
    instructor: str = ""
    url: str = ""
    notes: str = ""
    credits: Optional[float] = None
    created_at: datetime = Field(default_factory=datetime.now)


class Task(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    notes: str = ""
    course_id: Optional[int] = Field(default=None, foreign_key="course.id", index=True)
    parent_id: Optional[int] = Field(default=None, foreign_key="task.id", index=True)
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
    theme: str = "light"
    accent: str = "#3D7DFF"
    density: float = 1.0
    fontscale: float = 1.0
    default_view: str = "week"
    display_name: str = ""
    canvas_base_url: str = ""
    canvas_token: str = ""
    canvas_ics_url: str = ""
    canvas_autosync: bool = False
    canvas_sync_hours: int = 12
    canvas_last_sync: Optional[datetime] = None


class TimeLog(SQLModel, table=True):
    """A logged chunk of work on a task (manual or from a completed block)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: int = Field(foreign_key="task.id", index=True)
    minutes: int
    logged_at: datetime = Field(default_factory=datetime.now, index=True)  # UTC
    source: str = "manual"   # manual | block | timer


class ActiveTimer(SQLModel, table=True):
    """The single running timer (one row, id=1). Survives reloads."""
    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: int = Field(foreign_key="task.id")
    started_at: datetime = Field(default_factory=lambda: datetime.now(__import__("datetime").timezone.utc))
    accumulated_sec: int = 0   # banked time from prior run segments
    paused: bool = False


class ApiKey(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    label: str
    hashed_key: str = Field(index=True)
    created_at: datetime = Field(default_factory=datetime.now)
    revoked: bool = False


class GradeCategory(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    course_id: int = Field(foreign_key="course.id", index=True)
    name: str = ""
    weight: float = 0.0
    position: int = 0


class GradeItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    category_id: int = Field(foreign_key="gradecategory.id", index=True)
    course_id: int = Field(foreign_key="course.id", index=True)
    title: str = ""
    earned: float = 0.0
    possible: float = 0.0


class LearningTrack(SQLModel, table=True):
    """A Forge learning path generated from a prompt/source and saved server-side."""
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(index=True)
    input_type: str = "source_text"
    role: str = ""
    source_hash: str = Field(default="", index=True)
    status: str = "draft"   # draft | active | archived
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class LearningSource(SQLModel, table=True):
    """Trusted material registered for Scholar learning. Parsing/RAG comes later."""
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(index=True)
    source_type: str = "text"        # text | markdown | pdf | url | syllabus
    trust_level: str = "user"        # user | course | official | web
    status: str = "registered"      # registered | parsed | indexed | archived
    content_hash: str = Field(default="", index=True)
    mime_type: str = "text/plain"
    original_name: str = ""
    body_text: str = ""
    metadata_json: str = "{}"
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class LearningTrackSource(SQLModel, table=True):
    """Join table: a course can be grounded by many registered sources."""
    id: Optional[int] = Field(default=None, primary_key=True)
    track_id: int = Field(foreign_key="learningtrack.id", index=True)
    source_id: int = Field(foreign_key="learningsource.id", index=True)
    role: str = "primary"
    created_at: datetime = Field(default_factory=datetime.now)


class LearningSourceSection(SQLModel, table=True):
    """Deterministic parsed section from a registered source. No embeddings yet."""
    id: Optional[int] = Field(default=None, primary_key=True)
    source_id: int = Field(foreign_key="learningsource.id", index=True)
    position: int = Field(index=True)
    heading: str
    level: int = 1
    body_text: str = ""
    char_count: int = 0
    section_hash: str = Field(default="", index=True)
    metadata_json: str = "{}"
    created_at: datetime = Field(default_factory=datetime.now)




class LearningSourceChunk(SQLModel, table=True):
    """Small deterministic text unit prepared for later embedding/RAG indexing."""
    id: Optional[int] = Field(default=None, primary_key=True)
    source_id: int = Field(foreign_key="learningsource.id", index=True)
    section_id: Optional[int] = Field(default=None, foreign_key="learningsourcesection.id", index=True)
    position: int = Field(index=True)
    section_position: int = 0
    heading: str = ""
    heading_path_json: str = "[]"
    body_text: str = ""
    char_count: int = 0
    token_estimate: int = 0
    chunk_hash: str = Field(default="", index=True)
    metadata_json: str = "{}"
    created_at: datetime = Field(default_factory=datetime.now)


class LearningModule(SQLModel, table=True):
    """A major region/unit inside a Forge learning track."""
    id: Optional[int] = Field(default=None, primary_key=True)
    track_id: int = Field(foreign_key="learningtrack.id", index=True)
    title: str
    position: int = Field(index=True)
    exp: int = 100
    locked: bool = False
    completed: bool = False
    mastery: float = 0.0
    created_at: datetime = Field(default_factory=datetime.now)


class LearningNode(SQLModel, table=True):
    """A concrete mission/lesson node inside a module."""
    id: Optional[int] = Field(default=None, primary_key=True)
    module_id: int = Field(foreign_key="learningmodule.id", index=True)
    title: str
    position: int = Field(index=True)
    node_type: str = "lesson"  # lesson | quiz | project | boss_fight
    exp: int = 50
    locked: bool = False
    completed: bool = False
    mastery: float = 0.0
    created_at: datetime = Field(default_factory=datetime.now)


class LearningLesson(SQLModel, table=True):
    """A saved lesson attached to a Forge node. Content lives in ordered blocks."""
    id: Optional[int] = Field(default=None, primary_key=True)
    node_id: int = Field(foreign_key="learningnode.id", index=True)
    title: str
    status: str = "draft"   # draft | generated | reviewed | archived
    estimated_min: int = 10
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class LearningBlock(SQLModel, table=True):
    """A safe lesson block payload. No raw generated HTML/JS belongs here."""
    id: Optional[int] = Field(default=None, primary_key=True)
    lesson_id: int = Field(foreign_key="learninglesson.id", index=True)
    position: int = Field(index=True)
    block_type: str = "text"
    title: str = ""
    payload_json: str = "{}"
    source_refs_json: str = "[]"
    confidence: float = 0.0
    created_at: datetime = Field(default_factory=datetime.now)

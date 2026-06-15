"""Subtask rollup: a parent task's effective time = sum of its subtasks.

A task with children derives time_needed_min / time_spent_min / status from
its subtasks, and the children are not independently scheduled by the cushion
(they'd double-count). Standalone tasks pass through unchanged.

Returns lightweight shims with the same duck-typed attributes the cushion and
streak engines read (.id, .title, .due_at, .remaining_min, .time_needed_min,
.time_spent_min, .priority_flag, .status, .completed_at).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class RolledTask:
    id: int
    title: str
    due_at: Optional[datetime]
    time_needed_min: int
    time_spent_min: int
    priority_flag: bool
    status: str
    completed_at: Optional[datetime]
    has_children: bool = False

    @property
    def remaining_min(self) -> int:
        if str(self.status) in ("done", "TaskStatus.done"):
            return 0
        return max(0, self.time_needed_min - self.time_spent_min)


def _status_str(s) -> str:
    return getattr(s, "value", s)


def roll_up(tasks):
    """Given all Task rows, return the list the engines should see: parents
    with rolled-up totals, standalone tasks unchanged, children omitted."""
    by_parent: dict[int, list] = {}
    for t in tasks:
        pid = getattr(t, "parent_id", None)
        if pid is not None:
            by_parent.setdefault(pid, []).append(t)

    out = []
    for t in tasks:
        if getattr(t, "parent_id", None) is not None:
            continue  # children represented via their parent
        kids = by_parent.get(t.id, [])
        if not kids:
            out.append(t)  # standalone — pass through unchanged
            continue
        need = sum(k.time_needed_min for k in kids)
        # parent total spent = sum of subtasks + any time logged directly on the
        # parent (e.g. general work not tied to a specific subtask).
        spent = sum(k.time_spent_min for k in kids) + t.time_spent_min
        all_done = all(_status_str(k.status) == "done" for k in kids)
        status = "done" if all_done else "todo"
        completed = t.completed_at if all_done else None
        out.append(RolledTask(
            id=t.id, title=t.title, due_at=t.due_at,
            time_needed_min=need or t.time_needed_min,
            time_spent_min=spent,
            priority_flag=bool(getattr(t, "priority_flag", False)),
            status=status, completed_at=completed, has_children=True,
        ))
    return out

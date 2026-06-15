"""Subtask rollup tests."""
import unittest
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from app.rollup import roll_up, RolledTask


@dataclass
class T:
    id: int
    title: str = "t"
    parent_id: Optional[int] = None
    due_at: Optional[datetime] = None
    time_needed_min: int = 60
    time_spent_min: int = 0
    priority_flag: bool = False
    status: str = "todo"
    completed_at: Optional[datetime] = None


class RollupTests(unittest.TestCase):
    def test_standalone_passthrough(self):
        ts = [T(1, time_needed_min=120)]
        out = roll_up(ts)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].time_needed_min, 120)

    def test_parent_sums_children(self):
        ts = [T(1, title="HW"), T(2, parent_id=1, time_needed_min=90),
              T(3, parent_id=1, time_needed_min=30)]
        out = roll_up(ts)
        self.assertEqual(len(out), 1)            # only the parent
        self.assertEqual(out[0].time_needed_min, 120)
        self.assertEqual(out[0].remaining_min, 120)
        self.assertTrue(out[0].has_children)

    def test_children_omitted(self):
        ts = [T(1), T(2, parent_id=1), T(3, parent_id=1)]
        ids = [t.id for t in roll_up(ts)]
        self.assertEqual(ids, [1])

    def test_spent_rolls_up(self):
        ts = [T(1), T(2, parent_id=1, time_needed_min=90, time_spent_min=30),
              T(3, parent_id=1, time_needed_min=30, time_spent_min=30)]
        out = roll_up(ts)
        self.assertEqual(out[0].time_spent_min, 60)
        self.assertEqual(out[0].remaining_min, 60)  # 120 - 60

    def test_parent_direct_time_adds_to_children(self):
        # parent has its own logged time (general work) PLUS subtasks.
        # total spent = sum(children) + parent direct.
        ts = [T(1, time_spent_min=20),  # 20m logged directly on the parent
              T(2, parent_id=1, time_needed_min=90, time_spent_min=30),
              T(3, parent_id=1, time_needed_min=30, time_spent_min=30)]
        out = roll_up(ts)
        self.assertEqual(out[0].time_needed_min, 120)
        self.assertEqual(out[0].time_spent_min, 80)   # 30 + 30 + 20 direct
        self.assertEqual(out[0].remaining_min, 40)     # 120 - 80

    def test_parent_done_when_all_children_done(self):
        ts = [T(1), T(2, parent_id=1, status="done"), T(3, parent_id=1, status="done")]
        out = roll_up(ts)
        self.assertEqual(out[0].status, "done")
        self.assertEqual(out[0].remaining_min, 0)

    def test_parent_open_if_any_child_open(self):
        ts = [T(1), T(2, parent_id=1, status="done"), T(3, parent_id=1, status="todo")]
        out = roll_up(ts)
        self.assertEqual(out[0].status, "todo")

    def test_mixed_standalone_and_parent(self):
        ts = [T(1, time_needed_min=60), T(2, title="P"),
              T(3, parent_id=2, time_needed_min=45)]
        out = roll_up(ts)
        self.assertEqual(len(out), 2)
        m = {t.id: t for t in out}
        self.assertEqual(m[1].time_needed_min, 60)
        self.assertEqual(m[2].time_needed_min, 45)


if __name__ == "__main__":
    unittest.main(verbosity=2)

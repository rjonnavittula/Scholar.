"""Canvas -> HIVE Tasks sync.

Pulls upcoming assignments from Canvas and upserts them via /ingest/canvas.
Run it on a schedule (cron / systemd timer / a H.I.V.E. agent task).

Env:
  HIVE_API_URL   default http://127.0.0.1:8077
  HIVE_API_KEY   key minted at POST /auth/keys
  CANVAS_URL     e.g. https://psu.instructure.com
  CANVAS_TOKEN   Canvas personal access token
"""
from __future__ import annotations

import json
import os
import urllib.request

from canvasapi import Canvas  # pip install canvasapi


# Rough reading/effort heuristic by keyword — refine to taste, or let the
# Cushion teach you (compare estimate vs time_spent over the term).
def estimate_minutes(name: str) -> int:
    n = name.lower()
    if any(k in n for k in ("exam", "midterm", "final", "project")):
        return 240
    if any(k in n for k in ("essay", "paper", "report")):
        return 180
    if any(k in n for k in ("reading", "chapter")):
        return 90
    return 60


def collect_items() -> list[dict]:
    canvas = Canvas(os.environ["CANVAS_URL"], os.environ["CANVAS_TOKEN"])
    items: list[dict] = []
    for course in canvas.get_courses(enrollment_state="active"):
        course_name = getattr(course, "name", None) or f"course-{course.id}"
        for a in course.get_assignments(bucket="upcoming"):
            items.append(
                {
                    "external_id": f"canvas:{a.id}",
                    "title": a.name,
                    "course_name": course_name,
                    "course_external_id": f"canvas:{course.id}",
                    "due_at": a.due_at,  # ISO8601 from Canvas, or null
                    "notes": getattr(a, "html_url", ""),
                    "time_needed_min": estimate_minutes(a.name),
                }
            )
    return items


def push(items: list[dict]) -> str:
    base = os.getenv("HIVE_API_URL", "http://127.0.0.1:8077")
    req = urllib.request.Request(
        f"{base}/ingest/canvas",
        data=json.dumps(items).encode(),
        headers={
            "X-API-Key": os.environ["HIVE_API_KEY"],
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode()


if __name__ == "__main__":
    items = collect_items()
    print(f"Collected {len(items)} assignments from Canvas")
    print(push(items))

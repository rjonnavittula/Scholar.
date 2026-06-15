"""Pure date-range helpers for the analytics page. No DB/ORM imports so this
stays unit-testable without sqlmodel."""
from __future__ import annotations

from datetime import date, timedelta

RANGE_LABELS = {
    "today": "Today", "yesterday": "Yesterday", "this_week": "This week",
    "last_week": "Last week", "last_7": "Last 7 days", "last_30": "Last 30 days",
    "this_month": "This month", "last_month": "Last month", "all": "All time",
}


def _month_end(d: date) -> date:
    if d.month == 12:
        return date(d.year, 12, 31)
    return date(d.year, d.month + 1, 1) - timedelta(days=1)


def range_bounds(key: str, today: date):
    """Return (start, end) inclusive dates for a range key, or (None, None)
    for 'all'. Week starts Monday."""
    monday = today - timedelta(days=today.weekday())
    if key == "today":
        return today, today
    if key == "yesterday":
        y = today - timedelta(days=1)
        return y, y
    if key == "this_week":
        return monday, monday + timedelta(days=6)
    if key == "last_week":
        return monday - timedelta(days=7), monday - timedelta(days=1)
    if key == "last_7":
        return today - timedelta(days=6), today
    if key == "last_30":
        return today - timedelta(days=29), today
    if key == "this_month":
        return date(today.year, today.month, 1), _month_end(today)
    if key == "last_month":
        first = date(today.year, today.month, 1)
        prev_end = first - timedelta(days=1)
        return date(prev_end.year, prev_end.month, 1), prev_end
    return None, None  # all


def week_label(d: date) -> str:
    """Mon-anchored week label like 'Jun 8 – 14' / 'Jun 30 – Jul 6'."""
    mon = d - timedelta(days=d.weekday())
    sun = mon + timedelta(days=6)
    if mon.month == sun.month:
        return f"{mon.strftime('%b')} {mon.day} \u2013 {sun.day}"
    return f"{mon.strftime('%b')} {mon.day} \u2013 {sun.strftime('%b')} {sun.day}"


def recent_weeks(today: date, n: int = 6):
    """List of (monday, label) for the last n Mon-anchored weeks, oldest first."""
    mon = today - timedelta(days=today.weekday())
    out = []
    for i in range(n - 1, -1, -1):
        m = mon - timedelta(days=7 * i)
        out.append((m, week_label(m)))
    return out

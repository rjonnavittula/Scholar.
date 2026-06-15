"""Tiny dependency-free iCalendar (VEVENT) parser for the Canvas feed.

Pure stdlib so it stays unit-testable without the DB/ORM layer.
"""
from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

UTC = ZoneInfo("UTC")


def parse_dt(val: str):
    """Parse an ICS DTSTART/DTEND value (with optional ;TZID=) → aware UTC dt."""
    if not val:
        return None
    v = val.strip()
    tzid = None
    if ";TZID=" in v:                       # DTSTART;TZID=America/New_York:20260613T235900
        tzid = v.split(";TZID=", 1)[1].split(":", 1)[0]
        v = v.split(":", 1)[1]
    elif ":" in v and ("=" in v.split(":", 1)[0]):  # other params e.g. ;VALUE=DATE:
        v = v.split(":", 1)[1]
    elif ":" in v and v.split(":", 1)[0].isalpha():  # bare "DTSTART:..."
        v = v.split(":", 1)[1]
    v = v.strip()
    try:
        if v.endswith("Z"):
            return datetime.strptime(v, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        if "T" in v:
            dt = datetime.strptime(v, "%Y%m%dT%H%M%S")
            return dt.replace(tzinfo=ZoneInfo(tzid) if tzid else UTC).astimezone(UTC)
        return datetime.strptime(v, "%Y%m%d").replace(tzinfo=UTC)
    except ValueError:
        return None


def parse_ics(text: str) -> list:
    """Unfold wrapped lines and return a list of VEVENT dicts."""
    raw = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lines, buf = [], ""
    for ln in raw:
        if ln[:1] in (" ", "\t"):
            buf += ln[1:]
        else:
            if buf:
                lines.append(buf)
            buf = ln
    if buf:
        lines.append(buf)

    events, cur = [], None
    for ln in lines:
        if ln == "BEGIN:VEVENT":
            cur = {}
        elif ln == "END:VEVENT":
            if cur is not None:
                events.append(cur)
            cur = None
        elif cur is not None:
            key = ln.split(":", 1)[0].split(";", 1)[0].upper()
            val = ln.split(":", 1)[1] if ":" in ln else ""
            if key == "UID":
                cur["uid"] = val
            elif key == "SUMMARY":
                cur["summary"] = val.replace("\\,", ",").replace("\\n", " ").strip()
            elif key == "URL":
                cur["url"] = val
            elif key in ("DTSTART", "DTEND"):
                cur[key.lower()] = parse_dt(ln)
    return events


def ext_id(ev: dict) -> str:
    """Map an event back to a Canvas assignment id when possible, so ICS rows
    dedup with token/bookmarklet imports (external_id ``canvas:{id}``)."""
    uid = ev.get("uid", "") or ""
    m = re.search(r"assignment[-_]?(\d+)", uid, re.I)
    if m:
        return f"canvas:{m.group(1)}"
    return f"canvas-ics:{uid or (ev.get('summary', '') or '')[:60]}"

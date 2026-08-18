"""iCloud CalDAV sync -- pulls events from the user's real iCloud calendars (not just a
public share) via CalDAV, using an Apple ID + an app-specific password generated at
appleid.apple.com (never the real account password -- Apple requires a per-app password
for any third-party CalDAV/CardDAV client once two-factor is on, which is effectively
mandatory now).

Uses the `caldav` library rather than hand-rolled PROPFIND/REPORT XML -- CalDAV discovery
(principal -> calendar-home-set -> calendar list) is fiddly enough that a maintained
client is worth the dependency, same reasoning as canvasapi for Canvas's own API.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

ICLOUD_CALDAV_URL = "https://caldav.icloud.com"


def _to_utc_datetime(value) -> datetime | None:
    """VEVENT DTSTART/DTEND comes back from vobject as either a datetime (timed event)
    or a bare date (all-day event) -- normalize both to an aware UTC datetime so
    everything downstream (Task.due_at) gets one consistent type."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        # All-day event -- anchor at end of day, same convention as syllabus imports
        # (app/integrations.py's import_syllabus_tasks uses 23:59 for date-only entries).
        return datetime(value.year, value.month, value.day, 23, 59, tzinfo=timezone.utc)
    return None


def fetch_events(username: str, password: str, calendar_url: str = "",
                  days_back: int = 7, days_ahead: int = 90) -> list[dict]:
    """Real network call to the live iCloud account -- lazy import so this module (and
    the app it's part of) still loads fine without `caldav` installed until this
    function is actually called, matching how canvasapi is imported lazily in
    integrations.py. Returns a flat list of {uid, summary, start, end, calendar}
    across every calendar on the account, or just the one at calendar_url if given."""
    import caldav

    client = caldav.DAVClient(url=ICLOUD_CALDAV_URL, username=username, password=password)

    if calendar_url:
        calendars = [caldav.Calendar(client=client, url=calendar_url)]
    else:
        principal = client.principal()
        calendars = principal.calendars()

    start = datetime.now(timezone.utc) - timedelta(days=days_back)
    end = datetime.now(timezone.utc) + timedelta(days=days_ahead)

    events = []
    for cal in calendars:
        try:
            cal_name = cal.name
        except Exception:
            cal_name = ""
        for event in cal.date_search(start=start, end=end, expand=True):
            vevent = event.vobject_instance.vevent
            uid = str(vevent.uid.value) if hasattr(vevent, "uid") else ""
            summary = str(vevent.summary.value) if hasattr(vevent, "summary") else "Event"
            dtstart = _to_utc_datetime(vevent.dtstart.value) if hasattr(vevent, "dtstart") else None
            dtend = _to_utc_datetime(vevent.dtend.value) if hasattr(vevent, "dtend") else dtstart
            if dtstart is None:
                continue
            events.append({
                "uid": uid or f"{cal_name}:{summary}:{dtstart.isoformat()}",
                "summary": summary,
                "start": dtstart,
                "end": dtend,
                "calendar": cal_name,
            })
    return events


def create_event(username: str, password: str, calendar_url: str,
                  summary: str, start: datetime, end: datetime | None = None) -> str:
    """Creates a real VEVENT on the user's actual iCloud calendar -- this is the write
    half fetch_events (read-only) doesn't cover. Needs calendar_url specifically, unlike
    fetch_events' "search every calendar": writing needs one unambiguous target, and
    icloud_status/settings already capture it once a sync has run at least once.

    Not verified against a live iCloud account (this project's own rule against testing
    against real personal data extends here -- there's no throwaway iCloud calendar to
    test with). Grounded in caldav>=1.3's documented save_event() kwargs API, same
    library version already pinned in requirements.txt for fetch_events."""
    import caldav

    if not calendar_url:
        raise ValueError("calendar_url required -- run an iCloud sync at least once so it's known")
    if end is None:
        end = start + timedelta(hours=1)

    client = caldav.DAVClient(url=ICLOUD_CALDAV_URL, username=username, password=password)
    cal = caldav.Calendar(client=client, url=calendar_url)
    event = cal.save_event(dtstart=start, dtend=end, summary=summary)
    return str(event.icalendar_component.get("uid", ""))

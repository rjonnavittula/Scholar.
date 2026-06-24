"""Heuristic syllabus -> candidate tasks.

`parse_syllabus(text)` is pure stdlib so it unit-tests offline; the PDF text
extraction in `extract_text()` is a thin, library-backed wrapper (runs on the
server, not exercised in the no-network build).

Designed to be locale-tolerant: it reads month-name dates in BOTH orders
("September 12" and "12 September"), ISO dates, and numeric dates with an
optional day-first flag (e.g. India's 13/09/2025). Output is always a reviewable
list — nothing is created without the user confirming.
"""
from __future__ import annotations

import re
from datetime import date

MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}

_MN = (r"(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|"
       r"aug|august|sep|sept|september|oct|october|nov|november|dec|december)")

RE_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
RE_MONTH_DAY = re.compile(_MN + r"\b\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s*(\d{4}))?", re.I)
RE_DAY_MONTH = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+" + _MN + r"\b\.?(?:,?\s*(\d{4}))?", re.I)
RE_NUMERIC = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b")

KEYWORDS = re.compile(
    r"\b(exam|midterm|final|test|quiz|lab|reading|read|chapter|discussion|forum|"
    r"response|project|proposal|draft|report|essay|paper|presentation|milestone|"
    r"deliverable|homework|hw|assignment|problem\s*set|pset|exercise|due|submit|"
    r"submission|deadline)\b", re.I)

DUE_HINT = re.compile(r"\b(due|deadline|submit(?:ted)?|submission|by|on|before)\b", re.I)

_CATS = [
    (re.compile(r"\b(quiz)\b", re.I), "Quiz"),
    (re.compile(r"\b(lab)\b", re.I), "Lab"),
    (re.compile(r"\b(project|proposal|draft|report|essay|paper|presentation|milestone|deliverable)\b", re.I), "Project"),
    (re.compile(r"\b(exam|midterm|final|test)\b", re.I), "Exam"),
    (re.compile(r"\b(reading|read|chapter)\b", re.I), "Reading"),
    (re.compile(r"\b(discussion|forum|response)\b", re.I), "Discussion"),
    (re.compile(r"\b(homework|hw|assignment|problem\s*set|pset|exercise)\b", re.I), "Homework"),
]


def _yr(raw, default_year):
    if not raw:
        return None
    y = int(raw)
    return y + 2000 if y < 100 else y


def find_dates(line, default_year, dayfirst=False):
    """All dates on a line as dicts {m, d, y(optional), span}, in reading order."""
    out = []
    for m in RE_ISO.finditer(line):
        try:
            date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            out.append({"m": int(m.group(2)), "d": int(m.group(3)), "y": int(m.group(1)), "span": m.span()})
        except ValueError:
            pass
    for m in RE_MONTH_DAY.finditer(line):
        out.append({"m": MONTHS[m.group(1).lower()], "d": int(m.group(2)),
                    "y": _yr(m.group(3), default_year), "span": m.span()})
    for m in RE_DAY_MONTH.finditer(line):
        out.append({"m": MONTHS[m.group(2).lower()], "d": int(m.group(1)),
                    "y": _yr(m.group(3), default_year), "span": m.span()})
    for m in RE_NUMERIC.finditer(line):
        a, b = int(m.group(1)), int(m.group(2))
        if dayfirst or a > 12:           # day-first (e.g. 13/09) — unambiguous when a>12
            d, mo = a, b
        else:
            mo, d = a, b
        if 1 <= mo <= 12 and 1 <= d <= 31:
            out.append({"m": mo, "d": d, "y": _yr(m.group(3), default_year), "span": m.span()})
    out.sort(key=lambda x: x["span"][0])
    return out


def _choose(line, dates):
    hint = DUE_HINT.search(line)
    if hint:
        after = [d for d in dates if d["span"][0] >= hint.start()]
        if after:
            return after[0]
    return dates[0]


def _title(line, span):
    s = (line[:span[0]] + " " + line[span[1]:])
    s = re.sub(r"\b(due|deadline|submit(?:ted)?|submission|by|on|before|at|11:?59\s*[ap]m)\b", " ", s, flags=re.I)
    s = re.sub(r"^(week\s*\d+\s*[-\u2013:.)]*\s*)", "", s.strip(), flags=re.I)
    s = re.sub(r"\s{2,}", " ", s).strip(" -\u2013:|.,\t")
    return s.strip()


def _categorize(line):
    for rx, cat in _CATS:
        if rx.search(line):
            return cat
    return ""


def parse_syllabus(text, default_year=None, dayfirst=False, now=None):
    """Return a sorted, de-duped list of candidate items:
    {title, due_date (ISO), category, line}."""
    today = now or date.today()
    default_year = default_year or today.year
    raw = []
    for line0 in (text or "").splitlines():
        line = " ".join(line0.split())
        if len(line) < 3 or not KEYWORDS.search(line):
            continue
        dates = find_dates(line, default_year, dayfirst)
        if not dates:
            continue
        ch = _choose(line, dates)
        raw.append({"m": ch["m"], "d": ch["d"], "y": ch.get("y"),
                    "title": _title(line, ch["span"]) or line, "category": _categorize(line),
                    "line": line})

    # academic-year rollover: if the doc clearly spans a fall term and also has
    # early-year months, treat Jan-Jun dates as the following year.
    has_fall = any(it["m"] >= 8 for it in raw)
    has_spring = any(it["m"] <= 6 for it in raw)

    items = []
    for it in raw:
        y = it["y"]
        if y is None:
            y = default_year + 1 if (has_fall and has_spring and it["m"] <= 6) else default_year
        try:
            due = date(y, it["m"], it["d"])
        except ValueError:
            continue
        items.append({"title": it["title"][:200], "due_date": due.isoformat(),
                      "category": it["category"], "line": it["line"]})

    seen, uniq = set(), []
    for it in sorted(items, key=lambda x: (x["due_date"], x["title"].lower())):
        key = (it["title"].lower(), it["due_date"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(it)
    return uniq


def extract_text(data: bytes, filename: str = "") -> str:
    """Best-effort text from an uploaded syllabus. PDF via pypdf; otherwise utf-8."""
    is_pdf = data[:5] == b"%PDF-" or (filename or "").lower().endswith(".pdf")
    if not is_pdf:
        try:
            return data.decode("utf-8", "replace")
        except Exception:
            return ""
    try:
        import io
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception:
        return ""

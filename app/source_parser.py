"""Deterministic source text parser for Scholar.

This is deliberately local and boring: no LLM, no embeddings, no RAG.
It turns pasted text/markdown into stable sections that later phases can chunk,
index, cite, and use for lesson generation.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

_MARKDOWN_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_NUMBERED_HEADING_RE = re.compile(
    r"^(?:(module|chapter|unit|lesson|section|part)\s+\d+|\d+(?:\.\d+)*)(?:\s*[:.)-]\s*|\s+)(.+)$",
    re.IGNORECASE,
)
_MAX_SECTION_BODY = 20_000


def _clean_text(value: object) -> str:
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _safe_heading(value: str, fallback: str) -> str:
    heading = re.sub(r"\s+", " ", value or "").strip(" #\t")
    return (heading[:120] or fallback).strip()


def _looks_like_plain_heading(line: str) -> tuple[bool, str, int]:
    stripped = line.strip()
    if not stripped:
        return False, "", 0

    numbered = _NUMBERED_HEADING_RE.match(stripped)
    if numbered:
        return True, _safe_heading(numbered.group(2), stripped), 2

    if stripped.endswith(":") and len(stripped) <= 90:
        return True, _safe_heading(stripped[:-1], stripped), 2

    words = stripped.split()
    has_sentence_end = stripped.endswith(('.', '!', '?'))
    if 1 <= len(words) <= 8 and len(stripped) <= 72 and not has_sentence_end:
        titleish = sum(1 for word in words if word[:1].isupper() or word.isupper())
        if titleish >= max(1, len(words) // 2):
            return True, _safe_heading(stripped, stripped), 2

    return False, "", 0


def _section(position: int, heading: str, level: int, body_lines: list[str]) -> dict[str, Any]:
    body = "\n".join(body_lines).strip()
    if len(body) > _MAX_SECTION_BODY:
        body = body[:_MAX_SECTION_BODY].rstrip()
    return {
        "position": position,
        "heading": _safe_heading(heading, f"Section {position}"),
        "level": max(1, min(int(level or 1), 6)),
        "body_text": body,
        "char_count": len(body),
        "section_hash": _hash_text(f"{heading}\n{body}"),
        "metadata": {},
    }


def parse_pasted_source(text: str, source_type: str = "text") -> dict[str, Any]:
    """Parse pasted source text into durable section records.

    Markdown headings are honored. Plain text falls back to simple title-ish and
    numbered headings. If no headings exist, a single Overview section is used.
    """
    body = _clean_text(text)
    if not body:
        raise ValueError("body_text_required")

    lines = body.split("\n")
    sections: list[dict[str, Any]] = []
    current_heading = "Overview"
    current_level = 1
    current_body: list[str] = []
    in_code_fence = False
    detected_headings = 0
    kind = (source_type or "text").lower()

    def flush() -> None:
        nonlocal current_body, current_heading, current_level
        if sections or current_body:
            section = _section(len(sections) + 1, current_heading, current_level, current_body)
            if section["heading"] or section["body_text"]:
                sections.append(section)
        current_body = []

    for raw_line in lines:
        line = raw_line.rstrip()
        if line.strip().startswith("```"):
            in_code_fence = not in_code_fence
            current_body.append(line)
            continue

        markdown_heading = None if in_code_fence else _MARKDOWN_HEADING_RE.match(line.strip())
        if markdown_heading and kind in {"markdown", "text", "syllabus"}:
            flush()
            detected_headings += 1
            current_level = len(markdown_heading.group(1))
            current_heading = _safe_heading(markdown_heading.group(2), f"Section {len(sections) + 1}")
            continue

        is_heading, heading, level = (False, "", 0) if in_code_fence else _looks_like_plain_heading(line)
        if is_heading and kind in {"text", "syllabus"}:
            flush()
            detected_headings += 1
            current_heading = heading
            current_level = level
            continue

        current_body.append(line)

    flush()

    if not sections:
        sections = [_section(1, "Overview", 1, [body])]
    elif detected_headings == 0 and len(sections) == 1 and not sections[0]["body_text"]:
        sections[0]["body_text"] = body
        sections[0]["char_count"] = len(body)
        sections[0]["section_hash"] = _hash_text(f"Overview\n{body}")

    outline = [{"position": s["position"], "heading": s["heading"], "level": s["level"]} for s in sections]
    return {
        "section_count": len(sections),
        "total_chars": sum(int(s["char_count"]) for s in sections),
        "outline": outline,
        "sections": sections,
    }

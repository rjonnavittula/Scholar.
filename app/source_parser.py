"""Deterministic source text parser for Scholar.

This is deliberately local and boring: no LLM, no embeddings, no RAG.
It turns pasted text/markdown into stable sections that later phases can chunk,
index, cite, and use for lesson generation.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

PARSER_VERSION = "source-parser-v2"

_MARKDOWN_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_SETEXT_HEADING_RE = re.compile(r"^\s*(=+|-{2,})\s*$")
_PDF_PAGE_HEADING_RE = re.compile(
    r"^[-–—\s]*Page\s+(\d+)(?:\s*(?:of|/)\s*\d+)?[-–—\s]*$",
    re.IGNORECASE,
)
_NUMBERED_HEADING_RE = re.compile(
    r"^(?:(module|chapter|unit|lesson|section|part)\s+\d+|\d+(?:\.\d+)*)(?:\s*[:.)-]\s*|\s+)(.+)$",
    re.IGNORECASE,
)
_ROMAN_HEADING_RE = re.compile(r"^(?=[IVXLCDM]+\b)([IVXLCDM]+)[.)-]\s+(.+)$", re.IGNORECASE)
_FRONT_MATTER_RE = re.compile(r"^\s*---\s*\n.*?\n\s*---\s*(?:\n|$)", re.DOTALL)
_MAX_SECTION_BODY = 20_000


def _clean_text(value: object) -> str:
    text = str(value or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ")
    text = text.replace("\t", "    ")
    text = _FRONT_MATTER_RE.sub("", text)
    text = re.sub(r"(?<=\w)-\n(?=\w)", "", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip()


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _safe_heading(value: str, fallback: str) -> str:
    heading = re.sub(r"\s+", " ", value or "").strip(" #\t:-–—")
    return (heading[:120] or fallback).strip()


def _is_list_or_table_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.startswith(("- ", "* ", "+ ", "• ", "– ", "— ")):
        return True
    if re.match(r"^\d+[.)]\s+", stripped):
        return True
    if stripped.count("|") >= 2:
        return True
    return False


def _looks_like_plain_heading(line: str) -> tuple[bool, str, int, str]:
    stripped = line.strip()
    if not stripped or _is_list_or_table_line(stripped):
        return False, "", 0, ""

    numbered = _NUMBERED_HEADING_RE.match(stripped)
    if numbered:
        return True, _safe_heading(numbered.group(2), stripped), 2, "numbered"

    roman = _ROMAN_HEADING_RE.match(stripped)
    if roman:
        return True, _safe_heading(roman.group(2), stripped), 2, "roman"

    if stripped.endswith(":") and len(stripped) <= 90:
        return True, _safe_heading(stripped[:-1], stripped), 2, "colon"

    words = stripped.split()
    has_sentence_end = stripped.endswith((".", "!", "?", ";"))
    if 1 <= len(words) <= 8 and len(stripped) <= 72 and not has_sentence_end:
        titleish = sum(1 for word in words if word[:1].isupper() or word.isupper())
        all_caps_words = sum(1 for word in words if len(word) > 1 and word.isupper())
        if all_caps_words >= max(1, len(words) - 1):
            return True, _safe_heading(stripped.title(), stripped), 2, "all_caps"
        if titleish >= max(1, len(words) // 2):
            return True, _safe_heading(stripped, stripped), 2, "titleish"

    return False, "", 0, ""


def _looks_like_setext_title(line: str) -> bool:
    stripped = line.strip()
    if not stripped or _is_list_or_table_line(stripped):
        return False
    if len(stripped) > 100 or stripped.endswith((".", "!", "?", ";")):
        return False
    return True


def _update_heading_path(stack: list[tuple[int, str]], level: int, heading: str) -> list[tuple[int, str]]:
    next_stack = [(lvl, text) for lvl, text in stack if lvl < level]
    next_stack.append((level, heading))
    return next_stack


def _section(
    position: int,
    heading: str,
    level: int,
    body_lines: list[str],
    *,
    source_type: str,
    heading_kind: str,
    heading_path: list[str],
) -> dict[str, Any]:
    body = "\n".join(body_lines).strip()
    if len(body) > _MAX_SECTION_BODY:
        body = body[:_MAX_SECTION_BODY].rstrip()
    safe_heading = _safe_heading(heading, f"Section {position}")
    return {
        "position": position,
        "heading": safe_heading,
        "level": max(1, min(int(level or 1), 6)),
        "body_text": body,
        "char_count": len(body),
        "section_hash": _hash_text(f"{safe_heading}\n{body}"),
        "metadata": {
            "parser_version": PARSER_VERSION,
            "source_type": source_type,
            "heading_kind": heading_kind or "fallback",
            "heading_path": heading_path or [safe_heading],
        },
    }


def parse_pasted_source(text: str, source_type: str = "text") -> dict[str, Any]:
    """Parse pasted source text into durable section records.

    Markdown headings are honored. Plain text falls back to simple title-ish,
    numbered, and roman-numeral headings. PDF text recognizes page markers.
    If no usable headings exist, a single Overview section is used.
    """
    body = _clean_text(text)
    if not body:
        raise ValueError("body_text_required")

    lines = body.split("\n")
    sections: list[dict[str, Any]] = []
    current_heading = "Overview"
    current_level = 1
    current_kind = "fallback"
    current_path = ["Overview"]
    heading_stack: list[tuple[int, str]] = []
    current_body: list[str] = []
    in_code_fence = False
    detected_headings = 0
    kind = (source_type or "text").lower()

    def flush() -> None:
        nonlocal current_body
        body_text = "\n".join(current_body).strip()
        if body_text:
            sections.append(_section(
                len(sections) + 1,
                current_heading,
                current_level,
                current_body,
                source_type=kind,
                heading_kind=current_kind,
                heading_path=current_path,
            ))
        current_body = []

    def start_heading(heading: str, level: int, heading_kind: str) -> None:
        nonlocal current_heading, current_level, current_kind, current_path, heading_stack, detected_headings
        flush()
        detected_headings += 1
        current_level = max(1, min(int(level or 1), 6))
        current_heading = _safe_heading(heading, f"Section {len(sections) + 1}")
        current_kind = heading_kind
        heading_stack = _update_heading_path(heading_stack, current_level, current_heading)
        current_path = [item[1] for item in heading_stack]

    i = 0
    while i < len(lines):
        raw_line = lines[i]
        line = raw_line.rstrip()
        stripped = line.strip()

        if stripped.startswith("```"):
            in_code_fence = not in_code_fence
            current_body.append(line)
            i += 1
            continue

        if not in_code_fence and kind == "pdf" and raw_line.strip(" \t") == "\f":
            start_heading(f"Page {detected_headings + 1}", 1, "pdf_page_break")
            i += 1
            continue

        page_heading = None if in_code_fence else _PDF_PAGE_HEADING_RE.match(stripped)
        if page_heading and kind == "pdf":
            start_heading(f"Page {page_heading.group(1)}", 1, "pdf_page")
            i += 1
            continue

        markdown_heading = None if in_code_fence else _MARKDOWN_HEADING_RE.match(stripped)
        if markdown_heading and kind in {"markdown", "text", "syllabus", "pdf", "transcript"}:
            start_heading(markdown_heading.group(2), len(markdown_heading.group(1)), "markdown")
            i += 1
            continue

        next_line = lines[i + 1].strip() if i + 1 < len(lines) else ""
        setext = None if in_code_fence else _SETEXT_HEADING_RE.match(next_line)
        if setext and kind in {"markdown", "text", "syllabus"} and _looks_like_setext_title(line):
            level = 1 if next_line.startswith("=") else 2
            start_heading(line, level, "setext")
            i += 2
            continue

        is_heading, heading, level, heading_kind = (False, "", 0, "") if in_code_fence else _looks_like_plain_heading(line)
        if is_heading and kind in {"text", "syllabus", "transcript"}:
            start_heading(heading, level, heading_kind)
            i += 1
            continue

        current_body.append(line)
        i += 1

    flush()

    if not sections:
        sections = [_section(
            1,
            "Overview",
            1,
            [body],
            source_type=kind,
            heading_kind="fallback",
            heading_path=["Overview"],
        )]

    outline = [{"position": s["position"], "heading": s["heading"], "level": s["level"]} for s in sections]
    return {
        "parser_version": PARSER_VERSION,
        "section_count": len(sections),
        "total_chars": sum(int(s["char_count"]) for s in sections),
        "outline": outline,
        "sections": sections,
        "warnings": [] if detected_headings else ["no_headings_detected"],
    }

"""Deterministic parsing helpers for HIVE-Courses / Scholar Forge inputs."""
from __future__ import annotations

import hashlib
import re
from typing import Any


_SYSTEM_PROMPT_MARKERS = (
    "system prompt",
    "role & persona",
    "role and persona",
    "core engineering philosophies",
    "teaching loop",
)

_SYLLABUS_MARKERS = (
    "syllabus",
    "grading",
    "course schedule",
    "office hours",
    "course objectives",
)

_RULE_MARKERS = {
    "teaching_rules": ("teach", "teaching", "lesson", "explain", "show", "guide", "ask", "recall", "question"),
    "assessment_rules": ("quiz", "test", "exam", "assessment", "rubric", "boss fight"),
    "visual_rules": ("visual", "diagram", "animation", "manim", "figure", "draw"),
    "constraints": ("never", "must", "do not", "constraint", "rule", "only"),
}


def source_hash(text: str) -> str:
    """Return a short stable hash for a pasted source."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def classify_input(text: str) -> str:
    """Classify pasted input without using an LLM."""
    lowered = text.lower()
    if any(marker in lowered for marker in _SYSTEM_PROMPT_MARKERS):
        return "system_prompt"
    if any(marker in lowered for marker in _SYLLABUS_MARKERS):
        return "syllabus"
    return "source_text"


def extract_modules(text: str) -> list[str]:
    """Extract module/chapter/unit-style headings."""
    patterns = [
        r"^\s*(?:module|chapter|unit)\s+\d+[:.-]\s*(.+)$",
        r"^\s*#{1,3}\s+(.+)$",
    ]
    found: list[str] = []
    for pattern in patterns:
        found.extend(re.findall(pattern, text, flags=re.I | re.M))
    return [_clean_line(item) for item in found if _clean_line(item)]


def extract_track_title(text: str) -> str:
    """Pick a useful user-facing course title from pasted material."""
    explicit = re.search(r"^\s*(?:course|track|title|name)\s*[:.-]\s*(.+)$", text, flags=re.I | re.M)
    if explicit:
        candidate = _clean_line(explicit.group(1))
        if candidate and not _is_generic_title(candidate):
            return candidate[:80]

    role_title = _title_from_role(extract_role(text))
    if role_title:
        return role_title

    modules = extract_modules(text)
    if modules:
        return _title_from_module(modules[0])

    for line in text.splitlines():
        clean = _clean_line(line)
        if clean and len(clean) <= 80 and not _is_generic_title(clean):
            return clean
    return "Untitled Course"


def extract_role(text: str) -> str | None:
    """Extract a role/persona line from a system-prompt style input."""
    role_match = re.search(r"(?:you are|role\s*&\s*persona|role and persona)[:\s-]+(.+)", text, flags=re.I)
    if role_match:
        role = _clean_line(role_match.group(1))
        return role[:160] if role else None
    return None


def extract_rule_buckets(text: str) -> dict[str, list[str]]:
    """Bucket obvious instruction lines into teaching/assessment/visual/constraint groups."""
    buckets: dict[str, list[str]] = {key: [] for key in _RULE_MARKERS}
    for line in text.splitlines():
        clean = _clean_line(line)
        if not clean or len(clean) < 8:
            continue
        lowered = clean.lower()
        for bucket, markers in _RULE_MARKERS.items():
            if any(marker in lowered for marker in markers):
                buckets[bucket].append(clean)
                break
    return {key: values[:12] for key, values in buckets.items()}


def parse_source(text: str) -> dict[str, Any]:
    """Parse pasted material into a stable Forge course seed."""
    cleaned = text.strip()
    rules = extract_rule_buckets(cleaned)
    return {
        "input_type": classify_input(cleaned),
        "track_title": extract_track_title(cleaned),
        "role": extract_role(cleaned),
        "modules": extract_modules(cleaned),
        "teaching_rules": rules["teaching_rules"],
        "assessment_rules": rules["assessment_rules"],
        "visual_rules": rules["visual_rules"],
        "constraints": rules["constraints"],
        "source_hash": source_hash(cleaned),
    }


def _title_from_role(role: str | None) -> str | None:
    if not role:
        return None
    clean = _clean_line(role).rstrip(".")
    clean = re.sub(r"^you\s+are\s+", "", clean, flags=re.I)
    clean = re.sub(r"^(?:an?|the)\s+", "", clean, flags=re.I)
    clean = re.sub(r"\b(?:mentor|tutor|teacher|instructor)\.?$", "", clean, flags=re.I).strip()
    if clean and not _is_generic_title(clean):
        return f"{clean} Course"[:80]
    return None


def _title_from_module(module: str) -> str:
    clean = _clean_line(module)
    clean = re.sub(r"\s+(?:basics|overview|fundamentals)$", "", clean, flags=re.I).strip() or clean
    return f"{clean} Course"[:80]


def _is_generic_title(value: str) -> bool:
    return value.strip().lower() in {
        "system prompt",
        "role & persona",
        "role and persona",
        "prompt",
        "course prompt",
        "syllabus",
    }


def _clean_line(line: str) -> str:
    return line.strip().strip("#*-—– ").strip()

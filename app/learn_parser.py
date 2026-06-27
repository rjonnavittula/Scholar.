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
    """Pick the first useful short line as a fallback track title."""
    for line in text.splitlines():
        clean = _clean_line(line)
        if clean and len(clean) <= 80:
            return clean
    return "Untitled Track"


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


def _clean_line(line: str) -> str:
    return line.strip().strip("#*-—– ").strip()

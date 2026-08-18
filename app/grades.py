"""Weighted course grade. Pure stdlib so it unit-tests without a database.

A course has weighted categories (Homework 30%, Exams 50%, ...); each category
holds graded items (earned / possible points). The *current* grade weights only
the categories that actually have graded work, so an empty "Final 30%" doesn't
drag the number down early in the term.
"""
from __future__ import annotations

# 11-point scale; tweak per syllabus later if needed.
_SCALE = [
    (93, "A"), (90, "A-"), (87, "B+"), (83, "B"), (80, "B-"),
    (77, "C+"), (73, "C"), (70, "C-"), (67, "D+"), (60, "D"), (0, "F"),
]


def letter(pct):
    if pct is None:
        return ""
    for floor, lab in _SCALE:
        if pct >= floor:
            return lab
    return "F"


def compute_grade(categories):
    """categories: [{name, weight, items: [{earned, possible}, ...]}, ...]
    Returns {percent, letter, breakdown[], weight_graded}."""
    breakdown = []
    for c in categories or []:
        items = c.get("items") or []
        earned = sum(float(i.get("earned") or 0) for i in items if (i.get("possible") or 0) > 0)
        possible = sum(float(i.get("possible") or 0) for i in items if (i.get("possible") or 0) > 0)
        pct = (earned / possible * 100) if possible > 0 else None
        breakdown.append({
            "name": c.get("name") or "",
            "weight": float(c.get("weight") or 0),
            "pct": round(pct, 1) if pct is not None else None,
            "earned": round(earned, 2), "possible": round(possible, 2),
            "count": len([i for i in items if (i.get("possible") or 0) > 0]),
        })

    graded = [b for b in breakdown if b["pct"] is not None and b["weight"] > 0]
    wsum = sum(b["weight"] for b in graded)
    overall = (sum(b["pct"] * b["weight"] for b in graded) / wsum) if wsum > 0 else None
    return {
        "percent": round(overall, 1) if overall is not None else None,
        "letter": letter(overall),
        "breakdown": breakdown,
        "weight_graded": round(wsum, 1),
    }

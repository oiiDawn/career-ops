"""Classify current scores into opportunities worth attention."""

from __future__ import annotations

import math
from datetime import date


ORDER = {"evidence_review": 0, "focus": 1, "deprioritize": 2, "discard": 3}


def valid_scores(score: dict) -> bool:
    return isinstance(score, dict) and set(score) in ({"direction", "compensation", "company"}, {"direction", "compensation", "company", "culture"}) and all(
        value is None or type(value) in (int, float) and math.isfinite(value) and 1 <= value <= 5 for value in score.values()
    )


def worth_attention(score: dict) -> bool:
    if not valid_scores(score):
        raise ValueError("invalid dimension scores")
    if "culture" in score:
        return False
    known = [value for value in score.values() if value is not None]
    return len(known) >= 2 and all(value >= 4 for value in known)


def classify(score: dict, prescreen: dict) -> str:
    """Apply the dimension threshold while honoring confirmed hard failures."""
    attention = worth_attention(score)
    if not isinstance(prescreen, dict) or prescreen.get("status") not in {"pass", "fail", "uncertain"}:
        raise ValueError("complete prescreen decision required")
    if prescreen["status"] == "fail":
        return "discard"
    if "culture" in score:
        return "evidence_review"
    return "focus" if attention else "deprioritize"


def order(rows: list[dict]) -> list[dict]:
    """Order actions by deadline, effort and stable opportunity ID."""
    ids = set()
    for row in rows:
        opportunity_id = row.get("opportunity_id")
        if not isinstance(opportunity_id, str) or not opportunity_id or opportunity_id in ids:
            raise ValueError("unique opportunity IDs required")
        ids.add(opportunity_id)
        if row.get("action") not in ORDER:
            raise ValueError("valid action required")
        deadline = row.get("deadline")
        if deadline is not None:
            try:
                if not isinstance(deadline, str) or date.fromisoformat(deadline).isoformat() != deadline:
                    raise ValueError
            except ValueError as error:
                raise ValueError("deadline must be ISO date or null") from error
        effort = row.get("effort_days")
        if effort is not None and (isinstance(effort, bool) or not isinstance(effort, (int, float))
                                   or not math.isfinite(effort) or effort < 0):
            raise ValueError("effort_days must be nonnegative or null")
    return sorted(rows, key=lambda row: (
        ORDER[row["action"]], row.get("deadline") or "9999-12-31",
        row.get("effort_days") if row.get("effort_days") is not None else math.inf,
        row["opportunity_id"],
    ))

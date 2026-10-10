"""Build a preparation plan for one role from the scan's capability matches."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re

from career_ops.evaluation.capabilities import rows


SCHEMA = "career-ops/preparation-plan"
CLASSIFICATIONS = {"proven": "evidenced", "adjacent": "adjacent", "gap": "actual_gap", "unverified": "unverified"}
PRE_ACTION = {
    "adjacent": "State the adjacent evidence and the boundary; do not claim direct experience.",
    "actual_gap": "Do not claim this capability; decide whether focused learning is worth the application.",
    "unverified": "Resolve from the JD, an approved source, or a recruiter question before relying on it.",
}
INTERVIEW_ACTION = {
    "adjacent": "Prepare a bridge answer from the adjacent experience to the requirement.",
    "actual_gap": "Prepare an honest gap-and-learning answer.",
    "unverified": "Prepare a clarifying question and avoid assumptions.",
}


def build_preparation_plan(company: str, role: str, scan: dict, *, generated_at: str | None = None) -> dict:
    """Turn each judged requirement into two honest, actionable checklists."""
    if not company or not role:
        raise ValueError("company and role are required")
    matches = rows(scan)
    requirements = [{"requirement": row["requirement"], "classification": CLASSIFICATIONS[row["match"]],
                     "evidence": row["evidence"] or None, "source": "scan"} for row in matches]
    raw = {"jd": scan.get("jd"), "matches": matches}
    source_hash = hashlib.sha256(json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()

    def actions(messages: dict) -> list[dict]:
        return [{"requirement": row["requirement"], "classification": row["classification"],
                 "action": messages[row["classification"]]} for row in requirements if row["classification"] != "evidenced"]

    return {"schema": SCHEMA, "schema_version": 1,
            "metadata": {"generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
                         "source_hash": source_hash, "sources": {"jd": scan.get("url")}},
            "role": {"company": company, "title": role}, "requirements": requirements,
            "pre_application": actions(PRE_ACTION), "interview_preparation": actions(INTERVIEW_ACTION)}


def validate_preparation_plan(plan: dict) -> dict:
    """Check the persisted plan contract before another tool consumes it."""
    errors = []
    if plan.get("schema") != SCHEMA or plan.get("schema_version") != 1:
        errors.append("schema mismatch")
    if not plan.get("role", {}).get("company") or not plan.get("role", {}).get("title"):
        errors.append("role is required")
    if not re.fullmatch(r"[a-f0-9]{64}", plan.get("metadata", {}).get("source_hash", "")):
        errors.append("metadata.source_hash is required")
    rows_ = plan.get("requirements")
    if not isinstance(rows_, list) or any(not isinstance(row, dict) or row.get("classification") not in CLASSIFICATIONS.values()
                                          for row in rows_):
        errors.append("invalid requirements")
    if not isinstance(plan.get("pre_application"), list) or not isinstance(plan.get("interview_preparation"), list):
        errors.append("preparation sections are required")
    return {"valid": not errors, "errors": errors}

"""Bind candidate inputs and validate frozen application package evidence."""

from __future__ import annotations


import hashlib
import json
from datetime import date
from pathlib import Path
import re
from career_ops.evaluation import jev
from career_ops.context import RULES_ROOT, INPUT_ROOT, SCAN_POLICY_VERSION, SCORE_POLICY_VERSION, company_valid_until


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def scoring_profile(profile: str) -> str:
    """Drop the discovery search keywords; they recall postings and never reach a scan or a rating."""
    return re.sub(r"(?m)^( +)search_keywords:.*\n(?:\1(?: +|- ).*\n)*", "", profile)


def scan_is_current(stored: str, current: str) -> bool:
    """Compare frozen and current scan inputs, ignoring the discovery search keywords."""
    values = [json.loads(stored), json.loads(current)]
    for value in values:
        value["profile"] = scoring_profile(value["profile"])
    return values[0] == values[1]


def score_inputs(report: dict) -> str:
    """Bind a JD report to every module-level policy and candidate input."""
    required = {"schema_version", "opportunity_id", "url", "company", "role", "jd", "captured_at", "prescreen"}
    missing = sorted(required - report.keys())
    if missing:
        raise ValueError("JD report missing: " + ", ".join(missing))
    if report["schema_version"] != "jd_report_v1":
        raise ValueError("Unsupported JD report schema")
    if not isinstance(report["jd"], str) or not report["jd"].strip():
        raise ValueError("A complete JD report is required")
    if not all(str(report[key]).strip() for key in ("opportunity_id", "url", "company", "role", "captured_at")):
        raise ValueError("JD report identity and capture fields cannot be empty")
    if not isinstance(report["prescreen"], dict) or report["prescreen"].get("status") not in {"pass", "fail", "incomplete", "uncertain"}:
        raise ValueError("JD report prescreen status is invalid")
    inputs = {
        "score_policy_version": SCORE_POLICY_VERSION,
        "rubric": (RULES_ROOT / "evaluation/four-dimension.md").read_text(),
        "company_valid_until": company_valid_until(),
        "company_evidence_as_of": date.today().isoformat(),
        "jd_report": report,
        "cv": (INPUT_ROOT / "cv.md").read_text(),
        "profile": (INPUT_ROOT / "profile.yml").read_text(),
        "targeting": (INPUT_ROOT / "targeting.md").read_text(),
        "rules": (RULES_ROOT / "scoring.md").read_text(),
        "articles": (INPUT_ROOT / "article-digest.md").read_text() if (INPUT_ROOT / "article-digest.md").is_file() else None,
        "voice": (INPUT_ROOT / "voice.md").read_text() if (INPUT_ROOT / "voice.md").is_file() else None,
        "writing_samples": {
            str(path.relative_to(INPUT_ROOT)): path.read_text()
            for path in sorted((INPUT_ROOT / "writing-samples").glob("**/*")) if path.is_file()
        } if (INPUT_ROOT / "writing-samples").is_dir() else {},
    }
    return json.dumps(inputs, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def score_is_current(connection, input_hash: str, report: dict) -> bool:
    """Verify frozen input integrity and scoring freshness independently of recommendation prose."""
    if not isinstance(report, dict) or not report.get("opportunity_id"):
        return False
    row = connection.execute(
        "SELECT input_payload FROM tasks WHERE module='score' AND opportunity_id=? AND input_hash=? ORDER BY rowid DESC LIMIT 1",
        (str(report['opportunity_id']), input_hash),
    ).fetchone()
    if not row or digest(row[0]) != input_hash:
        return False
    stored, current = json.loads(row[0]), json.loads(score_inputs(report))
    if not all(isinstance(value.get("rubric"), str) for value in (stored, current)):
        return False
    for value in (stored, current):
        value.pop("company_valid_until", None)
        value.pop("company_evidence_as_of", None)
        value['rubric'] = jev.standards(value['rubric'], jev.DIMENSIONS)
        if isinstance(value.get("profile"), str):
            value["profile"] = scoring_profile(value["profile"])
    return stored == current


def score_refresh_reasons(current: bool, profiles: dict) -> list[str]:
    """Unify refresh eligibility while retaining input and evidence-expiry causes."""
    reasons = [] if current else ["inputs_changed"]
    if any(ref.get("valid_until") and ref["valid_until"] < date.today().isoformat()
           for ref in profiles.values()):
        reasons.append("company_evidence_expired")
    return reasons


def canonical_score_input(value: str) -> str:
    try:
        report = json.loads(value) if value.lstrip().startswith("{") else json.loads(Path(value).read_text())
    except (json.JSONDecodeError, OSError) as error:
        raise ValueError("score requires a jd_report_v1 JSON file or object") from error
    if not isinstance(report, dict) or "jd_report" in report:
        raise ValueError("score input must be one jd_report_v1 object, not a workflow envelope")
    return score_inputs(report)


def canonical_scan_input(value: str) -> str:
    try:
        source = json.loads(value) if value.lstrip().startswith("{") else json.loads(Path(value).read_text())
    except (json.JSONDecodeError, OSError) as error:
        raise ValueError("scan requires a scan_input_v1 JSON file or object") from error
    if not isinstance(source, dict) or "source" in source:
        raise ValueError("scan input must be one scan_input_v1 object, not a workflow envelope")
    required = {"schema_version", "opportunity_id", "url", "company", "role", "jd", "captured_at"}
    missing = sorted(required - source.keys())
    if missing:
        raise ValueError("Scan input missing: " + ", ".join(missing))
    if source["schema_version"] != "scan_input_v1":
        raise ValueError("Unsupported scan input schema")
    if any(not isinstance(source[key], str) or not source[key].strip() for key in ("opportunity_id", "url", "company", "role", "captured_at")):
        raise ValueError("Scan input identity and capture fields must be nonempty strings")
    if not isinstance(source["jd"], str):
        raise ValueError("Scan input JD is invalid")
    inputs = {
        "scan_policy_version": SCAN_POLICY_VERSION,
        "source": source,
        "cv": (INPUT_ROOT / "cv.md").read_text(),
        "profile": (INPUT_ROOT / "profile.yml").read_text(),
        "targeting": (INPUT_ROOT / "targeting.md").read_text(),
        "rules": (RULES_ROOT / "scoring.md").read_text(),
    }
    return json.dumps(inputs, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def apply_inputs(jd_report: dict, score_result: dict) -> str:
    score_inputs(jd_report)
    inputs = {
        "artifact_contract_version": 4,
        "jd_report": jd_report,
        "score_result": score_result,
        "cv": (INPUT_ROOT / "cv.md").read_text(),
        "profile": (INPUT_ROOT / "profile.yml").read_text(),
        "targeting": (INPUT_ROOT / "targeting.md").read_text(),
        "rules": (RULES_ROOT / "scoring.md").read_text(),
        "contract": (RULES_ROOT / "shared/contract.md").read_text(),
        "requirements": (RULES_ROOT / "applications/workflow.md").read_text(),
        "articles": (INPUT_ROOT / "article-digest.md").read_text() if (INPUT_ROOT / "article-digest.md").is_file() else None,
        "voice": (INPUT_ROOT / "voice.md").read_text() if (INPUT_ROOT / "voice.md").is_file() else None,
        "writing_samples": {
            str(path.relative_to(INPUT_ROOT)): path.read_text()
            for path in sorted((INPUT_ROOT / "writing-samples").glob("**/*")) if path.is_file()
        } if (INPUT_ROOT / "writing-samples").is_dir() else {},
        "market_rules": {
            market: (RULES_ROOT / "markets" / market / "employment.md").read_text()
            for market in ("cn", "hk", "remote")
        },
    }
    return json.dumps(inputs, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def validate_resume_payload(payload: dict) -> None:
    if not payload.get("candidate", {}).get("name") or not isinstance(payload.get("summary"), str):
        raise ValueError("resume_payload requires candidate.name and summary")
    if "projects_start_on_new_page" in payload and not isinstance(payload["projects_start_on_new_page"], bool):
        raise ValueError("resume_payload projects_start_on_new_page must be boolean")
    for entry in payload.get("experience", []):
        if not all(key in entry for key in ("company", "role", "dates", "bullets")) or not isinstance(entry["bullets"], list):
            raise ValueError("resume experience requires company, role, dates and bullets")
    for entry in payload.get("education", []):
        if not all(key in entry for key in ("org", "title", "year")):
            raise ValueError("resume education requires org, title and year")
    for entry in payload.get("projects", []):
        if "name" not in entry or not isinstance(entry.get("bullets", []), list):
            raise ValueError("resume projects require name and bullets")
    for entry in payload.get("skills", []):
        if "category" not in entry or "items" not in entry:
            raise ValueError("resume skills require category and items")

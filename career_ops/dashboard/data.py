"""Derive dashboard rows from retained business facts without writing the store."""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import sqlite3

from career_ops.applications.application_lifecycle import OUTCOMES, TRANSITIONS
from career_ops.evaluation.capabilities import core_counts, rows as capability_rows
from career_ops.evaluation.decisions import classify, valid_scores
from career_ops.input_contracts import apply_inputs, digest, score_is_current


# The package files the page shows, in display order; the rendering intermediates stay on disk.
MATERIAL_LABELS = {
    "resume_pdf": "简历 PDF",
    "cover_letter": "Cover letter",
    "interview_prep": "面试准备",
    "upskill": "Upskill",
    "questions": "反问问题",
    "changes": "简历改动",
}
TEXT_SUFFIXES = {".md", ".json", ".txt"}


def connect(database: Path) -> sqlite3.Connection:
    """Open the store read-only; dashboard writes go only through the CLI."""
    db = sqlite3.connect(f"file:{database.resolve()}?mode=ro", uri=True, check_same_thread=False)
    db.row_factory = sqlite3.Row
    return db


def _has_table(db: sqlite3.Connection, name: str) -> bool:
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def _latest_results(db: sqlite3.Connection, module: str) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for row in db.execute("SELECT opportunity_id,payload FROM results WHERE module=? ORDER BY rowid DESC", (module,)):
        latest.setdefault(str(row["opportunity_id"]), json.loads(row["payload"]))
    return latest


def _lifecycle(db: sqlite3.Connection) -> dict[str, dict]:
    if not _has_table(db, "application_lifecycle"):
        return {}
    return {str(row["opportunity_id"]): dict(row) for row in db.execute("SELECT * FROM application_lifecycle")}


def _apply_tasks(db: sqlite3.Connection) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for row in db.execute("SELECT task_id,opportunity_id,status,waiting_reason FROM tasks WHERE module='apply' ORDER BY rowid DESC"):
        latest.setdefault(str(row["opportunity_id"]), {"task_id": row["task_id"], "status": row["status"],
                                                        "reason": row["waiting_reason"]})
    return latest


def _score_current(db: sqlite3.Connection, score_result: dict | None, scan: dict | None) -> bool | None:
    """Mirror the apply guard: a score is current only for today's JD, candidate and policy inputs."""
    if not score_result or not scan or scan.get("outcome") != "jd_report":
        return None
    try:
        return score_is_current(db, score_result.get("input_hash"), scan["artifact"])
    except (KeyError, OSError, ValueError):
        return False



def _action(score: dict | None, scan: dict | None) -> str | None:
    prescreen = (scan or {}).get("artifact", {}).get("prescreen")
    if not valid_scores(score):
        return None
    try:
        return classify(score, prescreen)
    except ValueError:
        return None


def _profile_expired(profiles: dict) -> bool:
    """Shared company dimensions are dated; an expired profile no longer describes the employer today."""
    today = date.today().isoformat()
    return any(ref.get("valid_until") and ref["valid_until"] < today for ref in profiles.values())


def _stage(row: sqlite3.Row, lifecycle: dict | None, score: dict | None) -> str:
    if lifecycle or row["application_state"] == "submitted":
        return "applied"
    # A later scan can exclude a job that was already scored; its retained score no longer counts.
    return "scored" if score is not None and row["state"] != "ineligible" else "scanned"


def list_jobs(db: sqlite3.Connection) -> list[dict]:
    """One row per opportunity with its current stage, score and application status."""
    scans, scores = _latest_results(db, "scan"), _latest_results(db, "score")
    lifecycle = _lifecycle(db)
    eligibility = {str(row["opportunity_id"]): row["status"] for row in db.execute("SELECT opportunity_id,status FROM eligibility")}
    evaluations = {str(row["opportunity_id"]): dict(row) for row in db.execute("SELECT * FROM evaluations")}
    materials = _material_counts(db)
    apply_tasks = _apply_tasks(db)
    jobs = []
    for row in db.execute("SELECT * FROM opportunities ORDER BY id DESC"):
        key = str(row["id"])
        scan, score_result = scans.get(key), scores.get(key)
        scan_artifact = (scan or {}).get("artifact", {})
        score = (score_result or {}).get("artifact", {}).get("score")
        evaluation = evaluations.get(key, {})
        artifact = (score_result or {}).get("artifact", {})
        application = lifecycle.get(key)
        jobs.append({
            "id": row["id"], "url": row["url"], "company": row["company"], "role": row["role"],
            "source": row["source"], "state": row["state"], "created_at": row["created_at"],
            "stage": _stage(row, application, score_result),
            "scan_outcome": (scan or {}).get("outcome"),
            "location": scan_artifact.get("location_evidence"),
            "liveness": scan_artifact.get("liveness"),
            "captured_at": scan_artifact.get("captured_at"),
            "prescreen": (scan_artifact.get("prescreen") or {}).get("status"),
            "capability_counts": core_counts(scan_artifact) if capability_rows(scan_artifact) else None,
            "eligibility": eligibility.get(key),
            "scores": score if isinstance(score, dict) else None,
            "dimensions": artifact.get("dimensions", {}),
            "company_profiles": artifact.get("company_profiles", {}),
            "profile_expired": _profile_expired(artifact.get("company_profiles", {})),
            "company_research": artifact.get("company_research", {}),
            "action": _action(score, scan) if _score_current(db, score_result, scan) else None,
            "score_current": _score_current(db, score_result, scan),
            "scored_at": evaluation.get("created_at"),
            "application_status": application["status"] if application else None,
            "application_updated_at": application["updated_at"] if application else None,
            "has_report": bool((score_result or {}).get("artifact", {}).get("report")),
            "material_count": materials.get(key, 0),
            "apply_task": apply_tasks.get(key),
        })
    # Profile IDs derive from scope alone, so sharing is per company.
    shared: dict[tuple, int] = {}
    for job in jobs:
        for ref in job["company_profiles"].values():
            if ref.get("profile_id"):
                key = (ref.get("company_id"), ref["profile_id"])
                shared[key] = shared.get(key, 0) + 1
    for job in jobs:
        job["profile_shared"] = {dim: shared[(ref.get("company_id"), ref["profile_id"])]
                                 for dim, ref in job["company_profiles"].items() if ref.get("profile_id")}
    return jobs


def _package_current(package: dict | None, scan: dict | None, score_result: dict | None) -> bool | None:
    """Whether the latest package was prepared from today's JD, score, candidate and rule inputs."""
    if not package:
        return None
    try:
        return package["input_hash"] == digest(apply_inputs(scan["artifact"], score_result))
    except (KeyError, OSError, TypeError, ValueError):
        return False


def _material_counts(db: sqlite3.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in db.execute("SELECT opportunity_id FROM results WHERE module='apply'"):
        counts[str(row[0])] = counts.get(str(row[0]), 0) + 1
    if _has_table(db, "interview_results"):
        for row in db.execute("SELECT t.opportunity_id FROM interview_results r JOIN interview_tasks t ON t.task_id=r.task_id"):
            counts[str(row[0])] = counts.get(str(row[0]), 0) + 1
    return counts


def material_files(db: sqlite3.Connection, opportunity_id: str) -> list[dict]:
    """The displayed files of this opportunity's latest package; the only paths the server may read."""
    files = (_latest_results(db, "apply").get(opportunity_id) or {}).get("artifact", {}).get("files", {})
    return [{"id": key, "label": label, "path": files[key]} for key, label in MATERIAL_LABELS.items() if key in files]


def _interview_materials(db: sqlite3.Connection, opportunity_id: str) -> list[dict]:
    if not _has_table(db, "interview_results"):
        return []
    return [
        {"task_id": row["task_id"], "kind": row["kind"], "session": row["session_key"],
         "confirmed_at": row["confirmed_at"], "artifact": json.loads(row["artifact"])}
        for row in db.execute(
            "SELECT t.task_id,t.kind,t.session_key,r.confirmed_at,r.artifact FROM interview_results r "
            "JOIN interview_tasks t ON t.task_id=r.task_id WHERE t.opportunity_id=? ORDER BY r.confirmed_at DESC",
            (opportunity_id,),
        )
    ]


def read_text(path: str) -> str | None:
    file = Path(path)
    if file.suffix.lower() not in TEXT_SUFFIXES or not file.is_file():
        return None
    return file.read_text(errors="replace")


def _report(score_result: dict | None, db: sqlite3.Connection, opportunity_id: str) -> str | None:
    report = (score_result or {}).get("artifact", {}).get("report")
    if report:
        return report
    row = db.execute("SELECT path FROM artifacts WHERE opportunity_id=? AND kind='report' ORDER BY id DESC LIMIT 1",
                     (opportunity_id,)).fetchone()
    return read_text(row["path"]) if row else None


def _rows(db: sqlite3.Connection, table: str, opportunity_id: str) -> list[dict]:
    if not _has_table(db, table):
        return []
    return [{**dict(row), "payload": json.loads(row["payload"])}
            for row in db.execute(f"SELECT * FROM {table} WHERE opportunity_id=? ORDER BY id", (opportunity_id,))]


def status_options(status: str | None) -> list[str]:
    """Status changes the lifecycle accepts next: `responded` is a transition, the rest are outcomes."""
    allowed = TRANSITIONS.get(status or "", set())
    options = ["responded"] if "responded" in allowed else []
    # A non-terminal status may repeat its own outcome, e.g. another interview round.
    return options + [name for name, target in OUTCOMES.items() if target in allowed or (allowed and target == status)]


def job_detail(db: sqlite3.Connection, opportunity_id: int) -> dict | None:
    """The full retained record of one opportunity for the detail panel."""
    job = next((item for item in list_jobs(db) if item["id"] == opportunity_id), None)
    if job is None:
        return None
    key = str(opportunity_id)
    scan = _latest_results(db, "scan").get(key)
    score_result = _latest_results(db, "score").get(key)
    scan_artifact = (scan or {}).get("artifact", {})
    eligibility = db.execute("SELECT status,evidence,created_at FROM eligibility WHERE opportunity_id=?", (key,)).fetchone()
    materials = [
        {"id": item["id"], "label": item["label"], "content": read_text(item["path"]),
         "exists": Path(item["path"]).is_file()}
        for item in material_files(db, key)
    ]
    return {
        **job,
        "jd": scan_artifact.get("jd"),
        "scan_artifact": {k: v for k, v in scan_artifact.items() if k != "jd"},
        "capability_rows": capability_rows(scan_artifact),
        "report": _report(score_result, db, key),
        "eligibility_detail": {**dict(eligibility), "evidence": json.loads(eligibility["evidence"])} if eligibility else None,
        "application_events": _rows(db, "application_events", key),
        "application_activity": _rows(db, "application_activity", key),
        "followups": _rows(db, "application_followup_directives", key),
        "status_options": status_options(job["application_status"]),
        "materials": materials,
        "materials_current": _package_current(_latest_results(db, "apply").get(key), scan, score_result),
        "interviews": _interview_materials(db, key),
    }

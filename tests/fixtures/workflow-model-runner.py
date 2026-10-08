"""Deterministic in-process model phase stub used by the public workflow CLI test."""

import hashlib
import os
from pathlib import Path
import sys
import time


def run(phase, payload):
    if path := os.environ.get("WORKFLOW_TEST_CALL_LOG"):
        with Path(path).open("a") as stream:
            stream.write(phase + "\n")
    if phase == "scan_evaluate":
        source = payload["inputs"]["source"]
        if source.get("test_exclude"):
            return {
                "outcome": "exclude",
                "artifact": {"type": "exclusion", "reason": "Confirmed employment mismatch", "evidence": ["contractor"]},
                "tool_calls": 1,
            }
        return {
            "outcome": "jd_report",
            "artifact": {
                "schema_version": "jd_report_v1",
                "opportunity_id": source["opportunity_id"],
                "url": source["url"],
                "company": source["company"],
                "role": source["role"],
                "jd": source["jd"],
                "captured_at": source["captured_at"],
                "liveness": source["liveness"],
                "prescreen": {"status": "pass", "unknowns": ["compensation"]},
            },
            "tool_calls": 1,
        }
    elif phase == "apply_evaluate":
        feedback = payload["inputs"].get("feedback", [])
        if "Emphasize verified testing work" in feedback and "Regenerate for current facts" not in feedback:
            assert payload.get("previous_artifact", {}).get("cover_letter") == "Grounded cover letter"
        if "Regenerate for current facts" in feedback:
            assert payload.get("previous_artifact") is None
        if "force-budget" in feedback:
            assert payload.get("previous_artifact", {}).get("cover_letter") == "Grounded cover letter"
        return {
            "outcome": "package",
            "artifact": {
                "resume_payload": {"candidate": {"name": "Jiaming Zhang"}, "summary": "Verified AI engineer", "experience": [], "projects": [], "education": [], "certifications": [], "awards": [], "skills": []},
                "changes": "# Evidence-backed changes",
                "cover_letter": "Grounded cover letter",
                "upskill": "# Upskill plan",
                "interview_prep": "# Interview preparation",
                "questions": "# Questions",
            },
            "tool_calls": 20 if "force-budget" in feedback else 1,
        }
    elif phase == "evaluate":
        if os.environ.get("WORKFLOW_TEST_DURABLE_FAIL") or os.environ.get("WORKFLOW_TEST_DURABLE_SUCCESS"):
            sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
            from career_ops.model import record_call
            record_call()
            if os.environ.get("WORKFLOW_TEST_DURABLE_FAIL"):
                raise RuntimeError("injected failure after model dispatch")
            record_call()
        if os.environ.get("WORKFLOW_TEST_SLEEP"):
            time.sleep(float(os.environ["WORKFLOW_TEST_SLEEP"]))
        if os.environ.get("WORKFLOW_TEST_INVALID_JSON"):
            return "not JSON"
        if os.environ.get("WORKFLOW_TEST_RUNNER_FAIL") == "1":
            raise RuntimeError("injected model failure")
        report = payload["inputs"]["jd_report"]
        if report["prescreen"]["status"] == "fail":
            return {
                "outcome": "exclude",
                "artifact": {"type": "exclusion", "reason": report["prescreen"]["reason"], "evidence": report["prescreen"].get("evidence", [report["url"]])},
                "tool_calls": 0,
            }
        known = lambda value: {"score": value, "confidence": .93, "evidence_sufficiency": .12,
                               "evidence_status": "assessed", "probabilities": {"0": 0, "1": 0, "2": 0, "3": 5-value, "4": value-4}}
        dimensions = {"direction": known(4.37), "compensation": known(4.12),
                      "company": {"score": None, "status": "pending", "reason": "summary_failed"},
                      "culture": {"score": None, "status": "pending", "reason": "no_matching_valid_profile"}}
        artifact = {
            "type": "score",
            "company": report["company"],
            "role": report["role"],
            "score": {name: value["score"] for name, value in dimensions.items()},
            "scoring_model": "attractiveness-v4", "dimensions": dimensions,
            "company_profiles": {}, "company_research": {"stages": []}, "company_ratings": [],
            "recommendation": "deprioritize",
            "report": "# Verified score report",
            "report_sha256": hashlib.sha256(b"# Verified score report").hexdigest(),
        }
        if os.environ.get("WORKFLOW_TEST_DRAFT_DIRECTORY"):
            artifact["draft_directory"] = os.environ["WORKFLOW_TEST_DRAFT_DIRECTORY"]
        return {
            "outcome": "score",
            "artifact": artifact,
            "tool_calls": 3,
        }
    else:
        raise RuntimeError(f"unknown phase: {phase}")

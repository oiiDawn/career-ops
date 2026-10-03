"""Keep validated core capability evidence in published JD reports."""

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from career_ops import model as model_adapter
from career_ops.evaluation.scan_graph import run_scan


with tempfile.TemporaryDirectory() as temp:
    original_call = model_adapter.call_agent
    capabilities = [{"name": "Terraform", "core": True, "mandatory": True,
                     "match": "gap", "evidence": "JD requires Terraform"}]
    evidence = {
        "company": "Acme", "role": "Engineer", "complete_jd": True,
        "liveness": "active", "liveness_reason": "official capture active", "assessment_complete": True,
        "location": {"status": "pass", "reason": "local", "evidence": "JD"},
        "employment": {"status": "pass", "reason": "full-time", "evidence": "JD"},
        "compensation": {"status": "unknown", "reason": "not posted", "evidence": "JD"},
        "company_size": {"status": "unknown", "reason": "not posted", "evidence": "JD"},
        "years": {"required": 0, "verified": 1, "evidence": "CV"},
        "core_capabilities": capabilities, "credentials": [],
    }
    model_adapter.call_agent = lambda *_args: (evidence, "session")
    source = {"opportunity_id": "1", "url": "https://acme.example/jobs/1", "company": "Acme",
              "role": "Engineer", "jd": "Build Terraform infrastructure", "captured_at": "2026-01-01",
              "capture_method": "official_job_page", "liveness_evidence": {"status": 200}}
    try:
        result = run_scan({"source": source, "cv": "CV", "profile": "profile",
                           "targeting": "targeting", "rules": "rules"}, Path(temp))
        assert result["outcome"] == "jd_report"
        assert result["artifact"]["core_capabilities"] == capabilities
        incomplete = {**evidence, "core_capabilities": None}
        model_adapter.call_agent = lambda *_args: (incomplete, "session")
        changed_source = {**source, "jd": "Build Terraform infrastructure for a new team"}
        waiting = run_scan({"source": changed_source, "cv": "CV", "profile": "profile",
                            "targeting": "targeting", "rules": "rules"}, Path(temp))
        assert waiting["waiting_reason"] == "core_evidence_missing"
    finally:
        model_adapter.call_agent = original_call

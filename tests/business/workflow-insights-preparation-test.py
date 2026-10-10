"""Check the preparation plan built from the scan's capability matches."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from career_ops.evaluation.preparation import build_preparation_plan, validate_preparation_plan

SCAN = {
    "url": "https://acme.example/jobs/1", "jd": "Build services in Python on Kubernetes.",
    "years": {"required": 3, "verified": None, "evidence": "CV dates unclear"},
    "credentials": [{"name": "Security clearance", "mandatory": False, "status": "absent", "evidence": "Not held"}],
    "capabilities": [
        {"name": "Rust", "core": False, "mandatory": False, "match": "adjacent", "evidence": "Systems work in C++"},
        {"name": "Python", "core": True, "mandatory": True, "match": "proven", "evidence": "Production services"},
    ],
}
plan = build_preparation_plan("Acme", "Engineer", SCAN, generated_at="2026-01-01T00:00:00.000Z")
# One row per judged requirement, core mandatory first; nothing is re-judged here.
assert [(row["requirement"], row["classification"]) for row in plan["requirements"]] == [
    ("Python", "evidenced"), ("相关经验 ≥ 3 年", "unverified"), ("Rust", "adjacent"), ("Security clearance", "actual_gap")]
assert plan["requirements"][0]["evidence"] == "Production services" and plan["requirements"][0]["source"] == "scan"
assert validate_preparation_plan(plan)["valid"]
for checklist in (plan["pre_application"], plan["interview_preparation"]):
    assert [row["requirement"] for row in checklist] == ["相关经验 ≥ 3 年", "Rust", "Security clearance"]
assert plan["metadata"]["source_hash"] == build_preparation_plan("Acme", "Engineer", SCAN)["metadata"]["source_hash"]
changed = {**SCAN, "capabilities": [{**SCAN["capabilities"][0], "match": "gap"}, SCAN["capabilities"][1]]}
assert plan["metadata"]["source_hash"] != build_preparation_plan("Acme", "Engineer", changed)["metadata"]["source_hash"]
assert build_preparation_plan("Acme", "Engineer", {"jd": "Nothing listed"})["requirements"] == []
print("preparation plan: scan capability matches passed")

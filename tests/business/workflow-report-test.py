"""Verify raw four-dimension reports and durable shared-company references."""

import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from career_ops.evaluation.report import render_report
from career_ops.db import BusinessStore

with tempfile.TemporaryDirectory(prefix="career-ops-report-") as temporary:
    root = Path(temporary)
    directory = root / "draft"
    directory.mkdir()
    (directory / "profile.txt").write_text("Current profile.")
    packet = {"root": str(root), "directory": str(directory), "sources": {"profile": "Current profile."}}
    evidence = {"company": "Example", "role": "Engineer", "complete_jd": True, "liveness": "active",
                "jd": "Build and maintain software products."}
    raw = {"score": 3.3700000000000006, "confidence": .93, "evidence_sufficiency": .12,
           "evidence_status": "threshold_pending", "probabilities": {"0": .1, "1": .1, "2": .43, "3": .07, "4": .3}}
    reference = {"company_id": "example", "profile_id": "culture-cn", "request_sha256": "batch",
                 "scope": {"region": "China"}, "valid_until": "2026-10-15"}
    assessment = {
        "dimensions": {"direction": raw, "culture": raw},
        "company_profiles": {"culture": reference},
        "company_research": {"stages": [{"dimension": "culture", "status": "summarized"}],
                             "sources": [{"url": "https://example.com", "summary": "Reviewable factual summary."}]},
        "sections": {name: "Complete evidence mapping, unknowns and specific next actions." for name in
                     ("overview", "capabilities", "compensation", "questions", "legitimacy", "risks", "checklist")},
    }
    rendered = render_report(packet, evidence, assessment)
    assert rendered["scores"]["culture"] == raw["score"]
    assert "| direction | 3.37 |" in rendered["report"]
    assert "| direction | 3.3700000000000006 |" not in rendered["report"]
    machine = yaml.safe_load(rendered["report"].split("```yaml\n")[1].split("```")[0])
    assert machine["scoring_model"] == "attractiveness-v4" and machine["recommendation"] == "evidence_review"
    assert machine["dimensions"]["culture"] == raw
    assert machine["dimensions"]["company"]["score"] is None and machine["dimensions"]["company"]["status"] == "pending"
    assert machine["company_profiles"] == assessment["company_profiles"]
    assert machine["company_research"] == assessment["company_research"]
    assert machine["sources"] and "advertised_comp" in machine
    assert "| culture |" in rendered["report"] and "总分" not in rendered["report"]
    assert "company" not in assessment["dimensions"]
    for invalid in (True, float("nan"), float("inf"), .9, 5.1):
        broken = {**assessment, "dimensions": {"direction": {**raw, "score": invalid}}}
        try:
            render_report(packet, evidence, broken)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid raw score accepted")
    for field in ("confidence", "evidence_sufficiency"):
        try:
            render_report(packet, evidence, {**assessment, "dimensions": {"direction": {**raw, field: -1}}})
        except ValueError:
            pass
        else:
            raise AssertionError("invalid probability accepted")
    for name in ("overview", "compensation"):
        incomplete = {**assessment, "sections": {k: v for k, v in assessment["sections"].items() if k != name}}
        try:
            render_report(packet, evidence, incomplete)
        except ValueError as error:
            assert "sections" in str(error)
        else:
            raise AssertionError("missing model section accepted")
    contradicted = {**assessment, "sections": {**assessment["sections"], "overview": "岗位办公城市未披露。"}}
    try:
        render_report(packet, {**evidence, "location_evidence": "Shanghai"}, contradicted)
    except ValueError as error:
        assert "contradicts retained posting" in str(error)
    else:
        raise AssertionError("contradictory location accepted")
    rendered = render_report(packet, evidence, assessment)
    rating = {"company_id": "example", "profile_id": "culture-cn", "dimension": "culture", "scope": {"region": "China"},
              "valid_until": "2026-10-15", "scoring_request_sha256": "batch", **raw}
    artifact = {"type": "score", "report": rendered["report"], "report_sha256": rendered["report_sha256"],
                "score": rendered["scores"], "scoring_model": "attractiveness-v4", "dimensions": machine["dimensions"],
                "recommendation": "evidence_review", "company_ratings": [rating], "company_profiles": {"culture": reference, "company": {"status": "pending"}}}
    store = BusinessStore(root / "business.db")
    pending = store.start("report-pending", "score", "not yet published")
    store.retain_company_ratings(store.db, [rating])
    assert store.task(pending["task_id"])["status"] == "running"
    assert store.db.execute("SELECT count(*) FROM results").fetchone()[0] == 0
    assert store.db.execute("SELECT count(*) FROM job_company_profiles").fetchone()[0] == 0
    independent_reader = BusinessStore(store.path)
    assert json.loads(independent_reader.db.execute("SELECT payload_json FROM company_ratings").fetchone()[0]) == rating
    independent_reader.close()
    store.retain_company_ratings(store.db, [{**rating, "score": 5, "valid_until": "2099-10-15"}])
    assert json.loads(store.db.execute("SELECT payload_json FROM company_ratings").fetchone()[0]) == rating
    with patch("career_ops.db.score_inputs", return_value=json.dumps({"jd_report": {}})):
        for opportunity in ("job1", "job2"):
            task = store.start(opportunity, "score", json.dumps({"jd_report": {}}))
            state = {"task_id": task["task_id"], "input_hash": store.task(task["task_id"])["input_hash"], "outcome": "score",
                     "material_hash": rendered["report_sha256"], "draft": json.dumps(artifact)}
            store.publish(state)
        rejected = store.start("bad-rating", "score", json.dumps({"jd_report": {}}))
        mismatched = {**artifact, "score": {**artifact["score"], "culture": 4.37}}
        state = {"task_id": rejected["task_id"], "input_hash": store.task(rejected["task_id"])["input_hash"],
                 "outcome": "score", "material_hash": rendered["report_sha256"], "draft": json.dumps(mismatched)}
        try:
            store.publish(state)
        except ValueError as error:
            assert "dimensions disagree" in str(error)
        else:
            raise AssertionError("score/raw metadata mismatch published")
        assert store.result(rejected["task_id"]) is None
        assert store.db.execute("SELECT count(*) FROM company_ratings").fetchone()[0] == 1
        saved = json.loads(store.db.execute("SELECT payload_json FROM company_ratings").fetchone()[0])
        assert saved["score"] == raw["score"] and saved["confidence"] == .93
        assert store.db.execute("SELECT count(*) FROM job_company_profiles").fetchone()[0] == 4
        assert store.db.execute("SELECT count(*) FROM job_company_profiles WHERE profile_id IS NULL").fetchone()[0] == 2
        assert store.score_views()[0]["dimensions"] == machine["dimensions"]
    store.close()

print("workflow report: raw four-dimension rendering and shared SQLite references passed")

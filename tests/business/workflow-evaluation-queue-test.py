"""Verify refresh selection, obsolete task replacement, and bounded evidence recovery."""

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from career_ops.db import BusinessStore
from career_ops.input_contracts import canonical_scan_input, digest, score_inputs
from career_ops.tasks import cron_score, retained_scan_source


def source(opportunity_id):
    return {"schema_version": "scan_input_v1", "opportunity_id": opportunity_id,
            "url": f"https://example.com/{opportunity_id}", "company": "Example", "role": "Engineer",
            "jd": "Build reviewed agent systems.", "captured_at": "2026-09-20T00:00:00Z"}


def complete(store, task, outcome, artifact):
    row = store.task(task["task_id"])
    payload = {"outcome": outcome, "artifact": artifact, "input_hash": row["input_hash"]}
    store.db.execute("UPDATE tasks SET status='completed' WHERE task_id=?", (task["task_id"],))
    store.db.execute("INSERT INTO results VALUES(?,?,?,?,?,?)",
                     (task["task_id"], task["task_id"], row["opportunity_id"], row["module"],
                      row["input_hash"], json.dumps(payload)))


def dispatch(directory, opportunity_id, module, value, crash_at, re_evaluate=False):
    """Exercise real scan reuse and replacement while leaving model-backed scoring inert."""
    if module == "score":
        return {"status": "waiting"}
    store = BusinessStore(directory / "opportunities.db")
    try:
        return store.start(opportunity_id, module, canonical_scan_input(value), re_evaluate=re_evaluate)
    finally:
        store.close()


with tempfile.TemporaryDirectory(prefix="career-ops-evaluation-queue-") as temporary:
    directory = Path(temporary)
    db = sqlite3.connect(directory / "opportunities.db")
    db.executescript("""
      CREATE TABLE opportunities(id INTEGER PRIMARY KEY,url TEXT,company TEXT,role TEXT,
        state TEXT DEFAULT 'evaluated',created_at TEXT DEFAULT '2026-09-20',claimed_by TEXT,attempts INTEGER DEFAULT 0);
      CREATE TABLE page_evidence(opportunity_id INTEGER PRIMARY KEY,content TEXT,captured_at TEXT);
      CREATE TABLE opportunity_events(opportunity_id INTEGER,type TEXT,payload TEXT);
      INSERT INTO opportunities(id,url,company,role) VALUES(1,'https://example.com/1','Example','Engineer');
    """)
    db.close()
    store = BusinessStore(directory / "opportunities.db")
    current_scan = canonical_scan_input(json.dumps(source("1")))
    old = json.loads(current_scan)
    old["cv"] = "Previous candidate evidence"
    old_scan = json.dumps(old)
    waiting = store.start("1", "scan", old_scan)
    store.wait(waiting["task_id"], "input_changed")
    store.close()
    with patch("career_ops.tasks.start_and_run", return_value={"status": "waiting"}) as start:
        assert cron_score(directory)["opportunity_id"] == "1"
        assert start.call_args.args[2] == "scan" and start.call_args.args[5] is True
        assert json.loads(start.call_args.args[3]) == source("1")
    store = BusinessStore(directory / "opportunities.db")
    replacement = store.start("1", "scan", current_scan, re_evaluate=True)
    assert store.task(waiting["task_id"])["status"] == "cancelled"
    store.wait(replacement["task_id"], "core_evidence_missing")
    store.close()
    with patch("career_ops.tasks.start_and_run") as start, patch("career_ops.tasks.capture_jd") as capture:
        assert cron_score(directory) == {"status": "idle", "reason": "no_runnable_evaluations"}
        start.assert_not_called()
        capture.assert_not_called()

    store = BusinessStore(directory / "opportunities.db")
    store.wait(replacement["task_id"], "input_changed")
    store.close()
    with patch("career_ops.tasks.start_and_run", return_value={"status": "waiting"}) as start:
        assert cron_score(directory)["opportunity_id"] == "1"
        assert start.call_args.args[2] == "scan" and start.call_args.args[5] is True

    store = BusinessStore(directory / "opportunities.db")
    report = {**source("1"), "schema_version": "jd_report_v1", "prescreen": {"status": "pass"}}
    complete(store, replacement, "jd_report", report)
    assert retained_scan_source(store, "1") == source("1")
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    old = json.loads(score_inputs(report))
    old["company_evidence_as_of"] = yesterday
    scored = store.start("1", "score", json.dumps(old))
    complete(store, scored, "score", {
        "score": {"direction": 4, "company": 4, "culture": 4, "compensation": 4},
        "company_profiles": {"company": {"valid_until": yesterday}},
    })
    item = store.score_views()[0]
    assert item["valid"] and item["needs_rescore"]
    assert item["refresh_reasons"] == ["company_evidence_expired"]
    assert not store.decision_views()["decisions"]
    failed_score = store.start("1", "score", score_inputs(report), re_evaluate=True)
    store.wait(failed_score["task_id"], "failure:OpenAIConnectionError")
    store.close()
    with patch("career_ops.tasks.resume_task", return_value={"status": "waiting"}) as resume:
        assert cron_score(directory)["opportunity_id"] == "1"
        assert resume.call_args.args == (directory, failed_score["task_id"], None, None)
    store = BusinessStore(directory / "opportunities.db")
    store.db.execute("UPDATE tasks SET attempt=2 WHERE task_id=?", (failed_score["task_id"],))
    store.close()
    with patch("career_ops.tasks.resume_task") as resume, patch("career_ops.tasks.start_and_run") as start:
        assert cron_score(directory)["status"] == "idle"
        resume.assert_not_called()
        start.assert_not_called()
    store = BusinessStore(directory / "opportunities.db")
    store.cancel(failed_score["task_id"])
    blocked = store.start("1", "apply", "{}")
    store.wait(blocked["task_id"], "failure:RuntimeError")
    failed_scan = store.start("1", "scan", canonical_scan_input(json.dumps({**source("1"), "jd": ""})), re_evaluate=True)
    store.wait(failed_scan["task_id"], "source_access_unknown")
    store.close()
    with patch("career_ops.tasks.capture_jd") as capture, \
         patch("career_ops.tasks.start_and_run", side_effect=dispatch) as start:
        assert cron_score(directory)["opportunity_id"] == "1"
        assert start.call_args.args[2] == "score"
        capture.assert_not_called()
    store = BusinessStore(directory / "opportunities.db")
    assert store.task(failed_scan["task_id"])["status"] == "cancelled"
    assert store.task(blocked["task_id"])["status"] == "waiting"
    updated = store.start("1", "score", score_inputs(report), re_evaluate=True)
    assert updated["task_id"] != scored["task_id"]
    store.wait(updated["task_id"], "core_evidence_missing")
    store.close()
    with patch("career_ops.tasks.start_and_run") as start:
        assert cron_score(directory)["status"] == "idle"
        start.assert_not_called()

    store = BusinessStore(directory / "opportunities.db")
    store.cancel(updated["task_id"])
    stale = json.loads(score_inputs(report))
    stale["targeting"] = "Previous role preferences"
    stale_task = store.start("1", "score", json.dumps(stale), re_evaluate=True)
    complete(store, stale_task, "score", {"score": {"direction": 4, "company": 4, "culture": 4, "compensation": 4}})
    assert store.score_views()[0]["refresh_reasons"] == ["inputs_changed"]
    store.close()
    with patch("career_ops.tasks.capture_jd") as capture, \
         patch("career_ops.tasks.start_and_run", side_effect=dispatch) as start:
        assert cron_score(directory)["opportunity_id"] == "1"
        assert start.call_args.args[2] == "score"
        capture.assert_not_called()

    store = BusinessStore(directory / "opportunities.db")
    incomplete = {**source("1"), "jd": "Partial new posting"}
    pending = store.start("1", "scan", canonical_scan_input(json.dumps(incomplete)), re_evaluate=True)
    store.wait(pending["task_id"], "core_evidence_missing")
    updated_jd = "New complete posting with explicit employment and capability evidence."
    capture = {"url": source("1")["url"], "scan_jd": {
        "text": updated_jd, "final_url": source("1")["url"], "content_hash": digest(updated_jd),
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }}
    store.db.execute("CREATE TABLE source_evidence(id INTEGER PRIMARY KEY,opportunity_id INTEGER,payload TEXT)")
    store.db.execute("INSERT INTO source_evidence(opportunity_id,payload) VALUES(1,?)", (json.dumps(capture),))
    store.close()
    with patch("career_ops.tasks.capture_jd") as fetch, \
         patch("career_ops.tasks.start_and_run", side_effect=dispatch) as start:
        assert cron_score(directory)["opportunity_id"] == "1"
        assert start.call_args.args[2] == "scan"
        assert json.loads(start.call_args.args[3])["jd"] == updated_jd
        fetch.assert_not_called()

print("evaluation queue: expired and changed scores refresh; unchanged waits do not retry; obsolete tasks are replaced")

"""Verify dashboard stages, materials, file boundary and CLI-backed application records."""

import hashlib
import json
from http.server import ThreadingHTTPServer
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
from urllib.error import HTTPError
import time
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from career_ops.dashboard.actions import ActionRunner  # noqa: E402
from career_ops.input_contracts import apply_inputs, digest, score_inputs  # noqa: E402
from career_ops.dashboard.server import handler_for  # noqa: E402


class StubRunner:
    def __init__(self):
        self.started = []

    def start(self, opportunity_id: int, action: str) -> dict:
        self.started.append((opportunity_id, action))
        return {"action": action, "status": "running"}

    def status(self, opportunity_id: int) -> dict | None:
        return next(({"action": action, "status": "running"} for key, action in self.started if key == opportunity_id), None)

    def statuses(self) -> dict[int, dict]:
        return {key: {"action": action, "status": "running"} for key, action in self.started}


def fetch(base: str, path: str, status: int = 200, method: str = "GET", headers: dict | None = None, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urlopen(Request(base + path, data=data, method=method, headers=headers or {})) as response:
            assert response.status == status, (path, response.status)
            body = response.read()
            return json.loads(body) if "json" in response.headers["Content-Type"] else body.decode()
    except HTTPError as error:
        assert error.code == status, (path, error.code)
        return json.loads(error.read())


with tempfile.TemporaryDirectory() as temporary:
    directory = Path(temporary)
    package = directory / "package-v001"
    package.mkdir()
    (package / "upskill.md").write_text("# Upskill\n\nLearn **evals**.")
    (package / "interview-prep.md").write_text("# Prep")
    (package / "resume.json").write_text("{}")
    (package / "resume.pdf").write_text("%PDF-1.4 fixture")
    (directory / "secret.md").write_text("not referenced")
    score = {"direction": 4.96, "compensation": None, "company": 4.02, "culture": None}
    prescreen = {"status": "pass"}
    database = directory / "opportunities.db"
    db = sqlite3.connect(database)
    db.executescript(
        """
        CREATE TABLE opportunities(id INTEGER PRIMARY KEY,url TEXT,company TEXT,role TEXT,source TEXT,state TEXT,application_state TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE tasks(task_id TEXT PRIMARY KEY,opportunity_id TEXT,module TEXT,status TEXT,input_hash TEXT,attempt INTEGER,waiting_reason TEXT,workflow_version TEXT,input_payload TEXT);
        CREATE TABLE results(result_key TEXT PRIMARY KEY,task_id TEXT UNIQUE,opportunity_id TEXT,module TEXT,input_hash TEXT,payload TEXT);
        CREATE TABLE eligibility(opportunity_id INTEGER PRIMARY KEY,status TEXT,evidence TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE evaluations(opportunity_id INTEGER PRIMARY KEY,lower_score REAL,upper_score REAL,coverage REAL,dimension_scores TEXT,report_hash TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE artifacts(id INTEGER PRIMARY KEY,opportunity_id INTEGER,kind TEXT,path TEXT,sha256 TEXT);
        CREATE TABLE application_lifecycle(opportunity_id TEXT PRIMARY KEY,status TEXT,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE application_events(id INTEGER PRIMARY KEY,operation_id TEXT,opportunity_id TEXT,from_status TEXT,to_status TEXT,action TEXT,source TEXT,payload TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        INSERT INTO opportunities(id,url,company,role,source,state,application_state) VALUES
          (1,'https://example.com/1','Acme','Scanned Engineer','search','discovered','none'),
          (2,'https://example.com/2','Beta','Scored Engineer','provider','evaluated','none'),
          (3,'https://example.com/3','Gamma','Applied Engineer','provider','evaluated','submitted');
        INSERT INTO application_lifecycle(opportunity_id,status) VALUES('3','applied');
        INSERT INTO application_events(operation_id,opportunity_id,to_status,action,source,payload) VALUES('op','3','applied','submit','user','{"notes":"ok"}');
        INSERT INTO evaluations(opportunity_id,report_hash) VALUES(2,'h'),(3,'h');
        INSERT INTO eligibility(opportunity_id,status,evidence) VALUES(3,'pass','{"evidence":[]}');
        """
    )
    def jd_report(opportunity: str) -> dict:
        return {"schema_version": "jd_report_v1", "opportunity_id": opportunity, "url": f"https://example.com/{opportunity}",
                "company": "Example", "role": "Engineer", "jd": "JD text", "captured_at": "2026-10-01T00:00:00Z",
                "location_evidence": "Shanghai", "liveness": "active", "prescreen": prescreen}

    # Job 2 is scored against today's inputs; job 3's score predates an input change.
    score_hashes = {"2": digest(score_inputs(jd_report("2"))), "3": "stale-inputs"}
    for opportunity in ("1", "2", "3"):
        scan = {"outcome": "jd_report", "input_hash": "h", "artifact": jd_report(opportunity)}
        db.execute("INSERT INTO results VALUES(?,?,?,?,?,?)", (f"scan-{opportunity}", f"scan-{opportunity}", opportunity, "scan", "h", json.dumps(scan)))
    for opportunity, input_hash in score_hashes.items():
        db.execute("INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?)", (f"score-{opportunity}", opportunity, "score", "completed", input_hash, 1, None, "v", score_inputs(jd_report(opportunity))))
        scored = {"outcome": "score", "input_hash": input_hash, "artifact": {"report": "## A. 岗位概览\n\nGood fit", "score": score, "scoring_model": "attractiveness-v4", "dimensions": {"culture": {"score": None, "reason": "no_matching_valid_profile"}}, "company_profiles": {"company": {"profile_id": "company-x", "valid_until": "2000-01-01"}}}}
        db.execute("INSERT INTO results VALUES(?,?,?,?,?,?)", (f"score-{opportunity}", f"score-{opportunity}", opportunity, "score", input_hash, json.dumps(scored)))
        if opportunity == "2":
            current_apply_hash = digest(apply_inputs(jd_report(opportunity), scored))
    # Job 3 keeps a superseded package and a newer one whose inputs have since changed; job 2's package is current.
    packages = (
        ("apply-3-old", "3", "old", {"upskill": str(directory / "secret.md")}),
        ("apply-3", "3", "h", {
            "upskill": str(package / "upskill.md"), "interview_prep": str(package / "interview-prep.md"),
            "resume_pdf": str(package / "missing.pdf"), "resume_payload": str(package / "resume.json")}),
        ("apply-2", "2", current_apply_hash, {"resume_pdf": str(package / "resume.pdf")}),
    )
    for task_id, opportunity, input_hash, files in packages:
        db.execute("INSERT INTO tasks VALUES(?,?,'apply','completed',?,1,NULL,'v','{}')", (task_id, opportunity, input_hash))
        db.execute("INSERT INTO results VALUES(?,?,?,'apply',?,?)", (task_id, task_id, opportunity, input_hash, json.dumps(
            {"outcome": "package", "input_hash": input_hash, "artifact": {"files": files}})))
    db.commit()
    db.close()
    before = hashlib.sha256(database.read_bytes()).hexdigest()

    runner = StubRunner()
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(database, runner))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        assert "<title>Career Ops Dashboard</title>" in fetch(base, "/")
        jobs = {job["id"]: job for job in fetch(base, "/api/jobs")}
        assert [jobs[i]["stage"] for i in (1, 2, 3)] == ["scanned", "scored", "applied"]
        assert "score" not in jobs[2] and jobs[2]["action"] == "deprioritize" and "score" not in jobs[1]
        assert jobs[2]["dimensions"]["culture"]["reason"] == "no_matching_valid_profile"
        assert jobs[2]["profile_expired"] and jobs[2]["profile_shared"] == {"company": 2} and not jobs[1]["profile_expired"]
        assert jobs[2]["scores"]["direction"] == 4.96 and jobs[3]["action"] is None
        assert jobs[3]["application_status"] == "applied" and jobs[3]["material_count"] == 2
        assert jobs[3]["url"] == "https://example.com/3" and jobs[1]["location"] == "Shanghai"
        assert [jobs[i]["score_current"] for i in (1, 2, 3)] == [None, True, False]

        detail = fetch(base, "/api/jobs/3")
        assert detail["report"].startswith("## A.") and detail["jd"] == "JD text"
        assert detail["application_events"][0]["payload"] == {"notes": "ok"}
        assert [item["id"] for item in detail["materials"]] == ["resume_pdf", "interview_prep", "upskill"], "latest package only, display order"
        materials = {item["id"]: item for item in detail["materials"]}
        assert materials["upskill"] == {"id": "upskill", "label": "Upskill", "content": "# Upskill\n\nLearn **evals**.", "exists": True}
        assert not materials["resume_pdf"]["exists"] and materials["resume_pdf"]["content"] is None
        assert detail["materials_current"] is False and "confirmed_package" not in detail
        current = fetch(base, "/api/jobs/2")
        assert current["materials_current"] is True and current["materials"][0]["exists"]
        assert fetch(base, "/api/jobs/1")["materials_current"] is None

        assert "Learn **evals**" in fetch(base, "/api/jobs/3/file?id=upskill")
        assert fetch(base, "/api/jobs/2/file?id=resume_pdf") == "%PDF-1.4 fixture"
        fetch(base, "/api/jobs/2/file?id=upskill", 404)
        fetch(base, "/api/jobs/3/file?id=resume_pdf", 404)
        fetch(base, "/api/jobs/3/file?id=resume_payload", 404)
        fetch(base, "/api/jobs/3/file?id=" + str(directory / "secret.md"), 404)
        fetch(base, "/api/jobs/99", 404)

        action = {"X-Career-Ops": "dashboard"}
        fetch(base, "/api/jobs/2/prepare", 403, "POST")
        fetch(base, "/api/jobs/2/prepare", 403, "POST", {**action, "Origin": "https://evil.example"})
        fetch(base, "/api/jobs/2/prepare", 403, "POST", {**action, "Host": "evil.example"})
        fetch(base, "/api/jobs/2/unknown", 404, "POST", action)
        assert "还没有打分" in fetch(base, "/api/jobs/1/prepare", 409, "POST", action)["error"]
        assert "过期" in fetch(base, "/api/jobs/3/prepare", 409, "POST", action)["error"]
        fetch(base, "/api/jobs/99/prepare", 404, "POST", action)
        assert runner.started == []
        origin = {**action, "Origin": base}
        assert fetch(base, "/api/jobs/2/prepare", 202, "POST", origin)["run"]["status"] == "running"
        assert fetch(base, "/api/jobs/1/rescore", 202, "POST", action)["run"]["action"] == "rescore"
        assert runner.started == [(2, "prepare"), (1, "rescore")]
        assert fetch(base, "/api/jobs/2/run")["run"]["action"] == "prepare" and fetch(base, "/api/jobs/3/run")["run"] is None
        assert {job["id"]: job["run"] for job in fetch(base, "/api/jobs")} == {
            1: {"action": "rescore", "status": "running"}, 2: {"action": "prepare", "status": "running"}, 3: None}
        assert fetch(base, "/api/jobs/3")["apply_task"] == {"task_id": "apply-3", "status": "completed", "reason": None}
    finally:
        server.shutdown()
        server.server_close()
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before, "dashboard must not write the store"

    # The real runner delegates to the CLI; job 3's score is stale, so the CLI refuses before any task or model call.
    real = ActionRunner(directory)
    assert real.start(3, "prepare")["status"] == "running"
    try:
        real.start(3, "rescore")
        raise AssertionError("duplicate preparation must be refused")
    except RuntimeError:
        pass
    deadline = time.monotonic() + 60
    while real.status(3)["status"] == "running" and time.monotonic() < deadline:
        time.sleep(0.2)
    finished = real.status(3)
    assert finished["status"] == "failed" and finished["finished_at"], finished
    assert "Current score is stale" in finished["error"], finished["error"]
    with sqlite3.connect(database) as check:
        assert check.execute("SELECT COUNT(*) FROM tasks WHERE opportunity_id='3' AND module='apply'").fetchone()[0] == 2

    # Application records are written synchronously through the CLI with the page's idempotency key.
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(database, StubRunner()))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    action = {"X-Career-Ops": "dashboard", "Content-Type": "application/json"}
    record = "/api/jobs/2/record"
    try:
        assert fetch(base, "/api/jobs/2")["status_options"] == []
        assert fetch(base, "/api/jobs/3")["status_options"][0] == "responded"
        submit = {"kind": "submit", "key": "dashboard-key-1", "date": "2026-10-01", "notes": "via friend"}
        fetch(base, record, 403, "POST", {"Content-Type": "application/json"}, submit)
        assert fetch(base, record, 200, "POST", action, submit)["result"]["status"] == "applied"
        assert fetch(base, record, 200, "POST", action, submit)["result"]["reused"] is True
        assert "submitted" in fetch(base, record, 409, "POST", action, {**submit, "key": "dashboard-key-2"})["error"]
        assert "YYYY-MM-DD" in fetch(base, record, 409, "POST", action, {**submit, "key": "dashboard-key-3", "date": "soon"})["error"]
        assert "不能记录" in fetch(base, record, 409, "POST", action, {"kind": "status", "key": "dashboard-key-4", "value": "hired"})["error"]
        fetch(base, record, 200, "POST", action, {"kind": "status", "key": "dashboard-key-5", "value": "responded"})
        fetch(base, record, 200, "POST", action, {"kind": "followup", "key": "dashboard-key-6", "date": "2026-10-05"})
        fetch(base, record, 200, "POST", action, {"kind": "schedule", "key": "dashboard-key-7", "date": "2099-01-01"})
        followup = fetch(base, "/api/jobs/2/followup")["followup"]
        assert followup["status"] == "responded" and followup["nextFollowupDate"] == "2099-01-01", followup
        assert followup["lastFollowupAt"] == "2026-10-05", followup
        detail = fetch(base, "/api/jobs/2")
        assert detail["application_status"] == "responded" and "rejected" in detail["status_options"]
        assert detail["application_events"][0]["payload"] == {"submitted_at": "2026-10-01", "notes": "via friend"}
        assert {event["source"] for event in detail["application_events"]} == {"dashboard"}
        assert fetch(base, "/api/jobs/1/followup")["followup"] is None
        fetch(base, record, 200, "POST", action, {"kind": "status", "key": "dashboard-key-8", "value": "rejected"})
        detail = fetch(base, "/api/jobs/2")
        assert [event["to_status"] for event in detail["application_events"]].count("rejected") == 1
        assert [item["type"] for item in detail["application_activity"]] == ["followup_sent"], "an outcome is one timeline entry"
    finally:
        server.shutdown()
        server.server_close()

print("workflow dashboard: ok")

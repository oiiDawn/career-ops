"""Verify readable single-package publication, replacement and failure recovery."""

import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from career_ops.db import BusinessStore
from career_ops.input_contracts import validate_resume_payload

PYTHON = ROOT / ".venv" / "bin" / "python"
RUNNER = str(ROOT / 'tests' / 'fixtures' / 'workflow-model-runner.py')
RESUME_RENDERER = f"{PYTHON} {ROOT / 'tests' / 'fixtures' / 'workflow-resume-renderer.py'}"

try:
    validate_resume_payload({"candidate": {"name": "Jane Doe"}, "summary": "Verified", "projects_start_on_new_page": "true"})
except ValueError as error:
    assert "projects_start_on_new_page" in str(error)
else:
    raise AssertionError("Non-boolean layout instruction was accepted")


def call(directory: Path, input_root: Path, *args: str, expected: int = 0,
         extra_env: dict | None = None) -> dict:
    result = subprocess.run(
        [str(PYTHON), str(ROOT / "tests/fixtures/workflow-cli.py"), "--directory", str(directory), *args],
        text=True, capture_output=True,
        env={**os.environ, "CAREER_OPS_MODEL_STUB": RUNNER, "CAREER_OPS_RESUME_RENDERER": RESUME_RENDERER,
             "CAREER_OPS_INPUT_ROOT": str(input_root), **(extra_env or {})},
    )
    assert result.returncode == expected, (args, result.stdout, result.stderr)
    return json.loads(result.stdout) if result.stdout else {}


def source(path: Path, opportunity: str, jd: str) -> Path:
    path.write_text(json.dumps({
        "schema_version": "scan_input_v1", "opportunity_id": opportunity,
        "url": f"https://example.com/{opportunity}", "company": "Example", "role": "AI Engineer",
        "captured_at": "2026-09-20T04:00:00Z", "liveness": "active", "jd": jd,
    }))
    return path


with tempfile.TemporaryDirectory(prefix="career-ops-apply-") as temporary:
    root = Path(temporary)
    directory = root / "workflow"
    inputs = root / "inputs"
    (inputs / "config").mkdir(parents=True)
    (inputs / "modes").mkdir()
    (inputs.parent / "rules" / "applications").mkdir(parents=True)
    (inputs.parent / "rules" / "shared").mkdir()
    (inputs / "writing-samples").mkdir()
    for market in ("cn", "hk", "remote"):
        (inputs.parent / "rules" / "markets" / market).mkdir(parents=True)
        (inputs.parent / "rules" / "markets" / market / "employment.md").write_text(f"{market} employment rule")
    (inputs / "cv.md").write_text("Verified candidate facts")
    (inputs / "profile.yml").write_text("language:\n  output: zh-CN\n")
    (inputs / "targeting.md").write_text("Target AI roles")
    (inputs.parent / "rules").mkdir(parents=True, exist_ok=True)
    (inputs.parent / "rules" / "scoring.md").write_text("Never invent claims")
    (inputs.parent / "rules" / "evaluation").mkdir()
    (inputs.parent / "rules" / "evaluation" / "four-dimension.md").write_text((ROOT / "rules/evaluation/four-dimension.md").read_text())
    (inputs.parent / "rules" / "shared" / "contract.md").write_text("Candidate claims require evidence")
    (inputs.parent / "rules" / "applications" / "workflow.md").write_text("Prepare resume and application materials; never submit.")
    (inputs / "article-digest.md").write_text("Approved article evidence")
    (inputs / "voice.md").write_text("Direct first-person voice")
    (inputs / "writing-samples" / "sample.md").write_text("Approved writing sample")

    first = source(root / "first.json", "job-1", "Build reviewed AI agents.")
    call(directory, inputs, "task", "start", "scan", "job-1", str(first))
    call(directory, inputs, "task", "start", "score", "job-1", "scan:job-1")
    (inputs / "cv.md").write_text("Current verified candidate facts")
    with sqlite3.connect(directory / "opportunities.db") as connection:
        score_row = connection.execute("SELECT payload FROM results WHERE opportunity_id='job-1' AND module='score'").fetchone()
        retained_score = json.loads(score_row[0])
        retained_score["artifact"]["company_profiles"] = {"company": {"valid_until": "2000-01-01"}}
        connection.execute("UPDATE results SET payload=? WHERE opportunity_id='job-1' AND module='score'", (json.dumps(retained_score),))
    with sqlite3.connect(directory / "opportunities.db") as connection:
        connection.execute("UPDATE tasks SET input_payload=input_payload || ' ' WHERE opportunity_id='job-1' AND module='score'")
    call(directory, inputs, "task", "start", "apply", "job-1", "score:job-1", expected=1)
    with sqlite3.connect(directory / "opportunities.db") as connection:
        connection.execute("UPDATE tasks SET input_payload=substr(input_payload,1,length(input_payload)-1) WHERE opportunity_id='job-1' AND module='score'")
    package = call(directory, inputs, "task", "start", "apply", "job-1", "score:job-1")
    with sqlite3.connect(directory / "opportunities.db") as connection:
        stored_input = json.loads(connection.execute("SELECT input_payload FROM tasks WHERE task_id=?", (package["task_id"],)).fetchone()[0])
    assert stored_input["cv"] == "Current verified candidate facts"
    assert stored_input["score_result"] == retained_score
    assert stored_input["artifact_contract_version"] == 4
    assert stored_input["articles"] == "Approved article evidence"
    assert stored_input["voice"] == "Direct first-person voice"
    assert stored_input["writing_samples"]["writing-samples/sample.md"] == "Approved writing sample"
    assert set(stored_input["market_rules"]) == {"cn", "hk", "remote"}
    assert "feedback" not in stored_input
    assert package["status"] == "completed" and package["reason"] is None and package["allowed_actions"] == []
    assert package["artifact"]["outcome"] == "package"
    files = package["artifact"]["artifact"]["files"]
    assert set(files) == {"resume_payload", "changes", "cover_letter", "upskill", "interview_prep", "questions",
                          "resume_pdf", "resume_metadata"}
    assert all(Path(path).is_file() for path in files.values())
    assert {Path(path).parent for path in files.values()} == {directory / "applications" / "Example__AI-Engineer__job-1"}
    assert Path(files["cover_letter"]).read_text() == "Grounded cover letter"
    assert package["artifact"]["artifact"]["pdf_receipt"]["pages"] == 1

    assert call(directory, inputs, "task", "start", "apply", "job-1", "score:job-1")["task_id"] == package["task_id"]
    call(directory, inputs, "task", "resume", package["task_id"], expected=1)
    assert call(directory, inputs, "task", "cancel", package["task_id"])["status"] == "completed"
    (inputs.parent / "rules" / "applications" / "workflow.md").write_text("Prepare materials; never submit or send.")
    call(directory, inputs, "task", "start", "apply", "job-1", "score:job-1", expected=1)
    original_metadata = Path(files["resume_metadata"]).read_bytes()
    call(directory, inputs, "task", "start", "apply", "job-1", "score:job-1", "--re-evaluate", expected=1,
         extra_env={"CAREER_OPS_RESUME_FAIL_ONCE": str(root / "regeneration-failed")})
    assert Path(files["resume_metadata"]).read_bytes() == original_metadata
    with sqlite3.connect(directory / "opportunities.db") as connection:
        assert connection.execute("SELECT task_id FROM results WHERE module='apply' AND opportunity_id='job-1'").fetchone()[0] == package["task_id"]
    failed_regeneration = next(task for task in reversed(call(directory, inputs, "task", "list"))
                               if task["opportunity_id"] == "job-1" and task["module"] == "apply")
    regenerated = call(directory, inputs, "task", "resume", failed_regeneration["task_id"])
    assert regenerated["status"] == "completed" and regenerated["task_id"] != package["task_id"]
    assert all(Path(path).is_file() for path in files.values())
    assert regenerated["artifact"]["artifact"]["files"] == files
    assert Path(files["resume_metadata"]).read_bytes() != original_metadata
    assert call(directory, inputs, "task", "show", package["task_id"])["status"] == "cancelled"
    with sqlite3.connect(directory / "opportunities.db") as connection:
        assert connection.execute("SELECT count(*) FROM results WHERE module='apply' AND opportunity_id='job-1'").fetchone()[0] == 1
    assert not list((directory / ".staging" / "apply").iterdir())

    third = source(root / "third.json", "job-3", "Build reliable AI agents.")
    call(directory, inputs, "task", "start", "scan", "job-3", str(third))
    call(directory, inputs, "task", "start", "score", "job-3", "scan:job-3")
    call(directory, inputs, "task", "start", "apply", "job-3", "score:job-3", "--crash-at", "publish", expected=86)
    crashed_task = next(task for task in call(directory, inputs, "task", "list") if task["opportunity_id"] == "job-3" and task["module"] == "apply")
    recovered = call(directory, inputs, "task", "run", crashed_task["task_id"])
    assert recovered["status"] == "completed" and recovered["artifact"]["outcome"] == "package"

    fourth = source(root / "fourth.json", "job-4", "Build verifiable AI agents.")
    call(directory, inputs, "task", "start", "scan", "job-4", str(fourth))
    call(directory, inputs, "task", "start", "score", "job-4", "scan:job-4")
    apply_call_log = root / "failed-export-model-calls.txt"
    call(directory, inputs, "task", "start", "apply", "job-4", "score:job-4", expected=1,
         extra_env={"CAREER_OPS_RESUME_FAIL_ONCE": str(root / "export-failed"), "WORKFLOW_TEST_CALL_LOG": str(apply_call_log)})
    export_task = next(task for task in call(directory, inputs, "task", "list") if task["opportunity_id"] == "job-4" and task["module"] == "apply")
    assert export_task["reason"] == "failure:RuntimeError" and export_task["allowed_actions"] == ["resume", "cancel"]
    call(directory, inputs, "task", "resume", export_task["task_id"], "--input", str(fourth), expected=1)
    export_recovered = call(directory, inputs, "task", "resume", export_task["task_id"],
                            extra_env={"WORKFLOW_TEST_CALL_LOG": str(apply_call_log)})
    assert export_recovered["status"] == "completed"
    assert apply_call_log.read_text().splitlines() == ["apply_evaluate"]
    assert Path(export_recovered["artifact"]["artifact"]["files"]["resume_pdf"]).is_file()

    fifth = source(root / "fifth.json", "job-5", "Build observable AI agents.")
    call(directory, inputs, "task", "start", "scan", "job-5", str(fifth))
    call(directory, inputs, "task", "start", "score", "job-5", "scan:job-5")
    call(directory, inputs, "task", "start", "apply", "job-5", "score:job-5", expected=1,
         extra_env={"CAREER_OPS_RESUME_FAIL_ONCE": str(root / "export-failed-again")})
    failed_task = next(task for task in call(directory, inputs, "task", "list") if task["opportunity_id"] == "job-5" and task["module"] == "apply")
    call(directory, inputs, "task", "start", "score", "job-5", "scan:job-5", "--re-evaluate")
    superseding = call(directory, inputs, "task", "start", "apply", "job-5", "score:job-5")
    assert superseding["status"] == "completed" and superseding["task_id"] != failed_task["task_id"]
    assert call(directory, inputs, "task", "show", failed_task["task_id"])["status"] == "cancelled"

print("workflow apply: readable publication, replacement and failure recovery passed")

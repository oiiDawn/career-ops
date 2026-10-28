"""Verify safe package replacement, interrupted swaps and physical data migration."""

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from career_ops.applications.materials import discard_finished_work, package_directory, publish_package, verify_files
from career_ops.db import BusinessStore

spec = importlib.util.spec_from_file_location("material_migration", ROOT / "scripts/migrate-application-materials.py")
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


def package(root: Path, text: str) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    files = {"resume_pdf": str(root / "resume.pdf"), "resume_metadata": str(root / "reactive-resume.json")}
    Path(files["resume_pdf"]).write_text(text)
    Path(files["resume_metadata"]).write_text('{"resume_id":"test","last_artifact_version":1}')
    return {"files": files, "file_hashes": {key: hashlib.sha256(Path(path).read_bytes()).hexdigest() for key, path in files.items()},
            "pdf_receipt": {"metadata_path": files["resume_metadata"]}, "package": {"cover_letter": text}}


def state(store: BusinessStore, task_id: str, artifact: dict) -> dict:
    return {"task_id": task_id, "module": "apply", "input_hash": store.task(task_id)["input_hash"],
            "outcome": "package", "material_hash": "package-hash", "draft": json.dumps(artifact)}


with tempfile.TemporaryDirectory() as temporary:
    directory = Path(temporary)
    report = {"company": "测试/公司", "role": "AI / Engineer"}
    destination = package_directory(directory, "42", report)
    assert destination.name == "测试-公司__AI-Engineer__42"
    assert len(package_directory(directory, "42", {"company": "中" * 100, "role": "岗" * 100}).name.encode()) < 255
    try:
        package_directory(directory, "../42", report)
    except ValueError:
        pass
    else:
        raise AssertionError("Unsafe opportunity ID accepted")
    store = BusinessStore(directory / "opportunities.db")
    first = store.start("42", "apply", json.dumps({"jd_report": report}))["task_id"]
    artifact = package(directory / ".staging" / "apply" / first / "package", "first")
    publish_package(store, directory, state(store, first, artifact))
    discard_finished_work(store, "42")
    second = store.start("42", "apply", json.dumps({"jd_report": report, "cv": "changed"}), re_evaluate=True)["task_id"]
    pending = directory / ".staging" / "apply" / second
    replacement = package(pending / "package", "replacement")
    next_state = state(store, second, replacement)
    publish = store.publish

    def fail(_):
        raise OSError("database publication failed")

    store.publish = fail
    try:
        publish_package(store, directory, next_state)
    except OSError:
        pass
    else:
        raise AssertionError("Expected publication failure")
    assert (destination / "resume.pdf").read_text() == "first"
    assert store.result(first) is not None and store.result(second) is None
    store.publish = publish
    destination.rename(pending / "previous")
    (pending / "package").rename(destination)
    publish_package(store, directory, next_state)
    discard_finished_work(store, "42")
    assert (destination / "resume.pdf").read_text() == "replacement"
    assert store.result(first) is None and store.task(first)["status"] == "cancelled"
    verify_files(store.result(second)["artifact"])
    assert not pending.exists()
    renamed_report = {**report, "role": "Senior AI Engineer"}
    third = store.start("42", "apply", json.dumps({"jd_report": renamed_report}), re_evaluate=True)["task_id"]
    artifact = package(directory / ".staging" / "apply" / third / "package", "renamed")
    publish_package(store, directory, state(store, third, artifact))
    discard_finished_work(store, "42")
    assert not destination.exists()
    assert (package_directory(directory, "42", renamed_report) / "resume.pdf").read_text() == "renamed"
    store.close()

with tempfile.TemporaryDirectory() as temporary:
    directory = Path(temporary)
    store = BusinessStore(directory / "opportunities.db")
    report = {"company": "Acme", "role": "AI Engineer"}
    for index in (1, 2):
        task_id = store.start("42", "apply", json.dumps({"jd_report": report, "revision": index}), re_evaluate=True)["task_id"]
        artifact = package(directory / "artifacts" / task_id / "input-hash" / "package", str(index))
        store.db.execute("INSERT INTO results VALUES(?,?,?,?,?,?)", (task_id, task_id, "42", "apply", store.task(task_id)["input_hash"],
                         json.dumps({"module": "apply", "artifact": artifact})))
        store.db.execute("UPDATE tasks SET status='completed' WHERE task_id=?", (task_id,))
    failed = store.start("43", "apply", json.dumps({"jd_report": report}))["task_id"]
    store.wait(failed, "failure:RuntimeError")
    store.close()
    migrated = migration.migrate(directory)
    assert len(migrated["packages"]) == 1
    store = BusinessStore(directory / "opportunities.db")
    current = store.module_result("42", "apply")["artifact"]
    verify_files(current)
    assert Path(current["files"]["resume_pdf"]).read_text() == "2"
    assert store.db.execute("SELECT count(*) FROM results WHERE module='apply'").fetchone()[0] == 1
    assert store.task(failed)["status"] == "waiting"
    assert not list((directory / "artifacts").iterdir())
    store.close()
    assert migration.migrate(directory)["packages"] == migrated["packages"]

print("application materials: readable names, rollback, interrupted replacement, migration and replay passed")

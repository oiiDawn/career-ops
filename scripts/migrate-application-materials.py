"""Migrate retained application packages into one readable directory per job."""

from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile

from langgraph.checkpoint.sqlite import SqliteSaver

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from career_ops.applications.materials import discard_finished_work, package_directory, relocate_artifact, verify_files
from career_ops.db import BusinessStore
from career_ops.liveness import execution_lock


def migrate(directory: Path) -> dict:
    """Back up SQLite, validate every source, commit new references, then remove old copies."""
    directory = directory.resolve()
    if not (directory / "opportunities.db").is_file():
        raise ValueError("Missing operational database")
    backup = Path(tempfile.mkdtemp(prefix="career-ops-material-migration-"))
    for name in ("opportunities.db", "workflow-checkpoints.db"):
        if (directory / name).exists():
            with sqlite3.connect(directory / name) as source, sqlite3.connect(backup / name) as target:
                source.backup(target)
    store = BusinessStore(directory / "opportunities.db")
    created = []
    committed = False
    try:
        with ExitStack() as locks:
            opportunities = [row[0] for row in store.db.execute("SELECT DISTINCT opportunity_id FROM tasks WHERE module='apply'")]
            for opportunity in opportunities:
                locks.enter_context(execution_lock(directory, opportunity))
            if store.db.execute("SELECT 1 FROM tasks WHERE module='apply' AND status='running'").fetchone():
                raise ValueError("Finish running application tasks before migration")
            selected = {}
            for row in store.db.execute(
                "SELECT r.rowid,r.task_id,r.opportunity_id,r.payload,t.input_payload FROM results r "
                "JOIN tasks t USING(task_id) WHERE r.module='apply' ORDER BY r.rowid DESC"
            ):
                selected.setdefault(row["opportunity_id"], row)
            store.db.execute("BEGIN IMMEDIATE")
            packages = []
            for opportunity, row in selected.items():
                payload = json.loads(row["payload"])
                artifact = payload["artifact"]
                verify_files(artifact)
                destination = package_directory(directory, opportunity, json.loads(row["input_payload"])["jd_report"])
                source = Path(artifact["files"]["resume_pdf"]).resolve().parent
                if source == destination:
                    packages.append(str(destination))
                    continue
                if not source.is_relative_to(directory / "artifacts" / row["task_id"]):
                    raise ValueError(f"Application source is outside its owned task directory: {source}")
                if any(Path(path).resolve().parent != source for path in artifact["files"].values()):
                    raise ValueError("Application files do not share one package directory")
                if destination.exists():
                    raise ValueError(f"Destination already exists: {destination}")
                destination.parent.mkdir(parents=True, exist_ok=True)
                created.append(destination)
                shutil.copytree(source, destination)
                updated = relocate_artifact(artifact, destination)
                metadata_path = Path(updated["files"]["resume_metadata"])
                metadata = json.loads(metadata_path.read_text())
                if "last_artifact_version" in metadata:
                    metadata.pop("last_artifact_version")
                    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
                    updated["file_hashes"]["resume_metadata"] = hashlib.sha256(metadata_path.read_bytes()).hexdigest()
                verify_files(updated)
                payload["artifact"] = updated
                store.db.execute("UPDATE results SET payload=? WHERE task_id=?", (json.dumps(payload, ensure_ascii=False, sort_keys=True), row["task_id"]))
                for key, old_path in artifact["files"].items():
                    if store.db.execute("SELECT 1 FROM sqlite_master WHERE name='artifacts' AND type='table'").fetchone():
                        store.db.execute("UPDATE artifacts SET path=?,sha256=? WHERE path=?",
                                         (updated["files"][key], updated["file_hashes"][key], old_path))
                packages.append(str(destination))
            for opportunity, row in selected.items():
                store.db.execute(
                    "UPDATE tasks SET status='cancelled',waiting_reason=NULL WHERE task_id IN "
                    "(SELECT task_id FROM results WHERE module='apply' AND opportunity_id=? AND task_id!=?)",
                    (opportunity, row["task_id"]),
                )
                store.db.execute("DELETE FROM results WHERE module='apply' AND opportunity_id=? AND task_id!=?",
                                 (opportunity, row["task_id"]))
            store.db.execute("COMMIT")
            committed = True
            for opportunity in opportunities:
                discard_finished_work(store, opportunity)
            draft_root = Path(os.environ.get("CAREER_OPS_DRAFT_ROOT", directory / "workflow-drafts"))
            active_keys = {
                hashlib.sha256(json.dumps({"inputs": json.loads(row[0])}, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
                for row in store.db.execute("SELECT input_payload FROM tasks WHERE module='apply' AND status='waiting'")
            }
            for draft in draft_root.glob("*/apply-checkpoints.db"):
                if draft.parent.name in active_keys:
                    continue
                with SqliteSaver.from_conn_string(str(draft)) as saver:
                    checkpoint = saver.get_tuple({"configurable": {"thread_id": draft.parent.name}})
                    values = checkpoint.checkpoint.get("channel_values", {}) if checkpoint else {}
                opportunity = str(values.get("payload", {}).get("inputs", {}).get("jd_report", {}).get("opportunity_id"))
                if opportunity in selected:
                    draft.unlink()
                    if not any(draft.parent.iterdir()):
                        draft.parent.rmdir()
            assert store.db.execute("PRAGMA quick_check").fetchone()[0] == "ok"
            assert not store.db.execute("PRAGMA foreign_key_check").fetchall()
            return {"packages": packages, "sqlite_backup": str(backup)}
    except Exception:
        if store.db.in_transaction:
            store.db.execute("ROLLBACK")
        if not committed:
            for path in created:
                shutil.rmtree(path, ignore_errors=True)
        raise
    finally:
        store.close()


if __name__ == "__main__":
    print(json.dumps(migrate(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data"), ensure_ascii=False, indent=2))

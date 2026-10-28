"""Publish one verified application package per job at a readable physical path."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3


def package_directory(directory: Path, opportunity_id: str, report: dict) -> Path:
    """Keep Unicode names while bounding components and excluding path separators."""
    def component(value: str) -> str:
        value = re.sub(r"[^\w.-]+", "-", str(value)).strip(".-_") or "unknown"
        return value.encode("utf-8")[:80].decode("utf-8", errors="ignore")

    if not re.fullmatch(r"[\w-]+", str(opportunity_id)) or len(str(opportunity_id).encode("utf-8")) > 80:
        raise ValueError("Invalid opportunity ID for application materials")
    name = "__".join((component(report["company"]), component(report["role"]), str(opportunity_id)))
    return directory / "applications" / name


def relocate_artifact(artifact: dict, root: Path) -> dict:
    """Change only stored file locations; content hashes and resume identity stay intact."""
    artifact = json.loads(json.dumps(artifact))
    artifact["files"] = {key: str(root / Path(path).name) for key, path in artifact["files"].items()}
    artifact["pdf_receipt"]["metadata_path"] = artifact["files"]["resume_metadata"]
    return artifact


def verify_files(artifact: dict) -> None:
    """Refuse to replace a usable package with missing or modified files."""
    if not artifact.get("files") or set(artifact["files"]) != set(artifact.get("file_hashes", {})):
        raise ValueError("Application package has incomplete file hashes")
    for key, name in artifact["files"].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest() != artifact["file_hashes"][key]:
            raise ValueError(f"Application material integrity check failed: {key}")


def publish_package(store, directory: Path, state: dict) -> dict:
    """Swap a validated package, rolling back on publication failure and resuming interrupted swaps."""
    task = store.task(state["task_id"])
    root = package_directory(directory, task["opportunity_id"], json.loads(task["input_payload"])["jd_report"])
    pending = directory / ".staging" / "apply" / task["task_id"]
    source = pending / "package"
    previous = pending / "previous"
    artifact = relocate_artifact(json.loads(state["draft"]), root)
    root.parent.mkdir(parents=True, exist_ok=True)
    try:
        if source.exists():
            verify_files(relocate_artifact(artifact, source))
            if root.exists():
                root.rename(previous)
            source.rename(root)
        verify_files(artifact)
        return store.publish({**state, "draft": json.dumps(artifact, ensure_ascii=False, sort_keys=True)})
    except Exception:
        if not source.exists() and root.exists():
            root.rename(source)
        if previous.exists() and not root.exists():
            previous.rename(root)
        raise


def discard_finished_work(store, opportunity_id: str) -> None:
    """Remove retired package copies and checkpoints; failed active work remains resumable."""
    directory = store.path.parent
    tasks = store.db.execute(
        "SELECT task_id,input_payload FROM tasks WHERE opportunity_id=? AND module='apply' "
        "AND status IN ('completed','cancelled')", (opportunity_id,),
    ).fetchall()
    checkpoint = directory / "workflow-checkpoints.db"
    if checkpoint.exists():
        with sqlite3.connect(checkpoint) as db:
            for task in tasks:
                for table in ("checkpoints", "writes"):
                    db.execute(f"DELETE FROM {table} WHERE thread_id GLOB ?", (task["task_id"] + ":*",))
    draft_root = Path(os.environ.get("CAREER_OPS_DRAFT_ROOT", directory / "workflow-drafts"))
    for task in tasks:
        for root in (directory / "artifacts" / task["task_id"], directory / ".staging" / "apply" / task["task_id"]):
            if root.exists():
                shutil.rmtree(root)
        payload = {"inputs": json.loads(task["input_payload"])}
        key = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        draft = draft_root / key / "apply-checkpoints.db"
        if draft.exists():
            draft.unlink()
            if not any(draft.parent.iterdir()):
                draft.parent.rmdir()
    current = store.module_result(opportunity_id, "apply")
    if current and current.get("artifact", {}).get("files"):
        root = Path(next(iter(current["artifact"]["files"].values()))).parent
        for other in (directory / "applications").glob("*__" + root.name.rsplit("__", 1)[-1]):
            if other != root and other.is_dir() and not other.is_symlink():
                shutil.rmtree(other)

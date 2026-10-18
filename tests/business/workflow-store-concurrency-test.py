"""Verify concurrent store opens preserve active task ownership."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import sys
import tempfile
from threading import Barrier

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from career_ops.db import BusinessStore


with tempfile.TemporaryDirectory(prefix="career-ops-store-concurrency-") as temporary:
    path = Path(temporary) / "opportunities.db"
    store = BusinessStore(path)
    task = store.start("shared", "scan", "{}")
    schema_version = store.db.execute("PRAGMA schema_version").fetchone()[0]
    store.close()
    ready = Barrier(8)

    def open_stores(worker: int) -> None:
        ready.wait(timeout=10)
        for _ in range(10):
            reader = BusinessStore(path)
            try:
                assert reader.start("shared", "scan", "{}")["task_id"] == task["task_id"]
                assert reader.db.execute("SELECT count(*) FROM tasks").fetchone()[0] == 1
            finally:
                reader.close()

    with ThreadPoolExecutor(max_workers=8) as workers:
        list(workers.map(open_stores, range(8)))

    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA schema_version").fetchone()[0] == schema_version
        try:
            db.execute(
                "INSERT INTO tasks(task_id,opportunity_id,module,status,input_hash,workflow_version,input_payload) "
                "SELECT 'duplicate',opportunity_id,module,status,input_hash,workflow_version,input_payload FROM tasks"
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("Two running tasks acquired the same opportunity")
        assert db.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert not db.execute("PRAGMA foreign_key_check").fetchall()

print("Store concurrency checks passed")

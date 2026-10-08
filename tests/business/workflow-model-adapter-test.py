"""Verify model response parsing and evidence normalization without model calls."""

import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from career_ops import model as adapter


assert adapter.parse_object('Explanation\n```json\n{"ok":true}\n```') == {"ok": True}
with tempfile.TemporaryDirectory() as temporary:
    path = Path(temporary) / "value.json"
    adapter.save(path, {"ok": True})
    assert json.loads(path.read_text()) == {"ok": True}
    assert path.read_text().endswith("\n")

scan_attempts = []
scan_responses = iter(({"jobs": []}, {"complete_jd": False, **dict.fromkeys((
    "company", "role", "liveness", "liveness_reason", "assessment_complete",
    "location", "employment", "compensation", "company_size", "years",
    "core_capabilities", "credentials",
))}))
with patch.object(adapter.llm, "complete_json",
                  lambda *_args: scan_attempts.append(True) or json.dumps(next(scan_responses))):
    result, _ = adapter.call_agent("prescreen_evidence", "scan prompt")
assert len(scan_attempts) == 2
assert result["complete_jd"] is False

for years, expected in [(0, None), (None, None), (3, 3), (False, False)]:
    evidence = adapter.attach_evidence({
        **dict.fromkeys((
            "company", "role", "complete_jd", "liveness", "liveness_reason",
            "assessment_complete", "core_capabilities", "credentials", "location",
            "employment", "compensation", "company_size",
        )),
        "years": {"verified": years},
    }, {"text": "Original JD"})
    assert evidence["prescreen"]["years"]["verified"] == expected
    assert evidence["jd"] == "Original JD"

print("workflow model adapter: parsing and evidence normalization passed")

with tempfile.TemporaryDirectory() as temporary:
    from career_ops.db import BusinessStore
    store = BusinessStore(Path(temporary) / "usage.db")
    task = store.start("job", "score", "inputs")
    token = adapter.USAGE.set((str(store.path), task["task_id"], None))
    try:
        for _ in range(25):
            adapter.record_call()
        assert store.task(task["task_id"])["attempt_tool_calls"] == 25
    finally:
        adapter.USAGE.reset(token)
    token = adapter.USAGE.set((str(store.path), task["task_id"], 25))
    try:
        try:
            adapter.record_call()
        except TimeoutError:
            pass
        else:
            raise AssertionError("explicit scan/apply call limit ignored")
    finally:
        adapter.USAGE.reset(token)
        store.close()

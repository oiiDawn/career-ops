"""Keep in-process model phases inside the task time and tool budgets."""

import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from career_ops import llm
from career_ops.db import BusinessStore
from career_ops.model import record_call
from career_ops.tasks import Runtime


with tempfile.TemporaryDirectory(prefix="career-ops-model-deadline-") as temporary:
    directory = Path(temporary)
    stub = directory / "stub.py"
    stub.write_text(
        "import os, time\n"
        "from career_ops import llm\n"
        "from career_ops.model import record_call\n"
        "def run(phase, payload):\n"
        "    if phase == 'slow':\n"
        "        time.sleep(1.2)\n"
        "        return {'artifact': {}}\n"
        "    if phase == 'expired':\n"
        "        time.sleep(1.2)\n"
        "        llm.remaining_seconds()\n"
        "    record_call()\n"
        "    return {'artifact': {}, 'remaining': llm.remaining_seconds()}\n"
    )
    store = BusinessStore(directory / "opportunities.db")
    with patch.dict(os.environ, {"CAREER_OPS_MODEL_STUB": str(stub)}):
        for phase in ("slow", "expired"):
            task = store.start(f"job-{phase}", "scan", "{}")
            with patch("career_ops.tasks.ATTEMPT_SECONDS", 1):
                try:
                    Runtime(store, directory).run_model(phase, {}, {"task_id": task["task_id"]})
                except TimeoutError as error:
                    assert str(error) == "time_budget_exhausted"
                else:
                    raise AssertionError(f"{phase} phase outlived the task deadline")
        task = store.start("job-metered", "scan", "{}")
        result = Runtime(store, directory).run_model("metered", {}, {"task_id": task["task_id"]})
        assert 0 < result["remaining"] <= llm.CALL_TIMEOUT_SECONDS
        assert store.task(task["task_id"])["attempt_tool_calls"] == 1
    assert llm.DEADLINE.get() is None
    record_call()  # outside a task the budget context is cleared
    store.close()

past = time.monotonic() - 1
token = llm.DEADLINE.set(past)
try:
    llm.remaining_seconds()
except TimeoutError as error:
    assert str(error) == "time_budget_exhausted"
else:
    raise AssertionError("Expired deadline allowed a model call")
finally:
    llm.DEADLINE.reset(token)

print("workflow model deadline: in-process time and tool budgets passed")

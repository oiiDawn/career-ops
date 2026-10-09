"""Keep scan/application phases bounded while long score research retains per-request timeouts."""

import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import httpx2
from openai import APITimeoutError

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
        score_task = store.start('job-score-uncapped', 'score', '{}')
        store.db.execute('UPDATE tasks SET attempt_elapsed_seconds=10000 WHERE task_id=?', (score_task['task_id'],))
        with patch('career_ops.tasks.ATTEMPT_SECONDS', 1):
            result = Runtime(store, directory).run_model('evaluate', {}, {'task_id': score_task['task_id']})
        assert result['remaining'] == llm.CALL_TIMEOUT_SECONDS
        assert store.task(score_task['task_id'])['attempt_tool_calls'] == 1
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

with patch.dict(os.environ, {"CAREER_OPS_MODEL": "m", "CAREER_OPS_LLM_BASE_URL": "http://127.0.0.1:9/v1",
                             "CAREER_OPS_LLM_API_KEY": "k"}):
    assert llm.chat_model().max_tokens == llm.MAX_OUTPUT_TOKENS  # endpoint default leaves no room after reasoning



class TimingOutModel:
    """Record each attempt's timeout and fail like an endpoint that never answers in time."""

    def __init__(self, timeouts):
        self.timeouts = timeouts

    def __call__(self, **kwargs):
        self.timeouts.append(kwargs["timeout"])
        return self

    def bind(self, **_kwargs):
        return self

    def invoke(self, *_args, **_kwargs):
        time.sleep(0.6)
        raise APITimeoutError(request=httpx2.Request("POST", "http://127.0.0.1:9/v1"))


timeouts = []
token = llm.DEADLINE.set(time.monotonic() + 1)
try:
    with patch.object(llm, "ChatOpenAI", TimingOutModel(timeouts)), patch.dict(os.environ, {
            "CAREER_OPS_MODEL": "m", "CAREER_OPS_LLM_BASE_URL": "http://127.0.0.1:9/v1", "CAREER_OPS_LLM_API_KEY": "k"}):
        llm.complete_json("system", "prompt")
except TimeoutError as error:
    assert str(error) == "time_budget_exhausted"
else:
    raise AssertionError("Model retries outlived the task deadline")
finally:
    llm.DEADLINE.reset(token)
assert len(timeouts) == 2 and timeouts[0] <= 1 and timeouts[1] < timeouts[0], timeouts

print("workflow model deadline: in-process time and tool budgets passed")

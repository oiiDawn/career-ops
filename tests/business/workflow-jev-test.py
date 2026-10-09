"""Check the isolated Jev rubric, native result preservation and bounded failure evidence."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
import httpx2


ROOT = Path(__file__).resolve().parents[2]
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from career_ops.evaluation import jev as jev
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.runnables import RunnableLambda


class Recorder(BaseCallbackHandler):
    def __init__(self):
        self.calls = []
        self.results = []
        self.errors = []

    def on_llm_start(self, serialized, prompts, **kwargs):
        self.calls.append(kwargs)
        assert 'test-key' not in prompts[0]

    def on_llm_end(self, response, **kwargs):
        self.results.append(response)

    def on_llm_error(self, error, **kwargs):
        self.errors.append(type(error).__name__)
request = jev.request_for({"posting": {"jd": "A retained job"}}, jev.RUBRIC.read_text())
assert len(request["questions"]) == 8
assert all(len(request["questions"][d]["criteria"]) == 5 for d in jev.DIMENSIONS)
assert "净工作时长" in request["questions"]["culture_evidence"]["instructions"]
assert "base / bonus / equity" in request["questions"]["compensation_evidence"]["instructions"]
response = {"model": jev.MODEL, "answers": {}, "usage": {"input_tokens": 120, "output_tokens": 8}}
for name, question in request["questions"].items():
    response["answers"][name] = ({"type": "noul", "noul": .12} if question["type"] == "noul" else
                                {"type": "score", "score": 2.37, "confidence": .93,
                                 "legend": {str(i): text for i, text in enumerate(question['criteria'])},
                                 "probabilities": {"0": 0, "1": 0, "2": .63, "3": .37, "4": 0}})
jev.validate(request, response)
raw = jev.dimensions(response)["culture"]
assert raw["score"] == 3.37 and raw["confidence"] == .93 and raw["evidence_sufficiency"] == .12
assert raw["evidence_status"] == "assessed"
for value in (float("nan"), float("inf"), True, -1, 5):
    invalid = deepcopy(response)
    invalid["answers"]["culture"]["score"] = value
    try:
        jev.validate(request, invalid)
    except ValueError:
        pass
    else:
        raise AssertionError("Invalid service score accepted")

http_client = httpx2.Client
status, body = 200, b'{"model":"invalid"}'
transport_error = None
calls = []

def dispatch(http):
    calls.append(http)
    assert str(http.url) == 'https://api.typesafe.ai/v1/systemone'
    assert json.loads(http.content) == request
    assert http.headers['authorization'] == 'Bearer test-key'
    if transport_error:
        raise transport_error('transport unavailable', request=http)
    return httpx2.Response(status, content=body)

def mock_client(**kwargs):
    return http_client(transport=httpx2.MockTransport(dispatch), **kwargs)

with tempfile.TemporaryDirectory() as directory, patch.object(jev.httpx2, 'Client', side_effect=mock_client):
    output = Path(directory)
    recorder = Recorder()
    evaluate = RunnableLambda(lambda _: jev.call("case", request, output, "test-key"))
    config = {'callbacks': [recorder], 'run_name': 'score'}
    assert evaluate.invoke({}, config)["status"] == "failed"
    assert len(calls) == 2 and not (output / "case.json").exists()
    assert len(recorder.calls) == 2 and recorder.errors == ['TypeSafeAPIResponseValidationError'] * 2
    assert all(c['parent_run_id'] is not None for c in recorder.calls)
    before = (output / "case.attempt-1.raw.txt").read_bytes()

    body = json.dumps(response).encode()
    result = evaluate.invoke({}, config)
    assert result["status"] == "scored" and len(result["attempts"]) == 3
    assert (output / "case.attempt-1.raw.txt").read_bytes() == before
    assert (output / "case.attempt-3.raw.txt").exists()
    assert evaluate.invoke({}, config) == result
    assert len(recorder.calls) == 3 and len(recorder.results) == 1
    assert json.loads(recorder.results[0].generations[0][0].text) == response
    assert recorder.results[0].llm_output['token_usage'] == {'prompt_tokens': 120, 'completion_tokens': 8}
    changed = deepcopy(request)
    changed["state"]["evidence"]["different"] = True
    try:
        jev.call("case", changed, output, "test-key")
    except ValueError:
        pass
    else:
        raise AssertionError("Changed request reused")

    status, body = 529, b'service unavailable'
    before_calls = len(calls)
    failure = jev.call("unavailable", request, output, "test-key")
    assert failure["status"] == "failed" and len(failure["attempts"]) == 2
    assert (output / "unavailable.attempt-1.raw.txt").read_bytes() == b"service unavailable"
    assert len(calls) == before_calls + 2
    status, body = 401, b'unauthorized'
    failure = jev.call('unauthorized', request, output, 'test-key')
    assert len(failure['attempts']) == 1 and failure['attempts'][0]['http_status'] == 401
    transport_error = httpx2.ReadTimeout
    before_calls = len(calls)
    failure = jev.call('timeout', request, output, 'test-key')
    assert len(calls) == before_calls + 2 and len(failure['attempts']) == 2
    assert failure['attempts'][0]['error'] == 'TypeSafeAPITimeoutError'
    assert not (output / 'timeout.json').exists()

print("PASS: four independent rubric questions, raw decimals/confidence, finite validation, bounded retries and retained failures")

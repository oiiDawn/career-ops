"""Check uncapped summary accounting, lossless input batching and retained failure attempts offline."""
import json
import math
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from career_ops.evaluation import company_pipeline as c
from langchain_core.messages import AIMessage
import httpx
from openai import InternalServerError

adaptive = c.research_adapter()
encoder = adaptive.tiktoken.get_encoding('cl100k_base')
public = {'company_id': 'summary-test', 'name': 'Sample', 'identity_url': 'https://sample.test',
          'seed_urls': [], 'scopes': [{'dimension': 'culture', 'scope': {'region': 'China'}}]}
source = {'source_id': 'source', 'url': 'https://sample.test/policy',
          'source_header': '2026 China employee policy', 'text': 'Leave policy; actual hours unknown.'}
bindings, dispatched = [], []
behavior = None
expected_deadline = None


def answer(messages, finish='stop', invalid=False, realistic_usage=False):
    payload = json.loads(messages[1].content)
    text = json.dumps({'profiles': [{'profile_id': p['profile_id'], 'facts': [{
        'claim': 'Policy exists; actual execution unknown', 'date': '2026', 'kind': 'official policy',
        'applicability': 'China', 'limitations': 'No actual-hours proof', 'source_id': 'source'}],
        'gaps': ['Actual hours unknown'], 'conflicts': []} for p in payload['profiles']]})
    if invalid:
        text = '{"profiles":'
    inputs = len(encoder.encode(json.dumps([m.model_dump() for m in messages], ensure_ascii=False), disallowed_special=()))
    total = inputs+1000 if realistic_usage else 100
    return AIMessage(content=text, response_metadata={'finish_reason': finish},
                     usage_metadata={'input_tokens': total-20, 'output_tokens': 20, 'total_tokens': total})


class Model:
    def bind(self, **parameters):
        bindings.append(parameters)
        assert parameters['reasoning_effort'] == 'low' and 0 < parameters['max_tokens'] <= adaptive.llm.MAX_OUTPUT_TOKENS
        return self

    def invoke(self, messages, config):
        if expected_deadline is not None:
            assert adaptive.llm.DEADLINE.get() == expected_deadline
        dispatched.append(messages)
        return behavior(messages, len(dispatched))


adaptive.llm.chat_model = Model
with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    def run(name, sources=None):
        bindings.clear()
        dispatched.clear()
        return c.summarize_company(public, sources or [source], root/name)

    behavior = lambda messages,n: answer(messages, finish='length' if n == 1 else 'stop')
    expected_deadline = time.monotonic()+100
    token = adaptive.llm.DEADLINE.set(expected_deadline)
    try:
        result = run('length')
        assert adaptive.llm.DEADLINE.get() == expected_deadline
    finally:
        adaptive.llm.DEADLINE.reset(token)
        expected_deadline = None
    assert result['status'] == 'summarized' and len(result['calls']) == 2
    assert result['repair_used'] and result['tokens_accounted'] == 200
    assert (root/'length/call-1.response.json').exists() and (root/'length/call-2.request.json').exists()

    def typed_repair(messages, n):
        reply = answer(messages)
        if n == 1:
            body = json.loads(reply.content)
            body['profiles'][0]['facts'][0]['date'] = None
            reply.content = json.dumps(body)
        else:
            assert 'date must be a nonempty string' in messages[-1].content
        return reply
    behavior = typed_repair
    result = run('typed-repair')
    assert result['status'] == 'summarized' and result['repair_used'] and len(result['calls']) == 2
    diagnostic = json.loads((root/'typed-repair/validation-1.json').read_text())
    assert 'date must be a nonempty string' in diagnostic['error']

    behavior = lambda messages,n: answer(messages, invalid=True)
    result = run('invalid')
    assert result['status'] == 'failed' and len(result['calls']) == 2 and result['tokens_accounted'] == 200

    class LengthFinishReasonError(Exception):
        def __init__(self):
            self.completion = SimpleNamespace(model_dump=lambda: {'usage': {'total_tokens': 500}, 'choices': []})
    def length_exception(messages, n):
        if n == 1:
            raise LengthFinishReasonError()
        return answer(messages)
    behavior = length_exception
    result = run('completion')
    assert result['status'] == 'summarized' and result['tokens_accounted'] == 600
    assert json.loads((root/'completion/call-1.failure.json').read_text())['completion']['usage']['total_tokens'] == 500

    def transient(messages, n):
        if n == 1:
            response = httpx.Response(503, request=httpx.Request('POST', 'https://offline.test'))
            raise InternalServerError('offline transient', response=response, body={'error': 'temporary'})
        return answer(messages)
    behavior = transient
    result = run('transient')
    assert result['status'] == 'summarized' and len(result['calls']) == 2
    assert result['calls'][0]['status'] == 'failed_usage_unknown'
    assert result['tokens_accounted'] == result['calls'][0]['tokens_reserved']+100
    assert (root/'transient/call-1.failure.json').exists()
    unit = '本地员工制度与实际工作时长不同。Scope and date remain explicit.\n'
    body = unit*(60_000//len(encoder.encode(unit)))
    large = {**source, 'text': body}
    behavior = lambda messages,n: answer(messages, realistic_usage=True)
    result = run('batched', [large])
    assert result['status'] == 'summarized' and result['tokens_accounted'] > 50_000
    batches = [json.loads(messages[1].content)['sources'] for messages in dispatched
               if 'sources' in json.loads(messages[1].content)]
    assert len(batches) > 1 and ''.join(s['text'] for group in batches for s in group) == body
    assert any(call['stage'] == 'merge' for call in result['calls'])
    assert all(call['input_tokens_estimated'] <= 16_000 for call in result['calls'] if call['stage'] == 'batch')
    assert all((root/'batched'/f'call-{call["index"]}.request.json').exists() and
               (root/'batched'/f'call-{call["index"]}.response.json').exists() for call in result['calls'])

    def expensive(messages, n):
        reply = answer(messages)
        reply.usage_metadata = {'input_tokens': 200000, 'output_tokens': 20, 'total_tokens': 200020}
        return reply
    behavior = expensive
    result = run('uncapped', [large])
    assert result['status'] == 'summarized' and result['tokens_accounted'] > 200000

    behavior = lambda messages,n: answer(messages, finish='length' if n in (1,3) else 'stop')
    result = run('single-repair-across-batches', [large])
    assert result['status'] == 'failed' and len(result['calls']) == 3 and result['repair_used']
print('summary batching, uncapped accounting, length/JSON repair and transient checks passed')

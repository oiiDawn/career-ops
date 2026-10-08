"""Exercise public company collection, cited LLM summaries, persisted scope reuse and unusable-JSON handling offline."""
from copy import deepcopy
from datetime import date
import importlib.util
import json
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('pipeline', ROOT/'scripts/experiments/company-score.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
a = c.research_adapter()
c.research_adapter = lambda: a
from langchain_core.messages import AIMessage

scopes = {'company': {'region': 'global'}, 'culture': {'region': 'China'},
          'compensation': {'region': 'China', 'level': 'SDE2', 'role_family': 'software_engineering',
                           'currency': 'CNY', 'basis': 'annual_total'}}
company = {'company_id': 'sample', 'name': 'Sample Inc.', 'identity_url': 'https://sample.test',
           'valid_until': '2026-10-15', 'scopes': [{'dimension': d, 'scope': s} for d,s in scopes.items()],
           'seed_urls': ['https://sample.test/facts']}
job = {'id': '1', 'company_id': 'sample', 'posting': {'company': 'Sample', 'role': 'Engineer',
       'url': 'https://sample.test/job/1', 'jd': 'Build agents.'}, 'scopes': scopes}
other = deepcopy(job)
other['id'] = '2'
other['posting']['jd'] = 'Build backend products.'
value = {'companies': [company], 'jobs': [job, other]}
body = 'Operating investment completed; annual leave policy; annual pay CNY 500000.\n\n' + 'Public context. ' * 500
model_calls, network_calls, scores, bindings = [], [], [], []
invalid_summary = False


class Model:
    def bind_tools(self, *args, **kwargs): return self
    def bind(self, **kwargs):
        bindings.append(kwargs)
        return self


def invoke(prepare, messages, name):
    prepare(Model())
    model_calls.append(name)
    if name == 'isolated-company-summary':
        data = json.loads(messages[1].content)
        assert 'standards' not in data and 'posting' not in data and '350000' not in messages[0].content
        source = data['sources'][0]
        answer = {'profiles': [{'profile_id': item['profile_id'], 'facts': [{'claim': 'Sample public fact',
            'source_id': source['source_id'], 'source_url': source['url'], 'date': '2026-10-08',
            'kind': 'official promise', 'applicability': 'Declared scope; execution unknown',
            'limitations': 'Does not establish offer or team execution'}], 'gaps': ['Team execution unknown'],
            'conflicts': []} for item in data['profiles']]}
        if invalid_summary: answer = {'profiles': 'unusable JSON structure'}
        text = json.dumps(answer)
        calls = []
    elif len(messages) == 2:
        text = ''
        calls = [{'name': 'web_extract', 'args': {'urls': ['https://sample.test/facts'],
                  'terms': ['Operating', 'annual']}, 'id': 'extract', 'type': 'tool_call'}]
    else:
        text = '{"facts":[],"gaps":"Research output is not the separate summary"}'
        calls = []
    return AIMessage(content=text, tool_calls=calls, usage_metadata={'input_tokens': 20, 'output_tokens': 20, 'total_tokens': 40})


def tavily(endpoint, payload):
    network_calls.append((endpoint, payload))
    return {'results': [{'url': 'https://sample.test/facts', 'raw_content': body}], 'usage': {'credits': 1}}


def score(name, request, output, key):
    cached = output/(name+'.json')
    if cached.exists(): return json.loads(cached.read_text())
    scores.append(request)
    response = {'model': c.jev.MODEL, 'answers': {}}
    for name,q in request['questions'].items():
        response['answers'][name] = {'type': 'noul', 'noul': .2} if q['type'] == 'noul' else {
            'type': 'score', 'score': 2.37, 'confidence': .91, 'probabilities': {'0': 0,'1': 0,'2': .63,'3': .37,'4': 0}}
    c.jev.validate(request, response)
    return {'status': 'scored', 'request_sha256': c.jev.digest(request), 'response': response,
            'attempts': [{'http_status': 200}], 'elapsed_seconds': .1}


a.llm.invoke, a.tavily, c.jev.call = invoke, tavily, score
rubric = c.jev.RUBRIC.read_text()
with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    def run(name, supplied=value, today=date(2026,10,8)):
        output = root/name
        output.mkdir()
        prepared = c.prepare_companies(supplied, root/'store', output, today=today)
        return c.evaluate(prepared, rubric, root/'store', output/'scores', 'test-key', today)
    cold = run('cold')
    assert len(network_calls) == 1 and model_calls.count('isolated-company-summary') == 1
    assert any(b.get('reasoning_effort') == 'low' and b.get('response_format') == {'type': 'json_object'} for b in bindings)
    assert len(scores) == 3 and len(cold['companies']['sample']['profiles']) == 3
    captures = list((root/'store/sample/evidence').glob('capture-*/ledger.json'))
    ledger = json.loads(captures[0].read_text())
    assert ledger['token_budget'] == 100000 and ledger['dispatch_deadline_seconds'] == 570
    assert ledger['sources'][0]['characters'] > 4000
    before = len(model_calls), len(network_calls), len(scores)
    warm = run('warm')
    assert (len(model_calls),len(network_calls),len(scores)) == before
    assert warm['http_attempts'] == 0
    assert all(warm['jobs'][0]['dimensions'][d]['score'] == 3.37 for d in c.SHARED)
    changed = deepcopy(value)
    changed['jobs'][0]['posting']['jd'] = 'Different duties.'
    run('jd', changed)
    assert (len(model_calls),len(network_calls)) == before[:2] and len(scores) == before[2]+1
    assert set(scores[-1]['questions']) == {'direction','direction_evidence'}
    changed = deepcopy(value)
    changed['companies'][0]['scopes'].append({'dimension': 'culture', 'scope': {'region': 'Hong Kong'}})
    changed['jobs'][0]['scopes']['culture'] = {'region': 'Hong Kong'}
    count = len(scores)
    revised = run('new-scope', changed)
    assert len(network_calls) == 2 and len(scores) == count+1
    assert len(scores[-1]['questions']) == 2
    assert all(p['scope'] == {'region': 'Hong Kong'} for p in scores[-1]['state']['evidence']['profiles'].values())
    assert revised['jobs'][1]['dimensions']['culture'] == cold['jobs'][1]['dimensions']['culture']
    c.SUMMARY_SYSTEM += '\nNew public organization rule.'
    count = len(network_calls)
    run('summary-rule-change')
    assert len(network_calls) == count
    rubric += '\nChanged scoring standard.'
    count = len(model_calls)
    run('scoring-rule-change')
    assert len(model_calls) == count
    changed = deepcopy(value)
    changed['companies'][0]['valid_until'] = '2026-10-25'
    run('expired', changed, date(2026,10,16))
    assert len(network_calls) == 3
    invalid_summary = True
    changed = deepcopy(value)
    changed['companies'][0]['company_id'] = 'bad-summary'
    for j in changed['jobs']: j['company_id'] = 'bad-summary'
    failed = run('invalid', changed)
    assert failed['companies']['bad-summary']['profiles'] == {}
    assert failed['jobs'][0]['dimensions']['company']['status'] == 'pending'
    assert not any(r['state']['evidence'].get('company',{}).get('company_id') == 'bad-summary' for r in scores)
    count = len(network_calls)
    run('invalid-repeat', changed)
    assert len(network_calls) == count
    try: c.summary_profiles({'profiles': [{'profile_id':'unknown','facts':[],'gaps':[],'conflicts':[]}]}, company['scopes'])
    except ValueError: pass
    else: raise AssertionError('Undeclared scope accepted')
print('company collection/summary/persistence/reuse and invalid summary/scope checks passed')

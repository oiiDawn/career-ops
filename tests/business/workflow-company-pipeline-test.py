"""Exercise public company collection, cited LLM summaries, persisted scope reuse and unusable-JSON handling offline."""
from copy import deepcopy
from datetime import date
import importlib.util
import json
from pathlib import Path
import threading
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from career_ops.evaluation import company_pipeline as c
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
company['scopes'].append({'dimension':'compensation', 'scope':{**scopes['compensation'],'region':'Suzhou'}})
value = {'companies': [company], 'jobs': [job, other]}
body = '# Sample public evidence\n2026-10-08\nOperating investment completed; annual leave policy; annual pay CNY 500000.\n\n' + 'Public context. ' * 500
model_calls, network_calls, scores, bindings = [], [], [], []
invalid_summary = False
invalid_summary_dimension = None
ready_check = False
score_failed_dimension = None
culture_scored = threading.Event()
summary_dimensions = []
summary_groups = []


class Model:
    def bind_tools(self, *args, **kwargs): return self
    def bind(self, **kwargs):
        bindings.append(kwargs)
        return self




def invoke(prepare, messages, name):
    prepare(Model())
    model_calls.append(name)
    if name in ('isolated-company-summary', 'isolated-source-summary'):
        data = json.loads(messages[1].content)
        assert 'standards' not in data and 'posting' not in data and '350000' not in messages[0].content
        dimension = data['profiles'][0]['dimension']
        assert all(p['dimension'] == dimension for p in data['profiles'])
        assert 'Organize only '+dimension in messages[0].content
        if name == 'isolated-company-summary': summary_dimensions.append(dimension)
        if ready_check and dimension == 'company' and name == 'isolated-company-summary':
            assert culture_scored.wait(3), 'Company summary blocked culture independent scoring'
        source = data['sources'][0]
        assert '2026-10-08' in source['source_header'] or source.get('material_kind') == 'document_fact_cards'
        answer = {'profiles': [{'profile_id': item['profile_id'], 'facts': [{'claim': 'Sample public fact',
            'source_id': source['source_id'], 'source_url': source['url'], 'date': '2026-10-08',
            'kind': 'official promise', 'applicability': 'Declared scope; execution unknown',
            'limitations': 'Does not establish offer or team execution'}], 'gaps': ['Team execution unknown'],
            'conflicts': []} for item in data['profiles']]}
        if invalid_summary or dimension == invalid_summary_dimension: answer = {'profiles': 'unusable JSON structure'}
        text = json.dumps(answer)
        calls = []
    elif len(messages) == 2:
        dimension = json.loads(messages[1].content)['public_company_and_scopes']['scopes'][0]['dimension']
        assert 'Research only the '+dimension in messages[0].content
        assert 'quotation offsets' in messages[0].content and 'exact contiguous' not in messages[0].content
        text = ''
        calls = [{'name': 'web_extract', 'args': {'urls': ['https://sample.test/facts']}, 'id': 'extract', 'type': 'tool_call'}]
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
    if score_failed_dimension and any(p['dimension'] == score_failed_dimension for p in request['state']['evidence'].get('profiles',{}).values()):
        return {'status':'failed','attempts':[{'http_status':503}],'elapsed_seconds':.1}
    if any(p['dimension'] == 'culture' for p in request['state']['evidence'].get('profiles',{}).values()):
        culture_scored.set()
    response = {'model': c.jev.MODEL, 'answers': {}}
    for name,q in request['questions'].items():
        response['answers'][name] = {'type': 'noul', 'noul': .2} if q['type'] == 'noul' else {
            'type': 'score', 'score': 2.37, 'confidence': .91, 'probabilities': {'0': 0,'1': 0,'2': .63,'3': .37,'4': 0}}
    c.jev.validate(request, response)
    return {'status': 'scored', 'request_sha256': c.jev.digest(request), 'response': response,
            'attempts': [{'http_status': 200}], 'elapsed_seconds': .1}


original_summary = c.summarize_company

def summary_with_tracking(public, sources, output, **kwargs):
    if not kwargs.get('document'): summary_groups.append(public['scopes'][0]['dimension'])
    return original_summary(public, sources, output, **kwargs)

c.summarize_company = summary_with_tracking
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
    assert len(network_calls) == 3 and model_calls.count('isolated-company-summary') == 3
    assert set(summary_dimensions) == set(c.SHARED) and summary_dimensions.count('compensation') == 1
    assert set(summary_groups) == set(c.SHARED)
    assert any(b.get('reasoning_effort') == 'low' and b.get('response_format') == {'type': 'json_object'} for b in bindings)
    assert len(scores) == 5 and len(cold['companies']['sample']['profiles']) == 4
    captures = list((root/'store/sample/evidence').glob('capture-*/ledger.json'))
    assert len(captures) == 3
    ledger = json.loads(captures[0].read_text())
    assert all(json.loads(p.read_text())['token_budget'] is None for p in captures)
    assert ledger['engine'] == a.ENGINE and ledger['credit_budget'] == 60
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
    assert len(network_calls) == 4 and len(scores) == count+1
    assert len(scores[-1]['questions']) == 2
    assert all(p['scope'] == {'region': 'Hong Kong'} for p in scores[-1]['state']['evidence']['profiles'].values())
    assert revised['jobs'][1]['dimensions']['culture'] == cold['jobs'][1]['dimensions']['culture']
    expanded = deepcopy(value)
    expanded['companies'][0]['scopes'].append({'dimension':'compensation',
        'scope':{**scopes['compensation'], 'region':'Beijing'}})
    run('comp-scope', expanded)
    c.SUMMARY_SYSTEM += '\nNew public organization rule.'
    summary_groups.clear()
    count = len(network_calls)
    run('summary-rule-change', expanded)
    assert len(network_calls) == count
    assert summary_groups.count('compensation') == 2
    rubric += '\nChanged scoring standard.'
    count = len(model_calls)
    run('scoring-rule-change')
    assert len(model_calls) == count
    changed = deepcopy(value)
    changed['companies'][0]['valid_until'] = '2026-10-25'
    count = len(network_calls)
    run('expired', changed, date(2026,10,16))
    assert len(network_calls) == count+3
    culture_scored.clear()
    ready_check = True
    supplied = deepcopy(value)
    supplied['companies'][0]['company_id'] = 'ready'
    for j in supplied['jobs']: j['company_id'] = 'ready'
    output = root/'ready'
    output.mkdir()
    def ready(company, dimension):
        return c.evaluate({'companies':[company],'jobs':[]}, rubric,
                          root/(company['company_id']+'-store'), output/dimension, 'test-key')
    prepared = c.prepare_companies(supplied, root/'ready-store', output, dimension_ready=ready)
    assert culture_scored.is_set()
    count = len(scores)
    aggregate = c.evaluate(prepared, rubric, root/'ready-store', output/'aggregate', 'test-key', reuse_company_scores=True)
    assert len(scores) == count+2 and aggregate['http_attempts'] == 2
    assert sum(call['http_attempts'] for call in json.loads((output/'dimension-scoring.json').read_text())) == 3
    ready_check = False
    score_failed_dimension = 'culture'
    supplied['companies'][0]['company_id'] = 'failed-score'
    for j in supplied['jobs']: j['company_id'] = 'failed-score'
    output = root/'failed-score'
    output.mkdir()
    prepared = c.prepare_companies(supplied, root/'failed-score-store', output, dimension_ready=ready)
    count = len(scores)
    aggregate = c.evaluate(prepared, rubric, root/'failed-score-store', output/'aggregate', 'test-key', reuse_company_scores=True)
    assert len(scores) == count+2 and aggregate['companies']['failed-score']['status'] == 'partial'
    assert aggregate['jobs'][0]['dimensions']['culture']['status'] == 'pending'
    assert len([x for x in json.loads((output/'dimension-scoring.json').read_text()) if x['status']=='failed']) == 1
    score_failed_dimension = None
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
    invalid_summary = False
    invalid_summary_dimension = 'company'
    with tempfile.TemporaryDirectory(dir=ROOT/'data/experiments') as main_temp:
        main_root = Path(main_temp)
        c.jev.save(main_root/'input.json', value)
        original_argv = sys.argv
        c.jev.dotenv_values = lambda path: {'TYPESAFE_API_KEY':'test-key'}
        sys.argv = ['company-score','--input',str(main_root/'input.json'),
                    '--store',str(main_root/'store'),'--output',str(main_root/'cold')]
        try:
            c.main()
        finally:
            sys.argv = original_argv
        aggregate = json.loads((main_root/'cold/scores/results.json').read_text())
        assert aggregate['companies']['sample']['status'] == 'partial'
        assert aggregate['jobs'][0]['dimensions']['company']['status'] == 'pending'
        assert aggregate['new_api_calls'] == 4 and aggregate['http_attempts'] == 4
        assert not any(call['unit'].endswith('-company') for call in aggregate['calls'])
    invalid_summary_dimension = None
    try: c.summary_profiles({'profiles': [{'profile_id':'unknown','facts':[],'gaps':[],'conflicts':[]}]}, company['scopes'])
    except ValueError: pass
    else: raise AssertionError('Undeclared scope accepted')
print('company collection/summary/persistence/reuse and invalid summary/scope checks passed')

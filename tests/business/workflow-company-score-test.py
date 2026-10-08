"""Check company reuse, scoped applicability, revision invalidation and independent job direction without a network."""
from copy import deepcopy
from datetime import date
import importlib.util
import json
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[2]
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from career_ops.evaluation import company_pipeline as c
scope = {'company': {'region': 'global'}, 'culture': {'region': 'China'},
         'compensation': {'region': 'Shanghai', 'level': 'SDE2', 'role_family': 'software_engineering',
                          'currency': 'CNY', 'basis': 'annual_total'}}
company = {'company_id': 'sample', 'name': 'Sample Inc.', 'identity_url': 'https://sample.test',
           'valid_until': '2026-10-15', 'profiles': [{'dimension': d, 'scope': s,
                'evidence': {'sources': [{'url': 'https://sample.test/facts', 'text': d + ' facts'}]}}
                for d,s in scope.items()]}
job = {'id': '1', 'company_id': 'sample', 'posting': {'company': 'Sample', 'role': 'Agent engineer',
       'url': 'https://sample.test/job/1', 'jd': 'Build Agent products.'}, 'scopes': scope}
other = deepcopy(job)
other['id'] = '2'
other['posting']['url'] += '2'
other['posting']['jd'] = 'Maintain backend products.'
bundle = {'companies': [company], 'jobs': [job, other]}
sent = []


def reply(name, request, output, key):
    cached = output / (name + '.json')
    if cached.exists():
        result = json.loads(cached.read_text())
        assert result['request_sha256'] == c.jev.digest(request)
        c.jev.validate(request, result['response'])
        return result
    sent.append(deepcopy(request))
    response = {'model': c.jev.MODEL, 'answers': {}}
    for name,q in request['questions'].items():
        response['answers'][name] = ({'type':'noul', 'noul':.23} if q['type']=='noul' else
            {'type':'score','score':2.37,'confidence':.91,
             'probabilities':{'0':0,'1':0,'2':.63,'3':.37,'4':0}})
    c.jev.validate(request, response)
    return {'status':'scored','request_sha256':c.jev.digest(request), 'response':response,
            'attempts':[{'http_status':200}], 'elapsed_seconds':.1}


c.jev.call = reply
rubric = c.jev.RUBRIC.read_text()
repeated = deepcopy(company)
repeated['profiles'][1]['evidence']['sources'] = repeated['profiles'][0]['evidence']['sources']
request = c.company_request(repeated, rubric)
assert len(request['state']['evidence']['sources']) == 2
assert len({tuple(p['evidence']['source_refs']) for p in request['state']['evidence']['profiles'].values()}) == 2
with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    def run(name, value=bundle, today=date(2026,10,8)):
        return c.evaluate(value, rubric, root/'store', root/name, 'test-key', today)
    result = run('first')
    assert result['new_api_calls'] == 5 and len(sent) == 5
    assert all('posting' not in r['state']['evidence'] for r in sent[:3])
    assert all(len({p['dimension'] for p in r['state']['evidence']['profiles'].values()}) == 1 for r in sent[:3])
    assert all(set(r['questions']) == {'direction','direction_evidence'} for r in sent[3:])
    assert result['jobs'][0]['company_profiles'] == result['jobs'][1]['company_profiles']
    assert result['jobs'][0]['dimensions']['culture'] == result['jobs'][1]['dimensions']['culture']
    assert result['jobs'][0]['dimensions']['culture']['score'] == 3.37
    result = run('repeat')
    assert result['new_api_calls'] == 0 and result['cached_api_calls'] == 5
    assert result['http_attempts'] == 0 and len(sent) == 5
    incomplete = deepcopy(bundle)
    incomplete['companies'][0]['profiles'][1]['evidence']['new_fact'] = 'not yet scored'
    partial = c.evaluate(incomplete, rubric, root/'store', root/'aggregation-only', 'test-key', reuse_company_scores=True)
    assert partial['companies']['sample']['status'] == 'partial'
    assert partial['http_attempts'] == 0 and partial['jobs'][0]['dimensions']['culture']['status'] == 'pending'
    changed = deepcopy(bundle)
    changed['companies'][0]['profiles'][1]['evidence']['new_fact'] = 'changed actual evidence'
    result = run('new-evidence', changed)
    assert result['new_api_calls'] == 1 and result['cached_api_calls'] == 4
    changed = deepcopy(bundle)
    changed['jobs'][1]['posting']['jd'] = 'Changed job responsibility.'
    result = run('new-jd', changed)
    assert result['new_api_calls'] == 1 and result['cached_api_calls'] == 4
    changed = deepcopy(bundle)
    changed['jobs'][1]['scopes']['culture']['region'] = 'Hong Kong'
    changed['jobs'][1]['scopes']['compensation']['level'] = 'Senior'
    result = run('wrong-scope', changed)
    assert result['jobs'][1]['dimensions']['culture']['status'] == 'pending'
    assert result['jobs'][1]['dimensions']['compensation']['status'] == 'pending'
    result = run('expired', today=date(2026,10,16))
    assert result['jobs'][0]['dimensions']['culture']['reason'] == 'expired_company_profile'
    assert 'direction' in result['jobs'][0]['dimensions']
    changed = deepcopy(bundle)
    changed['jobs'][0]['compensation_quote'] = {'scope': scope['compensation'],
                 'evidence': {'url':'https://sample.test/job/1', 'text':'Annual quote CNY 400K'}}
    result = run('quote', changed)
    assert result['new_api_calls'] == 1
    assert result['jobs'][0]['company_profiles']['compensation']['source'] == 'explicit_job_quotation'
    try:
        run('overwrite')
        run('overwrite')
    except FileExistsError:
        pass
    else:
        raise AssertionError('Immutable run overwritten')
print('company profile reuse and scope checks passed')

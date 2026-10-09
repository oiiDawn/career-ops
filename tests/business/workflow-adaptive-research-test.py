"""Check isolated research preserves full bodies and enforces resources before provider dispatch."""
import importlib.util
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import tempfile

root = Path(__file__).resolve().parents[2]
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from career_ops.evaluation import adaptive_research as a
public_company = {'company_id':'sample', 'name':'Sample', 'identity_url':'https://example.test',
                  'scopes':[{'dimension':'compensation', 'scope':{'region':'China','level':'SDE2','role_family':'software_engineering','currency':'CNY','basis':'annual_total'}}],
                  'seed_urls':['https://example.test/pay']}
prompt = a.company_prompt(public_company)
assert 'research_unit' in prompt and 'company' in prompt
assert '350K' not in prompt and '720K' not in prompt and '候选' not in prompt
public_company['scopes'][0]['scope']['personal_floor'] = 'private value'
try:
    a.company_prompt(public_company)
except ValueError:
    pass
else:
    raise AssertionError('Private preferences accepted in company research')
with tempfile.TemporaryDirectory() as temp:
    r = a.Research(Path(temp) / 'run')
    body = 'Menu\n\n' + 'x' * 4500 + '\n\n## Paid leave\nAnnual leave 20 days\n\n' + 'z' * 22000
    sid, frozen = r.freeze({'url': 'https://example.test/benefits', 'raw_content': body})
    assert frozen == body and (r.output / 'bodies' / (sid + '.txt')).read_text() == body
    assert r.sources[sid]['sha256'] == a.sha(body)
    tools = {t.name: t for t in r.tools()}
    calls = []
    a.tavily = lambda endpoint,payload: calls.append((endpoint,payload)) or {'results': [], 'usage': {'credits': 1}}
    for i in range(7):
        tools['collect_facts'].invoke({'query': 'company fact ' + str(i)})
    for i in range(2):
        tools['collect_facts'].invoke({'urls': ['https://example.test/' + str(i)]})
    assert len(calls) == 9 and r.credits == 9
    tools['collect_facts'].invoke({'query': 'COMPANY  fact 0'})
    tools['collect_facts'].invoke({'urls': ['https://example.test/0']})
    assert len(calls) == 9 and r.credits == 9
    a.tavily = lambda endpoint,payload: calls.append((endpoint,payload)) or {'failed_results': [{'url':u,'error':'403'} for u in payload['urls']]}
    for _ in range(2):
        tools['collect_facts'].invoke({'urls': ['https://blocked.test']})
    assert len(calls) == 10 and r.credits == 10
    r.credits = a.CREDIT_BUDGET - 1
    response = json.loads(tools['collect_facts'].invoke({'urls': ['https://a.test', 'https://b.test']}))
    assert response['operational_status']=='credit_budget_exhausted' and len(calls) == 10
    a.tavily = lambda endpoint,payload: calls.append((endpoint,payload)) or {'results': [], 'usage': {'credits': 1}}
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(lambda query: tools['collect_facts'].invoke({'query':query}), ['last credit one','last credit two']))
    assert len(calls) == 11 and r.credits == a.CREDIT_BUDGET
    assert sum('operational_status' not in json.loads(value) for value in results) == 1
    assert json.loads((r.output/'ledger.json').read_text())['credit_budget'] == 60
    handed = r.retrieved_evidence()
    assert not handed['retrieved_sources']
    assert handed['research_status'] == 'partial'
    r.stop = 'model_finished'
    (r.output / 'answer.txt').write_text('{"sources":[],"gaps":["unknown"]}')
    assert r.retrieved_evidence()['overview']['gaps'] == ['unknown']
    assert r.retrieved_evidence()['research_status'] == 'completed'
print('adaptive research checks passed')

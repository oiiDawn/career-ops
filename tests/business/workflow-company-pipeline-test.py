"""Verify scoped Codex fact reuse, empty evidence and failure recovery without network calls."""
from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from career_ops.evaluation import company_pipeline as c

scopes = [{'dimension': d, 'scope': {'region': 'China', **({'level':'unknown',
    'role_family':'software_engineering','currency':'CNY','basis':'annual_total'} if d=='compensation' else {})}}
    for d in c.SHARED]
company = {'company_id':'sample','name':'Sample','identity_url':'https://sample.test/',
           'scopes':scopes,'seed_urls':[],'valid_until':'2026-10-11'}
value = {'companies':[company], 'jobs':[]}
calls = []
empty = False

def research(public, postings, output):
    calls.append(deepcopy(public))
    output.mkdir(parents=True)
    c.jev.save(output/'result.json', {'status':'researched','usage':[]})
    return {'profiles':[{'profile_id':c.scope_key(p['dimension'],p['scope']), 'facts':[] if empty else [{
        'claim':'Public reference', 'date':'unknown', 'kind':'employer_statement',
        'applicability':'Global policy; local applicability uncertain', 'limitations':'Not proof of execution',
        'source_url':'https://sample.test/policy'}], 'gaps':[], 'conflicts':[]} for p in public['scopes']]}

with tempfile.TemporaryDirectory() as directory, patch.object(c.research,'run',research):
    root=Path(directory)
    def run(name, data=value, refresh=False, today=date(2026,10,9)):
        output=root/name
        output.mkdir()
        return c.prepare_companies(data,root/'store',output,refresh,today)
    first=run('cold')
    assert len(calls)==1 and len(calls[0]['scopes'])==3
    assert len(first['companies'][0]['profiles'])==3
    assert run('warm')==first and len(calls)==1
    changed=deepcopy(value)
    changed['companies'][0]['scopes'].append({'dimension':'culture','scope':{'region':'Hong Kong'}})
    result=run('new-scope',changed)
    assert len(calls)==2 and len(calls[-1]['scopes'])==1 and len(result['companies'][0]['profiles'])==4
    extended=deepcopy(value)
    extended['companies'][0]['valid_until']='2026-10-18'
    assert run('same-week',extended)['companies'][0]['valid_until']=='2026-10-11'
    run('expired',extended,today=date(2026,10,12))
    assert len(calls)==3
    run('refresh',refresh=True)
    assert len(calls)==4
    with patch.object(c.research,'rule_digest',return_value='changed-rule'):
        run('new-rule')
    assert len(calls)==5
    with patch.object(c.research,'run',side_effect=RuntimeError('CLI failed')):
        try:run('failed',refresh=True)
        except RuntimeError:pass
        else:raise AssertionError('Research failure swallowed')
    empty=True
    result=run('empty',refresh=True)
    assert result['companies'][0]['profiles']==[]
    before=len(calls)
    assert run('empty-warm')['companies'][0]['profiles']==[] and len(calls)==before
    bad=deepcopy(value)
    bad['companies'][0]['cv']='private'
    try:c.validate_input(bad)
    except ValueError:pass
    else:raise AssertionError('Private company input accepted')
    try:c.summary_profiles({'profiles':[]},scopes)
    except ValueError:pass
    else:raise AssertionError('Missing profile accepted')
print('Codex company profiles: single task, scope cache, expiry, rule invalidation, empty facts and failures passed')

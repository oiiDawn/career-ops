"""Exercise the real subprocess boundary, public-only prompt, retained output and deadline cleanup offline."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from career_ops.evaluation import codex_research as r, company_pipeline as c

public = {'company_id':'sample','name':'Sample','identity_url':'https://sample.test/',
          'scopes':[{'dimension':'culture','scope':{'region':'China'}}], 'seed_urls':[]}
posting = {'url':'https://sample.test/job', 'jd':'Public duties', 'role':'Engineer',
           'cv':'PRIVATE-CV', 'profile':'PRIVATE-PREFERENCE'}
real_popen = subprocess.Popen
answer = {'profiles':[{'profile_id':c.scope_key('culture',{'region':'China'}), 'facts':[{
    'claim':'Public policy', 'date':'unknown', 'kind':'employer_statement', 'applicability':'Global reference',
    'limitations':'Team applicability uncertain', 'source_url':'https://sample.test/policy'}], 'gaps':[], 'conflicts':[]}]}

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    fake = root/'cli.py'
    fake.write_text('import json, pathlib, sys\np=pathlib.Path(sys.argv[1])\np.write_text(sys.argv[2])\nprint(json.dumps({"type":"turn.completed","usage":{"input_tokens":10,"output_tokens":5}}))\n')
    invalid = False
    timeout = False
    workdirs = []
    def spawn(command, **kwargs):
        workdirs.append(Path(command[command.index('-C')+1]))
        prompt = kwargs['stdin'].read()
        assert 'Public duties' in prompt and 'PRIVATE-CV' not in prompt and 'PRIVATE-PREFERENCE' not in prompt
        assert 'CAREER_OPS_LLM_API_KEY' not in kwargs['env'] and 'TYPESAFE_API_KEY' not in kwargs['env']
        assert '--ignore-user-config' in command and '--search' in command and 'read-only' in command
        if timeout:
            return real_popen([sys.executable,'-c','import time; time.sleep(60)'],**kwargs)
        return real_popen([sys.executable,str(fake),command[command.index('-o')+1],
                           '{"profiles":[]}' if invalid else json.dumps(answer)],**kwargs)
    with patch.object(r,'executable',return_value='codex'), patch.object(r.subprocess,'Popen',spawn), \
         patch.dict(os.environ,{'TYPESAFE_API_KEY':'PRIVATE-KEY','CAREER_OPS_LLM_API_KEY':'PRIVATE-KEY'}):
        result = r.run(public,[posting],root/'success')
        assert result==answer and not workdirs[-1].exists()
        metrics=json.loads((root/'success/result.json').read_text())
        assert metrics['status']=='researched' and metrics['usage'][0]['output_tokens']==5
        assert json.loads((root/'success/facts.json').read_text())==answer
        invalid=True
        try:r.run(public,[posting],root/'invalid')
        except ValueError:pass
        else:raise AssertionError('Invalid profile accepted')
        assert json.loads((root/'invalid/result.json').read_text())['status']=='failed'
        assert (root/'invalid/facts.json').exists()
        timeout=True
        with patch.object(r,'TIMEOUT_SECONDS',.1):
            try:r.run(public,[posting],root/'timeout')
            except subprocess.TimeoutExpired:pass
            else:raise AssertionError('Deadline not enforced')
        assert not workdirs[-1].exists()
        assert json.loads((root/'timeout/result.json').read_text())['error_type']=='TimeoutExpired'
print('Codex subprocess: public data, credential isolation, raw retention, schema validation and deadline passed')

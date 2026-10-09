"""Exercise immediate document compression, uncapped usage and recovery without repeated network or summary calls."""
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from career_ops.evaluation import adaptive_research as a
from langchain_core.messages import AIMessage, ToolMessage

public = {'company_id':'sample','name':'Sample','identity_url':'https://sample.test',
          'scopes':[{'dimension':'culture','scope':{'region':'China'}}],'seed_urls':[]}
network, models, digests = [], [], []
fail_once = True
body = '# Policy\nAnnual leave 20 days.\n\n' + 'BODY_ONLY_SENTINEL '*1000
class Model:
    def __init__(self): self.summary = False
    def bind_tools(self, tools, **kwargs): return self
    def bind(self, **kwargs):
        self.summary = 'response_format' in kwargs
        return self
    def invoke(self, messages, config):
        global fail_once
        models.append(messages)
        if self.summary:
            data = json.loads(messages[1].content)
            digests.append(data)
            answer = {'profiles':[{'profile_id':p['profile_id'], 'facts':[{
                'claim':'Annual leave policy is 20 days.', 'date':'unknown','kind':'official promise',
                'applicability':'China; execution unknown', 'limitations':'Team execution unknown',
                'source_id':data['sources'][0]['source_id']}], 'gaps':['Execution unknown'], 'conflicts':[]}
                for p in data['profiles']]}
            reply = AIMessage(content=json.dumps(answer))
        elif not any(isinstance(m, ToolMessage) for m in messages):
            reply = AIMessage(content='',tool_calls=[{'name':'collect_facts','args':{
                'urls':['https://sample.test/policy']},'id':'extract','type':'tool_call'}])
        elif fail_once:
            assert digests and all('BODY_ONLY_SENTINEL' not in m.content for m in messages)
            fail_once = False
            raise RuntimeError('interrupted after successful document compression')
        else:
            facts=json.loads(next(m.content for m in reversed(messages) if isinstance(m,ToolMessage)))['facts']
            reply = AIMessage(content=json.dumps({'profiles':[{'profile_id':p['profile_id'], 'facts':[{k:v for k,v in f.items() if k!='profile_id'} for f in facts if f['profile_id']==p['profile_id']], 'gaps':[], 'conflicts':[]} for p in json.loads(messages[1].content)['profiles']]}))
        reply.usage_metadata = {'input_tokens':210000,'output_tokens':10,'total_tokens':210010}
        return reply

def provider(endpoint, payload):
    network.append((endpoint,payload))
    return {'results':[{'url':'https://sample.test/policy','raw_content':body}],'usage':{'credits':1}}

with tempfile.TemporaryDirectory() as temp, patch.object(a.llm,'chat_model',Model),patch.object(a,'tavily',provider):
    path=Path(temp)/'research'
    first=a.Research(path)
    a.save(path/'company-input.json',public)
    first.run(a.company_prompt(public))
    assert first.stop=='failed_RuntimeError' and len(network)==1 and first.tokens>200000
    assert digests and 'BODY_ONLY_SENTINEL' in json.dumps(digests)
    assert all('BODY_ONLY_SENTINEL' not in m.content for m in first.messages)
    returned=json.loads(next(m for m in first.messages if isinstance(m,ToolMessage)).content)
    assert returned['facts'][0]['claim']=='Annual leave policy is 20 days.'
    assert len(list(path.glob('model-*.failure.json')))==1
    before_digests=len(digests)
    resumed=a.Research(path)
    resumed.run(a.company_prompt(public))
    assert resumed.stop=='model_finished' and len(network)==1 and len(digests)==before_digests
    source=resumed.retrieved_evidence()['retrieved_sources'][0]
    assert Path(source['full_body_local_path']).read_text()==body and 'sections' not in source
    tools={t.name:t for t in resumed.tools()}
    repeated=json.loads(tools['collect_facts'].invoke({'urls':['https://sample.test/policy']}))
    assert repeated['facts'] and len(network)==1 and len(digests)==before_digests
    before=len(models)
    complete=a.Research(path)
    complete.run(a.company_prompt(public))
    assert len(models)==before and json.loads((path/'ledger.json').read_text())['token_budget'] is None
print('document facts: immediate compression, full-body retention, uncapped usage and resume reuse passed')

from career_ops.evaluation import company_pipeline as c
with tempfile.TemporaryDirectory() as temp:
    researcher=a.Research(Path(temp)/'research')
    a.save(researcher.output/'company-input.json',public)
    sid,_=researcher.freeze({'url':'https://sample.test/policy','raw_content':body})
    saved=researcher.output/f'source-summary-{sid}-1'
    saved.mkdir()
    answer={'profiles':[{'profile_id':c.scope_key('culture',{'region':'China'}),
        'facts':[], 'gaps':['Execution unknown'],'conflicts':[]}]}
    a.save(saved/'result.json',{'status':'summarized','answer':answer,'tokens_accounted':123,'calls':[]})
    with patch.object(c,'summarize_source',side_effect=AssertionError('A durable successful digest must be reused')):
        assert researcher.source_facts(sid)['facts']==answer['profiles'] and researcher.tokens==123
    failed_sid,_=researcher.freeze({'url':'https://sample.test/failure','raw_content':body})
    with patch.object(c,'summarize_source',return_value={'status':'failed','tokens_accounted':456,'calls':[]}):
        try:
            researcher.source_facts(failed_sid)
        except RuntimeError:
            pass
        else:
            raise AssertionError('A failed digest must not expose the raw body to research')
    assert 'facts' not in researcher.sources[failed_sid] and researcher.tokens==579
    assert all(s['source_id']!=failed_sid for s in researcher.retrieved_evidence()['retrieved_sources'])
print('durable document digest reuse and failed-summary isolation passed')

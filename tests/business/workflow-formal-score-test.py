"""Exercise formal scoring, independent company reuse and checkpoint recovery through actual model nodes."""
import json
import fcntl
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from langchain_core.messages import AIMessage
from career_ops import model
from career_ops.db import BusinessStore
from career_ops.evaluation import adaptive_research as a, company_pipeline as c, score_graph as g

scopes = {'company': {'region':'global'}, 'culture': {'region':'China'}, 'compensation': {
    'region':'China:Suzhou', 'level':'SDE2', 'role_family':'software_engineering', 'currency':'CNY', 'basis':'annual_total'}}
model_calls, research_calls, jev_calls = [], [], []

class Model:
    def bind_tools(self, *args, **kwargs): return self
    def bind(self, **kwargs): return self




def invoke(prepare, messages, name):
    prepare(Model())
    research_calls.append(name)
    if name == 'isolated-source-summary':
        data = json.loads(messages[1].content)
        assert 'cv' not in data and 'standards' not in data
        source = data['sources'][0]
        answer = {'profiles': [{'profile_id': p['profile_id'], 'facts': [{'claim': 'Public employer fact',
            'date': 'unknown', 'kind': 'official policy', 'applicability': 'Declared scope only',
            'limitations': 'Execution unknown', 'source_ids': [source['source_id'], 'second-public-source']}], 'gaps':['Offer and team unknown'],
            'conflicts':[]} for p in data['profiles']]}
        return AIMessage(content=json.dumps(answer), usage_metadata={'input_tokens':20,'output_tokens':20,'total_tokens':40})
    calls = [] if len(messages)>2 else [{'name':'collect_facts','args':{'urls':['https://sample.test/policy']},'id':'read','type':'tool_call'}]
    data = json.loads(messages[1].content)
    facts = json.loads(messages[-1].content)['facts'] if not calls else []
    answer = {'profiles':[{'profile_id':p['profile_id'], 'facts':[{k:v for k,v in f.items() if k!='profile_id'} for f in facts if f['profile_id']==p['profile_id']], 'gaps':[], 'conflicts':[]} for p in data['profiles']]}
    return AIMessage(content='' if calls else json.dumps(answer), tool_calls=calls,
                     usage_metadata={'input_tokens':20,'output_tokens':20,'total_tokens':40})


def agent(phase, prompt):
    model_calls.append(phase)
    if phase == 'scope_plan':
        assert 'secret CV' not in prompt and 'personal_floor' not in prompt
        return {'identity_url':'https://sample.test/', 'scopes':scopes}, 'plan'
    assert phase == 'score_sections'
    return {n:'Grounded explanation; unknown facts remain unknown.' for n in (
        'overview','capabilities','compensation','questions','legitimacy','risks','checklist')}, 'sections'


def jev(name, request, output, key):
    jev_calls.append(request)
    assert 'secret CV' not in json.dumps(request)
    response = {'model':c.jev.MODEL,'answers':{}}
    for n,q in request['questions'].items():
        response['answers'][n] = {'type':'noul','noul':.2} if q['type']=='noul' else {
            'type':'score','score':2.37,'confidence':.9,'probabilities':{'0':0,'1':0,'2':.63,'3':.37,'4':0}}
    return {'status':'scored','response':response,'request_sha256':c.jev.digest(request),
            'attempts':[{'http_status':200}],'elapsed_seconds':.1}


def provider(endpoint,payload):
    return {'results':[{'url':'https://sample.test/policy','raw_content':'# Public policy\nPublic employer facts. '*50}],
            'usage':{'credits':1}}

with tempfile.TemporaryDirectory() as temp:
    root=Path(temp)
    jd={'opportunity_id':'1','url':'https://sample.test/jobs/1','company':'Sample','role':'Software Engineer II',
        'jd':'Build agent products. Grade SDE2. Suzhou, China.', 'captured_at':'2026-10-08',
        'liveness':'active','prescreen':{'status':'pass'}}
    values={'jd_report':jd,'cv':'secret CV','profile':'language: {output: zh-CN}', 'targeting':'Agent work',
            'rules':'Current rules','rubric':c.jev.RUBRIC.read_text()}
    with patch.object(model,'call_agent',agent),patch.object(a.llm,'invoke',invoke),patch.object(a,'tavily',provider),\
         patch.object(c.jev,'call',jev),patch.object(c.jev,'dotenv_values',lambda _: {'TYPESAFE_API_KEY':'key'}):
        store=BusinessStore(root/'opportunities.db')
        usage=model.USAGE.set((str(store.path),'test',None))
        try:
            with patch.object(a,'record_call'):
                first=g.run_score(values,root/'workflow-drafts',root)
            assert store.db.execute('SELECT count(*) FROM company_ratings').fetchone()[0]==3, first['artifact']['company_research']['stages']
            assert store.db.execute('SELECT count(*) FROM results').fetchone()[0]==0
        finally:
            model.USAGE.reset(usage)
            store.close()
        assert set(first['artifact']['score']) == {'direction','company','culture','compensation'}
        assert first['artifact']['score']['culture']==3.37 and first['artifact']['recommendation']=='deprioritize'
        assert len(jev_calls)==4 and len(research_calls)==9
        before=(len(jev_calls),len(research_calls),len(model_calls))
        assert g.run_score(values,root/'workflow-drafts',root)==first
        assert before==(len(jev_calls),len(research_calls),len(model_calls))
        values={**values,'jd_report':{**jd,'opportunity_id':'2','url':'https://sample.test/jobs/2','jd':'Build backend products. Grade SDE2. Suzhou, China.'}}
        original=g.render_report
        with patch.object(g,'render_report',side_effect=RuntimeError('interrupted render')):
            try:g.run_score(values,root/'workflow-drafts',root)
            except RuntimeError:pass
            else:raise AssertionError('Interruption was swallowed')
        before=(len(jev_calls),len(research_calls),len(model_calls))
        second=g.run_score(values,root/'workflow-drafts',root)
        assert before==(len(jev_calls),len(research_calls),len(model_calls))
        assert len(jev_calls)==5 and len(research_calls)==9
        assert first['artifact']['company_profiles']==second['artifact']['company_profiles']
        assert len(second['artifact']['company_ratings'])==3
        assert 'attractiveness-v4' in second['artifact']['report']
        values={**values,'jd_report':{**jd,'opportunity_id':'3','url':'https://sample.test/jobs/3'}}
        company_id=first['artifact']['company_profiles']['company']['company_id']
        with (root/'company-profiles'/(company_id+'.lock')).open('a') as locked:
            fcntl.flock(locked, fcntl.LOCK_EX | fcntl.LOCK_NB)
            before=(len(jev_calls),len(research_calls))
            try:g.run_score(values,root/'workflow-drafts',root)
            except TimeoutError as error:assert str(error)=='company_research_in_progress'
            else:raise AssertionError('Concurrent company research was duplicated')
            assert before==(len(jev_calls),len(research_calls))
        third=g.run_score(values,root/'workflow-drafts',root)
        assert len(jev_calls)==6 and len(research_calls)==9
        assert third['artifact']['company_profiles']==first['artifact']['company_profiles']
print('formal score: cold four requests, shared company cache, raw metadata and resume without repeated calls passed')

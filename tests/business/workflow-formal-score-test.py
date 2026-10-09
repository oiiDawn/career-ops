"""Exercise formal scoring, independent company reuse and checkpoint recovery through actual model nodes."""
import json
import fcntl
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from career_ops import model
from career_ops.db import BusinessStore
from career_ops.evaluation import codex_research as a, company_pipeline as c, score_graph as g

scopes = {'company': {'region':'global'}, 'culture': {'region':'China'}, 'compensation': {
    'region':'China:Suzhou', 'level':'SDE2', 'role_family':'software_engineering', 'currency':'CNY', 'basis':'annual_total'}}
model_calls, research_calls, jev_calls = [], [], []

def research(company, postings, output):
    research_calls.append(company)
    assert 'secret CV' not in json.dumps([company, postings])
    output.mkdir(parents=True)
    c.jev.save(output/'result.json', {'status':'researched', 'usage':[]})
    return {'profiles': [{'profile_id':c.scope_key(p['dimension'],p['scope']), 'facts':[{
        'claim':'Public employer fact', 'date':'unknown', 'kind':'employer_statement',
        'applicability':'Declared region; target team uncertain', 'limitations':'Not an offer',
        'source_url':'https://sample.test/policy'}], 'gaps':[], 'conflicts':[]} for p in company['scopes']]}


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


with tempfile.TemporaryDirectory() as temp:
    root=Path(temp)
    jd={'opportunity_id':'1','url':'https://sample.test/jobs/1','company':'Sample','role':'Software Engineer II',
        'jd':'Build agent products. Grade SDE2. Suzhou, China.', 'captured_at':'2026-10-08',
        'liveness':'active','prescreen':{'status':'pass'}}
    values={'jd_report':jd,'cv':'secret CV','profile':'language: {output: zh-CN}', 'targeting':'Agent work',
            'rules':'Current rules','rubric':c.jev.RUBRIC.read_text()}
    with patch.object(model,'call_agent',agent),patch.object(a,'run',research),\
         patch.object(c.jev,'call',jev),patch.object(c.jev,'dotenv_values',lambda _: {'TYPESAFE_API_KEY':'key'}):
        store=BusinessStore(root/'opportunities.db')
        usage=model.USAGE.set((str(store.path),'test',None))
        try:
            first=g.run_score(values,root/'workflow-drafts',root)
            assert store.db.execute('SELECT count(*) FROM company_ratings').fetchone()[0]==3, first['artifact']['company_research']['stages']
            assert store.db.execute('SELECT count(*) FROM results').fetchone()[0]==0
        finally:
            model.USAGE.reset(usage)
            store.close()
        assert set(first['artifact']['score']) == {'direction','company','culture','compensation'}
        assert first['artifact']['score']['culture']==3.37 and first['artifact']['recommendation']=='deprioritize'
        assert len(jev_calls)==4 and len(research_calls)==1
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
        assert len(jev_calls)==5 and len(research_calls)==1
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
        assert len(jev_calls)==6 and len(research_calls)==1
        assert third['artifact']['company_profiles']==first['artifact']['company_profiles']
with tempfile.TemporaryDirectory() as temp, patch.object(model,'call_agent',lambda phase,prompt: ({'identity_url':'https://www.microsoft.com/', 'scopes':{**scopes,'compensation':{**scopes['compensation'],'level':'2'}}},'plan')):
    bundle=g.public_bundle({**jd,'company':'Microsoft','role':'Software Engineer 2--M365 UIPilot team'},Path(temp),'2026-10-11')
    assert bundle['companies'][0]['scopes'][2]['scope']['level']=='Software Engineer 2'
with tempfile.TemporaryDirectory() as temp:
    attempts=[]
    def plan_repair(phase,prompt):
        attempts.append(prompt)
        compensation={**scopes['compensation'],'level':'unknown'}
        if len(attempts)==1:
            compensation['cities']='Shanghai'
        else:
            assert 'Explicit applicability scope required' in prompt and 'secret CV' not in prompt
        return {'identity_url':'https://www.nvidia.com/', 'scopes':{**scopes,'compensation':compensation}},'plan'
    with patch.object(model,'call_agent',plan_repair):
        bundle=g.public_bundle({**jd,'company':'NVIDIA'},Path(temp),'2026-10-11')
    assert len(attempts)==2 and len(list(Path(temp).glob('scope-plan-attempt-*')))==2
    assert bundle['companies'][0]['scopes'][2]['scope']['level']=='unknown'
    assert 'cities' not in bundle['companies'][0]['scopes'][2]['scope']
    with patch.object(model,'call_agent',side_effect=AssertionError('Repeated saved scope plan')):
        g.public_bundle({**jd,'company':'NVIDIA'},Path(temp),'2026-10-11')
print('formal score: cold four requests, shared company cache, raw metadata and resume without repeated calls passed')

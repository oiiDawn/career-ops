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
    assert phase == 'score_sections'
    assert 'verdict, direction, compensation, responsibilities, risks, questions, advertised_comp' in prompt
    text = 'Grounded explanation; unknown facts remain unknown.'
    return {'verdict':text, 'direction':text, 'compensation':text, 'responsibilities':[text], 'risks':[], 'questions':[text],
            'advertised_comp':{'amount':'1', 'currency':'CNY', 'quote':'not in the JD'}}, 'sections'


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
        'location_evidence':'China, Jiangsu, Suzhou', 'liveness':'active','prescreen':{'status':'pass'}}
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
        assert second['artifact']['report'].startswith('## 结论') and '```' not in second['artifact']['report']
        assert 'Public employer fact' in second['artifact']['report']
        assert second['artifact']['advertised_comp'] is None and second['artifact']['captured_at'] == jd['captured_at']
        assert {s['id'] for s in second['artifact']['sources']} >= {'cv', 'jd', 'research'}
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
        values = {**values, 'jd_report': {**jd, 'opportunity_id':'4', 'url':'https://sample.test/jobs/4',
            'location_evidence':'Shanghai, China', 'role':'Senior '+jd['role']}}
        fourth = g.run_score(values, root/'workflow-drafts', root)
        assert len(research_calls) == 2
        assert [item['dimension'] for item in research_calls[-1]['scopes']] == ['compensation']
        assert fourth['artifact']['company_profiles']['culture'] == first['artifact']['company_profiles']['culture']
        assert set(model_calls) == {'score_sections'}
with tempfile.TemporaryDirectory() as temp:
    directory = Path(temp)/'workflow-drafts'/'job'
    directory.mkdir(parents=True)
    identity_calls, identity_answer = [], [None]
    def identity(phase, prompt):
        identity_calls.append(prompt)
        assert phase == 'company_identity'
        return {'company_id': identity_answer[0]}, 'identity'
    with patch.object(model, 'call_agent', identity):
        bundle = g.public_bundle({**jd, 'company':'Microsoft', 'role':'Software Engineer 2--M365 UIPilot team',
            'location_evidence':'China, Shanghai, Shanghai; China, Beijing, Beijing; China, Jiangsu, Suzhou'}, directory, '2026-10-11')
        assert bundle['jobs'][0]['scopes']['culture'] == {'region':'China'}
        compensation = bundle['jobs'][0]['scopes']['compensation']
        assert compensation['level'] == 'Software Engineer 2'
        assert compensation['region'] == 'China'
        entity = {k:bundle['companies'][0][k] for k in ('company_id','name','identity_url')}
        entity['identity_url'] = 'https://www.microsoft.com/'
        archive = directory.parent.parent/'company-profiles'/entity['company_id']/'evidence'
        archive.mkdir(parents=True)
        (archive/'existing.json').write_text(json.dumps({'entity':entity}))
        second = g.public_bundle({**jd, 'company':'Microsoft', 'role':'Senior Software Engineer',
            'url':'https://another-ats.test/job', 'location_evidence':[{'address':{
                'addressCountry':'CN', 'addressLocality':'Suzhou'}}]}, directory, '2026-10-11')
        assert second['companies'][0]['identity_url'] == entity['identity_url']
        assert second['companies'][0]['company_id'] == entity['company_id']
        assert second['jobs'][0]['scopes']['compensation']['level'] == 'senior'
        assert not identity_calls, 'New and exactly named employers must not call a model'
        unknown = g.public_bundle({**jd, 'location_evidence':None, 'role':'Engineer'}, directory, '2026-10-11')
        assert unknown['jobs'][0]['scopes']['culture']['region'] == 'unknown'
        assert unknown['jobs'][0]['scopes']['compensation']['level'] == 'unknown'
        coded = g.public_bundle({**jd, 'location_evidence':'CN-Jiaozi Financial Center, Chengdu'}, directory, '2026-10-11')
        assert coded['jobs'][0]['scopes']['compensation']['region'] == 'China'
        city_only = g.public_bundle({**jd, 'location_evidence':'Beijing'}, directory, '2026-10-11')
        assert city_only['jobs'][0]['scopes']['compensation']['region'] == 'China'
        # Location spellings seen in retained scans; an uncounted or cross-border posting stays unknown.
        for place, region in (('Hong Kong SAR', 'Hong Kong'), ('Hong Kong Island', 'Hong Kong'),
                              ('Shanghai Hongkou, CN - AIA Group Office', 'China'), ('Shanghai, CN-AIA China', 'China'),
                              ('PRC, Shanghai', 'China'), ('北京', 'China'), ('重庆/成都', 'China'),
                              ('Beijing Yizhuang', 'China'), ('2 Locations', 'unknown'), ('Hong Kong SAR; China', 'unknown')):
            spelled = g.public_bundle({**jd, 'location_evidence':place}, directory, '2026-10-11')['jobs'][0]['scopes']
            assert spelled['culture']['region'] == region, (place, spelled['culture']['region'])
            assert (spelled['compensation']['currency'] == 'unknown') == (region == 'unknown')
        # Same employer, same country and seniority share one compensation scope across titles and cities.
        shared = [g.public_bundle({**jd, 'role':role, 'location_evidence':place}, directory, '2026-10-11')['jobs'][0]['scopes']
                  for role, place in (('AI Engineer_BD', 'China, Jiangsu, Suzhou'), ('数据挖掘工程师（大模型方向）_XC', 'China, Shanghai, Shanghai'),
                                      ('Senior Full Stack Developer', 'Beijing'), ('资深平台工程师', 'China, Shanghai, Shanghai'),
                                      ('Business Analyst, AVP', 'China, Zhejiang, Hangzhou'))]
        assert shared[0] == shared[1] and shared[2] == shared[3]
        assert shared[0]['compensation']['role_family'] == 'software_engineering'
        assert shared[2]['compensation']['level'] == 'senior' and shared[4]['compensation']['role_family'] == 'other'
        # An unseen name is matched to a retained employer by the model once; the kept decision serves later postings.
        assert unknown['companies'][0]['company_id'] != entity['company_id'] and 'Microsoft' in identity_calls[-1]
        identity_answer[0], asked = entity['company_id'], len(identity_calls)
        for _ in range(2):
            alias = g.public_bundle({**jd, 'company':'微软（中国）有限公司'}, directory, '2026-10-11')
            assert {k:alias['companies'][0][k] for k in entity} == entity
            assert alias['jobs'][0]['posting']['company'] == '微软（中国）有限公司'
        assert len(identity_calls) == asked + 1
        identity_answer[0] = 'not-retained'
        try: g.public_bundle({**jd, 'company':'Another Name'}, directory, '2026-10-11')
        except ValueError as error: assert 'retained employer' in str(error)
        else: raise AssertionError('An identity answer outside the retained employers was accepted')
print('formal score: deterministic scopes, retained identity, company reuse and checkpoint recovery passed')

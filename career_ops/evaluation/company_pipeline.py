"""Persist Codex employer facts and scoped Jev ratings for reusable job scoring."""
from __future__ import annotations

from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import re
import time

from career_ops.company_keys import normalize_company

from career_ops.evaluation import jev, codex_research as research
from career_ops.evaluation.decisions import classify
SHARED = ('company', 'culture', 'compensation')


def scope_key(dimension: str, scope: dict) -> str:
    """Match exact declared applicability; unknown levels and regions never imply a broader match."""
    required = {'region'}
    if dimension == 'compensation':
        required |= {'level', 'role_family', 'currency', 'basis'}
    if (not isinstance(scope, dict) or not required <= scope.keys()
            or not scope.keys() <= {'region', 'team', 'level', 'role_family', 'currency', 'basis'}
            or any(not isinstance(v, str) or not v.strip() for v in scope.values())):
        raise ValueError('Explicit applicability scope required')
    return dimension + '-' + jev.digest(scope)[:16]


def rating(response: dict, name: str) -> dict:
    """Preserve the native distribution, confidence and independent sufficiency without recommendation thresholds."""
    answer = response['answers'][name]
    return {'score': answer['score'] + 1, 'confidence': answer['confidence'],
            'probabilities': answer['probabilities'],
            'evidence_sufficiency': response['answers'][name + '_evidence']['noul'],
            'evidence_status': 'assessed'}


def company_request(company: dict, rubric: str) -> dict:
    """Evaluate each scoped company profile once; job content is absent from this request."""
    templates = jev.request_for({}, rubric)['questions']
    profiles, questions, sources = {}, {}, {}
    for profile in company['profiles']:
        dimension = profile['dimension']
        if dimension not in SHARED:
            raise ValueError('Company profiles may only contain the three shared dimensions')
        name = scope_key(dimension, profile['scope'])
        if name in profiles:
            raise ValueError('Duplicate company profile scope')
        profiles[name] = deepcopy(profile)
        evidence_sources = profiles[name]['evidence'].pop('sources', [])
        if not isinstance(evidence_sources, list) or any(not isinstance(s, dict) for s in evidence_sources):
            raise ValueError('Profile sources must be public source records')
        refs = []
        for source in evidence_sources:
            source_id = jev.digest(source)
            sources[source_id] = source
            refs.append(source_id)
        profiles[name]['evidence']['source_refs'] = refs
        for suffix in ('', '_evidence'):
            question = deepcopy(templates[dimension + suffix])
            question['instructions'] += (
                f' Evaluate only state.evidence.profiles["{name}"] and its declared scope for '
                'state.evidence.company. This is a reusable company baseline, not a job or offer guarantee. '
                'Read only its evidence.source_refs in state.evidence.sources. '
                'Do not borrow evidence from another profile. Same-employer reference evidence included in this profile '
                'may inform a provisional decision even when its region, level or team applicability is uncertain. '
                'Keep its actual scope; do not turn reference pay into target-role pay or policy into guaranteed execution. '
                'Assess usefulness for public-information screening, not completeness of internal or individual offer details.'
            )
            questions[name + suffix] = question
    return {'model': jev.MODEL, 'state': {'standards': rubric, 'evidence': {
            'company': {k: company[k] for k in ('company_id', 'name', 'identity_url')},
            'profiles': profiles, 'sources': sources}}, 'questions': questions}


def job_request(job: dict, rubric: str) -> dict:
    """Only direction needs per-job inference, except a separately evidenced explicit pay quotation."""
    request = jev.request_for({'posting': job['posting']}, rubric)
    names = {'direction', 'direction_evidence'}
    quote = job.get('compensation_quote')
    if quote:
        if (not isinstance(quote, dict) or set(quote) != {'scope', 'evidence'}
                or not isinstance(quote['evidence'], dict) or not quote['evidence']):
            raise ValueError('Job quotation requires explicit scope and evidence')
        scope_key('compensation', quote['scope'])
        if quote['scope'] != job['scopes']['compensation']:
            raise ValueError('Job quotation must match the requested compensation scope')
        request['state']['evidence']['explicit_job_quotation'] = quote
        names |= {'compensation', 'compensation_evidence'}
        for name in ('compensation', 'compensation_evidence'):
            request['questions'][name]['instructions'] += (
                ' Evaluate only explicit_job_quotation for this posting, not other company salary ranges.'
            )
    request['questions'] = {k: v for k, v in request['questions'].items() if k in names}
    return request


def validate_bundle(bundle: dict) -> dict:
    """Require explicit employer links; name normalization helps lookup but never resolves aliases automatically."""
    if not isinstance(bundle, dict) or set(bundle) != {'companies', 'jobs'}:
        raise ValueError('Bundle requires companies and jobs')
    companies = {}
    for company in bundle['companies']:
        if (set(company) != {'company_id', 'name', 'identity_url', 'valid_until', 'profiles'}
                or not re.fullmatch(r'[a-z0-9_-]+', company['company_id'])
                or not normalize_company(company['name'])
                or not company['identity_url'].startswith('https://')
                or not isinstance(company['profiles'], list)):
            raise ValueError('Company requires safe ID, verified identity URL, validity date and scoped profiles')
        date.fromisoformat(company['valid_until'])
        if company['company_id'] in companies:
            raise ValueError('Duplicate company identity')
        scopes = set()
        for profile in company['profiles']:
            if (set(profile) != {'dimension', 'scope', 'evidence'} or profile['dimension'] not in SHARED
                    or not isinstance(profile['evidence'], dict)):
                raise ValueError('Profile requires dimension, scope and public evidence')
            key = scope_key(profile['dimension'], profile['scope'])
            if key in scopes:
                raise ValueError('Duplicate profile')
            scopes.add(key)
        companies[company['company_id']] = company
    seen = set()
    for job in bundle['jobs']:
        if (not {'id', 'company_id', 'posting', 'scopes'} <= job.keys()
                or not job.keys() <= {'id', 'company_id', 'posting', 'scopes', 'compensation_quote'}
                or not re.fullmatch(r'[A-Za-z0-9_-]+', str(job['id'])) or str(job['id']) in seen
                or job['company_id'] not in companies or not isinstance(job['posting'], dict)
                or not isinstance(job['posting'].get('jd'), str) or not job['posting']['jd'].strip()
                or not job['posting'].get('url', '').startswith('https://')
                or set(job['scopes']) != set(SHARED)):
            raise ValueError('Job requires unique ID, public JD, explicit company association and three requested scopes')
        seen.add(str(job['id']))
        for dimension in SHARED:
            scope_key(dimension, job['scopes'][dimension])
    return companies


def evaluate(bundle: dict, rubric: str, store: Path, output: Path, key: str | None,
             today: date | None = None, reuse_company_scores=False) -> dict:
    """Reuse identical current company versions across runs; retain expired versions without presenting them as current."""
    companies = validate_bundle(bundle)
    today = today or date.today()
    output.mkdir(parents=True, exist_ok=False)
    store.mkdir(parents=True, exist_ok=True)
    requests = store / 'requests'
    requests.mkdir(exist_ok=True)
    jev.save(output / 'input.json', bundle)
    (output / 'rubric.md').write_text(rubric)
    ledger, versions, rows = [], {}, []

    def score(unit, request):
        fingerprint = jev.digest(request)
        # Failures get new attempt directories, so repeated runs cannot overwrite their evidence.
        cached_path = requests / (fingerprint + '.json')
        cached = cached_path.exists()
        if key is None:
            jev.save(output / (unit + '.request.json'), request)
            return None, fingerprint
        if cached:
            result = jev.call(fingerprint, request, requests, key)
        else:
            attempts = requests / fingerprint
            attempts.mkdir(exist_ok=True)
            attempt_dir = attempts / str(len(list(attempts.iterdir())) + 1)
            attempt_dir.mkdir()
            result = jev.call(fingerprint, request, attempt_dir, key)
            if result['status'] == 'scored':
                jev.save(cached_path, result)
                jev.save(requests / (fingerprint + '.request.json'), request)
        ledger.append({'unit': unit, 'request_sha256': fingerprint, 'cache_hit': cached,
                       'questions': len(request['questions']), 'status': result['status'],
                       'http_attempts': 0 if cached else len(result['attempts']),
                       'elapsed_seconds': 0 if cached else result['elapsed_seconds']})
        return result, fingerprint

    for company_id, company in companies.items():
        if date.fromisoformat(company['valid_until']) < today:
            versions[company_id] = {'status': 'expired', 'profiles': {}}
            continue
        profiles, missing, fingerprints = {}, [], {}
        profile_store = store / company_id / 'ratings'
        profile_store.mkdir(parents=True, exist_ok=True)
        for profile in company['profiles']:
            one = {**company, 'profiles': [profile]}
            fingerprint = jev.digest(company_request(one, rubric))
            name = scope_key(profile['dimension'], profile['scope'])
            fingerprints[name] = fingerprint
            path = profile_store / (fingerprint + '.json')
            if key is not None and path.exists():
                cached = json.loads(path.read_text())
                jev.validate(cached['request'], cached['response'])
                profiles[name] = cached['rating']
            else:
                missing.append(profile)
        fingerprint = None
        results = []
        for dimension in SHARED:
            pending = [p for p in missing if p['dimension'] == dimension]
            if pending and not reuse_company_scores:
                request = company_request({**company, 'profiles': pending}, rubric)
                result, fingerprint = score('company-' + company_id + '-' + dimension, request)
                if result:
                    results.append(result)
                if result and result['status'] == 'scored':
                    for name, profile in request['state']['evidence']['profiles'].items():
                        value = {'scope': profile['scope'], 'dimension': profile['dimension'],
                                 'scoring_request_sha256': fingerprint, **rating(result['response'], name)}
                        profiles[name] = value
                        jev.save(profile_store / (fingerprints[name] + '.json'), {
                            'request': request, 'response': result['response'], 'rating': value})
            elif any(p['dimension'] == dimension for p in profiles.values()):
                ledger.append({'unit': 'company-' + company_id + '-' + dimension, 'cache_hit': True, 'questions': 0,
                               'status': 'scored', 'http_attempts': 0, 'elapsed_seconds': 0})
        unrated = any(scope_key(p['dimension'], p['scope']) not in profiles for p in company['profiles'])
        version = {'company_id': company_id, 'normalized_name': normalize_company(company['name']),
                   'identity_url': company['identity_url'], 'valid_until': company['valid_until'],
                   'request_sha256': fingerprint, 'rubric_sha256': jev.digest(rubric),
                   'status': ('partial' if unrated and profiles else 'failed' if results and not profiles
                              else 'pending' if unrated or not profiles else 'scored'), 'profiles': profiles}
        versions[company_id] = version
        if key is not None:
            directory = store / company_id
            directory.mkdir(exist_ok=True)
            # Validity is part of the version, but extending it does not repeat an unchanged inference.
            jev.save(directory / (jev.digest(version) + '.json'), version)

    for job in bundle['jobs']:
        result, fingerprint = score('job-' + str(job['id']), job_request(job, rubric))
        dimensions, refs = {}, {}
        if result and result['status'] == 'scored':
            dimensions['direction'] = rating(result['response'], 'direction')
        version = versions[job['company_id']]
        for dimension in SHARED:
            profile_id = scope_key(dimension, job['scopes'][dimension])
            profile = version['profiles'].get(profile_id)
            refs[dimension] = {'company_id': job['company_id'], 'profile_id': profile_id,
                               'request_sha256': profile.get('scoring_request_sha256') if profile else None,
                               'scope': job['scopes'][dimension], 'valid_until': companies[job['company_id']]['valid_until']}
            dimensions[dimension] = ({k: v for k, v in profile.items() if k not in ('scope', 'dimension', 'scoring_request_sha256')}
                                     if profile else {'status': 'pending', 'reason':
                                         'expired_company_profile' if version['status'] == 'expired' else 'no_matching_valid_profile'})
        if job.get('compensation_quote') and result and result['status'] == 'scored':
            dimensions['compensation'] = rating(result['response'], 'compensation')
            refs['compensation'] = {'source': 'explicit_job_quotation', 'request_sha256': fingerprint,
                                    'scope': job['compensation_quote']['scope']}
        rows.append({'id': str(job['id']), 'company_id': job['company_id'], 'dimensions': dimensions,
                     'company_profiles': refs, 'direction_request_sha256': fingerprint,
                     'recommendation': classify({d: dimensions.get(d, {}).get('score') for d in jev.DIMENSIONS},
                                                {'status': 'uncertain'})})
    summary = {'production_writes': False, 'companies': versions, 'jobs': rows, 'calls': ledger,
               'new_api_calls': sum(not c['cache_hit'] for c in ledger),
               'cached_api_calls': sum(c['cache_hit'] for c in ledger),
               'http_attempts': sum(c['http_attempts'] for c in ledger)}
    jev.save(output / 'results.json', summary)
    return summary


def validate_input(value: dict) -> dict:
    """Accept public research inputs, not preassembled evidence or candidate preferences."""
    if not isinstance(value, dict) or set(value) != {'companies', 'jobs'}:
        raise ValueError('Input requires companies and jobs')
    prepared = deepcopy(value)
    for company in prepared['companies']:
        if set(company) != {'company_id', 'name', 'identity_url', 'scopes', 'seed_urls', 'valid_until'}:
            raise ValueError('Company requires public identity, scopes, seed_urls and explicit valid_until')
        public = {k: company[k] for k in ('company_id', 'name', 'identity_url', 'scopes', 'seed_urls')}
        research.validate_public(public)
        if len({scope_key(s['dimension'], s['scope']) for s in company['scopes']}) != len(company['scopes']):
            raise ValueError('Duplicate requested scope')
        company.pop('scopes')
        company.pop('seed_urls')
        company['profiles'] = []
    validate_bundle(prepared)
    return value


def summary_profiles(answer: dict, requested: list) -> list:
    """Map usable JSON facts to exact declared profile identities."""
    if not isinstance(answer, dict) or set(answer) != {'profiles'} or not isinstance(answer['profiles'], list):
        raise ValueError('Invalid company summary JSON')
    expected = {scope_key(p['dimension'], p['scope']): p for p in requested}
    seen, profiles = set(), []
    for profile in answer['profiles']:
        if (not isinstance(profile, dict) or set(profile) != {'profile_id', 'facts', 'gaps', 'conflicts'}
                or not isinstance(profile['profile_id'], str) or profile['profile_id'] not in expected
                or profile['profile_id'] in seen or not isinstance(profile['facts'], list)
                or any(not isinstance(profile[k], list) or any(not isinstance(x, str) or not x.strip()
                       for x in profile[k]) for k in ('gaps', 'conflicts'))):
            raise ValueError('Invalid scoped summary structure')
        name = profile['profile_id']
        seen.add(name)
        sources = []
        for fact in profile['facts']:
            if not isinstance(fact, dict):
                raise ValueError('Invalid company fact JSON')
            fields = {'claim', 'date', 'kind', 'applicability', 'limitations'}
            for field in fields:
                if not isinstance(fact.get(field), str) or not fact[field].strip():
                    raise ValueError(f'Company fact {field} must be a nonempty string; unknown dates use \"unknown\"')
            if set(fact) != fields | {'source_url'} or not research.public_url(fact['source_url']):
                raise ValueError('Original HTTP source URL required')
            sources.append({'source_url': fact['source_url']})
        if profile['facts']:
            declared = expected[name]
            profiles.append({'dimension': declared['dimension'], 'scope': declared['scope'], 'evidence': {
                'facts': profile['facts'], 'gaps': profile['gaps'], 'conflicts': profile['conflicts'],
                'sources': sources, 'summary_rule_sha256': research.rule_digest(),
                'summary_sha256': jev.digest(answer), 'claim_semantics_verified': False}})
    if seen != set(expected):
        raise ValueError('Missing requested company summary scope')
    return profiles


def prepare_companies(value: dict, store: Path, output: Path, refresh=False, today=None, dimension_ready=None) -> dict:
    """Reuse current scoped facts; research all missing company scopes in one Codex task."""
    validate_input(value)
    today = today or date.today()
    prepared, events, references, scoring = {'companies': [], 'jobs': value['jobs']}, [], [], []
    rule = research.rule_digest()
    for company in value['companies']:
        directory = store / company['company_id'] / 'evidence'
        directory.mkdir(parents=True, exist_ok=True)
        entity = {k: company[k] for k in ('company_id', 'name', 'identity_url')}
        requested = {scope_key(s['dimension'], s['scope']): s for s in company['scopes']}
        found, profiles = {}, []
        valid_until = company['valid_until']
        if not refresh:
            for path in sorted(directory.glob('*.json'), key=lambda p: p.stat().st_mtime_ns, reverse=True):
                archive = json.loads(path.read_text())
                if (archive['entity'] != entity or date.fromisoformat(archive['valid_until']) < today
                        or archive.get('summary_rule_sha256') != rule or archive['summary_status'] != 'summarized'):
                    continue
                restored = summary_profiles(archive['summary_answer'], archive['scopes'])
                for item in archive['scopes']:
                    name = scope_key(item['dimension'], item['scope'])
                    if name in requested and name not in found:
                        found[name] = path.stem
                        valid_until = min(valid_until, archive['valid_until'])
                        profiles.extend(p for p in restored if scope_key(p['dimension'], p['scope']) == name)
                        references.append({'company_id': company['company_id'], 'scope_key': name, 'archive_sha256': path.stem})
                        events.append({'company_id': company['company_id'], 'dimension': item['dimension'],
                                       'scope': name, 'stage': 'archive', 'status': 'cached', 'archive_sha256': path.stem})
        missing = [item for name, item in requested.items() if name not in found]
        if missing and date.fromisoformat(company['valid_until']) >= today:
            public = {**entity, 'scopes': missing, 'seed_urls': company['seed_urls']}
            postings = [job['posting'] for job in value['jobs'] if job['company_id'] == company['company_id']]
            run = directory / ('capture-' + str(time.time_ns()))
            answer = research.run(public, postings, run)
            captured = summary_profiles(answer, missing)
            sources = list({f['source_url']: {'source_url': f['source_url'], 'capture_kind': 'codex_reference'}
                            for p in captured for f in p['evidence']['facts']}.values())
            archive = {'entity': entity, 'scopes': missing, 'valid_until': company['valid_until'],
                       'summary_rule_sha256': rule, 'summary_status': 'summarized', 'summary_answer': answer,
                       'capture': {'directory': str(run.resolve()), 'sources': sources}, 'profiles': captured}
            fingerprint = jev.digest(archive)
            jev.save(directory / (fingerprint + '.json'), archive)
            profiles.extend(captured)
            references.extend({'company_id': company['company_id'], 'scope_key': scope_key(p['dimension'], p['scope']),
                               'archive_sha256': fingerprint} for p in missing)
            events.append({'company_id': company['company_id'], 'stage': 'research', 'status': 'researched',
                           'capture_directory': str(run), **json.loads((run / 'result.json').read_text())})
        current = {**entity, 'valid_until': valid_until, 'profiles': profiles}
        prepared['companies'].append(current)
        if dimension_ready:
            for dimension in SHARED:
                scoped = {**current, 'profiles': [p for p in profiles if p['dimension'] == dimension]}
                if scoped['profiles']:
                    scored = dimension_ready(scoped, dimension)
                    if scored:
                        scoring.extend(scored['calls'])
    jev.save(output / 'company-stages.json', events)
    jev.save(output / 'prepared.json', prepared)
    jev.save(output / 'summary-references.json', references)
    jev.save(output / 'dimension-scoring.json', scoring)
    return prepared

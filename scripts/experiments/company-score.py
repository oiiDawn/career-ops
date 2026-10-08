"""Maintain scoped company ratings and score job direction in an isolated, content-addressed evidence store."""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import date
import importlib.util
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from career_ops.company_keys import normalize_company

spec = importlib.util.spec_from_file_location('jev', Path(__file__).with_name('jev-score.py'))
jev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(jev)
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
            'evidence_status': 'threshold_pending'}


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
                'Do not borrow evidence from another profile, region or level. Unknown applicability remains unknown.'
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
                or not company['profiles']):
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
             today: date | None = None) -> dict:
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
        request = company_request(company, rubric)
        result, fingerprint = score('company-' + company_id, request)
        profiles = {}
        if result and result['status'] == 'scored':
            profiles = {name: {'scope': profile['scope'], 'dimension': profile['dimension'],
                        **rating(result['response'], name)}
                        for name, profile in request['state']['evidence']['profiles'].items()}
        version = {'company_id': company_id, 'normalized_name': normalize_company(company['name']),
                   'identity_url': company['identity_url'], 'valid_until': company['valid_until'],
                   'request_sha256': fingerprint, 'rubric_sha256': jev.digest(rubric),
                   'status': result['status'] if result else 'check_only', 'profiles': profiles}
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
                               'request_sha256': version.get('request_sha256'),
                               'scope': job['scopes'][dimension], 'valid_until': companies[job['company_id']]['valid_until']}
            dimensions[dimension] = ({k: v for k, v in profile.items() if k not in ('scope', 'dimension')}
                                     if profile else {'status': 'pending', 'reason':
                                         'expired_company_profile' if version['status'] == 'expired' else 'no_matching_valid_profile'})
        if job.get('compensation_quote') and result and result['status'] == 'scored':
            dimensions['compensation'] = rating(result['response'], 'compensation')
            refs['compensation'] = {'source': 'explicit_job_quotation', 'request_sha256': fingerprint,
                                    'scope': job['compensation_quote']['scope']}
        rows.append({'id': str(job['id']), 'company_id': job['company_id'], 'dimensions': dimensions,
                     'company_profiles': refs, 'direction_request_sha256': fingerprint,
                     'recommendation': 'threshold_pending'})
    summary = {'production_writes': False, 'companies': versions, 'jobs': rows, 'calls': ledger,
               'new_api_calls': sum(not c['cache_hit'] for c in ledger),
               'cached_api_calls': sum(c['cache_hit'] for c in ledger),
               'http_attempts': sum(c['http_attempts'] for c in ledger)}
    jev.save(output / 'results.json', summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--store', type=Path, required=True, help='Persistent isolated company profile store')
    parser.add_argument('--output', type=Path, required=True, help='New immutable run directory')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    store = args.store.resolve()
    if not store.is_relative_to((ROOT / 'data/experiments').resolve()):
        parser.error('Company store must remain under data/experiments until production integration is approved')
    key = None if args.check else jev.dotenv_values(ROOT / '.env').get('TYPESAFE_API_KEY')
    if not args.check and not key:
        parser.error('Missing TYPESAFE_API_KEY')
    result = evaluate(json.loads(args.input.read_text()), jev.RUBRIC.read_text(), store, args.output, key)
    print(json.dumps({'jobs': len(result['jobs']), 'new_api_calls': result['new_api_calls'],
                      'cached_api_calls': result['cached_api_calls'], 'production_writes': False}))


if __name__ == '__main__':
    main()

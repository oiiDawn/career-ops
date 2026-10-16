"""Verify failed/missing liveness checks do not gate real workflow commits or invalidate scores."""

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from career_ops.db import BusinessStore
from career_ops.discovery.store import DiscoveryStore
from career_ops.input_contracts import canonical_scan_input, score_inputs, score_is_current
from career_ops.liveness import save_observation
from career_ops.tasks import evaluate_opportunity, cron_score


with TemporaryDirectory() as temporary:
    directory = Path(temporary)
    discovery = DiscoveryStore(directory / 'opportunities.db')
    jd = 'Build and review agent workflows as a full-time software engineer in Shanghai.'
    captured = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    for number in (1, 2):
        url = f'https://example.org/jobs/{number}'
        discovery.ingest({'url': url, 'company': 'Example', 'title': f'Engineer {number}',
                          'description': jd, '_capture': {'url': url, 'method': 'official_job_page',
                          'status': 200, 'retrieved_at': captured,
                          'content_hash': hashlib.sha256(jd.encode()).hexdigest()}}, 'test')
    row = dict(discovery.db.execute('SELECT * FROM opportunities WHERE id=1').fetchone())
    failure = {'url': row['url'], 'result': 'uncertain', 'code': 'access_blocked',
               'checked_at': datetime.now(timezone.utc).isoformat(), 'via_api': False, 'evidence': {}}
    assert save_observation(discovery.db, row, failure)
    discovery.scan_outcome({'url': 'https://example.org/jobs/2', 'reason': 'legacy unlisted result'}, 'skipped_expired')
    legacy_source = {'schema_version': 'scan_input_v1', 'opportunity_id': '1', 'url': row['url'],
                     'company': 'Example', 'role': 'Engineer 1', 'jd': jd, 'captured_at': captured,
                     'liveness': 'uncertain'}
    store = BusinessStore(directory / 'opportunities.db')
    waiting = store.start('1', 'scan', canonical_scan_input(json.dumps(legacy_source)))
    store.wait(waiting['task_id'], 'source_access_unknown')
    store.close()
    with patch.dict(os.environ, {'CAREER_OPS_MODEL_STUB': str(ROOT / 'tests/fixtures/workflow-model-runner.py')}), \
         patch('career_ops.tasks.capture_jd', side_effect=AssertionError('Usable retained JD was fetched again')):
        for opportunity_id in ('1', '2'):
            result = evaluate_opportunity(directory, opportunity_id)
            assert result['status'] == 'completed', result
    store = BusinessStore(directory / 'opportunities.db')
    scan = store.module_result('1', 'scan')['artifact']
    score = store.module_result('1', 'score')
    frozen = store.db.execute("SELECT input_hash,input_payload FROM tasks WHERE module='score' AND opportunity_id='1'").fetchone()
    assert score_is_current(store.db, score['input_hash'], scan)
    assert save_observation(discovery.db, row, {**failure, 'code': 'collection_error'})
    assert score_is_current(store.db, score['input_hash'], scan)
    assert tuple(frozen) == tuple(store.db.execute("SELECT input_hash,input_payload FROM tasks WHERE module='score' AND opportunity_id='1'").fetchone())
    assert json.loads(score_inputs({**scan, 'liveness': 'uncertain'}))['jd_report']['liveness'] == 'uncertain'
    assert store.task(waiting['task_id'])['status'] == 'completed'
    for number in (3, 4):
        url = f'https://example.org/jobs/{number}'
        discovery.ingest({'url': url, 'company': 'Example', 'title': f'Engineer {number}',
                          'description': jd, '_capture': {'url': url, 'method': 'official_job_page',
                          'status': 200, 'retrieved_at': captured,
                          'content_hash': hashlib.sha256(jd.encode()).hexdigest()}}, 'test')
    discovery.scan_outcome({'url': 'https://example.org/jobs/3', 'maintenance_closed': True}, 'skipped_expired')
    with patch.dict(os.environ, {'CAREER_OPS_MODEL_STUB': str(ROOT / 'tests/fixtures/workflow-model-runner.py')}), \
         patch('career_ops.tasks.capture_jd', side_effect=AssertionError('Repeated JD fetch')):
        assert cron_score(directory)['opportunity_id'] == '4'
    store.close()
    discovery.close()

print('liveness evaluation: historical waiting input, failed/missing checks, retained JD and score integrity passed')

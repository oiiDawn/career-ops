"""Require complete browser evidence before the LinkedIn no-Apply policy can delete a posting."""
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from career_ops.discovery.store import DiscoveryStore
from career_ops.discovery.liveness_check import maintain
from career_ops.liveness import explicit_closure

url = 'https://cn.linkedin.com/jobs/view/engineer-4475675400'
observation = {'url': url, 'result': 'expired', 'code': 'linkedin_no_apply', 'via_api': False,
               'checked_at': '2026-10-16T01:00:00+00:00', 'evidence': {
                   'source_url': url, 'final_url': url, 'status': 200, 'posting_id': '4475675400',
                   'title': 'Engineer', 'description_length': 500, 'settled': True, 'apply_control_present': False}}
assert explicit_closure(observation)
assert not explicit_closure({**observation, 'via_api': True})
for patch_values in [
    {'status': 403}, {'settled': False}, {'apply_control_present': True}, {'title': ''},
    {'description_length': 20}, {'posting_id': '9999999999'},
    {'final_url': 'https://cn.linkedin.com/authwall'},
]:
    assert not explicit_closure({**observation, 'evidence': {**observation['evidence'], **patch_values}})
with TemporaryDirectory() as temporary:
    directory = Path(temporary)
    store = DiscoveryStore(directory / 'opportunities.db')
    store.ingest({'url': url, 'company': 'Example', 'title': 'Engineer'}, 'test')
    def reader(urls, *, on_observation, **options):
        for posting in urls:
            on_observation({**observation, 'url': posting})
    with patch('career_ops.discovery.liveness_check.observe', side_effect=reader):
        result = maintain(directory, headed_fallback=False, throttle_ms=0)
    assert result['status'] == 'completed', result
    assert result['observations'][0]['maintenance_status'] == 'deleted', result
    assert not store.db.execute('SELECT id FROM opportunities').fetchall()
    assert not store.db.execute('PRAGMA foreign_key_check').fetchall()
    store.close()
print('LinkedIn no-Apply: complete browser evidence authorizes isolated deletion; incomplete evidence cannot')

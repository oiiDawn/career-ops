"""Keep localized closure evidence bound to the posting during destructive maintenance."""
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from career_ops.discovery.store import DiscoveryStore
from career_ops.discovery.liveness_check import maintain
from career_ops.liveness import explicit_closure

with TemporaryDirectory() as temporary:
    directory = Path(temporary)
    store = DiscoveryStore(directory / 'opportunities.db')
    url = 'https://cn.linkedin.com/jobs/view/4469654437'
    store.ingest({'url': url, 'company': 'Example', 'title': 'Engineer'}, 'test')
    observation = {'url': url, 'result': 'expired', 'code': 'linkedin_closed_marker',
                   'via_api': True, 'checked_at': '2026-10-16T01:00:00+00:00',
                   'evidence': {'posting_url': url, 'source_url': 'https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/4469654437',
                                'status': 200, 'excerpt': '已停止接受求职申请'}}
    assert explicit_closure(observation)
    assert not explicit_closure({**observation, 'evidence': {**observation['evidence'], 'posting_url': url + '0'}})
    assert not explicit_closure({**observation, 'result': 'uncertain'})
    def reader(urls, *, on_observation, **options):
        for posting in urls:
            on_observation({**observation, 'url': posting})
    with patch('career_ops.discovery.liveness_check.observe', side_effect=reader):
        result = maintain(directory, headed_fallback=False, throttle_ms=0)
    assert result['status'] == 'completed', result
    assert result['observations'][0]['maintenance_status'] == 'deleted', result
    assert not store.db.execute('SELECT id FROM opportunities').fetchall()
    assert store.db.execute('PRAGMA foreign_key_check').fetchall() == []
    store.close()
print('localized closure: identity-bound evidence reaches isolated maintenance deletion')

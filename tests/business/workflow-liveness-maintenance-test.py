"""Exercise persisted streaming, freshness and nonblocking per-posting failures."""

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from career_ops.discovery.liveness_check import maintain
from career_ops.discovery.store import DiscoveryStore
from career_ops.liveness import current_observations, save_observation


with TemporaryDirectory() as temporary:
    directory = Path(temporary)
    store = DiscoveryStore(directory / 'opportunities.db')
    for number in (1, 2):
        store.ingest({'url': f'https://boards.greenhouse.io/acme/jobs/{number}',
                      'company': 'Acme', 'title': f'Engineer {number}'}, 'test')
    fixture = directory / 'fetch.mjs'
    fixture.write_text("""globalThis.fetch = async url => {
  if (url.endsWith('/2')) process.exit(7);
  return new Response('{}', {status: 200});
};
""")
    with patch.dict(os.environ, {'NODE_OPTIONS': f'--import={fixture}'}):
        result = maintain(directory, headed_fallback=False, throttle_ms=0)
    assert result['status'] == 'partial', result
    assert len(result['observations']) == 2
    views = current_observations(store.db)
    assert views['1']['liveness'] == 'active'
    assert views['2']['liveness'] == 'uncertain'
    assert list(store.db.execute('SELECT state,application_state FROM opportunities'))
    assert all(tuple(row) == ('discovered', 'none') for row in store.db.execute('SELECT state,application_state FROM opportunities'))
    later = datetime.now(timezone.utc) + timedelta(hours=25)
    assert current_observations(store.db, now=later)['1']['liveness'] == 'uncertain'
    opportunity = dict(store.db.execute('SELECT * FROM opportunities WHERE id=1').fetchone())
    failure = {'url': opportunity['url'], 'checked_at': datetime.now(timezone.utc).isoformat(),
               'result': 'uncertain', 'code': 'access_blocked', 'via_api': False, 'evidence': {}}
    assert save_observation(store.db, opportunity, failure)
    view = current_observations(store.db)['1']
    assert view['liveness'] == 'uncertain' and view['liveness_last_active_at']
    assert not save_observation(store.db, {**opportunity, 'url': 'https://example.org/changed'},
                                {**failure, 'url': 'https://example.org/changed'})
    store.close()

print('liveness maintenance: committed streaming progress, isolated failure and freshness passed')

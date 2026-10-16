"""Exercise persisted streaming, freshness and nonblocking per-posting failures."""

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
import subprocess
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
    def malformed_reader(urls, *, on_observation, **_options):
        for index, url in enumerate(urls):
            on_observation({**failure, 'url': url, 'code': {} if index == 0 else 'api_ok',
                            'result': 'expired' if index == 0 else 'active'})
        return []

    with patch('career_ops.discovery.liveness_check.observe', side_effect=malformed_reader):
        malformed = maintain(directory, headed_fallback=False, throttle_ms=0)
    assert malformed['status'] == 'partial' and malformed['errors']
    assert current_observations(store.db)['1']['liveness'] == 'uncertain'
    assert current_observations(store.db)['2']['liveness'] == 'active'
    fixture.write_text("globalThis.fetch = async url => new Response('{}', {status: url.endsWith('/2') ? 404 : 200});\n")
    run = subprocess.run([sys.executable, '-B', '-m', 'career_ops', 'system', 'liveness', '--apply',
                          '--no-fallback', '--directory', str(directory)], cwd=ROOT,
                         env={**os.environ, 'NODE_OPTIONS': f'--import={fixture}'},
                         capture_output=True, text=True, timeout=20)
    assert run.returncode == 0, (run.stdout, run.stderr)
    assert json.loads(run.stdout)['status'] == 'completed'
    assert store.db.execute('SELECT id FROM opportunities').fetchall()[0][0] == 1
    assert store.db.execute('SELECT COUNT(*) FROM opportunities').fetchone()[0] == 1
    assert store.db.execute("SELECT status FROM scan_outcomes WHERE url LIKE '%/2'").fetchone()[0] == 'skipped_expired'
    store.close()

print('liveness maintenance: committed streaming progress, isolated failure and freshness passed')

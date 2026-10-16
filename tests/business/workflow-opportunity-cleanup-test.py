"""Exercise destructive closure transactions, races, protected data and cleanup recovery."""

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from career_ops.db import BusinessStore
from career_ops.discovery.store import DiscoveryStore
from career_ops.liveness import execution_lock, require_open, save_observation
from career_ops.opportunity_cleanup import cleanup_pending, delete_closed
from career_ops.applications.application_lifecycle import ApplicationStore
from career_ops.interviews.store import InterviewStore


def closure(row):
    return {'url': row['url'], 'result': 'expired', 'code': 'linkedin_closed_marker', 'via_api': True,
            'checked_at': datetime.now(timezone.utc).isoformat(), 'reason': 'Closed',
            'evidence': {'posting_url': row['url'], 'source_url': 'https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/12',
                         'status': 200, 'excerpt': 'Not currently accepting applications'}}


with TemporaryDirectory() as temporary:
    directory = Path(temporary)
    discovery = DiscoveryStore(directory / 'opportunities.db')
    store = BusinessStore(directory / 'opportunities.db')
    applications = ApplicationStore(directory / 'opportunities.db')
    interviews = InterviewStore(directory / 'opportunities.db')
    rows = []
    for number in (11, 12):
        discovery.ingest({'url': f'https://www.linkedin.com/jobs/view/{number}',
                          'company': 'Acme', 'title': f'Engineer {number}'}, 'test')
        rows.append(dict(discovery.db.execute('SELECT * FROM opportunities WHERE id=?', (len(rows) + 1,)).fetchone()))
    protected, target = rows
    task = store.start(str(target['id']), 'scan', json.dumps({'source': {'opportunity_id': str(target['id'])}}))
    task_id = task['task_id']
    report = directory / 'artifacts' / task_id / 'report.md'
    report.parent.mkdir(parents=True)
    report.write_text('exclusive report')
    shared = directory / 'artifacts' / 'shared.md'
    shared.write_text('shared')
    with discovery.db:
        for row, path in ((target, report), (target, shared), (protected, shared)):
            discovery.db.execute('INSERT INTO artifacts(opportunity_id,kind,path,sha256) VALUES(?,?,?,?)',
                                 (row['id'], str(path), str(path), 'hash'))
        discovery.db.execute("INSERT INTO application_lifecycle(opportunity_id,status) VALUES(?,'applied')", (str(protected['id']),))
        discovery.db.execute('CREATE TABLE notification_deliveries(opportunity_id TEXT,report_hash TEXT,status TEXT)')
        discovery.db.execute("INSERT INTO notification_deliveries VALUES(?,'hash','delivered')", (str(target['id']),))
    observation = closure(target)
    assert save_observation(discovery.db, target, observation)
    assert delete_closed(discovery.db, directory, protected, closure(protected)) == 'protected'
    assert delete_closed(discovery.db, directory, target,
                         {**observation, 'code': 'ashby_api_unlisted'}) == 'unconfirmed'
    assert delete_closed(discovery.db, directory, target,
                         {**observation, 'via_api': False, 'code': 'http_gone',
                          'evidence': {'status': 404, 'source_url': target['url'], 'final_url': 'https://example.org/search'}}) == 'unconfirmed'
    with execution_lock(directory, str(target['id'])):
        assert delete_closed(discovery.db, directory, target, observation) == 'busy'
    try:
        store.start(str(target['id']), 'score', '{}')
        raise AssertionError('Closed opportunity started new work')
    except ValueError as error:
        assert 'closed' in str(error)
    assert discovery.ingest({'url': target['url'] + '?utm_source=other', 'company': 'Acme', 'title': 'reinserted'}, 'test') is None
    with patch('career_ops.opportunity_cleanup.shutil.rmtree', side_effect=OSError('disk busy')):
        assert delete_closed(discovery.db, directory, target, observation) == 'cleanup_pending'
    assert not discovery.db.execute('SELECT 1 FROM opportunities WHERE id=?', (target['id'],)).fetchone()
    assert not store.db.execute('SELECT 1 FROM tasks WHERE task_id=?', (task_id,)).fetchone()
    assert not discovery.db.execute('SELECT 1 FROM notification_deliveries WHERE opportunity_id=?', (str(target['id']),)).fetchone()
    assert shared.exists() and report.parent.exists()
    assert not cleanup_pending(discovery.db, directory)
    assert not report.exists() and shared.exists()
    payload = json.loads(discovery.db.execute('SELECT payload FROM scan_outcomes WHERE url=?', (target['url'],)).fetchone()[0])
    assert 'cleanup' not in payload and 'pending_opportunity' not in payload
    fresh = discovery.ingest({'url': target['url'].replace('/12', '/13'), 'company': 'Acme', 'title': target['role']}, 'test')
    assert fresh and fresh['id'] == target['id']
    assert not discovery.db.execute('PRAGMA foreign_key_check').fetchall()
    store.close()
    discovery.close()
    applications.close()
    interviews.close()

print('opportunity cleanup: explicit evidence, active lock, submitted/shared protection and crash recovery passed')

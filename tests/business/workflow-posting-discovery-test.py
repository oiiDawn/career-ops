"""Exercise real posting identities through configured/global discovery and checkpoint publication."""

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from career_ops.discovery.configured import discover
from career_ops.discovery.reverse_runner import discover_global
from career_ops.discovery.fingerprint import fingerprint
from career_ops.discovery.store import DiscoveryStore
from career_ops.tasks import discovery_query, discovered_scan_source

POSTINGS = json.loads((ROOT / 'tests/fixtures/discovery-real-postings.json').read_text())['postings']
NOW = datetime.now(timezone.utc)
CONFIG = 'company_aliases:\n  Siemens: [西门子]\ntracked_companies:\n  - name: Siemens fixture\n    provider: search\n'


def capture(directory, url):
    posting = next(p for p in POSTINGS.values() if p['url'] == url)
    return {'text': posting['description'], 'url': url, 'retrieved_at': NOW.isoformat()}


with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary); config = root / 'portals.yml'; config.write_text(CONFIG)
    jobs = [{**POSTINGS['472'], 'description': ''}, POSTINGS['512']]
    collected = ([{'status': 'fetched', 'provider': 'search', 'jobs': jobs}], [])
    with patch('career_ops.discovery.configured.collect_provider_results', return_value=collected):
        result = discover(root / 'work', config, capture=capture)
    assert result['added'] == 1 and result['filtered']['dupes'] == 1, result
    with sqlite3.connect(root / 'work/opportunities.db') as db:
        assert db.execute('SELECT count(*) FROM opportunities').fetchone()[0] == 1
        assert db.execute('SELECT count(*) FROM source_evidence').fetchone()[0] == 2
        assert db.execute('SELECT fingerprint FROM repost_inputs').fetchone()[0] == fingerprint(POSTINGS['472']['description'])
        summary = json.loads(db.execute('SELECT summary FROM scan_runs').fetchone()[0])
        assert summary['newAdded'] == 1 and summary['filtered']['dupes'] == 1
    store = DiscoveryStore(root / 'work/opportunities.db')
    select, join = discovery_query(store)
    posting = store.db.execute(f'SELECT o.*,p.content,p.captured_at,{select} capture_payload FROM opportunities o {join}').fetchone()
    source = discovered_scan_source(posting)
    assert source['jd'] == POSTINGS['472']['description']
    assert source['capture_method'] == 'browser_snapshot'
    store.close()
    with patch('career_ops.discovery.configured.collect_provider_results', side_effect=AssertionError('collector repeated')):
        resumed = discover(root / 'work', config, resume=True,
                           capture=lambda *_: (_ for _ in ()).throw(AssertionError('capture repeated')))
    assert resumed == result
    with patch('career_ops.discovery.configured.collect_provider_results', return_value=collected):
        repeated = discover(root / 'work', config, capture=capture)
    assert repeated['added'] == 0 and repeated['filtered']['dupes'] == 2
    distinct = [{**POSTINGS['472'], 'url': f'https://jobs.siemens.com/en_US/externaljobs/JobDetail/{code}'}
                for code in (526058,526059)]
    with patch('career_ops.discovery.configured.collect_provider_results', return_value=([
        {'status':'fetched','provider':'search','jobs':distinct}], [])):
        kept = discover(root / 'distinct', config, capture=lambda *_: None)
    assert kept['added'] == 2, 'Same-title official requisitions were discarded before ingestion'

with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary); config = root / 'portals.yml'; config.write_text(CONFIG)
    jobs = [{**POSTINGS[str(i)], 'postedAt': NOW.timestamp()*1000} for i in (472,512)]
    def collect(targets, cutoff, include_undated, concurrency):
        return [{'status':'fetched','jobs':jobs} for _ in targets]
    def load_source(*args, **kwargs):
        return ['fixture'], 'ok'
    arguments = dict(ats=['greenhouse'], now_ms=NOW.timestamp()*1000, collect=collect, load_source=load_source)
    result = discover_global(root / 'work', config, **arguments)
    assert result['postingsKept'] == 1, result
    repeated = discover_global(root / 'work', config, **arguments)
    assert repeated['postingsKept'] == 0, repeated
    with sqlite3.connect(root / 'work/opportunities.db') as db:
        assert db.execute('SELECT count(*) FROM opportunities').fetchone()[0] == 1
        assert not db.execute('PRAGMA foreign_key_check').fetchall()

print('posting discovery: configured/global aliases, final-JD fingerprints, counts, distinct requisitions and resumed publication passed')

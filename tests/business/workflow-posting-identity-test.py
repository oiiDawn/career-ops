"""Replay public duplicate postings and protect distinct requisitions at the real ingest boundary."""

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sqlite3
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from career_ops.discovery.dedup import company_aliases
from career_ops.discovery.store import DiscoveryStore
from career_ops.discovery.fingerprint import fingerprint
from career_ops.tasks import discovery_query

POSTINGS = json.loads((ROOT / 'tests/fixtures/discovery-real-postings.json').read_text())['postings']
ALIASES = company_aliases({'Siemens': ['西门子'], 'Intel': ['英特尔'], 'Longbridge': ['长桥证券（新加坡）'],
                           'AIA': ['AIA Hong Kong and Macau', 'AIA International Limited.'],
                           'State Street': ['美国道富银行'], 'Microsoft': ['微软'],
                           'NVIDIA': ['英伟达'], 'Hypebeast': ['Hypebeast Hong Kong Limited']})


def offer(i):
    return dict(POSTINGS[str(i)])


with tempfile.TemporaryDirectory() as temporary:
    store = DiscoveryStore(Path(temporary) / 'opportunities.db', aliases=ALIASES)
    first = store.ingest(offer(472), 'avature-api')
    store.db.execute("UPDATE opportunities SET application_state='submitted' WHERE id=?", (first['id'],))
    store.db.commit()
    capture = store.db.execute('SELECT * FROM page_evidence').fetchone()
    duplicate = store.ingest(offer(512), 'search')
    assert duplicate['id'] == first['id'], 'Siemens 472/512 created two opportunities'
    assert tuple(capture) == tuple(store.db.execute('SELECT * FROM page_evidence').fetchone())
    assert store.db.execute('SELECT application_state FROM opportunities').fetchone()[0] == 'submitted'
    assert store.db.execute('SELECT count(*) FROM source_evidence').fetchone()[0] == 2
    select, join = discovery_query(store)
    primary_capture = store.db.execute(f'SELECT {select} FROM opportunities o {join} WHERE o.id=?', (first['id'],)).fetchone()[0]
    assert json.loads(primary_capture)['url'] == offer(472)['url'], 'Alternate-source evidence replaced the primary capture'
    replay = {**offer(512), 'url': 'https://www.linkedin.com/jobs/view/4479386764?trackingId=new', 'company': 'Unrecognized label'}
    assert store.ingest(replay, 'search')['id'] == first['id'], 'Source aliases must survive changed labels'
    store.close()
    store = DiscoveryStore(Path(temporary) / 'opportunities.db')
    assert store.ingest(replay, 'search')['id'] == first['id'], 'Source aliases must survive reopen/resume'
    store.close()

for left, right in [(233,133), (240,134), (170,281), (279,250), (529,409), (529,440), (195,81), (361,501)]:
    with tempfile.TemporaryDirectory() as temporary:
        store = DiscoveryStore(Path(temporary) / 'opportunities.db', aliases=ALIASES)
        a = store.ingest(offer(left), 'fixture')
        b = store.ingest(offer(right), 'fixture')
        assert a['id'] == b['id'], (left, right, 'confirmed duplicate was not resolved')
        store.close()

for primary, duplicates in [(472,[512]), (233,[133]), (240,[134]), (170,[281]), (279,[250]),
                             (529,[409,440]), (451,[464]), (490,[462]), (195,[81]), (361,[501]),
                             (5,[144]), (123,[349]), (456,[514])]:
    with tempfile.TemporaryDirectory() as temporary:
        store = DiscoveryStore(Path(temporary) / 'opportunities.db')
        a = store.ingest(offer(primary), 'fixture')
        for duplicate in duplicates:
            d = offer(duplicate)
            store.db.execute('INSERT INTO scan_observations(opportunity_id,url,company,title,observed_on) VALUES(?,?,?,?,?)',
                             (a['id'], d['url'], d['company'], d['title'], '2026-10-18'))
        store.db.commit()
        for duplicate in duplicates:
            d = offer(duplicate)
            assert store.ingest({**d, 'company': 'Changed source label'}, 'fixture')['id'] == a['id'], (primary,duplicate)
        store.close()

with tempfile.TemporaryDirectory() as temporary:
    store = DiscoveryStore(Path(temporary) / 'opportunities.db', aliases=ALIASES)
    base = offer(472)
    row = store.ingest({**base, 'description': '', 'fingerprint': '', 'scan_jd': {'text': base['description']}}, 'fixture')
    assert store.db.execute('SELECT fingerprint FROM repost_inputs').fetchone()[0] == fingerprint(base['description'])
    for index, changed in enumerate([
        {'location': 'Shanghai'}, {'company': 'Unrelated Employer'},
        {'description': base['description'].replace('3 年', '5 年')},
        {'description': base['description'].replace('核心能力要求', '必须具备支付清算系统经验。\n核心能力要求')},
    ]):
        d = {**offer(512), **changed, 'url': f'https://www.linkedin.com/jobs/view/{9000000+index}'}
        assert store.ingest(d, 'fixture')['id'] != row['id'], index
    for code in ['JR-64011', 'JR-63708', 'R-798477', 'R-797003']:
        d = {**base, 'url': 'https://aia.wd3.myworkdayjobs.com/External/job/Shanghai/Engineer_' + code}
        assert store.ingest(d, 'fixture')['created'], code
    store.close()

for left, right in [(4,6), (8,9), (10,358), (51,52), (55,56), (520,527), (522,528), (292,307), (439,465)]:
    with tempfile.TemporaryDirectory() as temporary:
        store = DiscoveryStore(Path(temporary) / 'opportunities.db', aliases=ALIASES)
        a = store.ingest(offer(left), 'fixture')
        b = store.ingest(offer(right), 'fixture')
        assert a['id'] != b['id'], (left, right, 'distinct or unconfirmed postings were merged')
        store.close()

with tempfile.TemporaryDirectory() as temporary:
    database = Path(temporary) / 'opportunities.db'
    DiscoveryStore(database).close()
    def ingest(i):
        store = DiscoveryStore(database, aliases=ALIASES)
        try:
            return store.ingest(offer(i), 'fixture')['id']
        finally:
            store.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(ingest, [472,512]))
    assert len(set(ids)) == 1, 'Concurrent discoveries bypassed the transaction-time resolver'
    with sqlite3.connect(database) as db:
        assert not db.execute('PRAGMA foreign_key_check').fetchall()

print('posting identity: real duplicate, distinct requisition, submitted-state, evidence, replay and concurrency checks passed')

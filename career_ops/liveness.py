"""Persist posting checks and project their current, nonblocking display status."""

from __future__ import annotations

from datetime import datetime, timezone
from contextlib import contextmanager
import fcntl
import hashlib
import json
import re
from pathlib import Path
import sqlite3
from urllib.parse import urlsplit

from career_ops.discovery.dedup import url_key


SCHEMA = """
CREATE TABLE IF NOT EXISTS liveness_observations (
  id INTEGER PRIMARY KEY,
  opportunity_id INTEGER NOT NULL REFERENCES opportunities(id),
  url TEXT NOT NULL,
  checked_at TEXT NOT NULL,
  result TEXT NOT NULL CHECK(result IN ('active','expired','uncertain')),
  code TEXT NOT NULL,
  payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS latest_liveness ON liveness_observations(opportunity_id,id);
"""


def closed_url(db: sqlite3.Connection, url: str, *, maintenance_only: bool = False) -> bool:
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='scan_outcomes'").fetchone():
        return False
    return any(url_key(row[0]) == url_key(url)
               and (not maintenance_only or json.loads(row[1]).get('maintenance_closed'))
               for row in db.execute("SELECT url,payload FROM scan_outcomes WHERE status='skipped_expired'"))


def require_open(db: sqlite3.Connection, opportunity_id: str) -> None:
    """Check business identity at write boundaries; standalone workflow stores have no postings."""
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='opportunities'").fetchone():
        return
    row = db.execute('SELECT url FROM opportunities WHERE id=?', (opportunity_id,)).fetchone()
    if not row or closed_url(db, row[0], maintenance_only=True):
        raise ValueError(f'Opportunity is removed or confirmed closed: {opportunity_id}')


@contextmanager
def execution_lock(directory: Path, opportunity_id: str):
    """Serialize deletion with model/file/network work for one opportunity only."""
    key = hashlib.sha256(str(opportunity_id).encode()).hexdigest()
    locks = directory / '.locks'
    locks.mkdir(parents=True, exist_ok=True)
    with (locks / f'opportunity-{key}.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def explicit_closure(observation: dict) -> bool:
    """Validate posting-bound closure evidence, including the confirmed LinkedIn UI rule."""
    if not isinstance(observation, dict) or observation.get('result') != 'expired':
        return False
    evidence, code = observation.get('evidence', {}), observation.get('code', '')
    if not isinstance(evidence, dict) or not isinstance(code, str):
        return False
    if observation.get('via_api'):
        if evidence.get('posting_url') != observation.get('url'):
            return False
        if code in {'greenhouse_api_gone', 'workday_api_gone'}:
            return evidence.get('status') in {404, 410}
        return (code == 'linkedin_closed_marker' and evidence.get('status') == 200
                and isinstance(evidence.get('excerpt'), str) and evidence['excerpt'].lower() in
                {'no longer accepting applications', 'not currently accepting applications',
                 '已停止接受求职申请', '不再接受應徵'})
    if (evidence.get('source_url') != observation.get('url')
            or url_key(evidence.get('final_url')) != url_key(observation.get('url'))):
        return False
    if code == 'linkedin_no_apply':
        source = urlsplit(observation['url'])
        posting_id = re.fullmatch(r'/jobs/view/(?:.*-)?(\d+)/?', source.path)
        return (source.scheme == 'https' and bool(re.fullmatch(r'(?:[\w-]+\.)*linkedin\.com', source.hostname or ''))
                and posting_id is not None and evidence.get('posting_id') == posting_id[1]
                and evidence.get('status') == 200 and evidence.get('settled') is True
                and evidence.get('apply_control_present') is False
                and isinstance(evidence.get('title'), str) and bool(evidence['title'].strip())
                and isinstance(evidence.get('description_length'), int) and evidence['description_length'] >= 300)
    return ((code == 'http_gone' and evidence.get('status') in {404, 410})
            or (code == 'expired_body' and evidence.get('status') == 200
                and bool(evidence.get('excerpt'))))


def save_observation(db: sqlite3.Connection, opportunity: dict, observation: dict) -> bool:
    """Bind a validated collector result to the exact opportunity selected before I/O."""
    if (observation.get('url') != opportunity['url']
            or observation.get('result') not in {'active', 'expired', 'uncertain'}
            or not isinstance(observation.get('via_api'), bool)
            or not isinstance(observation.get('code'), str)
            or not observation['code']
            or not isinstance(observation.get('evidence'), dict)
            or not isinstance(observation.get('checked_at'), str)):
        raise ValueError('Invalid liveness observation')
    checked = datetime.fromisoformat(observation['checked_at'].replace('Z', '+00:00'))
    if checked.tzinfo is None:
        raise ValueError('Liveness observation needs a timezone')
    checked = checked.astimezone(timezone.utc)
    db.execute('BEGIN IMMEDIATE')
    try:
        current = db.execute('SELECT url,created_at FROM opportunities WHERE id=?', (opportunity['id'],)).fetchone()
        if not current or tuple(current) != (opportunity['url'], opportunity['created_at']):
            db.rollback()
            return False
        db.execute('INSERT INTO liveness_observations(opportunity_id,url,checked_at,result,code,payload) '
                   'VALUES(?,?,?,?,?,?)', (opportunity['id'], opportunity['url'], checked.isoformat(),
                   observation['result'], observation['code'], json.dumps(observation, ensure_ascii=False)))
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise


def current_observations(db: sqlite3.Connection, *, now: datetime | None = None) -> dict[str, dict]:
    """Calculate freshness at read time without changing eligibility or frozen reports."""
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='liveness_observations'").fetchone():
        return {}
    now = now or datetime.now(timezone.utc)
    views = {}
    for row in db.execute('SELECT o.*, (SELECT MAX(a.checked_at) FROM liveness_observations a '
                          "WHERE a.opportunity_id=o.opportunity_id AND a.result='active') AS last_active "
                          'FROM liveness_observations o WHERE o.id=(SELECT MAX(n.id) '
                          'FROM liveness_observations n WHERE n.opportunity_id=o.opportunity_id)'):
        payload = json.loads(row['payload'])
        age = (now - datetime.fromisoformat(row['checked_at'])).total_seconds()
        stale = not 0 <= age < 86400
        views[str(row['opportunity_id'])] = {
            'liveness': 'uncertain' if stale else row['result'],
            'liveness_checked_at': row['checked_at'], 'liveness_last_active_at': row['last_active'],
            'liveness_reason': '检查结果已过期' if stale else payload.get('reason', row['code']),
        }
    return views

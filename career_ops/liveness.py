"""Persist posting checks and project their current, nonblocking display status."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import sqlite3


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


def save_observation(db: sqlite3.Connection, opportunity: dict, observation: dict) -> bool:
    """Bind a validated collector result to the exact opportunity selected before I/O."""
    if (observation.get('url') != opportunity['url']
            or observation.get('result') not in {'active', 'expired', 'uncertain'}
            or not isinstance(observation.get('via_api'), bool)
            or not isinstance(observation.get('code'), str)
            or not observation['code']
            or not isinstance(observation.get('evidence'), dict)):
        raise ValueError('Invalid liveness observation')
    checked = datetime.fromisoformat(observation['checked_at'].replace('Z', '+00:00'))
    if checked.tzinfo is None:
        raise ValueError('Liveness observation needs a timezone')
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

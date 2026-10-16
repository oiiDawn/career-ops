"""Delete explicitly closed, unsubmitted postings and recover their exclusive file cleanup."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver

from career_ops.discovery.dedup import url_key
from career_ops.liveness import execution_lock, explicit_closure


OPPORTUNITY_TABLES = (
    'workflow_source_evidence', 'notification_deliveries', 'application_activity',
    'application_events', 'application_followup_directives', 'application_lifecycle',
    'source_evidence', 'page_evidence', 'repost_inputs', 'opportunity_events',
    'scan_observations', 'eligibility', 'evaluations', 'artifacts', 'checkpoints',
    'deliveries', 'liveness_observations',
)


def tables(db):
    return {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def submitted(db, opportunity_id):
    row = db.execute('SELECT application_state FROM opportunities WHERE id=?', (opportunity_id,)).fetchone()
    return (not row or row[0] not in {'none', 'preparing'} or
            ('application_lifecycle' in tables(db) and db.execute(
                'SELECT 1 FROM application_lifecycle WHERE opportunity_id=?', (str(opportunity_id),)).fetchone()))


def _paths(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key == 'path' and isinstance(item, str):
                yield item
            else:
                yield from _paths(item)
    elif isinstance(value, list):
        for item in value:
            yield from _paths(item)


def _manifest(db, directory, opportunity):
    present, paths, task_ids, interview_ids = tables(db), set(), [], []
    if 'artifacts' in present:
        paths.update(row[0] for row in db.execute('SELECT path FROM artifacts WHERE opportunity_id=?', (opportunity['id'],)))
    for table, ids in (('tasks', task_ids), ('interview_tasks', interview_ids)):
        if table not in present:
            continue
        for row in db.execute(f'SELECT * FROM {table} WHERE opportunity_id=?', (str(opportunity['id']),)):
            ids.append(row['task_id'])
            if table == 'tasks':
                paths.add(str(directory / 'artifacts' / row['task_id']))
                inputs = json.loads(row['input_payload'])
                payload = {'inputs': inputs} if row['module'] == 'apply' else inputs
                key = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
                drafts = Path(os.environ.get('CAREER_OPS_DRAFT_ROOT', directory / 'workflow-drafts'))
                paths.add(str(drafts / key))
                paths.update(_paths(inputs))
    if 'task_context' in present:
        for task_id in task_ids:
            for row in db.execute('SELECT payload FROM task_context WHERE task_id=?', (task_id,)):
                paths.update(_paths(json.loads(row[0])))
    threads = []
    checkpoint = directory / 'workflow-checkpoints.db'
    if checkpoint.exists():
        with sqlite3.connect(f'file:{checkpoint.resolve()}?mode=ro', uri=True) as snapshots:
            if snapshots.execute("SELECT 1 FROM sqlite_master WHERE name='checkpoints'").fetchone():
                threads = [row[0] for row in snapshots.execute('SELECT DISTINCT thread_id FROM checkpoints')
                           if any(row[0].startswith(task + ':') for task in task_ids)
                           or any(row[0].startswith('interview:' + task + ':') for task in interview_ids)
                           or row[0].startswith('notification:' + str(opportunity['id']) + ':')]
    return {'paths': sorted(paths), 'threads': threads}


def _shared(db, path):
    """Check surviving registered and embedded artifact references before removing a subtree."""
    present = tables(db)
    for table, column in (('artifacts', 'path'), ('results', 'payload'), ('tasks', 'input_payload'),
                          ('task_context', 'payload'), ('interview_tasks', 'input_payload'),
                          ('interview_drafts', 'artifact'), ('interview_results', 'artifact'),
                          ('workflow_source_evidence', 'payload'), ('source_evidence', 'payload')):
        if table in present and db.execute(f'SELECT 1 FROM {table} WHERE instr({column},?)>0 LIMIT 1',
                                          (str(path),)).fetchone():
            return True
    return False


def _cleanup(db, directory, url, payload):
    manifest = payload.get('cleanup', {})
    failures = []
    roots = [directory / 'artifacts', directory / 'workflow-drafts', directory / 'cache']
    drafts = Path(os.environ.get('CAREER_OPS_DRAFT_ROOT', directory / 'workflow-drafts'))
    roots.append(drafts)
    roots = [root.absolute() for root in roots]
    candidates = set(manifest.get('paths', []))
    for cached in (directory / 'cache' / 'scan-jds').glob('*.json'):
        try:
            if url_key(json.loads(cached.read_text()).get('requested_url')) == url_key(url):
                candidates.add(str(cached))
        except (ValueError, OSError):
            continue
    for value in sorted(candidates, key=len):
        path = Path(value).absolute()
        try:
            if not path.exists() and not path.is_symlink():
                continue
            if _shared(db, path):
                continue
            if not any(path != root and path.is_relative_to(root) and
                       path.resolve().is_relative_to(root.resolve()) for root in roots):
                raise ValueError(f'Unowned cleanup path: {path}')
            if path.is_symlink():
                raise ValueError(f'Symlink cleanup path: {path}')
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
        except (OSError, ValueError) as error:
            failures.append(str(error))
    checkpoint = directory / 'workflow-checkpoints.db'
    if checkpoint.exists() and manifest:
        try:
            with SqliteSaver.from_conn_string(str(checkpoint)) as saver:
                for thread in manifest.get('threads', []):
                    saver.delete_thread(thread)
        except (sqlite3.Error, OSError) as error:
            failures.append(str(error))
    if not failures and 'cleanup' in payload:
        payload = {key: value for key, value in payload.items() if key != 'cleanup'}
        with db:
            db.execute('UPDATE scan_outcomes SET payload=? WHERE url=? AND status=?',
                       (json.dumps(payload), url, 'skipped_expired'))
    return failures


def cleanup_pending(db, directory):
    failures = []
    for row in db.execute("SELECT url,payload FROM scan_outcomes WHERE status='skipped_expired'").fetchall():
        payload = json.loads(row['payload'])
        if payload.get('maintenance_closed') and not payload.get('pending_opportunity'):
            failures.extend(_cleanup(db, directory, row['url'], payload))
    return failures


def delete_closed(db, directory: Path, opportunity: dict, observation: dict) -> str:
    """Commit business removal before idempotent physical cleanup; never interrupt active work."""
    if not explicit_closure(observation):
        return 'unconfirmed'
    outcome = {'maintenance_closed': True, 'code': observation['code'],
               'checked_at': observation['checked_at'], 'pending_opportunity': opportunity['id']}
    db.execute('BEGIN IMMEDIATE')
    try:
        current = db.execute('SELECT url,created_at FROM opportunities WHERE id=?', (opportunity['id'],)).fetchone()
        if (not current or tuple(current) != (opportunity['url'], opportunity['created_at'])
                or submitted(db, opportunity['id'])):
            db.rollback()
            return 'protected'
        db.execute('INSERT INTO scan_outcomes(url,status,payload) VALUES(?,?,?) ON CONFLICT(url) '
                   'DO UPDATE SET status=excluded.status,payload=excluded.payload',
                   (opportunity['url'], 'skipped_expired', json.dumps(outcome)))
        db.commit()
    except Exception:
        db.rollback()
        raise
    try:
        with execution_lock(directory, str(opportunity['id'])):
            db.execute('BEGIN IMMEDIATE')
            try:
                current = db.execute('SELECT url,created_at FROM opportunities WHERE id=?', (opportunity['id'],)).fetchone()
                if (not current or tuple(current) != (opportunity['url'], opportunity['created_at'])
                        or submitted(db, opportunity['id'])):
                    db.rollback()
                    return 'protected'
                present = tables(db)
                manifest = _manifest(db, directory, opportunity)
                for table, children in (
                    ('interview_tasks', ('interview_drafts', 'interview_results', 'interview_feedback', 'interview_events')),
                    ('tasks', ('events', 'task_context', 'results')),
                ):
                    ids = [row[0] for row in db.execute(f'SELECT task_id FROM {table} WHERE opportunity_id=?',
                                                       (str(opportunity['id']),))] if table in present else []
                    for task_id in ids:
                        if table == 'tasks' and 'job_company_profiles' in present:
                            db.execute('DELETE FROM job_company_profiles WHERE result_key IN '
                                       '(SELECT result_key FROM results WHERE task_id=?)', (task_id,))
                        for child in children:
                            if child in present:
                                db.execute(f'DELETE FROM {child} WHERE task_id=?', (task_id,))
                        db.execute(f'DELETE FROM {table} WHERE task_id=?', (task_id,))
                for table in OPPORTUNITY_TABLES:
                    if table in present:
                        db.execute(f'DELETE FROM {table} WHERE opportunity_id=?', (str(opportunity['id']),))
                db.execute('DELETE FROM opportunities WHERE id=?', (opportunity['id'],))
                outcome.pop('pending_opportunity')
                outcome['cleanup'] = manifest
                db.execute('UPDATE scan_outcomes SET payload=? WHERE url=?', (json.dumps(outcome), opportunity['url']))
                db.commit()
            except Exception:
                db.rollback()
                raise
    except BlockingIOError:
        return 'busy'
    failures = _cleanup(db, directory, opportunity['url'], outcome)
    return 'cleanup_pending' if failures else 'deleted'

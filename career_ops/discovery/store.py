"""Persist discovered opportunities and immutable source observations in SQLite."""

from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path
import sqlite3

from career_ops.liveness import SCHEMA as LIVENESS_SCHEMA, closed_url
from career_ops.discovery.dedup import url_key
from career_ops.discovery.fingerprint import fingerprint
from career_ops.discovery.identity import resolve_posting


SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS opportunities (
  id INTEGER PRIMARY KEY, url TEXT NOT NULL UNIQUE, company TEXT NOT NULL,
  role TEXT NOT NULL, identity TEXT NOT NULL UNIQUE, source TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'discovered' CHECK(state IN ('discovered','evaluating','eligible','ineligible','evaluated')),
  application_state TEXT NOT NULL DEFAULT 'none' CHECK(application_state IN ('none','preparing','submitted')),
  claimed_by TEXT, attempts INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS source_evidence (
  id INTEGER PRIMARY KEY, opportunity_id INTEGER NOT NULL REFERENCES opportunities(id),
  source TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS page_evidence (
  opportunity_id INTEGER PRIMARY KEY REFERENCES opportunities(id), content TEXT NOT NULL,
  content_hash TEXT NOT NULL, captured_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS repost_inputs (
  opportunity_id INTEGER PRIMARY KEY REFERENCES opportunities(id), fingerprint TEXT NOT NULL,
  first_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS opportunity_events (
  id INTEGER PRIMARY KEY, opportunity_id INTEGER NOT NULL REFERENCES opportunities(id),
  type TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS scan_outcomes (
  url TEXT PRIMARY KEY, status TEXT NOT NULL, payload TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS scan_runs (
  id INTEGER PRIMARY KEY, operation TEXT NOT NULL, summary TEXT NOT NULL, run_id TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS scan_observations (
  id INTEGER PRIMARY KEY, opportunity_id INTEGER NOT NULL REFERENCES opportunities(id),
  url TEXT NOT NULL, company TEXT NOT NULL, title TEXT NOT NULL, observed_on TEXT NOT NULL,
  UNIQUE(url, observed_on)
);
CREATE TABLE IF NOT EXISTS source_health (
  id INTEGER PRIMARY KEY, scan_run_id INTEGER NOT NULL REFERENCES scan_runs(id),
  source TEXT NOT NULL, status TEXT NOT NULL, checked_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS eligibility (
  opportunity_id INTEGER PRIMARY KEY REFERENCES opportunities(id),
  status TEXT NOT NULL CHECK(status IN ('pass','fail','unknown')),
  evidence TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS evaluations (
  opportunity_id INTEGER PRIMARY KEY REFERENCES opportunities(id), lower_score REAL,
  upper_score REAL, coverage REAL, dimension_scores TEXT, report_hash TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS artifacts (
  id INTEGER PRIMARY KEY, opportunity_id INTEGER NOT NULL REFERENCES opportunities(id),
  kind TEXT NOT NULL, path TEXT NOT NULL, sha256 TEXT NOT NULL,
  UNIQUE(opportunity_id, kind, path)
);
CREATE TABLE IF NOT EXISTS checkpoints (
  opportunity_id INTEGER NOT NULL REFERENCES opportunities(id), phase TEXT NOT NULL,
  input_hash TEXT NOT NULL, output_hash TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(opportunity_id, phase)
);
CREATE TABLE IF NOT EXISTS deliveries (
  opportunity_id INTEGER NOT NULL REFERENCES opportunities(id), channel TEXT NOT NULL,
  report_hash TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'claimed'
  CHECK(status IN ('claimed','delivered')),
  delivered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(opportunity_id, channel, report_hash)
);
"""


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class DiscoveryStore:
    """Own one discovery transaction; callers decide filters and capture policy."""

    def __init__(self, path: Path, *, aliases: dict[str, str] | None = None):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.aliases = aliases or {}
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.executescript(SCHEMA + LIVENESS_SCHEMA)
        self._migrate()

    def _migrate(self) -> None:
        """Accept business stores created before the canonical identity columns."""
        columns = {row["name"] for row in self.db.execute("PRAGMA table_info(opportunities)")}
        if "attempts" not in columns:
            self.db.execute("ALTER TABLE opportunities ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0")
        if "application_state" not in columns:
            self.db.execute("ALTER TABLE opportunities ADD COLUMN application_state TEXT NOT NULL DEFAULT 'none'")
        if "identity" not in columns:
            self.db.execute("ALTER TABLE opportunities ADD COLUMN identity TEXT")
            self.db.execute("CREATE UNIQUE INDEX IF NOT EXISTS opportunities_identity ON opportunities(identity)")
        self.db.execute('UPDATE opportunities SET identity=url WHERE identity IS NULL OR identity<>url')
        delivery_columns = {row["name"] for row in self.db.execute("PRAGMA table_info(deliveries)")}
        if "status" not in delivery_columns:
            self.db.execute("ALTER TABLE deliveries ADD COLUMN status TEXT NOT NULL DEFAULT 'claimed'")
        run_columns = {row["name"] for row in self.db.execute("PRAGMA table_info(scan_runs)")}
        if "run_id" not in run_columns:
            self.db.execute("ALTER TABLE scan_runs ADD COLUMN run_id TEXT")
        self.db.execute("CREATE UNIQUE INDEX IF NOT EXISTS scan_runs_run_id ON scan_runs(run_id)")
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def ingest(self, offer: dict, source: str, *, observed_on: str | None = None, run_id: str | None = None) -> dict | None:
        """Resolve current posting identity atomically and retain source-specific evidence."""
        url, company, role = (str(offer.get(key) or "").strip() for key in ("url", "company", "title"))
        if not url or not company or not role:
            raise ValueError("Discovered offer requires URL, company, and title")
        capture = offer.get("scan_jd") if isinstance(offer.get("scan_jd"), dict) else {}
        description = capture.get("text") or offer.get("description") or offer.get("text") or ""
        payload = {**offer, "description": description, "fingerprint": fingerprint(description)}
        if not self.db.in_transaction:
            self.db.execute("BEGIN IMMEDIATE")
        with self.db:
            if closed_url(self.db, url):
                return None
            row = resolve_posting(self.db, {**payload, 'url': url, 'company': company, 'title': role}, self.aliases)
            created = row is None
            if row is None:
                cursor = self.db.execute("INSERT INTO opportunities(url,company,role,identity,source) VALUES(?,?,?,?,?)",
                                         (url, company, role, url, source))
                row = {'id': cursor.lastrowid, 'url': url}
            exists = self.db.execute("SELECT 1 FROM source_evidence WHERE opportunity_id=? AND source=? AND json_extract(payload,'$.url')=?",
                                     (row["id"], source, url)).fetchone()
            if not exists:
                self.db.execute("INSERT INTO source_evidence(opportunity_id,source,payload) VALUES(?,?,?)",
                                (row["id"], source, _json(payload)))
                self.db.execute("INSERT INTO opportunity_events(opportunity_id,type,payload) VALUES(?,'discovered',?)",
                                (row["id"], _json({"source": source, 'run_id': run_id if created else None})))
            primary = url_key(row['url']) == url_key(url)
            if primary and isinstance(description, str) and description.strip():
                self.db.execute("INSERT OR IGNORE INTO page_evidence(opportunity_id,content,content_hash) VALUES(?,?,?)",
                                (row["id"], description, hashlib.sha256(description.encode()).hexdigest()))
            if primary and payload["fingerprint"]:
                self.db.execute("INSERT OR IGNORE INTO repost_inputs(opportunity_id,fingerprint) VALUES(?,?)",
                                (row["id"], payload["fingerprint"]))
            self.db.execute("INSERT OR IGNORE INTO scan_observations(opportunity_id,url,company,title,observed_on) VALUES(?,?,?,?,?)",
                            (row["id"], url, company, role, observed_on or date.today().isoformat()))
            created_in_run = created or bool(run_id and self.db.execute(
                "SELECT 1 FROM opportunity_events WHERE opportunity_id=? AND type='discovered' "
                "AND json_extract(payload,'$.run_id')=? LIMIT 1", (row['id'], run_id),
            ).fetchone())
        return {**row, 'created': created, 'created_in_run': created_in_run}

    def scan_outcome(self, offer: dict, status: str) -> None:
        url = offer.get("url")
        if not isinstance(url, str) or not url:
            raise ValueError("Scan outcome requires URL")
        with self.db:
            if any(url_key(row[0]) == url_key(url) and json.loads(row[1]).get('maintenance_closed')
                   for row in self.db.execute("SELECT url,payload FROM scan_outcomes WHERE status='skipped_expired'")):
                return
            self.db.execute("INSERT INTO scan_outcomes(url,status,payload) VALUES(?,?,?) "
                            "ON CONFLICT(url) DO UPDATE SET status=excluded.status,payload=excluded.payload",
                            (url, status, _json({key: value for key, value in offer.items() if key != "url"})))

    def scan_run(self, operation: str, summary: dict, health: list[dict]) -> int:
        with self.db:
            cursor = self.db.execute("INSERT INTO scan_runs(operation,summary) VALUES(?,?)", (operation, _json(summary)))
            for item in health:
                self.db.execute("INSERT INTO source_health(scan_run_id,source,status,checked_at) VALUES(?,?,?,?)",
                                (cursor.lastrowid, item["company"], item["status"], item["timestamp"]))
        return cursor.lastrowid

    def scan_run_once(self, operation: str, run_id: str, summary: dict, health: list[dict]) -> int:
        """Make a replay after business commit but before checkpoint removal idempotent."""
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute("SELECT id FROM scan_runs WHERE operation=? AND run_id=?", (operation, run_id)).fetchone()
            run_id_existing = row["id"] if row else None
            if run_id_existing is None:
                for row in self.db.execute("SELECT id,summary FROM scan_runs WHERE operation=? AND run_id IS NULL", (operation,)):
                    if json.loads(row["summary"]).get("run_id") == run_id:
                        run_id_existing = row["id"]
                        break
            if run_id_existing is None:
                cursor = self.db.execute("INSERT INTO scan_runs(operation,summary,run_id) VALUES(?,?,?)",
                                         (operation, _json(summary), run_id))
                run_id_existing = cursor.lastrowid
            else:
                self.db.execute("UPDATE scan_runs SET summary=?,run_id=? WHERE id=?",
                                (_json(summary), run_id, run_id_existing))
                self.db.execute("DELETE FROM source_health WHERE scan_run_id=?", (run_id_existing,))
            for item in health:
                self.db.execute("INSERT INTO source_health(scan_run_id,source,status,checked_at) VALUES(?,?,?,?)",
                                (run_id_existing, item["company"], item["status"], item["timestamp"]))
            self.db.commit()
            return run_id_existing
        except Exception:
            self.db.rollback()
            raise

    def health_streaks(self, current: list[dict]) -> dict[str, int]:
        """Count consecutive unhealthy observations, including this run."""
        streaks: dict[str, int] = {}
        rows = self.db.execute("SELECT source AS company,status FROM source_health ORDER BY id")
        for row in [*rows, *current]:
            company = row["company"]
            streaks[company] = 0 if row["status"] in {"reachable", "empty"} else streaks.get(company, 0) + 1
        return streaks

"""Check current postings independently and optionally maintain their business observations."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import os
import selectors
import time
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
from typing import Callable

from dotenv import load_dotenv


from career_ops.context import ROOT


def current_urls(database: Path) -> list[str]:
    """Map Pending, Scored and Awaiting Confirmation to current business rows."""
    with sqlite3.connect(f"file:{database.resolve()}?mode=ro", uri=True) as connection:
        rows = connection.execute(
            "SELECT url FROM opportunities "
            "WHERE state IN ('discovered', 'evaluating', 'eligible', 'evaluated') "
            "AND application_state IN ('none', 'preparing') ORDER BY id"
        ).fetchall()
    return list(dict.fromkeys(url for (url,) in rows))


def input_urls(args: argparse.Namespace) -> list[str]:
    if args.file:
        return [line.strip() for line in args.file.read_text().splitlines()
                if line.strip() and not line.lstrip().startswith("#")]
    if args.urls:
        return args.urls
    return current_urls(args.directory / "opportunities.db")


def observe(urls: list[str], *, headed_fallback: bool, throttle_ms: int,
            on_observation: Callable[[dict], None] | None = None) -> list[dict]:
    """Commit streamed progress before a later URL or collector process can fail."""
    observations = []
    with tempfile.TemporaryDirectory(prefix="career-ops-liveness-") as temporary:
        source = Path(temporary) / "input.json"
        source.write_text(json.dumps({"urls": urls, "headed_fallback": headed_fallback,
                                      "throttle_ms": throttle_ms}))
        command = ["node", str(ROOT / "adapters/node/browser/_liveness-observe.mjs"), str(source)]
        with tempfile.TemporaryFile() as errors, subprocess.Popen(
            command, cwd=ROOT, stdout=subprocess.PIPE, stderr=errors,
        ) as process, selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            buffer = b""
            deadline = time.monotonic() + max(900, len(urls) * (120 + 2 * throttle_ms / 1000) + 60)
            try:
                while selector.get_map():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("Liveness collector exceeded its time budget")
                    if not selector.select(min(remaining, 1)):
                        continue
                    chunk = os.read(process.stdout.fileno(), 65536)
                    if not chunk:
                        selector.unregister(process.stdout)
                        break
                    buffer += chunk
                    while b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        observation = json.loads(line)
                        index = len(observations)
                        if (index >= len(urls) or not isinstance(observation, dict)
                                or observation.get("url") != urls[index]
                                or observation.get("result") not in {"active", "expired", "uncertain"}
                                or not isinstance(observation.get("via_api"), bool)):
                            raise ValueError("Invalid liveness collector observation")
                        observations.append(observation)
                        if on_observation:
                            on_observation(observation)
                process.wait(timeout=max(0.1, deadline - time.monotonic()))
                if process.returncode or buffer or len(observations) != len(urls):
                    errors.seek(0)
                    raise RuntimeError(errors.read().decode(errors="replace")[-2000:] or "Incomplete liveness collection")
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
    return observations


def maintain(directory: Path, *, headed_fallback: bool, throttle_ms: int) -> dict:
    """Persist each posting independently; errors never change eligibility or scoring."""
    from career_ops.discovery.store import DiscoveryStore
    from career_ops.liveness import save_observation, explicit_closure, closed_url
    from career_ops.opportunity_cleanup import cleanup_pending, delete_closed, submitted

    store = DiscoveryStore(directory / "opportunities.db")
    locks = directory / ".locks"
    locks.mkdir(exist_ok=True)
    try:
        with (locks / "liveness.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return {"status": "busy", "observations": [], "errors": []}
            cleanup_errors = cleanup_pending(store.db, directory)
            for pending in store.db.execute("SELECT url,payload FROM scan_outcomes WHERE status='skipped_expired'").fetchall():
                payload = json.loads(pending['payload'])
                if not payload.get('pending_opportunity'):
                    continue
                current = store.db.execute('SELECT id,url,created_at FROM opportunities WHERE id=? AND url=?',
                                           (payload['pending_opportunity'], pending['url'])).fetchone()
                if current:
                    evidence = store.db.execute("SELECT payload FROM liveness_observations WHERE opportunity_id=? "
                                                "AND result='expired' ORDER BY id DESC LIMIT 1", (current['id'],)).fetchone()
                    if evidence:
                        try:
                            delete_closed(store.db, directory, dict(current), json.loads(evidence[0]))
                        except (OSError, ValueError, sqlite3.Error) as error:
                            cleanup_errors.append(str(error))
            rows = {row["url"]: dict(row) for row in store.db.execute(
                "SELECT id,url,created_at FROM opportunities WHERE state IN "
                "('discovered','evaluating','eligible','evaluated') AND application_state IN ('none','preparing')"
            )}
            rows = {url: row for url, row in rows.items() if not submitted(store.db, row["id"]) and not closed_url(store.db, url)}
            observations, errors, completed = [], cleanup_errors, set()

            def persist(observation):
                url = observation["url"]
                completed.add(url)
                try:
                    confirmed = explicit_closure(observation)
                    if observation.get('result') == 'expired' and not confirmed:
                        observation = {**observation, 'result': 'uncertain'}
                    if save_observation(store.db, rows[url], observation):
                        observations.append(observation)
                        if confirmed:
                            status = delete_closed(store.db, directory, rows[url], observation)
                            if status == 'cleanup_pending':
                                errors.append(f'{url}: physical cleanup pending')
                except (OSError, ValueError, KeyError, sqlite3.Error) as error:
                    errors.append(f"{url}: {error}")

            try:
                observe(list(rows), headed_fallback=headed_fallback, throttle_ms=throttle_ms,
                        on_observation=persist)
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                errors.append(str(error))
                for url in rows.keys() - completed:
                    persist({"url": url, "result": "uncertain", "code": "collection_error",
                             "checked_at": datetime.now(timezone.utc).isoformat(), "via_api": False,
                             "reason": str(error)[:500], "evidence": {}})
            return {"status": "partial" if errors else "completed", "observations": observations, "errors": errors}
    finally:
        store.close()


def check(*, select_urls: Callable[[], list[str]], reader: Callable[[list[str]], list[dict]]) -> dict:
    """Read observations once and summarize them without persistent execution state."""
    observations = reader(select_urls())
    counts = {"active": 0, "expired": 0, "uncertain": 0, "via_api": 0}
    for observation in observations:
        counts[observation["result"]] += 1
        counts["via_api"] += int(observation["via_api"])
    return {"observations": observations, "summary": counts}


def main(argv: list[str] | None = None) -> int:
    load_dotenv(ROOT / ".env", override=False)
    argv = list(sys.argv[1:] if argv is None else argv)
    argv = ["--throttle=5000" if value == "--throttle" else value for value in argv]
    parser = argparse.ArgumentParser(description="Check current opportunity URLs without changing business state")
    parser.add_argument("--directory", type=Path, default=ROOT / "data")
    parser.add_argument("--file", type=Path)
    parser.add_argument("--apply", action="store_true", help="Maintain observations for current stored postings")
    parser.add_argument("--no-fallback", action="store_true")
    parser.add_argument("--throttle")
    parser.add_argument("urls", nargs="*")
    args = parser.parse_args(argv)
    if args.file and args.urls:
        parser.error("--file cannot be combined with URLs")
    if args.apply and (args.file or args.urls):
        parser.error("--apply requires database-backed selection, without URLs or --file")
    try:
        throttle_ms = int(args.throttle) if args.throttle is not None else 0
    except ValueError:
        parser.error("--throttle requires milliseconds")
    if throttle_ms < 0:
        parser.error("--throttle must be nonnegative")
    if args.throttle is not None and throttle_ms == 0:
        throttle_ms = 5000
    if args.apply:
        result = maintain(args.directory, headed_fallback=not args.no_fallback, throttle_ms=throttle_ms)
        print(json.dumps(result, ensure_ascii=False))
        return int(bool(result["errors"]))
    notes = []
    if not args.no_fallback:
        notes.append("headed fallback on challenge")
    if throttle_ms:
        notes.append(f"throttle ~{throttle_ms / 1000:g}-{2 * throttle_ms / 1000:g}s")
    suffix = f" ({', '.join(notes)})" if notes else ""

    def select_urls() -> list[str]:
        urls = input_urls(args)
        print(f"Checking {len(urls)} URL(s)...{suffix}\n", flush=True)
        return urls

    try:
        result = check(select_urls=select_urls,
                       reader=lambda values: observe(values, headed_fallback=not args.no_fallback,
                                                     throttle_ms=throttle_ms))
    except (OSError, sqlite3.Error, subprocess.SubprocessError, ValueError, RuntimeError) as error:
        parser.exit(1, f"Liveness check failed: {error}\n")
    for observation in result["observations"]:
        icon = {"active": "✅", "expired": "❌", "uncertain": "⚠️"}[observation["result"]]
        print(f"{icon} {observation['result']:<10}{'(api) ' if observation['via_api'] else '      '}{observation['url']}")
        if observation["result"] != "active":
            print(f"           {observation.get('reason', '')}")
    counts = result["summary"]
    print(f"\nResults: {counts['active']} active  {counts['expired']} expired  "
          f"{counts['uncertain']} uncertain  ({counts['via_api']} via API, no browser)")
    return int(bool(counts["expired"] or counts["uncertain"]))

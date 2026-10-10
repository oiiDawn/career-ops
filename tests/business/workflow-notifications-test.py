"""Check notification at-most-once business state across graph replays and failures."""

from pathlib import Path
import os
import subprocess
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from career_ops.notifications import deliver, thread_title

scores = {"direction": 4.28, "company": 3.95, "culture": 4.46, "compensation": 4.6}
title = thread_title("122", "c5175ea73d0aff", " Microsoft ", "Software Engineer II – Windows Cloud Experience", scores)
assert title == "Microsoft · Software Engineer II – Windows Cloud Experience · 方向4.3 公司4.0 文化4.5 薪酬4.6 · #122-c517"
long_title = thread_title("122", "c5175ea73d0aff", "Microsoft", "Engineer " * 30, scores)
# Discord caps thread names at 100 characters; the role gives way, never the scores or the thread key.
assert len(long_title) == 100 and long_title.endswith("薪酬4.6 · #122-c517")


def check(outcome):
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        payload = {
            "opportunity_id": "unit-opportunity", "report_hash": "unit-report-hash",
            "title": "reviewed role · 3–5/5 (50%)", "report": "unit report",
        }
        calls = []

        def sender(message):
            calls.append(message)
            if outcome == "timeout":
                raise TimeoutError("remote result unknown")
            if outcome == "failure":
                raise RuntimeError("remote request failed")
            if outcome == "crash":
                raise SystemExit("process stopped after claim")

        with patch("career_ops.notifications.eligible_report", return_value=payload):
            if outcome == "crash":
                try:
                    deliver(directory, payload["opportunity_id"], sender)
                except SystemExit:
                    pass
                else:
                    raise AssertionError("Expected simulated process stop")
                first = {"status": "uncertain"}
            else:
                first = deliver(directory, payload["opportunity_id"], sender)
            second = deliver(directory, payload["opportunity_id"], sender)
        assert len(calls) == 1
        expected = "uncertain" if outcome in ("failure", "timeout", "crash") else "delivered"
        assert first["status"] == second["status"] == expected


check("success")
check("failure")
check("timeout")
check("crash")

with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    python = root / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text('#!/bin/sh\nprintf "%s|%s\\n" "${CAREER_OPS_NOTIFICATIONS_ENABLED:-}" "$*" >> "$CALLS"\n')
    python.chmod(0o755)
    calls = root / "calls"
    environment = {key: value for key, value in os.environ.items() if key != "CAREER_OPS_NOTIFICATIONS_ENABLED"}
    subprocess.run(["sh", str(Path(__file__).resolve().parents[2] / "scripts/career-ops-score.sh")],
                   cwd=root, env={**environment, "CALLS": str(calls)}, check=True)
    assert calls.read_text().splitlines() == [
        "|-B -m career_ops system advance",
        "1|-B -m career_ops system notify cron",
    ]
print("notification graph and scheduled wrapper: delivery and replay checks passed")

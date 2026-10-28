"""Check career-run webhook delivery: request body, transport selection, and uncertain failures."""

from contextlib import redirect_stdout
from io import BytesIO, StringIO
from pathlib import Path
import json
import os
import sqlite3
import sys
import tempfile
from urllib.error import HTTPError
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from career_ops.notifications import (
    WEBHOOK_TIMEOUT_SECONDS,
    deliver,
    discord_sender,
    main,
    notification_sender,
    webhook_sender,
)

PAYLOAD = {
    "opportunity_id": "122",
    "report_hash": "abc123hash",
    "title": "Acme · Engineer",
    "report": "# 报告\n全文",
    "path": "/tmp/should-not-travel.md",
    "scores": {"direction": 4.2, "company": 3.9, "culture": 4.4, "compensation": 4.6},
}
WEBHOOK_URL = "https://example.invalid/career-run/webhook"


class Response:
    def __init__(self, status):
        self.status = status

    def read(self):
        return b""

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def header_map(request):
    return {name.lower(): value for name, value in request.header_items()}


def posted(sender_key):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return Response(200)

    environment = {
        "CAREER_OPS_GROKBOT_WEBHOOK_URL": WEBHOOK_URL,
        "CAREER_OPS_GROKBOT_WEBHOOK_SENDER_KEY": sender_key,
    }
    with patch.dict(os.environ, environment, clear=False), patch("career_ops.notifications.urlopen", fake_urlopen):
        webhook_sender(PAYLOAD)
    request = captured["request"]
    return json.loads(request.data.decode()), header_map(request), request, captured["timeout"]


body, headers, request, timeout = posted("panel-key")
assert request.full_url == WEBHOOK_URL
assert request.get_method() == "POST"
assert timeout == WEBHOOK_TIMEOUT_SECONDS
assert headers["content-type"] == "application/json"
assert headers["authorization"] == "Bearer panel-key"
assert body == {
    "opportunity_id": "122",
    "report_hash": "abc123hash",
    "title": "Acme · Engineer",
    "report": "# 报告\n全文",
    "scores": PAYLOAD["scores"],
}
assert "path" not in body
assert "panel-key" not in json.dumps(body)

body, headers, _, _ = posted("")
assert "authorization" not in headers
assert body["report"] == PAYLOAD["report"]

with patch.dict(os.environ, {}, clear=False):
    os.environ.pop("CAREER_OPS_NOTIFY_TRANSPORT", None)
    assert notification_sender() is webhook_sender
with patch.dict(os.environ, {"CAREER_OPS_NOTIFY_TRANSPORT": "  Discord  "}):
    assert notification_sender() is discord_sender
with patch.dict(os.environ, {"CAREER_OPS_NOTIFY_TRANSPORT": ""}):
    assert notification_sender() is webhook_sender
try:
    with patch.dict(os.environ, {"CAREER_OPS_NOTIFY_TRANSPORT": "slack"}):
        notification_sender()
except SystemExit as error:
    assert "slack" in str(error)
else:
    raise AssertionError("unsupported transport must exit before a send")


def run_main(action, environment, opportunity_id=None):
    argv = ["notify", action]
    if opportunity_id:
        argv.append(opportunity_id)
    argv.extend(["--directory", "/tmp/career-ops-notify-unused"])
    with patch.dict(os.environ, environment, clear=False), patch.object(sys, "argv", argv), \
            patch("career_ops.notifications.deliver_next", return_value={"status": "idle"}) as cron, \
            patch("career_ops.notifications.deliver", return_value={"status": "delivered"}) as once:
        try:
            with redirect_stdout(StringIO()):
                main()
        except SystemExit as error:
            return error, cron, once
        return None, cron, once


enabled = {"CAREER_OPS_NOTIFICATIONS_ENABLED": "1"}
missing, cron, once = run_main("cron", {**enabled, "CAREER_OPS_NOTIFY_TRANSPORT": "webhook", "CAREER_OPS_GROKBOT_WEBHOOK_URL": ""})
assert missing is not None and "CAREER_OPS_GROKBOT_WEBHOOK_URL" in str(missing)
assert not cron.called and not once.called

error, cron, once = run_main("cron", {**enabled, "CAREER_OPS_NOTIFY_TRANSPORT": "webhook", "CAREER_OPS_GROKBOT_WEBHOOK_URL": WEBHOOK_URL})
assert error is None and cron.call_args.args[1] is webhook_sender and not once.called

error, cron, once = run_main("send", {**enabled, "CAREER_OPS_NOTIFY_TRANSPORT": "discord"}, "122")
assert error is None and once.call_args.args[2] is discord_sender and not cron.called
error, cron, once = run_main("cron", {**enabled, "CAREER_OPS_NOTIFY_TRANSPORT": "discord", "CAREER_OPS_GROKBOT_WEBHOOK_URL": ""})
assert error is None and cron.call_args.args[1] is discord_sender


def attempt(failure):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(json.loads(request.data.decode()))
        if failure == "http":
            raise HTTPError(WEBHOOK_URL, 503, "unavailable", None, BytesIO(b"no"))
        if failure == "timeout":
            raise TimeoutError("timed out")
        if failure == "status":
            return Response(500)
        return Response(200)

    environment = {"CAREER_OPS_GROKBOT_WEBHOOK_URL": WEBHOOK_URL, "CAREER_OPS_GROKBOT_WEBHOOK_SENDER_KEY": "panel-key"}
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        with patch.dict(os.environ, environment, clear=False), \
                patch("career_ops.notifications.eligible_report", return_value=PAYLOAD), \
                patch("career_ops.notifications.urlopen", fake_urlopen):
            first = deliver(directory, PAYLOAD["opportunity_id"], webhook_sender)
            second = deliver(directory, PAYLOAD["opportunity_id"], webhook_sender)
        row = sqlite3.connect(directory / "opportunities.db").execute(
            "SELECT status, detail FROM notification_deliveries"
        ).fetchone()
    return first, second, calls, row


first, second, calls, row = attempt("success")
assert first["status"] == second["status"] == "delivered"
assert row[0] == "delivered"
assert len(calls) == 1 and calls[0]["report"] == PAYLOAD["report"] and "path" not in calls[0]

for failure, detail in (("http", "webhook HTTP 503"), ("timeout", "timed out"), ("status", "webhook HTTP 500")):
    first, second, calls, row = attempt(failure)
    assert first["status"] == second["status"] == "uncertain"
    assert row[0] == "uncertain" and row[0] != "delivered"
    assert row[1] == detail
    assert len(calls) == 1

print("career-run webhook notify: body, transport, and uncertain failure checks passed")

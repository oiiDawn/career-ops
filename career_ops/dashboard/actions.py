"""Run dashboard actions and application records through the CLI; the CLI owns all workflow state."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys
import threading


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_LIMIT = 4000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _command(action: str, opportunity_id: int) -> list[str]:
    target = str(opportunity_id)
    if action == "prepare":
        # --re-evaluate is safe: unchanged inputs reuse the stored package and a waiting
        # draft is returned as-is, so a model call only happens for new inputs.
        return ["apply", "prepare", target, "--re-evaluate"]
    if action == "rescore":
        # Re-score the retained JD against current candidate and policy inputs without rescanning.
        return ["task", "start", "score", target, f"scan:{target}", "--re-evaluate"]
    raise ValueError(f"Unknown dashboard action: {action}")


ACTIONS = ("prepare", "rescore")
RECORD_SOURCE = "dashboard"
RECORD_KINDS = ("submit", "status", "followup", "schedule")
DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
KEY = re.compile(r"^[A-Za-z0-9-]{8,64}$")


def run_cli(directory: Path, arguments: list[str]) -> dict | list:
    """Run one CLI command synchronously; the CLI's own error message becomes the ValueError."""
    result = subprocess.run([sys.executable, "-B", "-m", "career_ops", "--directory", str(directory), *arguments],
                            cwd=ROOT, text=True, capture_output=True)
    if result.returncode != 0:
        raise ValueError((result.stderr or result.stdout).strip()[-OUTPUT_LIMIT:] or f"exit code {result.returncode}")
    return json.loads(result.stdout)


def record_command(opportunity_id: int, body: dict, status_options: list[str], package_key: str | None) -> list[str]:
    """Translate one dashboard form into a confirmed `apply record` command; the lifecycle validates the rest."""
    def text(name: str) -> str:
        value = body.get(name)
        return value.strip()[:2000] if isinstance(value, str) else ""

    def day(name: str, required: bool = False) -> str | None:
        value = text(name)
        if (value or required) and not DAY.match(value):
            raise ValueError("日期必须是 YYYY-MM-DD")
        return value or None

    kind, key = body.get("kind"), body.get("key")
    if kind not in RECORD_KINDS:
        raise ValueError(f"未知的记录类型：{kind}")
    if not isinstance(key, str) or not KEY.match(key):
        raise ValueError("缺少有效的提交标识，请刷新页面重试")
    value = ""
    if kind == "submit":
        action = "submit"
        payload = {"submitted_at": day("date"), "package_result_key": package_key}
    elif kind == "status":
        value = text("value")
        if value not in status_options:
            raise ValueError(f"当前状态下不能记录：{value or '空'}")
        action, payload = ("transition" if value == "responded" else "outcome"), {}
    elif kind == "followup":
        action, value, payload = "activity", "followup_sent", {"sent_at": day("date")}
    else:
        action, value, payload = "schedule", day("date", required=True), {}
    payload = {name: item for name, item in {**payload, "notes": text("notes")}.items() if item}
    return ["apply", "record", action, str(opportunity_id), *([value] if value else []), "--confirmed",
            "--source", RECORD_SOURCE, "--idempotency-key", key, "--payload", json.dumps(payload, ensure_ascii=False)]


def followup_state(directory: Path, opportunity_id: int) -> dict | None:
    """This application's follow-up cadence entry, or None when it is closed, retired or not submitted."""
    entries = run_cli(directory, ["apply", "record", "followups"])["entries"]
    return next((entry for entry in entries if str(entry["opportunityId"]) == str(opportunity_id)), None)


class ActionRunner:
    """At most one running action per opportunity."""

    def __init__(self, directory: Path):
        self.directory = directory
        self.lock = threading.Lock()
        self.runs: dict[int, dict] = {}

    def status(self, opportunity_id: int) -> dict | None:
        with self.lock:
            run = self.runs.get(opportunity_id)
            return dict(run) if run else None

    def statuses(self) -> dict[int, dict]:
        with self.lock:
            return {key: {"action": run["action"], "status": run["status"]} for key, run in self.runs.items()}

    def start(self, opportunity_id: int, action: str) -> dict:
        arguments = _command(action, opportunity_id)
        with self.lock:
            current = self.runs.get(opportunity_id)
            if current and current["status"] == "running":
                raise RuntimeError("Another dashboard action is already running for this opportunity")
            run = {"action": action, "status": "running", "started_at": _now(), "finished_at": None,
                   "task": None, "error": None}
            self.runs[opportunity_id] = run
        threading.Thread(target=self._run, args=(opportunity_id, arguments), daemon=True).start()
        return dict(run)

    def _run(self, opportunity_id: int, arguments: list[str]) -> None:
        task, error = None, None
        try:
            task = run_cli(self.directory, arguments)
        except ValueError as exception:
            error = str(exception)
        except Exception as exception:  # report launcher failures to the page
            error = repr(exception)
        with self.lock:
            self.runs[opportunity_id] = {
                **self.runs[opportunity_id], "finished_at": _now(),
                "status": "failed" if error else "succeeded", "error": error,
                "task": {key: task.get(key) for key in ("task_id", "status", "reason", "allowed_actions")} if task else None,
            }

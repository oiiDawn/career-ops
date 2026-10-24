"""Advance and recover long tasks without owning the CLI."""

from __future__ import annotations


from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import os
import re
import shutil
import sqlite3
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langchain_core.runnables import RunnableLambda
from uuid import uuid4
from career_ops.discovery.configured import capture_jd
from career_ops.discovery.dedup import url_key
from career_ops.applications.resume_renderer import render_resume
from career_ops.applications.apply_graph import apply_evaluate as run_apply
from career_ops.context import ATTEMPT_CALLS, ATTEMPT_SECONDS, INPUT_ROOT, ROOT, WORKFLOW_VERSION
from career_ops.evaluation.scan_graph import run_scan
from career_ops.evaluation.score_graph import run_score
from career_ops.input_contracts import apply_inputs, canonical_scan_input, canonical_score_input, digest, score_inputs, score_is_current, score_refresh_reasons, scan_is_current, validate_resume_payload
from career_ops.task_state import WorkflowState
from career_ops.db import BusinessStore
from career_ops.liveness import execution_lock, require_open
from career_ops.llm import DEADLINE, load_stub
from career_ops.model import USAGE
from career_ops.tracing import traced


def task_view(store: BusinessStore, task: sqlite3.Row) -> dict:
    """Return the stable JSON shape shared by start, show, list, resume and cancel."""
    return {
        "task_id": task["task_id"],
        "opportunity_id": task["opportunity_id"],
        "module": task["module"],
        "status": task["status"],
        "reason": task["waiting_reason"],
        "artifact": store.result(task["task_id"]),
        "attempt": task["attempt"],
        "allowed_actions": ["resume", "cancel"] if task["status"] == "waiting" else [],
    }


def view(directory: Path, identifier: str) -> dict:
    store = BusinessStore(directory / "opportunities.db")
    try:
        return task_view(store, store.find_task(identifier))
    finally:
        store.close()


def list_views(directory: Path) -> list[dict]:
    store = BusinessStore(directory / "opportunities.db")
    try:
        return [task_view(store, task) for task in store.list_tasks()]
    finally:
        store.close()


def cancel_task(directory: Path, task_id: str) -> dict:
    store = BusinessStore(directory / "opportunities.db")
    try:
        return task_view(store, store.cancel(task_id))
    finally:
        store.close()


class Runtime:
    """Build one explicit graph while keeping formal writes behind BusinessStore."""

    def __init__(self, store: BusinessStore, fault_dir: Path, crash_at: str | None = None):
        self.store = store
        self.fault_dir = fault_dir
        self.crash_at = crash_at
        self.started_at = time.monotonic()

    def crash_once(self, state: WorkflowState, stage: str) -> None:
        marker = self.fault_dir / f"{state['task_id']}-{stage}.faulted"
        if self.crash_at == stage and not marker.exists():
            marker.touch()
            os._exit(86)

    def run_model(self, phase: str, payload: dict, state: WorkflowState) -> dict:
        """Run one model-backed module graph in process while enforcing the module budget."""
        task = self.store.task(state["task_id"])
        calls_before = task["attempt_tool_calls"]
        call_limit = None if phase == "evaluate" else ATTEMPT_CALLS
        if call_limit is not None and calls_before >= call_limit:
            raise TimeoutError("tool_budget_exhausted")
        remaining = ATTEMPT_SECONDS - task["attempt_elapsed_seconds"] - (time.monotonic() - self.started_at)
        if phase != "evaluate" and remaining <= 0:
            raise TimeoutError("time_budget_exhausted")
        deadline = None if phase == "evaluate" else time.monotonic() + remaining
        draft_root = Path(os.environ.get("CAREER_OPS_DRAFT_ROOT", self.store.path.parent / "workflow-drafts"))
        stub = load_stub("CAREER_OPS_MODEL_STUB")
        phases = {
            "scan_evaluate": lambda: run_scan(payload["inputs"], draft_root),
            "apply_evaluate": lambda: run_apply(payload, draft_root),
            "evaluate": lambda: run_score(payload["inputs"], draft_root, ROOT),
        }
        deadline_token = DEADLINE.set(deadline)
        usage_token = USAGE.set((str(self.store.path), state["task_id"], call_limit))
        try:
            value = stub(phase, payload) if stub else phases[phase]()
        except Exception as error:
            task = self.store.add_usage(state["task_id"], time.monotonic() - self.started_at, 0)
            self.started_at = time.monotonic()
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError("time_budget_exhausted") from error
            if call_limit is not None and task["attempt_tool_calls"] >= call_limit:
                raise TimeoutError("tool_budget_exhausted") from error
            raise
        finally:
            DEADLINE.reset(deadline_token)
            USAGE.reset(usage_token)
        try:
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError("time_budget_exhausted")
            if not isinstance(value, dict):
                raise ValueError("Model phase response must be an object")
            reported_calls = int(value.pop("tool_calls", 0))
        except (ValueError, TypeError, OverflowError, TimeoutError):
            self.store.add_usage(state["task_id"], time.monotonic() - self.started_at, 0)
            self.started_at = time.monotonic()
            raise
        durable_calls = self.store.task(state["task_id"])["attempt_tool_calls"] - calls_before
        calls = reported_calls if stub and not durable_calls else 0
        task = self.store.add_usage(state["task_id"], time.monotonic() - self.started_at, calls)
        self.started_at = time.monotonic()
        if call_limit is not None and task["attempt_tool_calls"] >= call_limit:
            raise TimeoutError("tool_budget_exhausted")
        value["tool_calls"] = task["tool_calls"]
        return value

    def evaluate(self, state: WorkflowState) -> dict:
        task = self.store.task(state["task_id"])
        inputs = json.loads(task["input_payload"])
        if task["input_payload"].startswith("{"):
            if task["module"] == "apply":
                result = self.run_model("apply_evaluate", {"inputs": inputs}, state)
                artifact = result["artifact"]
                return {
                    "outcome": "package", "draft": json.dumps(artifact, ensure_ascii=False, sort_keys=True),
                    "material_hash": digest(json.dumps(artifact, ensure_ascii=False, sort_keys=True)),
                    "tool_calls": result["tool_calls"],
                }
            if task["module"] == "scan":
                if not inputs["source"]["jd"].strip():
                    return {"waiting_reason": "jd_evidence_missing"}
                result = self.run_model("scan_evaluate", {"inputs": inputs}, state)
                if result.get("waiting_reason"):
                    return {"waiting_reason": result["waiting_reason"], "tool_calls": result["tool_calls"]}
                artifact = result["artifact"]
                if result["outcome"] == "jd_report":
                    score_inputs(artifact)
                return {
                    "outcome": result["outcome"],
                    "draft": json.dumps(artifact, ensure_ascii=False, sort_keys=True),
                    "material_hash": digest(json.dumps(artifact, ensure_ascii=False, sort_keys=True)),
                    "tool_calls": result["tool_calls"],
                }
            if inputs["jd_report"]["prescreen"]["status"] == "incomplete":
                return {"waiting_reason": "core_evidence_missing"}
            result = self.run_model(
                "evaluate",
                {"inputs": inputs},
                state,
            )
            artifact = result["artifact"]
            return {
                "outcome": result["outcome"],
                "draft": json.dumps(artifact, ensure_ascii=False, sort_keys=True),
                "material_hash": digest(json.dumps(artifact, ensure_ascii=False, sort_keys=True)),
                "tool_calls": result["tool_calls"],
            }
        raise ValueError("Workflow input must be canonical JSON")

    @staticmethod
    def route_evaluate(state: WorkflowState) -> str:
        return "wait" if state.get("waiting_reason") else "stage" if state["module"] == "apply" else "publish"

    @staticmethod
    def wait(state: WorkflowState) -> dict:
        return {"waiting_reason": state["waiting_reason"]}

    def publish(self, state: WorkflowState) -> dict:
        existing = self.store.result(state["task_id"])
        if existing:
            payload = existing
        else:
            self.crash_once(state, "before_publish")
            artifact = json.loads(state["draft"]) if state["draft"].startswith("{") else None
            if artifact and artifact.get("report"):
                path = self.fault_dir / "artifacts" / state["task_id"] / state["input_hash"] / "report.md"
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = path.with_suffix(".tmp")
                temporary.write_text(artifact["report"])
                temporary.replace(path)
                artifact["path"] = str(path)
                state = {**state, "draft": json.dumps(artifact, ensure_ascii=False, sort_keys=True)}
            payload = self.store.publish(state)
        self.crash_once(state, "publish")
        return {"waiting_reason": None}

    def stage(self, state: WorkflowState) -> dict:
        package = json.loads(state["draft"])
        required = {
            "resume_payload", "changes", "cover_letter", "upskill",
            "interview_prep", "questions",
        }
        missing = sorted(required - package.keys())
        if missing or not package.get("resume_payload", {}).get("candidate", {}).get("name"):
            raise ValueError("Invalid application package: " + ", ".join(missing or ["resume candidate name"]))
        for key in required - {"resume_payload"}:
            if not isinstance(package[key], str) or not package[key].strip():
                raise ValueError(f"Invalid application package: {key} must be a nonempty Markdown string")
        validate_resume_payload(package["resume_payload"])
        root = self.fault_dir / "artifacts" / state["task_id"] / state["input_hash"] / "package"
        root.mkdir(parents=True, exist_ok=True)
        names = {
            "resume_payload": "resume.json", "changes": "changes.md", "cover_letter": "cover-letter.md",
            "upskill": "upskill.md", "interview_prep": "interview-prep.md", "questions": "questions.md",
        }
        files = {}
        for key, name in names.items():
            path = root / name
            value = package[key]
            path.write_text(
                json.dumps(value, ensure_ascii=False, indent=2) + "\n" if key == "resume_payload" else str(value)
            )
            files[key] = str(path)
        pdf_receipt = None
        remaining = ATTEMPT_SECONDS - self.store.task(state["task_id"])["attempt_elapsed_seconds"] - (time.monotonic() - self.started_at)
        if remaining <= 0:
            raise TimeoutError("time_budget_exhausted")
        pdf_path = root / "resume.pdf"
        metadata_path = root / "reactive-resume.json"
        previous_metadata = root.parents[1] / "reactive-resume.json"
        if not metadata_path.exists() and previous_metadata.is_file():
            shutil.copyfile(previous_metadata, metadata_path)
        started = time.monotonic()
        try:
            inputs = json.loads(self.store.task(state["task_id"])["input_payload"])
            pdf_receipt = render_resume(
                state["task_id"], root.parents[1], Path(files["resume_payload"]),
                pdf_path, INPUT_ROOT / "profile.yml",
                package["resume_payload"]["candidate"]["name"],
                inputs["jd_report"]["company"], inputs["jd_report"]["role"],
                timeout_seconds=min(120, max(1, int(remaining))),
            )
        finally:
            self.store.add_usage(state["task_id"], time.monotonic() - started, 1)
        files["resume_pdf"] = str(pdf_path)
        files["resume_metadata"] = pdf_receipt["metadata_path"]
        artifact = {
            "files": files, "file_hashes": {
                name: hashlib.sha256(Path(path).read_bytes()).hexdigest()
                for name, path in files.items()
            }, "package": package, "pdf_receipt": pdf_receipt,
        }
        return {"draft": json.dumps(artifact, ensure_ascii=False, sort_keys=True)}

    def graph(self, checkpointer: SqliteSaver):
        graph = StateGraph(WorkflowState)
        graph.add_node("evaluate", self.evaluate)
        graph.add_node("wait", self.wait)
        graph.add_node("publish", self.publish)
        graph.add_node("stage", self.stage)
        graph.add_edge(START, "evaluate")
        graph.add_conditional_edges("evaluate", self.route_evaluate, {"wait": "wait", "publish": "publish", "stage": "stage"})
        graph.add_edge("wait", END)
        graph.add_edge("publish", END)
        graph.add_edge("stage", "publish")
        return graph.compile(checkpointer=checkpointer)


def initial_state(task: sqlite3.Row) -> WorkflowState:
    return {
        "task_id": task["task_id"],
        "module": task["module"],
        "input_hash": task["input_hash"],
        "outcome": "score",
        "draft": "{}",
        "waiting_reason": None,
        "material_hash": "",
        "tool_calls": 0,
    }


def _run_task(
    directory: Path,
    task_id: str,
    *,
    start_state: WorkflowState | None = None,
    crash_at: str | None = None,
) -> dict:
    store = BusinessStore(directory / "opportunities.db")
    try:
        task = store.task(task_id)
        existing = store.result(task_id)
        if existing:
            return {"task_id": task_id, "status": "completed", "result": existing, "reconciled": True}
        if task["status"] == "cancelled":
            return {"task_id": task_id, "status": "cancelled", "reconciled": True}
        if task["status"] == "waiting" and not str(task["waiting_reason"] or "").startswith("failure:"):
            return {"task_id": task_id, "status": "waiting", "reason": task["waiting_reason"]}
        if task["workflow_version"] != WORKFLOW_VERSION:
            store.wait(task_id, "workflow_version_incompatible")
            return {"task_id": task_id, "status": "waiting", "reason": "workflow_version_incompatible"}
        require_open(store.db, task["opportunity_id"])
        runtime = Runtime(store, directory, crash_at)
        name = "prescreen" if task["module"] == "scan" else task["module"]
        config = traced({"configurable": {"thread_id": f"{task_id}:{task['attempt']}"}}, name, task_id)
        with SqliteSaver.from_conn_string(str(directory / "workflow-checkpoints.db")) as saver:
            graph = runtime.graph(saver)
            if start_state is None and task["status"] == "waiting" and (task["waiting_reason"] or "").startswith("failure:"):
                if graph.get_state(config).next:
                    store.resume_failed_checkpoint(task_id)
            if start_state is None and not graph.get_state(config).next:
                start_state = initial_state(task)
            value = graph.invoke(start_state, config)
        if value.get("waiting_reason"):
            store.wait(task_id, value["waiting_reason"])
            return {"task_id": task_id, "status": "waiting", "reason": value["waiting_reason"]}
        return {"task_id": task_id, "status": store.task(task_id)["status"], "result": store.result(task_id)}
    except TimeoutError as error:
        store.wait(task_id, str(error))
        return {"task_id": task_id, "status": "waiting", "reason": str(error)}
    except Exception as error:
        remaining = store.db.execute("SELECT status FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        if remaining and remaining["status"] == "running":
            store.wait(task_id, f"failure:{type(error).__name__}")
        raise
    finally:
        store.close()


def run_task(
    directory: Path,
    task_id: str,
    *,
    start_state: WorkflowState | None = None,
    crash_at: str | None = None,
) -> dict:
    """Run one task under a crash-safe process lock; business state remains authoritative."""
    lock_directory = directory / ".locks"
    lock_directory.mkdir(parents=True, exist_ok=True)
    with (lock_directory / f"{task_id}.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError(f"Task is already executing: {task_id}") from error
        store = BusinessStore(directory / "opportunities.db")
        try:
            opportunity_id = store.task(task_id)["opportunity_id"]
        finally:
            store.close()
        with execution_lock(directory, opportunity_id):
            return _run_task(directory, task_id, start_state=start_state, crash_at=crash_at)


def start_and_run(directory: Path, opportunity: str, module: str, input_text: str, crash_at: str | None, re_evaluate: bool = False) -> dict:
    if module == "scan":
        input_text = canonical_scan_input(input_text)
    store = BusinessStore(directory / "opportunities.db")
    if module == "score" and input_text.startswith("scan:"):
        scan = store.module_result(input_text.removeprefix("scan:"), "scan")
        if not scan or scan["outcome"] != "jd_report":
            store.close()
            raise ValueError("Missing completed scan result")
        input_text = score_inputs(scan["artifact"])
    elif module == "score":
        input_text = canonical_score_input(input_text)
    elif module == "apply" and input_text.startswith("score:"):
        upstream = input_text.removeprefix("score:")
        scan = store.module_result(upstream, "scan")
        score = store.module_result(upstream, "score")
        if not scan or scan["outcome"] != "jd_report" or not score or score["outcome"] != "score":
            store.close()
            raise ValueError("Missing completed scan and score results")
        scored_inputs = store.db.execute(
            "SELECT input_payload FROM tasks WHERE module='score' AND opportunity_id=? AND input_hash=? ORDER BY rowid DESC LIMIT 1",
            (upstream, score["input_hash"]),
        ).fetchone()
        if not scored_inputs or digest(scored_inputs[0]) != score["input_hash"]:
            store.close()
            raise ValueError("Retained score input integrity check failed")
        input_text = apply_inputs(scan["artifact"], score)
    elif module == "apply":
        store.close()
        raise ValueError("apply requires score:<opportunity_id>")
    inputs = json.loads(input_text) if input_text.startswith("{") else None
    report = inputs["source"] if module == "scan" and inputs else inputs["jd_report"] if inputs else None
    if report and report["opportunity_id"] != opportunity:
        store.close()
        raise ValueError("CLI opportunity does not match the JD report")
    if module == "scan" and inputs:
        store.retain_source(opportunity, input_text)
    started = store.start(opportunity, module, input_text, re_evaluate=re_evaluate)
    task = store.task(started["task_id"])
    store.close()
    if started["status"] != "running":
        return started
    return run_task(directory, task["task_id"], start_state=initial_state(task), crash_at=crash_at)


def discovery_query(store: BusinessStore) -> tuple[str, str]:
    """Select the latest immutable capture and JD version for a discovered row."""
    has_source_evidence = bool(store.db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='source_evidence'"
    ).fetchone())
    has_page_versions = bool(store.db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='page_evidence_versions'"
    ).fetchone())
    capture_select = ("(SELECT payload FROM source_evidence s WHERE s.opportunity_id=o.id "
                      "AND COALESCE(json_extract(s.payload,'$.url'),json_extract(s.payload,'$._capture.url'))=o.url "
                      "ORDER BY s.id DESC LIMIT 1)") if has_source_evidence else "NULL"
    page_join = "LEFT JOIN page_evidence_versions p ON p.id=(SELECT id FROM page_evidence_versions v WHERE v.opportunity_id=o.id ORDER BY v.id DESC LIMIT 1)" if has_page_versions else "LEFT JOIN page_evidence p ON p.opportunity_id=o.id"
    return capture_select, page_join


def same_posting_url(requested: str, final: str) -> bool:
    """Compare posting keys; accept IBM's locale redirect only when the public job ID is unchanged."""
    if url_key(requested) == url_key(final):
        return True
    try:
        source, target = urlsplit(requested), urlsplit(final)
        source_query = parse_qs(source.query, keep_blank_values=True)
        target_query = parse_qs(target.query, keep_blank_values=True)
        return (source.scheme == target.scheme == "https"
                and source.netloc == target.netloc == "careers.ibm.com"
                and source.path == "/careers/JobDetail"
                and re.fullmatch(r"/[a-z]{2}_[A-Z]{2}/careers/JobDetail", target.path) is not None
                and not source.fragment and not target.fragment
                and len(source_query) == len(target_query) == 1
                and len(source_query.get("jobId", [])) == len(target_query.get("jobId", [])) == 1
                and re.fullmatch(r"\d+", source_query.get("jobId", [""])[0]) is not None
                and source_query == target_query)
    except (TypeError, ValueError):
        return False


def discovered_scan_source(opportunity: sqlite3.Row, refreshed: dict | None = None) -> dict:
    """Build a scan input from intact, identity-bound JD evidence regardless of check freshness."""
    opportunity_id = str(opportunity["id"])
    capture = json.loads(opportunity["capture_payload"]) if opportunity["capture_payload"] else {}
    snapshot = (
        {"text": refreshed["text"], "retrieved_at": refreshed["retrieved_at"],
         "final_url": refreshed["url"], "content_hash": digest(refreshed["text"])}
        if refreshed and refreshed.get("status") == "captured"
        else capture.get("scan_jd") or {}
    )
    metadata = capture.get("_capture", {})
    jd = snapshot.get("text") or opportunity["content"] or ""
    captured_at = snapshot.get("retrieved_at") or metadata.get("retrieved_at", "")
    try:
        valid_capture_time = datetime.fromisoformat(captured_at.replace("Z", "+00:00")) <= datetime.now(timezone.utc)
    except (TypeError, ValueError):
        valid_capture_time = False
    verified_snapshot = (
        (refreshed is not None or (capture.get("url") or metadata.get("url")) == opportunity["url"])
        and same_posting_url(opportunity["url"], snapshot.get("final_url"))
        and isinstance(snapshot.get("text"), str)
        and snapshot.get("content_hash") == digest(snapshot["text"])
        and valid_capture_time
    )
    verified_capture = verified_snapshot or (
        metadata.get("method") in {"workday_cxs_api", "oraclecloud_detail_api", "smartrecruiters_detail_api", "successfactors_job_page", "phenom_job_page", "beesite_job_page", "ikea_job_page", "jibeapply_job_page", "avature_job_page", "eightfold_job_page", "mtr_taleo_job_page", "official_job_page", "browser_snapshot"}
        and metadata.get("status") == 200
        and metadata.get("url") == opportunity["url"]
        and metadata.get("content_hash") == digest(jd)
        and valid_capture_time
    )
    evidence = (
        {"method": "browser_snapshot", "status": "captured", "url": opportunity["url"],
         "final_url": snapshot.get("final_url"), "content_hash": snapshot.get("content_hash")}
        if verified_snapshot else metadata if verified_capture else {"reason": "No verified source capture"}
    )
    return {
        "schema_version": "scan_input_v1", "opportunity_id": opportunity_id,
        "source_contract_version": 3,
        "url": opportunity["url"], "company": opportunity["company"], "role": opportunity["role"],
        "captured_at": captured_at or opportunity["captured_at"] or time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "capture_method": "browser_snapshot" if verified_snapshot else metadata.get("method", "unknown"),
        "capture_evidence": evidence,
        "location_evidence": capture.get("structured_posting", {}).get("jobLocation")
            or capture.get("jobPostingInfo", {}).get("location") or capture.get("location"),
        "employment_evidence": capture.get("structured_posting", {}).get("employmentType"),
        "jd": jd if verified_capture else "",
    }


def current_discovered_scan_source(opportunity: sqlite3.Row, directory: Path) -> dict:
    """Reuse intact JD evidence; fetch only when no usable source capture exists."""
    source = discovered_scan_source(opportunity)
    if source["jd"].strip():
        return source
    refreshed = capture_jd(directory, opportunity["url"])
    return discovered_scan_source(opportunity, refreshed) if refreshed else source


def retained_scan_source(store: BusinessStore, opportunity_id: str) -> dict | None:
    """Reuse a hash-verified source bound to the latest completed JD report."""
    row = store.db.execute(
        "SELECT t.input_payload,t.input_hash,r.payload FROM results r JOIN tasks t ON t.task_id=r.task_id "
        "WHERE r.opportunity_id=? AND r.module='scan' ORDER BY r.rowid DESC LIMIT 1", (opportunity_id,),
    ).fetchone()
    if not row or digest(row["input_payload"]) != row["input_hash"]:
        return None
    inputs, result = json.loads(row["input_payload"]), json.loads(row["payload"])
    source, report = inputs.get("source", {}), result.get("artifact", {})
    if (result.get("outcome") == "jd_report" and source.get("jd", "").strip()
            and all(source.get(key) == report.get(key) for key in ("opportunity_id", "url", "jd", "captured_at"))):
        return source
    return None


def replacement_input(store: BusinessStore, task: sqlite3.Row) -> str | None:
    """Replace obsolete evaluation inputs; unchanged evidence waits require new evidence."""
    try:
        if digest(task["input_payload"]) != task["input_hash"]:
            return None
        if task["module"] == "scan":
            source = json.loads(task["input_payload"])["source"]
            retained = retained_scan_source(store, task["opportunity_id"])
            if retained and task["waiting_reason"] in {"source_access_unknown", "jd_evidence_missing"}:
                source = retained
            capture_select, page_join = discovery_query(store)
            opportunity = store.db.execute(
                f"SELECT o.*,p.content,p.captured_at,{capture_select} AS capture_payload "
                f"FROM opportunities o {page_join} WHERE o.id=?", (task["opportunity_id"],),
            ).fetchone()
            if opportunity:
                captured = discovered_scan_source(opportunity)
                if captured["jd"].strip() and captured["jd"] != source.get("jd"):
                    source = captured
            current = canonical_scan_input(json.dumps(source))
            changed = not scan_is_current(task["input_payload"], current)
        else:
            scan = store.module_result(task["opportunity_id"], "scan")
            if not scan or scan.get("outcome") != "jd_report":
                return None
            current = score_inputs(scan["artifact"])
            frozen = json.loads(task["input_payload"])
            changed = (not score_is_current(store.db, task["input_hash"], scan["artifact"])
                       or frozen.get("company_valid_until", "9999-12-31") < datetime.now(timezone.utc).date().isoformat())
        if changed or task["workflow_version"] != WORKFLOW_VERSION or task["waiting_reason"] == "input_changed":
            return current
    except (KeyError, TypeError, ValueError):
        return None
    return None


def scan_discovered(directory: Path, opportunity_id: str, re_evaluate: bool = False) -> dict:
    """Start the scan graph from a retained provider capture by opportunity ID."""
    store = BusinessStore(directory / "opportunities.db")
    try:
        capture_select, page_join = discovery_query(store)
        row = store.db.execute(
            f"SELECT o.id,o.url,o.company,o.role,p.content,p.captured_at,{capture_select} AS capture_payload "
            f"FROM opportunities o {page_join} WHERE o.id=?", (opportunity_id,),
        ).fetchone()
        if not row:
            raise ValueError(f"Discovered opportunity not found: {opportunity_id}")
        if re_evaluate:
            source = retained_scan_source(store, opportunity_id) or current_discovered_scan_source(row, directory)
        else:
            source = current_discovered_scan_source(row, directory)
        waiting = store.db.execute(
            "SELECT task_id,input_hash FROM tasks WHERE opportunity_id=? AND module='scan' "
            "AND status='waiting' AND waiting_reason IN ('source_access_unknown','jd_evidence_missing') ORDER BY rowid DESC LIMIT 1",
            (opportunity_id,),
        ).fetchone()
    finally:
        store.close()
    input_text = json.dumps(source, ensure_ascii=False)
    if waiting and not re_evaluate:
        if source["jd"].strip():
            changed = digest(canonical_scan_input(input_text)) != waiting["input_hash"]
            return resume_task(directory, waiting["task_id"], input_text if changed else None, None)
        return view(directory, waiting["task_id"])
    return start_and_run(directory, opportunity_id, "scan", input_text, None, re_evaluate)


def evaluate_opportunity(directory: Path, opportunity_id: str, re_evaluate: bool = False) -> dict:
    """Trace one opportunity from JD capture and prescreen through published scoring."""
    def evaluate(_):
        started = scan_discovered(directory, opportunity_id, re_evaluate)
        screened = view(directory, started["task_id"])
        if screened["status"] == "completed" and screened["artifact"]["outcome"] == "jd_report":
            started = start_and_run(directory, opportunity_id, "score", f"scan:{opportunity_id}", None, re_evaluate)
        return view(directory, started["task_id"])

    return RunnableLambda(evaluate).invoke(
        {"opportunity_id": opportunity_id},
        traced({}, "job-evaluation", f"opportunity:{opportunity_id}"),
    )


def cron_score(directory: Path) -> dict:
    """Evaluate one scheduled opportunity, continuing a completed prescreen into score."""
    def advance(_):
        result = _advance_evaluation(directory)
        task = result.get("task", {})
        if task.get("status") == "waiting" and task.get("task_id") and task.get("reason") in {"source_access_unknown", "jd_evidence_missing"}:
            store = BusinessStore(directory / "opportunities.db")
            try:
                store.set_context(task["task_id"], "source_probe", {"at": datetime.now(timezone.utc).isoformat()})
            finally:
                store.close()
        if task.get("status") != "completed" or not task.get("task_id"):
            return result
        store = BusinessStore(directory / "opportunities.db")
        try:
            completed = store.task(task["task_id"])
            artifact = store.result(task["task_id"])
            needs_score = completed["module"] == "scan" and artifact and artifact["outcome"] == "jd_report"
        finally:
            store.close()
        if needs_score:
            opportunity_id = result["opportunity_id"]
            result["task"] = start_and_run(directory, opportunity_id, "score", f"scan:{opportunity_id}", None, True)
        return result

    return RunnableLambda(advance).invoke({}, traced({}, "job-evaluation", f"evaluation:{uuid4()}"))


def _advance_evaluation(directory: Path) -> dict:
    """Select one opportunity and resume its current durable evaluation stage."""
    store = BusinessStore(directory / "opportunities.db")
    refresh_opportunity_id = None
    refresh_scan_input = None
    retry_task_id = None
    try:
        if not store.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='opportunities'").fetchone():
            return {"status": "idle", "reason": "scanner_store_not_initialized"}
        capture_select, page_join = discovery_query(store)
        replacements = {
            task["task_id"]: inputs for task in store.db.execute(
                "SELECT * FROM tasks WHERE module IN ('scan','score') AND status='waiting'"
            ) if (inputs := replacement_input(store, task)) is not None
        }
        replaceable = ",".join("?" for _ in replacements) or "''"
        probe_before = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        closed_filter = ("NOT EXISTS (SELECT 1 FROM scan_outcomes c WHERE c.url=o.url AND c.status='skipped_expired' AND json_extract(c.payload,'$.maintenance_closed')=1)"
                         if store.db.execute("SELECT 1 FROM sqlite_master WHERE name='scan_outcomes'").fetchone() else "1")
        opportunity = store.db.execute(
            f"""
            SELECT o.id,o.url,o.company,o.role,p.content,p.captured_at,{capture_select} AS capture_payload
            FROM opportunities o
            {page_join}
            WHERE {closed_filter} AND NOT EXISTS (
              SELECT 1 FROM results r
              WHERE r.opportunity_id=CAST(o.id AS TEXT) AND r.module='score'
            )
            AND NOT EXISTS (
              SELECT 1 FROM results r
              WHERE r.rowid=(
                SELECT MAX(recent.rowid) FROM results recent
                WHERE recent.opportunity_id=CAST(o.id AS TEXT) AND recent.module='scan'
              ) AND json_extract(r.payload,'$.outcome')='exclude'
            )
            AND NOT EXISTS (
              SELECT 1 FROM tasks t JOIN task_context c ON c.task_id=t.task_id AND c.key='source_probe'
              WHERE t.opportunity_id=CAST(o.id AS TEXT) AND t.status='waiting'
                AND t.task_id NOT IN ({replaceable}) AND json_extract(c.payload,'$.at')>?
            )
            AND NOT EXISTS (
              SELECT 1 FROM tasks t
              WHERE t.opportunity_id=CAST(o.id AS TEXT) AND t.status='waiting'
                AND t.module IN ('scan','score') AND t.task_id NOT IN ({replaceable})
                AND NOT (t.module='scan' AND t.waiting_reason IN ('source_access_unknown','jd_evidence_missing'))
                AND NOT (t.waiting_reason LIKE 'failure:%' AND t.attempt<2)
            )
            ORDER BY EXISTS(
              SELECT 1 FROM tasks t WHERE t.opportunity_id=CAST(o.id AS TEXT)
                AND t.status='waiting' AND t.module='scan' AND t.waiting_reason IN ('source_access_unknown','jd_evidence_missing')
            ), EXISTS(
              SELECT 1 FROM tasks t WHERE t.opportunity_id=CAST(o.id AS TEXT)
                AND t.status='waiting' AND t.waiting_reason LIKE 'failure:%'
            ), EXISTS(
              SELECT 1 FROM tasks t WHERE t.opportunity_id=CAST(o.id AS TEXT)
                AND t.status='waiting' AND t.module='scan'
            ), COALESCE((
              SELECT json_extract(c.payload,'$.at') FROM tasks t
              JOIN task_context c ON c.task_id=t.task_id AND c.key='source_probe'
              WHERE t.opportunity_id=CAST(o.id AS TEXT) AND t.status='waiting' AND t.module='scan'
            ), ''), o.id LIMIT 1
            """, (*replacements, probe_before, *replacements),
        ).fetchone()
        deferred = opportunity and store.db.execute(
            f"SELECT 1 FROM tasks WHERE opportunity_id=? AND module IN ('scan','score') "
            f"AND status='waiting' AND task_id NOT IN ({replaceable})", (str(opportunity["id"]), *replacements),
        ).fetchone()
        if not opportunity or deferred:
            for item in store.score_views():
                if not item["needs_rescore"]:
                    continue
                candidate = item["opportunity_id"]
                try:
                    require_open(store.db, candidate)
                except ValueError:
                    continue
                scan = store.module_result(candidate, "scan")
                if not scan or scan["outcome"] != "jd_report" or store.db.execute(
                    f"SELECT 1 FROM tasks WHERE opportunity_id=? AND "
                    f"(status='running' OR (status='waiting' AND module IN ('scan','score') "
                    f"AND task_id NOT IN ({replaceable}) "
                    f"AND NOT (waiting_reason LIKE 'failure:%' AND attempt<2)))", (candidate, *replacements),
                ).fetchone():
                    continue
                refresh_opportunity_id = candidate
                retry = store.db.execute(
                    f"SELECT task_id FROM tasks WHERE opportunity_id=? AND module IN ('scan','score') "
                    f"AND status='waiting' AND waiting_reason LIKE 'failure:%' AND attempt<2 "
                    f"AND task_id NOT IN ({replaceable}) ORDER BY rowid DESC LIMIT 1", (candidate, *replacements),
                ).fetchone()
                retry_task_id = retry["task_id"] if retry else None
                refresh_scan_input = next((replacements[task["task_id"]] for task in store.db.execute(
                    "SELECT task_id FROM tasks WHERE opportunity_id=? AND module='scan' "
                    "AND status='waiting' ORDER BY rowid DESC", (candidate,),
                ) if task["task_id"] in replacements), None)
                break
            if not refresh_opportunity_id and not opportunity:
                return {"status": "idle", "reason": "no_runnable_evaluations"}
        if not refresh_opportunity_id:
            opportunity_id = str(opportunity["id"])
            scan = store.module_result(opportunity_id, "scan")
            active = store.db.execute(
                "SELECT task_id,module,status,waiting_reason,input_hash FROM tasks WHERE opportunity_id=? "
                "AND (status='running' OR (status='waiting' AND module IN ('scan','score'))) ORDER BY rowid DESC LIMIT 1",
                (opportunity_id,),
            ).fetchone()
            if active and active["module"] == "score" and active["task_id"] in replacements:
                refresh_opportunity_id = opportunity_id
    finally:
        store.close()
    if retry_task_id:
        return {"status": "advanced", "opportunity_id": refresh_opportunity_id,
                "task": resume_task(directory, retry_task_id, None, None)}
    if refresh_opportunity_id:
        started = (start_and_run(directory, refresh_opportunity_id, "scan",
                                 json.dumps(json.loads(refresh_scan_input)["source"]), None, True)
                   if refresh_scan_input else scan_discovered(directory, refresh_opportunity_id, True))
        refreshed = view(directory, started["task_id"])
        if refreshed["status"] != "completed" or refreshed["artifact"]["outcome"] != "jd_report":
            return {"status": refreshed["status"], "opportunity_id": refresh_opportunity_id, "task": refreshed}
        result = start_and_run(directory, refresh_opportunity_id, "score", f"scan:{refresh_opportunity_id}", None, True)
        return {"status": "advanced", "opportunity_id": refresh_opportunity_id, "task": result}
    if active:
        if active["task_id"] in replacements:
            result = start_and_run(directory, opportunity_id, "scan",
                                   json.dumps(json.loads(replacements[active["task_id"]])["source"]), None, True)
            return {"status": "advanced", "opportunity_id": opportunity_id, "task": result}
        if active["status"] == "waiting" and active["waiting_reason"].startswith("failure:"):
            result = resume_task(directory, active["task_id"], None, None)
            return {"status": "advanced", "opportunity_id": opportunity_id, "task": result}
        if active["status"] == "waiting" and active["module"] == "scan" and active["waiting_reason"] in {"source_access_unknown", "jd_evidence_missing"}:
            source = current_discovered_scan_source(opportunity, directory)
            input_text = json.dumps(source, ensure_ascii=False)
            if not source["jd"].strip():
                store = BusinessStore(directory / "opportunities.db")
                try:
                    store.wait(active["task_id"], "jd_evidence_missing")
                    store.set_context(active["task_id"], "source_probe", {"at": datetime.now(timezone.utc).isoformat()})
                finally:
                    store.close()
                return {"status": "waiting", "opportunity_id": opportunity_id, "reason": "jd_evidence_missing"}
            changed = digest(canonical_scan_input(input_text)) != active["input_hash"]
            store = BusinessStore(directory / "opportunities.db")
            try:
                store.set_context(active["task_id"], "source_probe", {"at": datetime.now(timezone.utc).isoformat()})
            finally:
                store.close()
            result = resume_task(directory, active["task_id"], input_text if changed else None, None)
            return {"status": "advanced", "opportunity_id": opportunity_id, "task": result}
        result = run_task(directory, active["task_id"])
        return {"status": "advanced", "opportunity_id": opportunity_id, "task": result}
    if not scan:
        result = start_and_run(directory, opportunity_id, "scan", json.dumps(current_discovered_scan_source(opportunity, directory), ensure_ascii=False), None)
        return {"status": "advanced", "opportunity_id": opportunity_id, "task": result}
    if scan["outcome"] == "exclude":
        return {"status": "complete", "opportunity_id": opportunity_id, "outcome": "exclude"}
    result = start_and_run(directory, opportunity_id, "score", f"scan:{opportunity_id}", None)
    return {"status": "advanced", "opportunity_id": opportunity_id, "task": result}


def resume_task(
    directory: Path,
    task_id: str,
    input_text: str | None,
    crash_at: str | None,
) -> dict:
    store = BusinessStore(directory / "opportunities.db")
    task = store.task(task_id)
    if task["status"] in ("completed", "cancelled"):
        store.close()
        raise ValueError(f"Terminal task cannot resume: {task['status']}")
    if task["module"] == "apply":
        if input_text is not None:
            store.close()
            raise ValueError("An apply task takes no new input; run apply prepare again")
        if task["status"] == "waiting" and str(task["waiting_reason"] or "").startswith("failure:"):
            # Keep the checkpoint so a completed model call is not repeated.
            store.resume_failed_checkpoint(task_id)
            store.close()
            return run_task(directory, task_id, crash_at=crash_at)
    if input_text is not None:
        input_text = canonical_scan_input(input_text) if task["module"] == "scan" else canonical_score_input(input_text)
        if task["module"] == "scan":
            store.retain_source(task["opportunity_id"], input_text)
    if input_text is not None:
        task = store.reset_input(task_id, input_text)
    elif task["status"] == "waiting":
        task = store.resume_current(task_id)
    store.close()
    return run_task(directory, task_id, start_state=initial_state(task), crash_at=crash_at)

"""Extract, prescreen, and retain one JD through a checkpointed LangGraph."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from career_ops import model as model_adapter
from career_ops.evaluation.prescreen import evaluate as evaluate_prescreen
from career_ops.tracing import traced


class ScanState(TypedDict, total=False):
    inputs: dict
    evidence: dict
    prescreen: dict
    waiting_reason: str
    outcome: str
    artifact: dict
    tool_calls: int


def run_scan(inputs: dict, draft_root: Path) -> dict:
    """Resume completed extraction before any deterministic prescreen or report work."""
    key = hashlib.sha256(json.dumps(inputs, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    directory = draft_root / key / "jd-extraction-v2"
    directory.mkdir(parents=True, exist_ok=True)

    def extract(state: ScanState) -> dict:
        values, source = state["inputs"], state["inputs"]["source"]
        prompt = model_adapter.EVIDENCE + json.dumps({
            "source_capture": source,
            "cv": values["cv"],
            "profile": values["profile"],
            "targeting": values["targeting"],
            "rules": values["rules"],
        }, ensure_ascii=False)
        extracted = model_adapter.call_agent("prescreen_evidence", prompt)[0]
        evidence = model_adapter.attach_evidence(extracted, {"text": source["jd"]})
        if evidence["complete_jd"] is not True:
            return {"evidence": evidence, "waiting_reason": "core_evidence_missing", "tool_calls": 1}
        return {"evidence": evidence, "tool_calls": 1}

    def prescreen(state: ScanState) -> dict:
        source, evidence = state["inputs"]["source"], state["evidence"]
        result = evaluate_prescreen({**evidence["prescreen"], "job": {"url": source["url"]}})
        if result["status"] == "incomplete":
            return {"prescreen": result, "waiting_reason": "core_evidence_missing"}
        if result["status"] == "fail":
            return {
                "prescreen": result, "outcome": "exclude",
                "artifact": {
                    "type": "exclusion", "reason_code": "prescreen_failed",
                    "reason": "; ".join(item["message"] for item in result["discard_reasons"]),
                    "evidence": result["discard_reasons"],
                },
            }
        return {"prescreen": result, "outcome": "jd_report"}

    def report(state: ScanState) -> dict:
        source, evidence = state["inputs"]["source"], state["evidence"]
        artifact = {
            "schema_version": "jd_report_v1",
            "opportunity_id": source["opportunity_id"],
            "url": source["url"],
            "company": evidence["company"],
            "role": evidence["role"],
            "jd": source["jd"],
            "captured_at": source["captured_at"],
            "capture_method": source.get("capture_method", "unknown"),
            "capture_evidence": source.get("capture_evidence", source.get("liveness_evidence", {})),
            "location_evidence": source.get("location_evidence"),
            "employment_evidence": source.get("employment_evidence"),
            "prescreen": state["prescreen"],
            **{key: evidence["prescreen"][key] for key in ("capabilities", "years", "credentials")},
        }
        return {"outcome": "jd_report", "artifact": artifact}

    graph = StateGraph(ScanState)
    graph.add_node("extract", extract)
    graph.add_node("prescreen", prescreen)
    graph.add_node("report", report)
    graph.add_edge(START, "extract")
    graph.add_conditional_edges("extract", lambda state: "wait" if state.get("waiting_reason") else "prescreen",
                                {"wait": END, "prescreen": "prescreen"})
    graph.add_conditional_edges("prescreen", lambda state: "wait" if state.get("waiting_reason") else state["outcome"],
                                {"wait": END, "exclude": END, "jd_report": "report"})
    graph.add_edge("report", END)
    config = traced({"configurable": {"thread_id": key}}, "prescreen-graph", key)
    with SqliteSaver.from_conn_string(str(directory / "scan-checkpoints.db")) as saver:
        compiled = graph.compile(checkpointer=saver)
        checkpoint = compiled.get_state(config)
        if checkpoint.next:
            result = compiled.invoke(None, config)
        elif checkpoint.values and (checkpoint.values.get("outcome") or checkpoint.values.get("waiting_reason")):
            result = checkpoint.values
        else:
            result = compiled.invoke({"inputs": inputs, "tool_calls": 0}, config)
    if result.get("waiting_reason"):
        return {"waiting_reason": result["waiting_reason"], "tool_calls": result["tool_calls"]}
    return {"outcome": result["outcome"], "artifact": result["artifact"], "tool_calls": result["tool_calls"]}

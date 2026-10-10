"""Verify the readable score report and durable shared-company references."""

import json
import re
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from career_ops.evaluation.report import render_report
from career_ops.db import BusinessStore

with tempfile.TemporaryDirectory(prefix="career-ops-report-") as temporary:
    root = Path(temporary)
    directory = root / "draft"
    directory.mkdir()
    (directory / "profile.txt").write_text("Current profile.")
    packet = {"root": str(root), "directory": str(directory), "sources": {"profile": "Current profile."},
              "url": "https://jobs.example.com/roles/1"}
    evidence = {"company": "Example", "role": "Engineer", "complete_jd": True, "liveness": "active",
                "captured_at": "2026-10-01T16:20:27Z",
                "jd": "Build and maintain software products. Annual salary CNY 300k-400k.",
                "years": {"required": 2, "verified": None, "evidence": "CV dates unclear"},
                "credentials": [{"name": "BSc", "mandatory": True, "status": "present", "evidence": "CV"}],
                "capabilities": [
                    {"name": "Kubernetes", "core": False, "mandatory": False, "match": "gap", "evidence": "none | in CV"},
                    {"name": "Python", "core": True, "mandatory": True, "match": "proven", "evidence": "VivoFlow"},
                    {"name": "Azure", "core": True, "mandatory": True, "match": "adjacent", "evidence": "Alibaba Cloud"}]}
    raw = {"score": 3.3700000000000006, "confidence": .93, "evidence_sufficiency": .12,
           "probabilities": {"0": .1, "1": .1, "2": .43, "3": .07, "4": .3}}
    reference = {"company_id": "example", "profile_id": "culture-cn", "request_sha256": "batch",
                 "scope": {"region": "China", "level": "unknown"}, "valid_until": "2026-10-15"}
    fact = {"claim": "Offices close on weekends.", "date": "2026-03-09", "kind": "官方制度",
            "limitations": "Group policy.", "source_url": "https://example.com/policy_(cn)"}
    research = {"prepared_profiles": [{"company_id": "example", "profiles": [{"dimension": "culture", "evidence": {
        "facts": [fact], "gaps": ["每周到岗几天？", "Is the employer direct?"], "conflicts": ["Two leave figures differ."]}}]}]}
    sections = {"verdict": "Deprioritize: culture and direction sit near 3.4.", "direction": "Product engineering duties.",
                "compensation": "The quoted range reaches the CNY 300K floor.",
                "responsibilities": ["Build the  product", "Run services"],
                "risks": ["Alibaba Cloud is adjacent to Azure."], "questions": ["Is the employer direct?"]}
    assessment = {"dimensions": {"direction": raw, "culture": raw}, "company_profiles": {"culture": reference},
                  "company_research": research, "sections": sections,
                  "advertised_comp": {"amount": "300k-400k", "currency": "CNY", "quote": "Annual  salary CNY 300k-400k"}}
    rendered = render_report(packet, evidence, assessment)
    report = rendered["report"]
    # The report is for reading: fixed sections in order, and no machine block or provenance hash.
    assert re.findall(r"^## (\S+)", report, re.M) == ["结论", "职责", "方向", "公司", "文化", "薪酬", "能力匹配", "风险", "待确认"]
    assert "```" not in report and "sha256" not in report and "总分" not in report
    assert not re.search(r"[0-9a-f]{32}", report)
    assert ("deprioritize ｜ 方向 3.37 · 公司 — · 文化 3.37 · 薪酬 — ｜ "
            "核心必备 1 直接 · 1 相邻 · 0 缺口 · 0 未知") in report
    assert "## 方向 3.37（置信度 93% · 充分度 12%）\n\nProduct engineering duties." in report
    assert "3.3700000000000006" not in report
    assert "## 公司 未评分（dimension_unavailable）\n\n暂无调研事实。" in report
    # Research facts are laid out by the program, with their limits and source, next to the score they explain.
    assert ("## 文化 3.37（置信度 93% · 充分度 12%） · 范围 China\n\n"
            "- 2026-03-09 · 官方制度 · Offices close on weekends. — 局限：Group policy. "
            "[来源](<https://example.com/policy_(cn)>)\n- 来源分歧：Two leave figures differ.") in report
    assert "JD 披露：300k-400k CNY（“Annual salary CNY 300k-400k”）\n\nThe quoted range" in report
    assert "- Build the product\n- Run services" in report
    # Capability rows come from the scan judgment, core mandatory first, with table cells escaped.
    assert ("| 类别 | 要求 | 判定 | 依据 |\n|---|---|---|---|\n| 核心必备 | Python | 直接 | VivoFlow |\n"
            "| 核心必备 | Azure | 相邻 | Alibaba Cloud |\n| 必备 | 相关经验 ≥ 2 年 | 未知 | CV dates unclear |\n"
            "| 必备 | BSc | 直接 | CV |\n| 加分 | Kubernetes | 缺口 | none \\| in CV |") in report
    # Research gaps join the questions once.
    assert "## 待确认\n\n- Is the employer direct?\n- 每周到岗几天？\n\n来源：" in report
    assert report.endswith("来源：[jobs.example.com](<https://jobs.example.com/roles/1>) · 2026-10-01 抓取时在线\n")
    # What programs need travels beside the report, not inside it.
    assert rendered["scores"]["culture"] == raw["score"] and rendered["recommendation"] == "deprioritize"
    assert rendered["advertised_comp"]["quote"] == "Annual salary CNY 300k-400k"
    assert rendered["captured_at"] == evidence["captured_at"]
    assert {item["id"] for item in rendered["sources"]} == {"profile", "jd", "research"}
    assert all(re.fullmatch(r"[0-9a-f]{64}", item["sha256"]) for item in rendered["sources"])
    assert "company" not in assessment["dimensions"]
    dimensions = {name: assessment["dimensions"].get(name, {"score": None, "reason": "dimension_unavailable"})
                  for name in ("direction", "company", "culture", "compensation")}
    headed = render_report(packet, evidence, {**assessment, "sections": {
        **sections, "verdict": "## Overview\nDeprioritize for now."}})
    assert "### Overview" in headed["report"] and "\n## Overview" not in headed["report"]
    assert headed["scores"] == rendered["scores"]
    empty = render_report(packet, evidence, {**assessment, "advertised_comp": None, "company_research": {},
                                             "sections": {**sections, "risks": [], "questions": []}})
    assert "## 风险\n\n无。\n\n## 待确认\n\n无。" in empty["report"] and "JD 披露" not in empty["report"]
    for invalid in (True, float("nan"), float("inf"), .9, 5.1):
        broken = {**assessment, "dimensions": {"direction": {**raw, "score": invalid}}}
        try:
            render_report(packet, evidence, broken)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid raw score accepted")
    for field in ("confidence", "evidence_sufficiency"):
        try:
            render_report(packet, evidence, {**assessment, "dimensions": {"direction": {**raw, field: -1}}})
        except ValueError:
            pass
        else:
            raise AssertionError("invalid probability accepted")
    for name, value in (("verdict", None), ("compensation", "  "), ("responsibilities", []), ("risks", "one string"),
                        ("questions", ["ok", ""])):
        incomplete = {**assessment, "sections": {**sections, name: value}}
        try:
            render_report(packet, evidence, incomplete)
        except ValueError as error:
            assert "sections" in str(error)
        else:
            raise AssertionError(f"malformed {name} accepted")
    for claim in ({"verdict": "岗位办公城市未披露。"}, {"questions": ["城市未知，需确认"]}):
        try:
            render_report(packet, {**evidence, "location_evidence": "Shanghai"},
                          {**assessment, "sections": {**sections, **claim}})
        except ValueError as error:
            assert "contradicts retained posting" in str(error)
        else:
            raise AssertionError("contradictory location accepted")
    try:
        render_report(packet, evidence, {**assessment, "advertised_comp": {
            "amount": "300k-400k", "currency": "CNY", "quote": "Monthly salary CNY 300k-400k"}})
    except ValueError as error:
        assert "annual JD evidence" in str(error)
    else:
        raise AssertionError("advertised pay without annual JD wording accepted")
    rendered = render_report(packet, evidence, assessment)
    rating = {"company_id": "example", "profile_id": "culture-cn", "dimension": "culture", "scope": {"region": "China"},
              "valid_until": "2026-10-15", "scoring_request_sha256": "batch", **raw}
    artifact = {"type": "score", "report": rendered["report"], "report_sha256": rendered["report_sha256"],
                "score": rendered["scores"], "scoring_model": "attractiveness-v4", "dimensions": dimensions,
                "recommendation": "deprioritize", "company_ratings": [rating], "company_profiles": {"culture": reference, "company": {"status": "pending"}}}
    store = BusinessStore(root / "business.db")
    pending = store.start("report-pending", "score", "not yet published")
    store.retain_company_ratings(store.db, [rating])
    assert store.task(pending["task_id"])["status"] == "running"
    assert store.db.execute("SELECT count(*) FROM results").fetchone()[0] == 0
    assert store.db.execute("SELECT count(*) FROM job_company_profiles").fetchone()[0] == 0
    independent_reader = BusinessStore(store.path)
    assert json.loads(independent_reader.db.execute("SELECT payload_json FROM company_ratings").fetchone()[0]) == rating
    independent_reader.close()
    store.retain_company_ratings(store.db, [{**rating, "score": 5, "valid_until": "2099-10-15"}])
    assert json.loads(store.db.execute("SELECT payload_json FROM company_ratings").fetchone()[0]) == rating
    with patch("career_ops.db.score_is_current", return_value=True):
        for opportunity in ("job1", "job2"):
            task = store.start(opportunity, "score", json.dumps({"jd_report": {"prescreen": {"status": "uncertain"}}}))
            state = {"task_id": task["task_id"], "input_hash": store.task(task["task_id"])["input_hash"], "outcome": "score",
                     "material_hash": rendered["report_sha256"], "draft": json.dumps(artifact)}
            store.publish(state)
        rejected = store.start("bad-rating", "score", json.dumps({"jd_report": {"prescreen": {"status": "uncertain"}}}))
        mismatched = {**artifact, "score": {**artifact["score"], "culture": 4.37}}
        state = {"task_id": rejected["task_id"], "input_hash": store.task(rejected["task_id"])["input_hash"],
                 "outcome": "score", "material_hash": rendered["report_sha256"], "draft": json.dumps(mismatched)}
        try:
            store.publish(state)
        except ValueError as error:
            assert "dimensions disagree" in str(error)
        else:
            raise AssertionError("score/raw metadata mismatch published")
        assert store.result(rejected["task_id"]) is None
        assert store.db.execute("SELECT count(*) FROM company_ratings").fetchone()[0] == 1
        saved = json.loads(store.db.execute("SELECT payload_json FROM company_ratings").fetchone()[0])
        assert saved["score"] == raw["score"] and saved["confidence"] == .93
        assert store.db.execute("SELECT count(*) FROM job_company_profiles").fetchone()[0] == 4
        assert store.db.execute("SELECT count(*) FROM job_company_profiles WHERE profile_id IS NULL").fetchone()[0] == 2
        assert store.score_views()[0]["dimensions"] == dimensions
        focused = render_report(packet, evidence, {**assessment, "dimensions": {
            name: {**raw, "score": 4.2, "confidence": .1, "evidence_sufficiency": 0}
            for name in ("direction", "company", "culture", "compensation")}})
        assert focused["recommendation"] == "focus"
        task = store.start("low-evidence-focus", "score", json.dumps({"jd_report": {"prescreen": {"status": "uncertain"}}}))
        focused_dimensions = {name: {**raw, "score": 4.2, "confidence": .1, "evidence_sufficiency": 0}
                              for name in ("direction", "company", "culture", "compensation")}
        store.publish({"task_id": task["task_id"], "input_hash": store.task(task["task_id"])["input_hash"],
            "outcome": "score", "material_hash": focused["report_sha256"], "draft": json.dumps({
                "type": "score", "report": focused["report"], "report_sha256": focused["report_sha256"],
                "score": focused["scores"], "scoring_model": "attractiveness-v4",
                "dimensions": focused_dimensions, "recommendation": "focus"})})
        assert next(row for row in store.decision_views()["decisions"]
                    if row["opportunity_id"] == "low-evidence-focus")["action"] == "focus"
    store.close()

print("workflow report: readable rendering and shared SQLite references passed")

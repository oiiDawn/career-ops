"""Render a frozen model assessment as the evidence-linked score report."""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

import yaml

from career_ops.insights.salary import parse_amount


HEADINGS = (
    "A. 岗位概览", "B. 能力竞争力", "C. 入职吸引力", "D. 薪酬与需求",
    "E. 补证问题", "G. 岗位真实性", "Risk Summary", "Evaluation Checklist", "Machine Summary",
)
DIMENSIONS = ("direction", "company", "culture", "compensation")


def conflicting_sections(sections: dict, evidence: dict) -> list[str]:
    """Reject claims that deny direct posting facts retained by scan."""
    if not isinstance(sections, dict):
        return []
    conflicts = []
    for name, body in sections.items():
        if not isinstance(body, str):
            continue
        if evidence.get("location_evidence") and re.search(
            r"(?:地点|城市).{0,8}(?:未披露|未知|未提供|无法确认)", body
        ):
            conflicts.append(name)
        elif "browser_snapshot" in str(evidence.get("liveness_reason", "")) and re.search(
            r"(?:不含|缺少|没有|未提供).{0,16}(?:岗位页面|页面|快照|liveness)", body, re.I
        ):
            conflicts.append(name)
    return conflicts


def digest(value: bytes | str) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode()).hexdigest()


def dimension_scores(dimensions: dict) -> dict:
    """Preserve Jev expectation scores; pending evidence never becomes a numeric rating."""
    if not isinstance(dimensions, dict) or set(dimensions) != set(DIMENSIONS):
        raise ValueError("Score dimensions must match")
    scores = {}
    for name, dimension in dimensions.items():
        if not isinstance(dimension, dict) or "score" not in dimension:
            raise ValueError(f"{name}: invalid dimension fields")
        score = dimension["score"]
        if score is not None and (type(score) not in (int, float) or not math.isfinite(score) or not 1 <= score <= 5):
            raise ValueError(f"{name}: score must be null or a number from 1 to 5")
        if score is None:
            if dimension.get("status") != "pending":
                raise ValueError(f"{name}: null score must be pending")
        else:
            for field in ("confidence", "evidence_sufficiency"):
                value = dimension.get(field)
                if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
                    raise ValueError(f"{name}: invalid {field}")
            if not isinstance(dimension.get("evidence_status"), str):
                raise ValueError(f"{name}: evidence status required")
        scores[name] = score
    return scores


def render_report(packet: dict, evidence: dict, assessment: dict) -> dict:
    root, directory = Path(packet["root"]), Path(packet["directory"])
    if evidence.get("complete_jd") is not True or evidence.get("liveness") != "active" or not evidence.get("jd", "").strip():
        raise ValueError("Complete live JD required")
    required_sections = ("overview", "capabilities", "compensation", "questions", "legitimacy", "risks", "checklist")
    sections = assessment.get("sections")
    if not isinstance(sections, dict) or any(not isinstance(sections.get(name), str) or not sections[name].strip() for name in required_sections):
        raise ValueError("Report sections are incomplete")
    conflicts = conflicting_sections(sections, evidence)
    if conflicts:
        raise ValueError(f"Report contradicts retained posting evidence: {', '.join(conflicts)}")
    files = {name: directory / f"{name}.txt" for name in packet["sources"]}
    files["jd"] = directory / "jd.txt"
    files["jd"].write_text(evidence["jd"])
    for index, source in enumerate(assessment.get("sources", []), 1):
        if source.get("id") != f"web{index}" or not source.get("text", "").strip():
            raise ValueError("External sources must be sequential web1, web2, ... with text")
        files[source["id"]] = directory / f"{source['id']}.txt"
        files[source["id"]].write_text(source["text"])
    dimensions = {name: assessment.get("dimensions", {}).get(name,
                  {"score": None, "status": "pending", "reason": "dimension_unavailable"}) for name in DIMENSIONS}
    score = dimension_scores(dimensions)
    research = assessment.get("company_research", {})
    if not isinstance(research, (dict, list)):
        raise ValueError("Company research provenance must be structured")
    advertised = assessment.get("advertised_comp")
    if advertised is not None:
        if (not isinstance(advertised, dict) or set(advertised) != {"amount", "currency", "quote"}
                or any(not isinstance(advertised[key], str) or not advertised[key].strip()
                       for key in ("amount", "currency", "quote"))
                or parse_amount(advertised["amount"]) is None):
            raise ValueError("Advertised annual compensation must have a parseable amount and JD quote")
        quote = advertised["quote"]
        match = re.search(r"\s+".join(re.escape(word) for word in quote.split()), evidence["jd"], re.I)
        if not match or not re.search(r"\b(?:annual(?:ly)?|yearly|per year)\b|年薪|每年|/yr\b|/year\b", quote, re.I):
            raise ValueError("Advertised compensation requires exact annual JD evidence")
        if any(number not in quote for number in re.findall(r"\d[\d.,]*", advertised["amount"])):
            raise ValueError("Advertised amount must appear in the JD quote")
        currency = advertised["currency"]
        if currency != "UNKNOWN" and (not re.fullmatch(r"[A-Z]{3}", currency)
                                      or not re.search(r"(?<![A-Z])" + currency + r"(?![A-Z])", quote)):
            raise ValueError("Advertised currency must appear as an ISO code in the JD quote")
        advertised = {**advertised, "quote": match.group(0)}
    files["research"] = directory / "research.json"
    files["research"].write_text(json.dumps(research, ensure_ascii=False, indent=2) + "\n")
    summary = {
        "report_format": "scoring-v3", "scoring_model": "attractiveness-v4",
        "company": evidence["company"], "role": evidence["role"], "complete_jd": True, "jd_source": "jd",
        "captured_at": evidence.get("captured_at"), "advertised_comp": advertised,
        "sources": [{"id": name, "path": str(path.relative_to(root)), "sha256": digest(path.read_bytes())} for name, path in files.items()],
        "dimensions": dimensions, "company_profiles": assessment.get("company_profiles", {}),
        "company_research": research, "recommendation": "evidence_review",
    }
    table = "| 维度 | 分数 | Confidence | 充分性 | 状态 |\n|---|---|---|---|---|\n" + "\n".join(
        f"| {name} | {format(score[name], '.2f') if score[name] is not None else 'Unknown'} | "
        f"{dimensions[name].get('confidence', '—')} | {dimensions[name].get('evidence_sufficiency', '—')} | "
        f"{dimensions[name].get('status', dimensions[name].get('evidence_status', 'pending'))} |"
        for name in DIMENSIONS
    )
    research_status = "公司档案、摘要与原始来源记录见 Machine Summary；充分性阈值待确认，需证据审阅"
    bodies = {
        "A. 岗位概览": sections["overview"], "B. 能力竞争力": sections["capabilities"],
        "C. 入职吸引力": f"**入职吸引力分项：**\n\n{table}",
        "D. 薪酬与需求": sections["compensation"], "E. 补证问题": sections["questions"],
        "G. 岗位真实性": sections["legitimacy"], "Risk Summary": sections["risks"],
        "Evaluation Checklist": f"{sections['checklist']}\n\n联网研究：{research_status}；记录见 E. 补证问题。",
        "Machine Summary": f"```yaml\n{yaml.safe_dump(summary, allow_unicode=True, sort_keys=False, width=10_000).strip()}\n```",
    }
    if any(not isinstance(body, str) or len(body.strip()) < 20 or re.search(r"^## ", body, re.MULTILINE) for body in bodies.values()):
        raise ValueError("Report section missing or contains extra level-two headings")
    report = "\n\n".join(f"## {heading}\n\n{bodies[heading]}" for heading in HEADINGS) + "\n"
    (directory / "report.md").write_text(report)
    return {"report": report, "report_sha256": digest(report), "scores": score}

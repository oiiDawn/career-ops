"""Render a frozen assessment record as the score report the candidate reads."""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from urllib.parse import urlsplit

from career_ops.insights.salary import parse_amount
from career_ops.evaluation.capabilities import VERDICTS, core_counts, rows
from career_ops.evaluation.decisions import classify


DIMENSIONS = ("direction", "company", "culture", "compensation")
LABELS = {"direction": "方向", "company": "公司", "culture": "文化", "compensation": "薪酬"}
TEXT_SECTIONS = ("verdict", "direction", "compensation")
LIST_SECTIONS = ("responsibilities", "risks", "questions")


def section_value(name: str, value: object) -> str | list[str] | None:
    """Accept one model-written field in its contracted shape; only risks and questions may be empty."""
    if name in TEXT_SECTIONS:
        return value.strip() if isinstance(value, str) and value.strip() else None
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        return None
    if name == "responsibilities" and not value:
        return None
    return [" ".join(item.split()) for item in value]


def conflicting_sections(sections: dict, evidence: dict) -> list[str]:
    """Reject claims that deny direct posting facts retained by scan."""
    if not isinstance(sections, dict):
        return []
    conflicts = []
    for name, value in sections.items():
        body = "\n".join(value) if isinstance(value, list) else value
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
            if not isinstance(dimension.get("reason"), str) or not dimension["reason"].strip():
                raise ValueError(f"{name}: null score requires a reason")
        else:
            for field in ("confidence", "evidence_sufficiency"):
                value = dimension.get(field)
                if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
                    raise ValueError(f"{name}: invalid {field}")
        scores[name] = score
    return scores


def advertised_compensation(advertised: object, jd: str) -> dict | None:
    """Record advertised pay only when the JD itself states the annual amount verbatim."""
    if advertised is None:
        return None
    if (not isinstance(advertised, dict) or set(advertised) != {"amount", "currency", "quote"}
            or any(not isinstance(advertised[key], str) or not advertised[key].strip()
                   for key in ("amount", "currency", "quote"))
            or parse_amount(advertised["amount"]) is None):
        raise ValueError("Advertised annual compensation must have a parseable amount and JD quote")
    quote = advertised["quote"]
    match = re.search(r"\s+".join(re.escape(word) for word in quote.split()), jd, re.I)
    if not match or not re.search(r"\b(?:annual(?:ly)?|yearly|per year)\b|年薪|每年|/yr\b|/year\b", quote, re.I):
        raise ValueError("Advertised compensation requires exact annual JD evidence")
    if any(number not in quote for number in re.findall(r"\d[\d.,]*", advertised["amount"])):
        raise ValueError("Advertised amount must appear in the JD quote")
    currency = advertised["currency"]
    if currency != "UNKNOWN" and (not re.fullmatch(r"[A-Z]{3}", currency)
                                  or not re.search(r"(?<![A-Z])" + currency + r"(?![A-Z])", quote)):
        raise ValueError("Advertised currency must appear as an ISO code in the JD quote")
    return {**advertised, "quote": match.group(0)}


def _heading(name: str, dimension: dict, profile: object) -> str:
    scope = profile.get("scope") if isinstance(profile, dict) else None
    scope = " / ".join(str(scope[key]) for key in ("region", "level") if scope.get(key) not in (None, "unknown")) \
        if isinstance(scope, dict) else ""
    if dimension["score"] is None:
        title = f"## {LABELS[name]} 未评分（{dimension['reason']}）"
    else:
        title = (f"## {LABELS[name]} {dimension['score']:.2f}（置信度 {dimension['confidence']:.0%} · "
                 f"充分度 {dimension['evidence_sufficiency']:.0%}）")
    return title + (f" · 范围 {scope}" if scope else "")


def _plain(value: object) -> str:
    """Keep quoted text on one line and stop a range tilde from reading as Markdown strikethrough."""
    return " ".join(str(value).split()).replace("~", "～")


def _research(research: object, name: str) -> tuple[list[str], list[str]]:
    """List one dimension's sourced facts as research wrote them; return its open questions separately."""
    lines, gaps = [], []
    companies = research.get("prepared_profiles", []) if isinstance(research, dict) else []
    for profile in (profile for company in companies for profile in company.get("profiles", [])):
        if profile.get("dimension") != name:
            continue
        evidence = profile.get("evidence", {})
        for fact in evidence.get("facts", []):
            lead = " · ".join(str(fact[key]) for key in ("date", "kind", "claim") if fact.get(key) and fact[key] != "unknown")
            limits = f" — 局限：{fact['limitations']}" if fact.get("limitations") else ""
            source = f" [来源](<{fact['source_url']}>)" if fact.get("source_url") else ""
            lines.append(f"- {_plain(lead + limits)}{source}")
        lines += [f"- 来源分歧：{_plain(conflict)}" for conflict in evidence.get("conflicts", [])]
        gaps += evidence.get("gaps", [])
    return lines, gaps


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {_plain(item)}" for item in items) or "无。"


def _cell(value: object) -> str:
    return _plain(value).replace("|", "\\|")


def render_report(packet: dict, evidence: dict, assessment: dict) -> dict:
    """Project the assessment record into Markdown; nothing reads the report back."""
    root, directory = Path(packet["root"]), Path(packet["directory"])
    if evidence.get("complete_jd") is not True or evidence.get("liveness") != "active" or not evidence.get("jd", "").strip():
        raise ValueError("Complete live JD required")
    given = assessment.get("sections")
    sections = {name: section_value(name, given.get(name)) for name in TEXT_SECTIONS + LIST_SECTIONS} \
        if isinstance(given, dict) else {}
    if not sections or any(value is None for value in sections.values()):
        raise ValueError("Report sections are incomplete")
    conflicts = conflicting_sections(sections, evidence)
    if conflicts:
        raise ValueError(f"Report contradicts retained posting evidence: {', '.join(conflicts)}")
    dimensions = {name: assessment.get("dimensions", {}).get(name,
                  {"score": None, "reason": "dimension_unavailable"}) for name in DIMENSIONS}
    score = dimension_scores(dimensions)
    research = assessment.get("company_research", {})
    if not isinstance(research, (dict, list)):
        raise ValueError("Company research provenance must be structured")
    advertised = advertised_compensation(assessment.get("advertised_comp"), evidence["jd"])
    files = {name: directory / f"{name}.txt" for name in packet["sources"]}
    files["jd"] = directory / "jd.txt"
    files["jd"].write_text(evidence["jd"])
    files["research"] = directory / "research.json"
    files["research"].write_text(json.dumps(research, ensure_ascii=False, indent=2) + "\n")
    recommendation = classify(score, evidence.get("prescreen", {"status": "uncertain"}))

    text = {name: re.sub(r"(?m)^#{1,2}(?=[ \t])", "###", sections[name]).replace("~", "～") for name in TEXT_SECTIONS}
    counts = core_counts(evidence)
    summary = " ｜ ".join((
        recommendation,
        " · ".join(f"{LABELS[name]} {'—' if score[name] is None else format(score[name], '.2f')}" for name in DIMENSIONS),
        "核心必备 " + " · ".join(f"{counts[match]} {label}" for match, label in VERDICTS.items()),
    ))
    blocks = [f"## 结论\n\n{summary}\n\n{text['verdict']}", f"## 职责\n\n{_bullets(sections['responsibilities'])}"]
    questions = list(sections["questions"])
    profiles = assessment.get("company_profiles", {})
    for name in DIMENSIONS:
        facts, gaps = _research(research, name)
        body = []
        if name == "direction":
            body.append(text["direction"])
        else:
            if name == "compensation":
                if advertised:
                    body.append(f"JD 披露：{advertised['amount']} {advertised['currency']}（“{advertised['quote']}”）")
                body.append(text["compensation"])
            body.append("\n".join(facts) or "暂无调研事实。")
        blocks.append(_heading(name, dimensions[name], profiles.get(name)) + "\n\n" + "\n\n".join(body))
        questions += [gap for gap in gaps if gap not in questions]
    table = "\n".join(f"| {row['tier']} | {_cell(row['requirement'])} | {VERDICTS[row['match']]} | {_cell(row['evidence'])} |"
                      for row in rows(evidence))
    blocks.append("## 能力匹配\n\n" + (f"| 类别 | 要求 | 判定 | 依据 |\n|---|---|---|---|\n{table}" if table else "无。"))
    blocks.append(f"## 风险\n\n{_bullets(sections['risks'])}")
    blocks.append(f"## 待确认\n\n{_bullets(questions)}")
    host = urlsplit(packet["url"]).netloc
    blocks.append(f"来源：[{host}](<{packet['url']}>) · {str(evidence.get('captured_at') or '')[:10]} 抓取时在线")
    report = "\n\n".join(blocks) + "\n"
    (directory / "report.md").write_text(report)
    return {
        "report": report, "report_sha256": digest(report), "scores": score, "recommendation": recommendation,
        "advertised_comp": advertised, "captured_at": evidence.get("captured_at"),
        "sources": [{"id": name, "path": str(path.relative_to(root)), "sha256": digest(path.read_bytes())}
                    for name, path in files.items()],
    }

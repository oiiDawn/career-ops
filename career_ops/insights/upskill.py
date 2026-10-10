"""Aggregate judged capability gaps across evaluated opportunities for learning strategy."""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import re
import sqlite3

from career_ops.skills import extract_skills, split_skills_section


def upskill_view(db: sqlite3.Connection, cv: Path, *, min_reports: int = 5) -> dict:
    """Aggregate the scan capability gaps of scored opportunities; no scalar fit is inferred from attractiveness."""
    if min_reports < 1:
        raise ValueError("Minimum reports must be positive")
    if not cv.is_file():
        return {"status": "source_missing", "source": "cv", "gaps": None}
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='results'").fetchone():
        return {"status": "source_missing", "source": "results", "gaps": None}
    reports = {}
    for row in db.execute("SELECT opportunity_id,module,payload FROM results WHERE module IN ('score','scan') ORDER BY rowid DESC"):
        reports.setdefault((str(row["opportunity_id"]), row["module"]), json.loads(row["payload"]))
    reviewed = []
    unjudged = 0
    for (key, module), payload in reports.items():
        if module != "score" or payload.get("outcome") != "score":
            continue
        scan = reports.get((key, "scan"), {})
        judged = scan.get("artifact", {}).get("capabilities") if scan.get("outcome") == "jd_report" else None
        if not isinstance(judged, list):
            unjudged += 1
            continue
        reviewed.append({"opportunity_id": key, "gaps": list(dict.fromkeys(
            item["name"] for item in judged if item.get("match") == "gap" and item.get("name")))})
    if len(reviewed) < min_reports:
        return {"status": "insufficient_data", "reports": len(reviewed), "minimum": min_reports,
                "unjudged_reports": unjudged, "gap_source": "scan capability matches", "gaps": None}
    named, _ = split_skills_section(re.sub(r"<!--[\s\S]*?-->", "", cv.read_text()))
    known = extract_skills(named)
    grouped = defaultdict(lambda: {"reports": set(), "topics": set()})
    topics = defaultdict(set)
    excluded = defaultdict(set)
    for report in reviewed:
        for topic in report["gaps"]:
            topics[topic].add(report["opportunity_id"])
            for skill in extract_skills(topic):
                if skill in known:
                    excluded[skill].add(report["opportunity_id"])
                    continue
                grouped[skill]["reports"].add(report["opportunity_id"])
                grouped[skill]["topics"].add(topic)
    gaps = []
    for skill, value in grouped.items():
        count = len(value["reports"])
        share = count / len(reviewed)
        tier = "Critical" if share >= 0.5 and count >= 3 else "High" if share >= 0.3 and count >= 2 else "Medium" if count >= 2 else "Low"
        gaps.append({"skill": skill, "reports": count, "share": round(share, 2), "tier": tier,
                     "sources": sorted(value["reports"]), "topics": sorted(value["topics"])})
    gaps.sort(key=lambda item: (-item["reports"], item["skill"]))
    topic_rows = [{"topic": topic, "reports": len(keys), "sources": sorted(keys)} for topic, keys in topics.items()]
    topic_rows.sort(key=lambda item: (-item["reports"], item["topic"]))
    return {"status": "observed", "reports": len(reviewed), "minimum": min_reports,
            "unjudged_reports": unjudged,
            "priority_basis": "gap prevalence among evaluated reports; scalar fit was retired",
            "topics": topic_rows, "gaps": gaps,
            "excludedAsKnown": [{"skill": skill, "reports": len(keys)} for skill, keys in sorted(excluded.items())],
            "knownSkills": sorted(known)}

"""Read the scan's capability matches: the one judgment of what the candidate can evidence."""

from __future__ import annotations


VERDICTS = {"proven": "直接", "adjacent": "相邻", "gap": "缺口", "unverified": "未知"}
TIERS = ("核心必备", "必备", "加分")


def rows(scan: dict) -> list[dict]:
    """Every requirement the scan judged, core mandatory first: capabilities, tenure and credentials."""
    found = []
    for item in scan.get("capabilities") or []:
        tier = 0 if item["core"] and item["mandatory"] else 1 if item["mandatory"] else 2
        found.append({"requirement": item["name"], "match": item["match"], "tier": TIERS[tier],
                      "evidence": item.get("evidence") or ""})
    years = scan.get("years") or {}
    if years.get("required"):
        verified = years.get("verified")
        match = "unverified" if verified is None else "proven" if verified >= years["required"] else "gap"
        found.append({"requirement": f"相关经验 ≥ {years['required']:g} 年", "match": match, "tier": TIERS[1],
                      "evidence": years.get("evidence") or ""})
    for item in scan.get("credentials") or []:
        match = {"present": "proven", "absent": "gap"}.get(item["status"], "unverified")
        found.append({"requirement": item["name"], "match": match, "tier": TIERS[1 if item["mandatory"] else 2],
                      "evidence": item.get("evidence") or ""})
    return sorted(found, key=lambda row: TIERS.index(row["tier"]))


def core_counts(scan: dict) -> dict:
    """Count core mandatory capabilities by verdict, the same items the prescreen gate reads."""
    counts = dict.fromkeys(VERDICTS, 0)
    for item in scan.get("capabilities") or []:
        if item["core"] and item["mandatory"]:
            counts[item["match"]] += 1
    return counts

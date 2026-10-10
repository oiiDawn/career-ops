"""Check the recurring capability gap strategy drawn from scan judgments."""

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from career_ops.insights.upskill import upskill_view


with tempfile.TemporaryDirectory() as temp:
    cv_path = Path(temp) / "cv.md"
    cv_path.write_text("## Skills\nPython\n## Experience\nI once mentioned Terraform but it is unverified.\n")
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    assert upskill_view(db, cv_path)["status"] == "source_missing"
    db.execute("CREATE TABLE results(opportunity_id TEXT,module TEXT,payload TEXT)")
    judged = [{"name": "Terraform 平台交付", "core": True, "mandatory": True, "match": "gap"},
              {"name": "企业架构路线图", "core": False, "mandatory": False, "match": "gap"},
              {"name": "Python 开发", "core": True, "mandatory": True, "match": "proven"}]
    for index in range(5):
        db.execute("INSERT INTO results VALUES(?,?,?)", (str(index), "score", json.dumps({"outcome": "score", "artifact": {}})))
        db.execute("INSERT INTO results VALUES(?,?,?)", (str(index), "scan", json.dumps({
            "outcome": "jd_report", "artifact": {"capabilities": judged}})))
    db.execute("INSERT INTO results VALUES(?,?,?)", ("bad", "score", json.dumps({"outcome": "score", "artifact": {}})))
    result = upskill_view(db, cv_path)
    assert result["status"] == "observed" and result["reports"] == 5
    assert result["unjudged_reports"] == 1
    assert result["gaps"][0]["skill"] == "Terraform"
    assert result["gaps"][0]["tier"] == "Critical"
    assert any(topic["topic"] == "企业架构路线图" for topic in result["topics"])
    assert all(gap["skill"] != "Python" for gap in result["gaps"])
    assert upskill_view(db, cv_path, min_reports=6)["status"] == "insufficient_data"
    db.close()

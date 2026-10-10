"""Check score-based attention, confirmed failures and deterministic ordering."""

import sys
import json

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from career_ops.evaluation.decisions import classify, order, valid_scores, worth_attention


score = {"direction": 4.5, "compensation": 4.5, "company": 3.5, "culture": 3.5}
assert classify(score, {"status": "pass"}) == "focus"
assert classify(score, {"status": "uncertain"}) == "focus"
assert classify({**score, "company": 3}, {"status": "pass"}) == "deprioritize"
assert classify({**score, "compensation": None}, {"status": "pass"}) == "deprioritize"
assert not valid_scores({"direction": 4, "compensation": 4, "company": None})
assert classify(score, {"status": "fail"}) == "discard"

rows = [
    {"opportunity_id": "later", "action": "focus", "deadline": None, "effort_days": 1, "scores": score},
    {"opportunity_id": "urgent", "action": "focus", "deadline": "2026-10-01", "effort_days": None, "scores": score},
    {"opportunity_id": "low", "action": "deprioritize", "deadline": "2026-09-30", "effort_days": 0, "scores": {**score, "company": 3}},
]
assert [row["opportunity_id"] for row in order(rows)] == ["urgent", "later", "low"]
assert [row["opportunity_id"] for row in order([
    {**rows[0], "opportunity_id": "z", "scores": {**score, "company": 5}},
    {**rows[0], "opportunity_id": "a", "scores": score},
])] == ["a", "z"]
for invalid in ("2026-02-30", "2026-9-30"):
    try:
        order([{**rows[0], "deadline": invalid}])
    except ValueError:
        pass
    else:
        raise AssertionError("invalid deadline accepted")

print("workflow decisions: action policy and ordering passed")

v4 = {"direction": 4.96, "company": 4.02, "culture": 3.40, "compensation": None}
assert valid_scores(v4) and not worth_attention(v4)
assert classify(v4, {"status": "pass"}) == "deprioritize"
assert classify({k: 5.0 for k in v4}, {"status": "pass"}) == "focus"
assert classify(v4, {"status": "fail"}) == "discard"
assert not valid_scores({**v4, "culture": float("nan")})

assert not worth_attention({k: 4.0 for k in v4})
assert worth_attention({'direction':4.1, 'company':3.1, 'culture':3.01, 'compensation':4.01})
assert not worth_attention({'direction':4.1, 'company':3.1, 'culture':3.0, 'compensation':4.01})
assert not worth_attention({'direction':4.1, 'company':3.1, 'culture':3.01, 'compensation':4.0})
assert not worth_attention({**{k: 4.1 for k in v4}, "company": None})

# Recommendation changes preserve scores; evidence and numeric rubric changes invalidate them.
import sqlite3
from unittest.mock import patch
from career_ops.input_contracts import digest, score_is_current

with sqlite3.connect(':memory:') as connection:
    connection.execute('CREATE TABLE tasks (module TEXT, opportunity_id TEXT, input_hash TEXT, input_payload TEXT)')
    frozen = {'rubric': 'intro old\n## 共同口径\nnumeric grading\n## 维护单位与岗位引用\nprocess old\n## 充分性与推荐的关系\n正式推荐按四维分数执行 old', 'rules': '初期四维均有分数且各自≥4才推荐；', 'cv': 'candidate', 'jd_report': {'opportunity_id': '7'}}
    payload = json.dumps(frozen)
    connection.execute('INSERT INTO tasks VALUES (?, ?, ?, ?)', ('score', '7', digest(payload), payload))
    updated = dict(frozen, rubric='intro new\n## 共同口径\nnumeric grading\n## 维护单位与岗位引用\nprocess new\n## 充分性与推荐的关系\n正式推荐按四维分数执行 new', rules='推荐阈值见 rules/evaluation/four-dimension.md；')
    with patch('career_ops.input_contracts.score_inputs', return_value=json.dumps(updated)):
        assert score_is_current(connection, digest(payload), frozen['jd_report'])
    for updated in (dict(frozen, rubric=frozen['rubric'].replace('numeric grading', 'changed grading')), dict(frozen, cv='changed candidate'), dict(frozen, jd_report={'opportunity_id': '7', 'jd': 'changed'})):
        with patch('career_ops.input_contracts.score_inputs', return_value=json.dumps(updated)):
            assert not score_is_current(connection, digest(payload), frozen['jd_report'])
    connection.execute('UPDATE tasks SET input_payload=?', (json.dumps(dict(frozen, cv='tampered')),))
    assert not score_is_current(connection, digest(payload), frozen['jd_report'])

"""Verify resume reuses a rendered score instead of repeating web research."""

import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from career_ops import model as model_adapter
from career_ops.applications import apply_graph
from career_ops.evaluation import score_graph

runner = SimpleNamespace(DRAFT_ROOT=None)
runner.apply_evaluate = lambda payload: apply_graph.apply_evaluate(payload, runner.DRAFT_ROOT)
runner.evaluate = lambda payload: score_graph.run_score(payload["inputs"], runner.DRAFT_ROOT, ROOT)

flattened = {"name": "Jiaming Zhang", "email": "candidate@example.com", "summary": "Grounded"}
normalized = apply_graph.normalize_resume_payload(flattened)
assert normalized["candidate"] == {"name": "Jiaming Zhang", "email": "candidate@example.com"}
assert "name" not in normalized

nested = {
    "basics": {"name": "Jiaming Zhang", "email": "candidate@example.com"},
    "sections": {
        "summary": {"headline": "Engineer", "summary": "Grounded"},
        "experience": [], "projects": [], "education": [], "skills": [],
        "projects_start_on_new_page": True,
    },
}
assert apply_graph.application_package_error({"resume_payload": nested, **{
    key: "Grounded" for key in ("changes", "cover_letter", "upskill", "interview_prep", "questions")
}}) is None
assert nested == {
    "candidate": {"name": "Jiaming Zhang", "email": "candidate@example.com"},
    "headline": "Engineer", "summary": "Grounded", "experience": [], "projects": [],
    "education": [], "skills": [], "projects_start_on_new_page": True,
}

grouped = {
    "basics": {"name": "Jiaming Zhang", "email": "candidate@example.com", "headline": "Engineer",
               "summary": "Grounded", "profiles": [{"network": "LinkedIn", "url": "https://linkedin.com/in/example"}]},
    "experience": [], "projects": [], "education": [], "skills": [],
}
assert apply_graph.normalize_resume_payload(grouped) == {
    "candidate": {"name": "Jiaming Zhang", "email": "candidate@example.com",
                  "linkedin": {"url": "https://linkedin.com/in/example", "display": "https://linkedin.com/in/example"}},
    "headline": "Engineer", "summary": "Grounded",
    "experience": [], "projects": [], "education": [], "skills": [],
}

complete_package = {
    "resume_payload": {
        "candidate": {"name": "Jiaming Zhang"}, "summary": "Grounded",
        "experience": [], "projects": [], "education": [], "skills": [],
    },
    "changes": "Grounded changes", "cover_letter": "Grounded letter",
    "upskill": "Grounded plan", "interview_prep": "Grounded preparation",
    "questions": "Grounded questions",
}
assert apply_graph.application_package_error({**complete_package, "upskill": {"topics": []}}) == "upskill must be a nonempty Markdown string"
package_phases = []
package_prompts = []
initial_drafts = tempfile.TemporaryDirectory(prefix="career-ops-model-initial-")
runner.DRAFT_ROOT = Path(initial_drafts.name)
original_call_agent = model_adapter.call_agent
def package_call(phase, *_args):
    package_phases.append(phase)
    package_prompts.append(_args[0])
    return ({"resume_payload": complete_package["resume_payload"], "changes": "partial"}
            if phase == "apply_evaluate" else complete_package), f"{phase}-session"
model_adapter.call_agent = package_call
try:
    package = runner.apply_evaluate({"inputs": {}, "revision": 0})
finally:
    model_adapter.call_agent = original_call_agent
assert package_phases == ["apply_evaluate", "apply_repair"]
assert "configured language.output" in package_prompts[0] and "JD language" not in package_prompts[0]
assert package["artifact"] == complete_package
assert package["tool_calls"] == 2

revision_phases = []
def revision_call(phase, *_args):
    revision_phases.append(phase)
    return {"questions": "# Corrected grounded questions"}, "revision-session"
model_adapter.call_agent = revision_call
try:
    revised = runner.apply_evaluate({"inputs": {}, "previous_artifact": complete_package})
finally:
    model_adapter.call_agent = original_call_agent
assert revision_phases == ["apply_evaluate"]
assert revised["artifact"] == {**complete_package, "questions": "# Corrected grounded questions"}
assert complete_package["questions"] == "Grounded questions"
initial_drafts.cleanup()

with tempfile.TemporaryDirectory(prefix="career-ops-apply-checkpoint-") as temporary:
    runner.DRAFT_ROOT = Path(temporary)
    payload = {"inputs": {"feedback": ["checkpoint test"]}}
    validation = apply_graph.application_package_error
    def interrupted_validation(_decision):
        raise RuntimeError("validation interrupted")
    model_adapter.call_agent = lambda *_args, **_kwargs: (complete_package, "draft-session")
    apply_graph.application_package_error = interrupted_validation
    try:
        try:
            runner.apply_evaluate(payload)
        except RuntimeError as error:
            assert str(error) == "validation interrupted"
        else:
            raise AssertionError("Apply validation interruption was not surfaced")
    finally:
        model_adapter.call_agent = original_call_agent
        apply_graph.application_package_error = validation
    assert len(list(runner.DRAFT_ROOT.glob("*/apply-checkpoints.db"))) == 1
    def no_more_apply_calls(*_args, **_kwargs):
        raise AssertionError("Recovery repeated application generation")
    model_adapter.call_agent = no_more_apply_calls
    try:
        assert runner.apply_evaluate(payload)["artifact"] == complete_package
    finally:
        model_adapter.call_agent = original_call_agent

with tempfile.TemporaryDirectory(prefix="career-ops-apply-repair-checkpoint-") as temporary:
    runner.DRAFT_ROOT = Path(temporary)
    payload = {"inputs": {"feedback": ["repair checkpoint test"]}}
    validation = apply_graph.application_package_error
    validations = 0
    def interrupted_finish(decision):
        global validations
        validations += 1
        if validations == 2:
            raise RuntimeError("finish interrupted after repair")
        return validation(decision)
    def repair_call(phase, *_args, **_kwargs):
        if phase == "apply_evaluate":
            return {"resume_payload": complete_package["resume_payload"]}, "draft-session"
        assert phase == "apply_repair"
        return complete_package, "repair-session"
    model_adapter.call_agent = repair_call
    apply_graph.application_package_error = interrupted_finish
    try:
        try:
            runner.apply_evaluate(payload)
        except RuntimeError as error:
            assert str(error) == "finish interrupted after repair"
        else:
            raise AssertionError("Apply finish interruption was not surfaced")
    finally:
        model_adapter.call_agent = original_call_agent
        apply_graph.application_package_error = validation
    model_adapter.call_agent = no_more_apply_calls
    try:
        recovered = runner.apply_evaluate(payload)
        assert runner.apply_evaluate(payload) == recovered
    finally:
        model_adapter.call_agent = original_call_agent
    assert recovered["artifact"] == complete_package and recovered["tool_calls"] == 2

print("workflow model runner: application generation and checkpoint recovery passed")

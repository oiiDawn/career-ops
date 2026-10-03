"""Keep Langfuse tracing optional, nested under one trace, and harmless when the host is down."""

import os
from pathlib import Path
import sys
from typing import TypedDict
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from langchain_core.callbacks import BaseCallbackHandler
from langfuse.langchain import CallbackHandler
from langgraph.graph import END, START, StateGraph

from career_ops.tracing import traced


class State(TypedDict):
    value: int


def graph(name, node):
    builder = StateGraph(State)
    builder.add_node("step", node)
    builder.add_edge(START, "step")
    builder.add_edge("step", END)
    return builder.compile(name=name)


class Recorder(BaseCallbackHandler):
    def __init__(self):
        self.names = []

    def on_chain_start(self, serialized, inputs, *, name=None, **kwargs):
        self.names.append(name)


SETTINGS = {"LANGFUSE_HOST": "http://127.0.0.1:9", "LANGFUSE_PUBLIC_KEY": "pk-lf-test",
            "LANGFUSE_SECRET_KEY": "sk-lf-test", "LANGFUSE_TRACING_ENABLED": "true", "LANGFUSE_TIMEOUT": "1"}

with patch.dict(os.environ, {**SETTINGS, "LANGFUSE_HOST": ""}):
    assert traced({}, "score", "task-1") == {"run_name": "score"}
with patch.dict(os.environ, {**SETTINGS, "LANGFUSE_TRACING_ENABLED": "false"}):
    assert "callbacks" not in traced({}, "score", "task-1")
for remote in ("https://cloud.langfuse.com", "http://langfuse.example.com:3001"):
    with patch.dict(os.environ, {**SETTINGS, "LANGFUSE_HOST": remote}):
        assert "callbacks" not in traced({}, "score", "task-1"), remote

with patch.dict(os.environ, SETTINGS):
    config = traced({"configurable": {"thread_id": "t"}}, "score", "task-1")
    assert config["configurable"] == {"thread_id": "t"} and config["run_name"] == "score"
    assert isinstance(config["callbacks"][0], CallbackHandler)
    assert config["metadata"]["langfuse_session_id"] == "task-1"
    assert config["metadata"]["langfuse_tags"] == ["score"]

    nested_configs = []

    def inner_step(state):
        return {"value": state["value"] + 1}

    def outer_step(state):
        nested = traced({}, "score-graph", "ignored")
        nested_configs.append(nested)
        return graph("inner", inner_step).invoke(state, nested)

    recorder = Recorder()
    result = graph("outer", outer_step).invoke({"value": 1}, {"callbacks": [recorder], "run_name": "task"})
    assert result == {"value": 2}
    assert nested_configs == [{"run_name": "score-graph"}]
    assert "score-graph" in recorder.names, recorder.names

    unreachable = graph("outer", inner_step).invoke({"value": 1}, traced({}, "score", "task-2"))
    assert unreachable == {"value": 2}

print("workflow tracing: optional, nested and failure-tolerant tracing passed")

"""Call the configured workflow model inside LangGraph nodes."""

from __future__ import annotations

from contextvars import ContextVar
import importlib.util
import os
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
import time
from typing import Callable

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
from openai import APIConnectionError, InternalServerError, RateLimitError


CALL_TIMEOUT_SECONDS = 600
# High reasoning effort can spend the endpoint default (8192) on reasoning alone; Hermes retried up to this cap.
MAX_OUTPUT_TOKENS = 32768
MODEL_ATTEMPTS = 3
RETRYABLE = (APIConnectionError, InternalServerError, RateLimitError)  # APITimeoutError subclasses APIConnectionError
CAPTURE: ContextVar[Path | None] = ContextVar("career_ops_model_capture", default=None)
DEADLINE: ContextVar[float | None] = ContextVar("career_ops_model_deadline", default=None)


def remaining_seconds() -> float:
    """Fail before a model call once the owning task has spent its time budget."""
    deadline = DEADLINE.get()
    if deadline is None:
        return CALL_TIMEOUT_SECONDS
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("time_budget_exhausted")
    return min(CALL_TIMEOUT_SECONDS, remaining)


def chat_model() -> ChatOpenAI:
    """Build the single workflow model from project settings."""
    missing = [name for name in ("CAREER_OPS_MODEL", "CAREER_OPS_LLM_BASE_URL", "CAREER_OPS_LLM_API_KEY")
               if not os.environ.get(name)]
    if missing:
        raise RuntimeError("Model settings are missing: " + ", ".join(missing))
    return ChatOpenAI(
        model=os.environ["CAREER_OPS_MODEL"],
        base_url=os.environ["CAREER_OPS_LLM_BASE_URL"],
        api_key=os.environ["CAREER_OPS_LLM_API_KEY"],
        reasoning_effort=os.environ.get("CAREER_OPS_REASONING_EFFORT", "high"),
        max_tokens=MAX_OUTPUT_TOKENS,
        timeout=remaining_seconds(),
        max_retries=0,
    )


def invoke(prepare: Callable[[ChatOpenAI], Runnable], messages: list[BaseMessage], name: str) -> BaseMessage:
    """Retry transient endpoint failures, giving every attempt only the task time that is left."""
    for attempt in range(MODEL_ATTEMPTS):
        directory = CAPTURE.get()
        path = directory / (uuid.uuid4().hex+'.json') if directory else None
        started = time.monotonic()
        record = {'name': name, 'attempt': attempt+1, 'started_at': datetime.now(timezone.utc).isoformat(),
                  'status': 'dispatching'}
        def retain():
            if path:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(record, ensure_ascii=False, default=str))
        retain()
        try:
            response = prepare(chat_model()).invoke(messages, {"run_name": name})
            record.update(status='completed', usage=response.usage_metadata or {},
                          response_metadata=response.response_metadata)
            return response
        except Exception as error:
            record.update(status='failed', error_type=type(error).__name__)
            if not isinstance(error, RETRYABLE) or attempt == MODEL_ATTEMPTS-1:
                raise
        finally:
            record['elapsed_seconds'] = time.monotonic()-started
            retain()


def complete_json(system: str, prompt: str, name: str = "model") -> str:
    """Run one tool-free JSON-mode model call and return its raw text."""
    parameters = {"response_format": {"type": "json_object"}}
    if name in ("scope_plan", "score_sections"):
        parameters.update(reasoning_effort="low")
    return invoke(lambda model: model.bind(**parameters),
                  [SystemMessage(system), HumanMessage(prompt)], name).text


def load_stub(variable: str) -> Callable[[str, dict], dict] | None:
    """Load an offline test double's run(phase, payload) from a file named by the environment."""
    path = os.environ.get(variable)
    if not path:
        return None
    spec = importlib.util.spec_from_file_location(f"career_ops_stub_{Path(path).stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.run

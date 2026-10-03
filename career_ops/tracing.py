"""Attach optional local Langfuse tracing to top-level LangGraph runs."""

from __future__ import annotations

from functools import cache
import logging
import os
import subprocess

from langchain_core.runnables.config import var_child_runnable_config

from career_ops.context import ROOT


SETTINGS = ("LANGFUSE_HOST", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")


def enabled() -> bool:
    """Trace only to an explicitly configured host; the SDK would otherwise default to Langfuse Cloud."""
    return (all(os.environ.get(name) for name in SETTINGS)
            and os.environ.get("LANGFUSE_TRACING_ENABLED", "true").lower() != "false")


@cache
def git_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True,
                              capture_output=True, timeout=5).stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def traced(config: dict, name: str, session_id: str) -> dict:
    """Name a graph run; a top-level run also gets one Langfuse trace grouped by business session.

    Nested graphs inherit the parent's callbacks, so they appear as spans inside the parent trace.
    """
    config = {**config, "run_name": name}
    if var_child_runnable_config.get() is not None or not enabled():
        return config
    try:
        from langfuse.langchain import CallbackHandler

        handler = CallbackHandler()
    except Exception:
        logging.getLogger(__name__).warning("Langfuse tracing unavailable", exc_info=True)
        return config
    return {**config, "callbacks": [handler], "metadata": {
        "langfuse_session_id": session_id, "langfuse_tags": [name], "git_sha": git_sha(),
    }}

"""Attach optional local Langfuse tracing to top-level LangGraph runs."""

from __future__ import annotations

from functools import cache
import logging
import os
import subprocess
from urllib.parse import urlsplit

from langchain_core.runnables.config import var_child_runnable_config

from career_ops.context import ROOT


SETTINGS = ("LANGFUSE_HOST", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def enabled() -> bool:
    """Trace only to an explicit local host: traces carry full prompts and candidate data.

    Without a host the SDK would default to Langfuse Cloud, so a missing or remote host disables tracing.
    """
    if (not all(os.environ.get(name) for name in SETTINGS)
            or os.environ.get("LANGFUSE_TRACING_ENABLED", "true").lower() == "false"):
        return False
    if urlsplit(os.environ["LANGFUSE_HOST"]).hostname not in LOCAL_HOSTS:
        logging.getLogger(__name__).warning("Langfuse tracing disabled: LANGFUSE_HOST must be a local host")
        return False
    return True


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

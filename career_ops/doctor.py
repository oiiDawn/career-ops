"""Check the actual local Python, Node, Hermes, model, browser and resume prerequisites."""
from __future__ import annotations

import argparse
from importlib.util import find_spec
import json
import os
import shutil
import subprocess
import sys
from urllib.request import urlopen

import yaml

from career_ops import tracing
from career_ops.context import INPUT_ROOT, ROOT
from career_ops.web_search import tavily_keys
from career_ops.evaluation.codex_research import executable


def checks() -> dict[str, bool]:
    profile_path = INPUT_ROOT / "profile.yml"
    profile = yaml.safe_load(profile_path.read_text()) if profile_path.is_file() else {}
    resume = (profile or {}).get("cv", {}).get("reactive_resume", {})
    try:
        tavily_keys()
        tavily_configured = True
    except RuntimeError:
        tavily_configured = False
    try:
        codex = subprocess.run([executable(), '--no-daemon', 'login', 'status'], capture_output=True, timeout=15)
        codex_ready = codex.returncode == 0
    except (RuntimeError, OSError, subprocess.TimeoutExpired):
        codex_ready = False
    result = {
        "python": sys.version_info >= (3, 11),
        "python_dependencies": all(find_spec(name) for name in ("langgraph", "langgraph.checkpoint.sqlite", "langchain_openai", "dotenv", "yaml")),
        "node": bool(shutil.which("node")),
        "hermes": bool(shutil.which("hermes")),
        "codex_authenticated": codex_ready,
        "model_settings": tavily_configured and all(os.environ.get(name) for name in ("CAREER_OPS_MODEL", "CAREER_OPS_LLM_BASE_URL", "CAREER_OPS_LLM_API_KEY")),
        "profile": profile_path.is_file(),
        "cv": (INPUT_ROOT / "cv.md").is_file(),
        "reactive_resume": bool(resume.get("base_resume_id") and resume.get("api_base_url") and os.environ.get("REACTIVE_RESUME_API_KEY")),
        "browser": False,
    }
    if result["node"]:
        probe = subprocess.run(
            ["node", "--input-type=module", "-e", "import {chromium} from 'playwright'; import {existsSync} from 'node:fs'; process.exit(existsSync(chromium.executablePath()) ? 0 : 1)"],
            cwd=ROOT, capture_output=True, timeout=15,
        )
        result["browser"] = probe.returncode == 0
    return result


def optional_checks() -> dict[str, bool]:
    """Report configured observability without making it a workflow prerequisite."""
    if not tracing.enabled():
        return {}
    try:
        with urlopen(f"{os.environ['LANGFUSE_HOST'].rstrip('/')}/api/public/health", timeout=3) as response:
            return {"langfuse": response.status == 200}
    except OSError:
        return {"langfuse": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = checks()
    optional = optional_checks()
    if args.json:
        print(json.dumps({**result, **optional}, sort_keys=True))
    else:
        for name, available in result.items():
            print(f'{"OK" if available else "MISSING"} {name}')
        for name, available in optional.items():
            print(f'OK {name}' if available else f'WARN {name} offline; traces are dropped')
    return int(not all(result.values()))

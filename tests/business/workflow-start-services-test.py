"""Exercise the local launcher with isolated command stubs, without Docker or business writes."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory() as temporary:
    base = Path(temporary)
    repo = base / "career ops"
    repo.mkdir()
    shutil.copy2(ROOT / "start.command", repo / "start.command")
    for relative in (".venv/bin", "data", "bin"):
        (repo / relative).mkdir(parents=True)
    (repo / "data/opportunities.db").touch()
    for directory, files in (("reactive-resume", ["compose.yml"]),
                             ("langfuse", ["docker-compose.yml", "docker-compose.override.yml"])):
        (base / directory).mkdir()
        for name in files:
            (base / directory / name).touch()
    log = base / "commands.log"

    def stub(name: str, body: str) -> None:
        path = repo / "bin" / name
        path.write_text('#!/bin/bash\necho "$(basename "$0") $*" >> "$COMMAND_LOG"\n' + body + '\n')
        path.chmod(0o755)

    stub("docker", '[[ "${DOCKER_FAIL:-}" != 1 ]]')
    stub("curl", '''[[ "${CURL_FAIL:-}" != 1 ]] || exit 22
echo "${PAGE:-<title>Career Ops Dashboard</title>}"''')
    stub("lsof", '[[ "${LISTENING:-}" == 1 ]]')
    stub("sleep", "exit 0")
    stub("open", "exit 0")
    python = repo / ".venv/bin/python"
    python.write_text('#!/bin/sh\necho "dashboard-launch" >> "$COMMAND_LOG"\ncat >> "$COMMAND_LOG"\n')
    python.chmod(0o755)
    env = {**os.environ, "PATH": f"{repo / 'bin'}:{os.environ['PATH']}", "COMMAND_LOG": str(log)}

    def run(**overrides):
        log.write_text("")
        return subprocess.run(["bash", str(repo / "start.command")], cwd=base,
                              env={**env, **overrides}, capture_output=True, text=True, timeout=15)

    result = run()
    assert result.returncode == 0, result.stderr
    commands = log.read_text()
    assert commands.count("up -d --no-build --pull never --no-recreate --wait") == 2, commands
    assert '"career_ops", "dashboard"' in commands and "start_new_session=True" in commands
    assert "/api/jobs" in commands and "/api/public/health" in commands
    assert "http://127.0.0.1:3000" in result.stdout

    result = run(LISTENING="1")
    assert result.returncode == 0, result.stderr
    assert "dashboard-launch" not in log.read_text()

    result = run(LISTENING="1", PAGE="Another application")
    assert result.returncode != 0 and "occupied by another service" in result.stderr
    assert "dashboard-launch" not in log.read_text()

    result = run(CURL_FAIL="1")
    assert result.returncode != 0 and "did not become ready" in result.stderr

    result = run(DOCKER_FAIL="1")
    assert result.returncode != 0 and "Docker is unavailable" in result.stderr
    assert "open -a Docker" in log.read_text()
    assert "up -d" not in log.read_text()

print("Local service launcher checks passed")

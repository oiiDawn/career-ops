#!/bin/bash
# Start the local Career Ops UI and its existing Docker services without running business jobs.
set -euo pipefail
export PATH="$PATH:/usr/local/bin:/opt/homebrew/bin"
cd "$(dirname "$0")"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

wait_url() {
  local name="$1" url="$2" attempt
  for attempt in {1..90}; do
    if curl --noproxy '*' -fsS --max-time 5 "$url" >/dev/null 2>&1; then
      echo "$name ready: $url"
      return
    fi
    sleep 2
  done
  fail "$name did not become ready: $url"
}

for tool in docker curl lsof; do
  command -v "$tool" >/dev/null || fail "Missing command: $tool"
done
[[ -x .venv/bin/python ]] || fail "Missing .venv; run uv sync --locked first."
[[ -f data/opportunities.db ]] || fail "Missing data/opportunities.db"
resume_dir="$(dirname "$PWD")/reactive-resume"
langfuse_dir="$(dirname "$PWD")/langfuse"
[[ -f "$resume_dir/compose.yml" ]] || fail "Missing $resume_dir/compose.yml"
[[ -f "$langfuse_dir/docker-compose.yml" ]] || fail "Missing $langfuse_dir/docker-compose.yml"
[[ -f "$langfuse_dir/docker-compose.override.yml" ]] || fail "Missing local Langfuse port overrides."

if ! docker info >/dev/null 2>&1; then
  echo "Starting Docker Desktop..."
  open -a Docker
  for attempt in {1..60}; do
    if docker info >/dev/null 2>&1; then break; fi
    sleep 2
  done
  docker info >/dev/null 2>&1 || fail "Docker is unavailable; check Docker Desktop."
fi

docker compose --project-directory "$langfuse_dir" \
  -f "$langfuse_dir/docker-compose.yml" -f "$langfuse_dir/docker-compose.override.yml" \
  up -d --no-build --pull never --no-recreate --wait --wait-timeout 180
docker compose --project-directory "$resume_dir" -f "$resume_dir/compose.yml" \
  up -d --no-build --pull never --no-recreate --wait --wait-timeout 180

mkdir -p local
if lsof -nP -iTCP:8765 -sTCP:LISTEN -t >/dev/null 2>&1; then
  page=$(curl --noproxy '*' -fsS --max-time 5 http://127.0.0.1:8765/)
  [[ "$page" == *'<title>Career Ops Dashboard</title>'* ]] || fail "Port 8765 is occupied by another service."
else
  .venv/bin/python -B - <<'PY'
import subprocess
import sys

with open("local/dashboard.log", "ab") as log:
    subprocess.Popen(
        [sys.executable, "-B", "-m", "career_ops", "dashboard"],
        stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True,
    )
PY
fi

wait_url "Career Ops Dashboard" http://127.0.0.1:8765/api/jobs
wait_url "Reactive Resume" http://127.0.0.1:3000/api/health
wait_url "Langfuse" http://127.0.0.1:3001/api/public/health
echo
echo "Career Ops Dashboard: http://127.0.0.1:8765"
echo "Reactive Resume:      http://127.0.0.1:3000"
echo "Langfuse:             http://127.0.0.1:3001"
echo "Dashboard log:        $PWD/local/dashboard.log"

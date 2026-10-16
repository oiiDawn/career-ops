#!/bin/sh
# Maintain posting availability independently of discovery, scoring and notifications.
set -eu
exec .venv/bin/python -B -m career_ops system liveness --apply --no-fallback --throttle=5000

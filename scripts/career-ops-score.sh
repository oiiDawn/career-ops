#!/bin/sh
# Advance one persisted scan/score task, then hand one eligible score report to career run.
# Hermes may still invoke this script. Delivery is the webhook transport; Discord is rollback only.
set -eu
.venv/bin/python -B -m career_ops system advance
CAREER_OPS_NOTIFICATIONS_ENABLED=1 .venv/bin/python -B -m career_ops system notify cron

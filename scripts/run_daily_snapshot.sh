#!/bin/bash
# Daily investment snapshot — cron wrapper
#
# Setup:
#   1. Fill in the variables below
#   2. chmod +x scripts/run_daily_snapshot.sh
#   3. crontab -e
#      0 13 * * 1-5 /path/to/monarch-mcp-server/scripts/run_daily_snapshot.sh >> /tmp/snapshot.log 2>&1

# ── Configure these ────────────────────────────────────────────────────────────
REPO_DIR="/path/to/monarch-mcp-server"
PYTHON="$REPO_DIR/.venv/bin/python3"

ALPHA_VANTAGE_API_KEY=""
SNAPSHOT_EMAIL_TO=""
SNAPSHOT_EMAIL_FROM=""
SNAPSHOT_GMAIL_APP_PASSWORD=""
# ──────────────────────────────────────────────────────────────────────────────

export ALPHA_VANTAGE_API_KEY
export SNAPSHOT_EMAIL_TO
export SNAPSHOT_EMAIL_FROM
export SNAPSHOT_GMAIL_APP_PASSWORD

cd "$REPO_DIR" || exit 1

echo "=== $(date) ==="
"$PYTHON" scripts/daily_snapshot.py

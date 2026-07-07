#!/bin/bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOCK_FILE="$REPO_DIR/tmp/retry_scheduled.lock"
LOG_FILE="/tmp/arvad-dailybrief-retry.log"

sleep 3600
rm -f "$LOCK_FILE"

exec /bin/bash "$REPO_DIR/macos/run_arvad_weekly_brief.sh" >>"$LOG_FILE" 2>&1

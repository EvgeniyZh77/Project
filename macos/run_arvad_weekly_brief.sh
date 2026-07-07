#!/bin/bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_PREFIX="[arvad-weekly-brief]"
LOCK_FILE="$REPO_DIR/tmp/retry_scheduled.lock"
RETRY_SCRIPT="$REPO_DIR/macos/retry_arvad_weekly_brief.sh"

echo "$LOG_PREFIX repo: $REPO_DIR"
cd "$REPO_DIR"

export PYTHONPYCACHEPREFIX="$REPO_DIR/tmp/pycache"
export ARVAD_BITRIX_WEBHOOK_URL="${ARVAD_BITRIX_WEBHOOK_URL:-https://team.arvad.ru/rest/5/ib6qhmme92wgyqed/}"
export ARVAD_BITRIX_DIALOG_ID="${ARVAD_BITRIX_DIALOG_ID:-chat4071}"

mkdir -p "$REPO_DIR/output/html" "$REPO_DIR/output/json" "$REPO_DIR/output/markdown" "$REPO_DIR/tmp/pycache"

if [ ! -f "scripts/build_arvad_market_brief.py" ]; then
  echo "$LOG_PREFIX error: build script not found"
  exit 1
fi

if ! /usr/bin/curl --head --silent --fail --max-time 15 https://www.cbr.ru/ >/dev/null; then
  echo "$LOG_PREFIX no internet, skip brief build"
  if [ ! -f "$LOCK_FILE" ]; then
    echo "$LOG_PREFIX schedule retry in 1 hour"
    date '+%Y-%m-%d %H:%M:%S' >"$LOCK_FILE"
    nohup /bin/bash "$RETRY_SCRIPT" >/tmp/arvad-dailybrief-retry-launch.log 2>&1 &
  else
    echo "$LOG_PREFIX retry already scheduled"
  fi
  exit 0
fi

python3 scripts/build_arvad_market_brief.py --lookback-hours 168 --send-bitrix

echo "$LOG_PREFIX done"

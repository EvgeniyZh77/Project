#!/bin/bash
set -euo pipefail

if [ $# -lt 2 ]; then
  echo "Usage: $0 <repo_dir> <target_dir> [branch]"
  exit 1
fi

REPO_DIR="$1"
TARGET_DIR="$2"
BRANCH="${3:-main}"
HTML_DIR="$REPO_DIR/output/html"
LOG_PREFIX="[arvad-brief]"

echo "$LOG_PREFIX repo: $REPO_DIR"
echo "$LOG_PREFIX target: $TARGET_DIR"

mkdir -p "$TARGET_DIR"

cd "$REPO_DIR"
if [ -d "$REPO_DIR/.git" ]; then
  git fetch origin "$BRANCH"
  git checkout "$BRANCH"
  git pull --ff-only origin "$BRANCH"
else
  echo "$LOG_PREFIX repo has no git metadata, using local files only"
fi

LATEST_HTML="$(ls -1t "$HTML_DIR"/arvad-market-brief-*.html 2>/dev/null | head -n 1 || true)"
if [ -z "$LATEST_HTML" ]; then
  echo "$LOG_PREFIX error: no HTML found in $HTML_DIR"
  exit 1
fi

cp "$LATEST_HTML" "$TARGET_DIR/"
echo "$LOG_PREFIX copied: $(basename "$LATEST_HTML")"

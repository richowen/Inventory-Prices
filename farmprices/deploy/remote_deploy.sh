#!/bin/bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/home/richowen/farmprices}"
BRANCH="${BRANCH:-main}"
SERVICE_NAME="${SERVICE_NAME:-farmprices}"
BACKUP_DIR="$APP_DIR/backups"
DB_PATH="$APP_DIR/prices.db"
TS="$(date +%Y-%m-%d_%H%M%S)"
SKIP_GIT_SYNC="${SKIP_GIT_SYNC:-auto}"

log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*"
}

require_cmd() {
    command -v "$1" >/dev/null 2>&1 || {
        log "ERROR: Required command not found: $1"
        exit 1
    }
}

log "Starting remote deploy for $APP_DIR (branch: $BRANCH, service: $SERVICE_NAME)"

require_cmd python3
require_cmd sudo

if [ "$SKIP_GIT_SYNC" = "1" ] || [ "$SKIP_GIT_SYNC" = "true" ]; then
    NEED_GIT=0
else
    NEED_GIT=1
fi

if [ "$NEED_GIT" -eq 1 ]; then
    require_cmd git
fi

if [ ! -d "$APP_DIR" ]; then
    log "ERROR: App directory not found: $APP_DIR"
    exit 1
fi

cd "$APP_DIR"

mkdir -p "$BACKUP_DIR"

CURRENT_COMMIT="unknown"
TARGET_COMMIT="unknown"
HAS_GIT_REPO=0
if [ -d ".git" ]; then
    HAS_GIT_REPO=1
    CURRENT_COMMIT="$(git rev-parse --short HEAD)"
    log "Current commit: $CURRENT_COMMIT"
else
    log "No git repository detected at $APP_DIR (.git missing)"
fi

if [ -f "$DB_PATH" ]; then
    DB_BACKUP="$BACKUP_DIR/prices_deploy_${TS}.db"
    cp "$DB_PATH" "$DB_BACKUP"
    log "Database backup created: $DB_BACKUP"
else
    log "WARNING: Database not found at $DB_PATH (skipping backup)"
fi

if [ "$SKIP_GIT_SYNC" = "1" ] || [ "$SKIP_GIT_SYNC" = "true" ]; then
    log "SKIP_GIT_SYNC enabled; skipping git fetch/reset"
elif [ "$SKIP_GIT_SYNC" = "auto" ] && [ "$HAS_GIT_REPO" -eq 0 ]; then
    log "SKIP_GIT_SYNC=auto and no git repo found; skipping git fetch/reset"
elif [ "$HAS_GIT_REPO" -eq 1 ]; then
    log "Fetching latest commit from origin/$BRANCH"
    git fetch --prune origin "$BRANCH"
    TARGET_COMMIT="$(git rev-parse --short "origin/$BRANCH")"
    log "Target commit: $TARGET_COMMIT"

    log "Checking out latest origin/$BRANCH"
    git reset --hard "origin/$BRANCH"
else
    log "ERROR: SKIP_GIT_SYNC disabled but no git repository found"
    exit 1
fi

if [ ! -d "$APP_DIR/venv" ]; then
    log "Virtual environment not found. Creating venv..."
    python3 -m venv "$APP_DIR/venv"
fi

log "Installing/updating Python dependencies"
"$APP_DIR/venv/bin/pip" install --upgrade pip
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"

log "Running pre-restart validation checks"
"$APP_DIR/venv/bin/python" - <<'PY'
import importlib
import os
import sqlite3
import sys

app_dir = os.getcwd()
sys.path.insert(0, app_dir)

module = importlib.import_module("app")
if hasattr(module, "init_db"):
    module.init_db()

path = os.path.join(app_dir, "prices.db")
if os.path.exists(path):
    conn = sqlite3.connect(path)
    try:
        result = conn.execute("PRAGMA integrity_check;").fetchone()[0]
    finally:
        conn.close()
    if str(result).lower() != "ok":
        raise SystemExit(f"Database integrity check failed: {result}")

print("Pre-restart checks passed")
PY

log "Restarting systemd service: $SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"

log "Verifying service state"
sudo systemctl is-active --quiet "$SERVICE_NAME" || {
    log "ERROR: Service failed to start"
    sudo systemctl status "$SERVICE_NAME" --no-pager || true
    sudo journalctl -u "$SERVICE_NAME" -n 80 --no-pager || true
    exit 1
}

log "Running post-deploy HTTP health check"
"$APP_DIR/venv/bin/python" - <<'PY'
import time
import urllib.error
import urllib.request

url = "http://127.0.0.1:5000/"
last_error = None

for _ in range(20):
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            status = response.getcode()
            if 200 <= status < 500:
                print(f"Health check passed with status {status}")
                raise SystemExit(0)
    except Exception as exc:
        last_error = exc
    time.sleep(1)

raise SystemExit(f"Health check failed: {last_error}")
PY

log "Deployment succeeded: $CURRENT_COMMIT -> $TARGET_COMMIT"

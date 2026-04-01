#!/bin/bash
# ── Tenbury Farm Supplies — Gunicorn startup script ──────────────────────────
# Run this to start the app manually, or use the systemd service for auto-start.
# Usage: bash start_gunicorn.sh

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="$APP_DIR/venv"
LOG_FILE="$APP_DIR/app.log"

echo "Starting Tenbury Farm Supplies Price App..."
echo "App directory: $APP_DIR"

# Activate virtual environment if it exists
if [ -d "$VENV_DIR" ]; then
    source "$VENV_DIR/bin/activate"
fi

cd "$APP_DIR"

# Run database init
python -c "import app; app.init_db()" 2>&1

# Start Gunicorn
# - 4 worker processes (handles multiple simultaneous phone/tablet requests)
# - Bind to all interfaces on port 5000
# - Timeout 120s
exec gunicorn \
    --workers 4 \
    --bind 0.0.0.0:5000 \
    --timeout 120 \
    --access-logfile "$LOG_FILE" \
    --error-logfile "$LOG_FILE" \
    --log-level info \
    "app:app"

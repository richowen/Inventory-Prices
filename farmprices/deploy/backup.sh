#!/bin/bash
# ── Tenbury Farm Supplies — Daily database backup via Taildrop ────────────────
#
# Safely snapshots prices.db and sends it to Unraid over Tailscale.
# Local copies are kept for 7 days; Unraid keeps 30 days.
#
# Set up as a cron job on the Pi:
#   crontab -e
#   0 2 * * * /home/richowen/Inventory-Prices/farmprices/deploy/backup.sh
#
# Manual test:
#   bash /home/richowen/Inventory-Prices/farmprices/deploy/backup.sh

set -euo pipefail

# ── Config ────────────────────────────────────────────────────────────────────
DB_PATH="/home/richowen/Inventory-Prices/farmprices/prices.db"
BACKUP_DIR="/home/richowen/Inventory-Prices/farmprices/backups"
UNRAID_HOST="server"                         # Tailscale hostname of Unraid
LOCAL_KEEP_DAYS=7                            # Days to keep backups on Pi
LOG="$BACKUP_DIR/backup.log"
TS=$(date +%Y-%m-%d_%H%M)
BACKUP_FILE="$BACKUP_DIR/prices_${TS}.db"

# ── Helpers ───────────────────────────────────────────────────────────────────
mkdir -p "$BACKUP_DIR"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$LOG"
}

log "────────────────────────────────────────"
log "Starting backup"

# ── 1. Check DB exists ────────────────────────────────────────────────────────
if [ ! -f "$DB_PATH" ]; then
    log "ERROR: Database not found at $DB_PATH"
    exit 1
fi

# ── 2. Ensure sqlite3 CLI is available ───────────────────────────────────────
if ! command -v sqlite3 >/dev/null 2>&1; then
    log "sqlite3 not found — installing via apt-get..."
    sudo apt-get update -qq && sudo apt-get install -y -qq sqlite3
    if ! command -v sqlite3 >/dev/null 2>&1; then
        log "ERROR: sqlite3 install failed"
        exit 1
    fi
    log "sqlite3 installed OK"
fi

# ── 3. Safe SQLite snapshot ───────────────────────────────────────────────────
# .backup is the correct way to copy a WAL-mode SQLite DB while the app is
# running — it checkpoints the WAL and produces a consistent single-file copy.
if ! sqlite3 "$DB_PATH" ".backup '${BACKUP_FILE}'"; then
    log "ERROR: sqlite3 .backup failed"
    exit 1
fi

SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
log "Local snapshot: $BACKUP_FILE ($SIZE)"

# ── 4. Send to Unraid via Taildrop ────────────────────────────────────────────
# tailscale file cp pushes the file to the Unraid node's Taildrop inbox.
# The receiver (unraid_receive.sh running on Unraid) auto-accepts it.
if tailscale file cp "$BACKUP_FILE" "${UNRAID_HOST}:"; then
    log "Taildrop: sent to $UNRAID_HOST OK"
else
    # Non-fatal — backup is still safe locally; log and continue
    log "WARNING: Taildrop send failed (is $UNRAID_HOST reachable on Tailscale?)"
    log "         Run 'tailscale status' to check connectivity"
fi

# ── 5. Rotate local backups ───────────────────────────────────────────────────
DELETED=$(find "$BACKUP_DIR" -name "prices_*.db" -mtime +${LOCAL_KEEP_DAYS} -print -delete | wc -l)
if [ "$DELETED" -gt 0 ]; then
    log "Local rotation: removed $DELETED backup(s) older than ${LOCAL_KEEP_DAYS} days"
fi

# ── 6. Keep log file tidy (max 500 lines) ─────────────────────────────────────
if [ -f "$LOG" ]; then
    LINES=$(wc -l < "$LOG")
    if [ "$LINES" -gt 500 ]; then
        tail -400 "$LOG" > "${LOG}.tmp" && mv "${LOG}.tmp" "$LOG"
    fi
fi

log "Backup complete"

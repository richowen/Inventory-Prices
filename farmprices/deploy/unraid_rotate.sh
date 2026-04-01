#!/bin/bash
# ── Unraid: 30-day backup rotation for farmprices backups ─────────────────────
#
# Deletes backups older than 30 days from the Taildrop receive directory.
# Set this up as a second User Script on Unraid running on a daily schedule.
#
# How to install on Unraid:
#   1. Go to Settings > User Scripts > Add New Script
#   2. Name it "farmprices-backup-rotate"
#   3. Paste the contents of this file
#   4. Set Schedule to Custom, enter:  0 3 * * *
#      (runs at 3 AM daily, one hour after the Pi sends the backup)
#   5. Click Save

RECEIVE_DIR="/mnt/user/backups/farmprices"
KEEP_DAYS=30
LOG="$RECEIVE_DIR/receive.log"

if [ ! -d "$RECEIVE_DIR" ]; then
    exit 0
fi

DELETED=$(find "$RECEIVE_DIR" -name "prices_*.db" -mtime +${KEEP_DAYS} -print -delete | wc -l)

if [ "$DELETED" -gt 0 ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') Rotation: removed $DELETED backup(s) older than ${KEEP_DAYS} days" >> "$LOG"
fi

# Show what's currently stored
COUNT=$(find "$RECEIVE_DIR" -name "prices_*.db" | wc -l)
NEWEST=$(find "$RECEIVE_DIR" -name "prices_*.db" | sort | tail -1 | xargs basename 2>/dev/null || echo "none")
echo "$(date '+%Y-%m-%d %H:%M:%S') Status: $COUNT backup(s) stored, newest: $NEWEST" >> "$LOG"

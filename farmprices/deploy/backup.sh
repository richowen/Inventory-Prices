#!/bin/bash
# ── Tenbury Farm Supplies — Daily database backup ─────────────────────────────
# Copies prices.db to a timestamped backup file.
# Set up as a daily cron job:
#   crontab -e
#   0 2 * * * /home/pi/farmprices/deploy/backup.sh
#
# Backups are kept for 30 days then auto-deleted.

DB_FILE="/home/richowen/farmprices/prices.db"
BACKUP_DIR="/home/richowen/farmprices/backups"
DATE=$(date +%Y-%m-%d_%H%M)
BACKUP_FILE="$BACKUP_DIR/prices_$DATE.db"

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Copy the database (SQLite WAL mode is safe to copy while running)
if [ -f "$DB_FILE" ]; then
    cp "$DB_FILE" "$BACKUP_FILE"
    echo "$(date): Backup created: $BACKUP_FILE" >> "$BACKUP_DIR/backup.log"
    
    # Delete backups older than 30 days
    find "$BACKUP_DIR" -name "prices_*.db" -mtime +30 -delete
    echo "$(date): Old backups cleaned up" >> "$BACKUP_DIR/backup.log"
else
    echo "$(date): ERROR — database file not found: $DB_FILE" >> "$BACKUP_DIR/backup.log"
    exit 1
fi

# Optional: also copy to USB stick if mounted
# USB_BACKUP="/media/pi/USB_BACKUP/farmprices"
# if [ -d "/media/pi/USB_BACKUP" ]; then
#     mkdir -p "$USB_BACKUP"
#     cp "$DB_FILE" "$USB_BACKUP/prices_$DATE.db"
#     echo "$(date): USB backup created" >> "$BACKUP_DIR/backup.log"
# fi

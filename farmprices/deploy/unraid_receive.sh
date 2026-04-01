#!/bin/bash
# ── Unraid: Taildrop receiver for farmprices backups ─────────────────────────
#
# Run this on Unraid to continuously accept incoming backup files from the Pi.
# Set it up as a User Script (Unraid > Settings > User Scripts) triggered
# "At Array Start" so it restarts automatically after a reboot.
#
# How to install on Unraid:
#   1. Install the "User Scripts" plugin from Community Apps if not already installed
#   2. Go to Settings > User Scripts > Add New Script
#   3. Name it "farmprices-taildrop-receiver"
#   4. Paste the contents of this file
#   5. Set Schedule to "At Array Start"
#   6. Click "Run Script" once to start it immediately without rebooting
#
# Files will appear in RECEIVE_DIR named prices_YYYY-MM-DD_HHMM.db

RECEIVE_DIR="/mnt/user/backups/farmprices"
LOG="$RECEIVE_DIR/receive.log"

mkdir -p "$RECEIVE_DIR"

echo "$(date '+%Y-%m-%d %H:%M:%S') Taildrop receiver starting (writing to $RECEIVE_DIR)" >> "$LOG"

# --loop   : keep running after each received file (don't exit after first)
# --wait   : block until a file arrives rather than exit immediately if inbox empty
# --conflict=overwrite : timestamps make filenames unique so this won't matter,
#                        but set explicitly to avoid any interactive prompt
tailscale file get \
    --loop \
    --wait \
    --conflict=overwrite \
    "$RECEIVE_DIR" \
    >> "$LOG" 2>&1 &

echo "$(date '+%Y-%m-%d %H:%M:%S') Receiver started (PID $!)" >> "$LOG"

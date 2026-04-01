# Tenbury Farm Supplies — Price Lookup App
## Setup & Deployment Guide

---

## Overview

This app runs on a **Raspberry Pi** on your local shop network. Staff use phones and tablets to look up prices via the shop WiFi. The Windows PC is used for admin (adding/editing prices).

```
Raspberry Pi (always on, runs the app)
       |
  Shop WiFi Router
    ┌──┴──────────────┐
  Windows PC        Phones / Tablets
  (admin panel)     (price lookup)
  
  URL: http://farmprices.local
```

---

## What You Need

| Item | Approx. Cost | Notes |
|---|---|---|
| Raspberry Pi 4 (2GB RAM) | £35 | Pi 3B+ also works |
| Official USB-C power supply | £8 | Don't use a phone charger |
| 32GB MicroSD card (Class 10) | £8 | Samsung or SanDisk recommended |
| Case (optional) | £5–10 | Any Pi 4 case |
| Network cable (recommended) | £3 | More reliable than WiFi |

**Total: ~£56**

---

## Part 1 — Prepare the Raspberry Pi

### Step 1: Flash the SD card

1. Download **Raspberry Pi Imager** from https://www.raspberrypi.com/software/
2. Insert the MicroSD card into your Windows PC
3. Open Raspberry Pi Imager
4. Choose OS: **Raspberry Pi OS Lite (64-bit)** — no desktop needed
5. Choose Storage: your MicroSD card
6. Click the **gear icon** (⚙) to open advanced settings:
   - ✅ Set hostname: `farmprices`
   - ✅ Enable SSH: Use password authentication
   - ✅ Set username: `richowen` (or whatever you prefer — **note it down**)
   - ✅ Set password: choose a secure password (e.g. `FarmPi2024!`)
   - ✅ Configure WiFi (if not using a network cable): enter your shop WiFi name and password
   - ✅ Set locale: `Europe/London`
7. Click **Write** and wait for it to finish

8. > **⚠️ Important:** The username you set here must match the `User=` and paths in `deploy/farmprices.service`. The service file is pre-configured for username `richowen`. If you use a different username, edit the service file before installing it.

### Step 2: First boot

1. Insert the SD card into the Raspberry Pi
2. Connect a network cable to the Pi and your router (recommended)
3. Plug in the power supply
4. Wait 60 seconds for it to boot

### Step 3: Connect via SSH from Windows PC

Open **Command Prompt** or **PowerShell** on the Windows PC and type:

```
ssh richowen@farmprices.local
```

Enter the password you set in Step 1. You should see a Linux prompt like `richowen@farmprices:~ $`

> **If `farmprices.local` doesn't work**, find the Pi's IP address from your router's admin page (usually http://192.168.1.1) and use that instead: `ssh richowen@192.168.1.XXX`

---

## Part 2 — Install the App

### Step 4: Update the system

```bash
sudo apt update && sudo apt upgrade -y
```

### Step 5: Install Python and pip

```bash
sudo apt install python3 python3-pip python3-venv -y
```

### Step 6: Copy the app files to the Pi

**Option A — USB stick:**
1. Copy the `farmprices/` folder to a USB stick on your Windows PC
2. Plug the USB stick into the Pi
3. In the SSH session:
```bash
sudo mkdir -p /media/usb
sudo mount /dev/sda1 /media/usb
cp -r /media/usb/farmprices /home/richowen/
sudo umount /media/usb
```

**Option B — SCP from Windows PC** (run this in PowerShell on the Windows PC, not the Pi):
```powershell
scp -r "C:\path\to\farmprices" richowen@farmprices.local:/home/richowen/
```

### Step 7: Create a Python virtual environment

```bash
cd /home/richowen/farmprices
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Step 8: Test the app runs

```bash
cd /home/richowen/farmprices
source venv/bin/activate
python app.py
```

You should see output like:
```
=======================================================
  Tenbury Farm Supplies - Price Lookup App
  Local:     http://localhost:5000
  Network:   http://192.168.1.XXX:5000
  Hostname:  http://farmprices.local:5000
  Password:  farm2024  (change in Settings)
=======================================================
```

Open a browser on your phone and go to `http://farmprices.local:5000` — you should see the price lookup page.

Press **Ctrl+C** to stop the test.

---

## Part 3 — Set Up Auto-Start (systemd)

This makes the app start automatically when the Pi boots, and restart if it crashes.

### Step 9: Install the systemd service

```bash
sudo cp /home/richowen/farmprices/deploy/farmprices.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable farmprices
sudo systemctl start farmprices
```

### Step 10: Check it's running

```bash
sudo systemctl status farmprices
```

You should see `Active: active (running)`. 

### Useful service commands

```bash
sudo systemctl stop farmprices      # Stop the app
sudo systemctl start farmprices     # Start the app
sudo systemctl restart farmprices   # Restart (after updating files)
sudo journalctl -u farmprices -f    # View live logs
```

---

## Part 4 — Set Up Daily Backups

### Step 11: Make the backup script executable

```bash
chmod +x /home/richowen/farmprices/deploy/backup.sh
```

### Step 12: Add a daily cron job

```bash
crontab -e
```

Select nano (option 1) if asked. Add this line at the bottom:

```
0 2 * * * /home/richowen/farmprices/deploy/backup.sh
```

This runs a backup every day at 2am. Backups are stored in `/home/richowen/farmprices/backups/` and kept for 30 days.

---

## Part 5 — Network Setup

### Step 13: Assign a static IP to the Pi (recommended)

Log into your router's admin page (usually http://192.168.1.1 or http://192.168.0.1).

Find the **DHCP Reservations** or **Static IP** section. Add a reservation for the Pi's MAC address with a fixed IP like `192.168.1.100`.

This ensures the Pi always gets the same IP address, so `farmprices.local` always works.

> **Finding the Pi's MAC address:**
> ```bash
> ip link show eth0 | grep ether
> ```

### Step 14: Test from phones and tablets

1. Connect your phone/tablet to the shop WiFi
2. Open a browser and go to: `http://farmprices.local`
3. You should see the price lookup page

**Bookmark this URL** on all staff devices. On iPhone/Android you can also "Add to Home Screen" to create an app-like icon.

---

## Part 6 — Windows PC Admin Setup

### Step 15: Update the Windows PC shortcut

The `start_app.bat` file is no longer needed on the Pi — the app runs automatically. However, you can keep it for testing on the Windows PC.

For the Windows PC to access the admin panel on the Pi, just open a browser and go to:
```
http://farmprices.local/admin
```

**Bookmark this** in the browser on the Windows PC.

Default admin password: **`farm2024`**

Change it immediately in **Admin → Settings → Change Admin Password**.

---

## Part 7 — Manual Deploy over Tailscale (Git Push + SSH Pull)

This section keeps deployment simple: **push to GitHub from your Windows PC**, then run one PowerShell script that SSHes over Tailscale and tells the Pi to pull and restart.

### What this gives you

- Secure remote access over your private Tailscale network
- No router port forwarding
- Simple one-command deployment from your Windows home PC
- Safe deploy sequence using [`remote_deploy.sh`](farmprices/deploy/remote_deploy.sh)

### Step 16: Install and enable Tailscale on the Pi (one time)

SSH to the Pi locally and run:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --ssh
```

In the Tailscale admin panel, confirm the Pi appears and note its Tailscale DNS name (for example `farmprices-pi.tailnet-name.ts.net`).

### Step 17: Install Tailscale on your Windows PC (one time)

1. Install Tailscale from https://tailscale.com/download
2. Sign in to the same tailnet as the Pi
3. Confirm you can reach the Pi over Tailscale:

```powershell
ssh richowen@farmprices.west-stonecat.ts.net
```

### Step 18: One-time Git and deploy prerequisites on Pi

On the Pi, ensure the app is a git clone and can pull from GitHub:

```bash
cd /home/richowen
git clone <your-repo-url> farmprices
cd /home/richowen/farmprices
git remote -v
git checkout main
git pull origin main
```

Then ensure deploy script is executable:

```bash
chmod +x /home/richowen/farmprices/deploy/remote_deploy.sh
```

If the repo is private, configure SSH deploy key/auth on the Pi so `git fetch` works non-interactively.

Ensure your SSH user can restart services without an interactive password prompt:

```bash
sudo visudo
```

Add this line (adjust username if needed):

```text
richowen ALL=(ALL) NOPASSWD:/bin/systemctl,/usr/bin/journalctl
```

### Step 19: Create one-command deploy script on Windows (one time)

Use the included script [`scripts/deploy_from_home.ps1`](scripts/deploy_from_home.ps1).

From PowerShell, run from your local repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\deploy_from_home.ps1
```

What it does:
1. Verifies you are on branch `main`
2. Verifies working tree is clean
3. Pushes to `origin/main`
4. SSHes over Tailscale to the Pi
5. Runs [`remote_deploy.sh`](farmprices/deploy/remote_deploy.sh), which pulls latest `origin/main`, installs deps, runs checks, and restarts service

Optional flags:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\deploy_from_home.ps1 -PiHost "farmprices.west-stonecat.ts.net" -PiUser "richowen"
```

Skip push only if you already pushed:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\deploy_from_home.ps1 -SkipPush
```

The script will:

1. Back up `prices.db`
2. Update/validate runtime environment
3. Install Python dependencies
4. Run pre-restart checks
5. Restart `farmprices` service
6. Run local health check

### Step 20: Verify deployment

```powershell
ssh richowen@farmprices-pi.tailnet-name.ts.net "sudo systemctl status farmprices --no-pager"
ssh richowen@farmprices-pi.tailnet-name.ts.net "sudo journalctl -u farmprices -n 120 --no-pager"
```

Then test in browser:

```text
http://farmprices.local
```

### Step 20b: Enforce a clean client database (no test data)

Run this after deployment and before client handover:

```bash
cd /home/richowen/farmprices
source venv/bin/activate
python reset_db.py
```

When prompted, type `RESET`.

Then restart the service and verify the database is clean:

```bash
sudo systemctl restart farmprices
sqlite3 /home/richowen/farmprices/prices.db "SELECT 'products', COUNT(*) FROM products UNION ALL SELECT 'price_history', COUNT(*) FROM price_history UNION ALL SELECT 'audit_log', COUNT(*) FROM audit_log;"
```

Expected result:

```text
products|0
price_history|0
audit_log|0
```

Notes:
- Categories and units remain pre-populated by design.
- No sample products are inserted by app startup.

### Step 21: Rollback procedure

If deployment fails:

```bash
ssh richowen@farmprices-pi.tailnet-name.ts.net
cd /home/richowen/farmprices
git log --oneline -n 5
git reset --hard <previous-good-commit>
sudo systemctl restart farmprices
```

If needed, restore a DB backup (stored in `/home/richowen/farmprices/backups/`):

```bash
sudo systemctl stop farmprices
cp /home/richowen/farmprices/backups/prices_deploy_YYYY-MM-DD_HHMMSS.db /home/richowen/farmprices/prices.db
sudo systemctl start farmprices
```

---

## Maintenance

### Updating the app (after code changes)

1. Copy the updated files to the Pi (via USB or SCP)
2. Restart the service:
```bash
sudo systemctl restart farmprices
```

### Viewing logs

```bash
sudo journalctl -u farmprices -n 50    # Last 50 log lines
sudo journalctl -u farmprices -f       # Live log stream
cat /home/richowen/farmprices/app.log        # Gunicorn access log
```

### Manual database backup

```bash
/home/richowen/farmprices/deploy/backup.sh
```

### Restoring a backup

```bash
sudo systemctl stop farmprices
cp /home/richowen/farmprices/backups/prices_YYYY-MM-DD_HHMM.db /home/richowen/farmprices/prices.db
sudo systemctl start farmprices
```

---

## Troubleshooting

| Problem | Solution |
|---|---|
| `farmprices.local` doesn't resolve | Use the IP address instead. Check the Pi is on and connected to the network. |
| App not loading | SSH into Pi and run `sudo systemctl status farmprices` to check for errors |
| Slow response | Normal on first load. If consistently slow, check `sudo journalctl -u farmprices -n 20` |
| Pi won't boot | Check power supply — must be official Pi power supply, not a phone charger |
| Forgot admin password | SSH into Pi and run: `python3 -c "import sqlite3,hashlib; db=sqlite3.connect('/home/richowen/farmprices/prices.db'); db.execute('UPDATE settings SET value=? WHERE key=?',(hashlib.sha256(b'farm2024').hexdigest(),'admin_password')); db.commit()"` |

---

## Quick Reference

| URL | Purpose |
|---|---|
| `http://farmprices.local` | Staff price lookup (phones/tablets) |
| `http://farmprices.local/admin` | Admin panel (Windows PC) |
| `http://farmprices.local/pricelist` | Print-friendly price list |

| SSH Command | Purpose |
|---|---|
| `ssh richowen@farmprices.local` | Connect to Pi from Windows PC |
| `sudo systemctl restart farmprices` | Restart app after updates |
| `sudo systemctl status farmprices` | Check app is running |

"""
reset_db.py — Tenbury Farm Supplies Price Lookup App
=====================================================
Clears all products, price history, and audit log entries from the database.
Settings (shop name, default markup, admin password) are PRESERVED.

Run this script ONCE before handing the app to the client:
    python reset_db.py

A backup of the current database is created before any changes are made.
"""

import os
import shutil
import sqlite3
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, "prices.db")


def main():
    if not os.path.exists(DB_PATH):
        print("ERROR: prices.db not found. Run the app first to create it.")
        return

    print()
    print("=" * 55)
    print("  Tenbury Farm Supplies — Database Reset")
    print("=" * 55)
    print()
    print("This will DELETE:")
    print("  • All products (including deleted ones)")
    print("  • All price history")
    print("  • All audit log entries")
    print()
    print("This will KEEP:")
    print("  • Shop name setting")
    print("  • Default markup setting")
    print("  • Admin password")
    print("  • Categories and units")
    print()

    # Show current counts
    db = sqlite3.connect(DB_PATH)
    products_count = db.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    history_count  = db.execute("SELECT COUNT(*) FROM price_history").fetchone()[0]
    audit_count    = db.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    db.close()

    print(f"Current data:")
    print(f"  Products:      {products_count}")
    print(f"  Price history: {history_count}")
    print(f"  Audit log:     {audit_count}")
    print()

    confirm = input("Type 'RESET' to confirm and proceed: ").strip()
    if confirm != "RESET":
        print("Cancelled — no changes made.")
        return

    # Create a backup first
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BASE_DIR, f"prices_backup_{timestamp}.db")
    shutil.copy2(DB_PATH, backup_path)
    print(f"\nBackup created: {os.path.basename(backup_path)}")

    # Wipe the data
    db = sqlite3.connect(DB_PATH)
    db.execute("DELETE FROM products")
    db.execute("DELETE FROM price_history")
    db.execute("DELETE FROM audit_log")
    db.execute("DELETE FROM sqlite_sequence WHERE name IN ('products', 'price_history', 'audit_log')")
    db.commit()
    db.close()

    print()
    print("✓ All products, price history, and audit log cleared.")
    print("✓ Settings, categories, and units preserved.")
    print()
    print("The app is ready for the client to add their products.")
    print()
    print(f"Backup saved as: {os.path.basename(backup_path)}")
    print("(You can delete this backup file once you're happy with the reset.)")
    print()


if __name__ == "__main__":
    main()

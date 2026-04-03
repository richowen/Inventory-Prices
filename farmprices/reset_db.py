"""
reset_db.py — Farm Supplies App — Database Reset
=================================================
Two modes:

  [1] DEPLOYMENT START — clears all test/client data then re-seeds categories
      and training records. Gets you back to the state after running
      seed_deploy.py for the first time. Use this during testing.

  [2] CLIENT HANDOVER  — clears all test/client data and leaves the database
      clean (categories and settings kept, NO products or suppliers). Use
      this once, right before handing the device/app to the client.

Always creates a timestamped backup of prices.db first.

Usage:
    python reset_db.py
"""
import os,shutil,sqlite3,sys
from datetime import datetime

BASE_DIR=os.path.dirname(os.path.abspath(__file__))
DB_PATH=os.path.join(BASE_DIR,"prices.db")


def _counts(db):
    return {
        "Products":      db.execute("SELECT COUNT(*) FROM products").fetchone()[0],
        "Suppliers":     db.execute("SELECT COUNT(*) FROM suppliers").fetchone()[0],
        "Price history": db.execute("SELECT COUNT(*) FROM price_history").fetchone()[0],
        "Audit log":     db.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0],
        "Categories":    db.execute("SELECT COUNT(*) FROM categories").fetchone()[0],
    }


def _wipe(db):
    db.execute("PRAGMA foreign_keys=OFF")
    for t in ("price_history","audit_log","products","suppliers"):
        db.execute(f"DELETE FROM {t}")
    db.execute(
        "DELETE FROM sqlite_sequence WHERE name IN "
        "('products','suppliers','price_history','audit_log')"
    )
    db.execute("PRAGMA foreign_keys=ON")


def _backup():
    ts=datetime.now().strftime("%Y%m%d_%H%M%S")
    dst=os.path.join(BASE_DIR,f"prices_backup_{ts}.db")
    shutil.copy2(DB_PATH,dst)
    return os.path.basename(dst)


def reset_to_deployment_start():
    """Wipe everything then re-seed categories and training data."""
    try:
        import seed_deploy as sd
    except ImportError:
        print("ERROR: seed_deploy.py not found alongside reset_db.py")
        sys.exit(1)

    db=sqlite3.connect(DB_PATH)
    db.row_factory=sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")

    bk=_backup()
    print(f"\n  Backup created: {bk}")

    _wipe(db)
    # Also wipe and re-seed categories — disable FK for self-referential delete
    db.execute("PRAGMA foreign_keys=OFF")
    db.execute("DELETE FROM categories")
    db.execute("DELETE FROM sqlite_sequence WHERE name='categories'")
    db.execute("PRAGMA foreign_keys=ON")
    # Re-seed default units (in case they were cleared)
    for u in ["each","bag","kg","litre","roll","box","metre","pair","set","pack"]:
        db.execute("INSERT OR IGNORE INTO units (name) VALUES (?)",(u,))

    db.commit()

    # Re-seed categories via seed_deploy
    added_p,added_s=sd.seed_categories(db)
    # Re-seed training data
    sd.seed_training(db)
    db.commit()
    db.close()

    print()
    print("  ✓ All products, suppliers, price history and audit log cleared.")
    print(f"  ✓ {added_p} parent categories + {added_s} subcategories restored.")
    print("  ✓ Training supplier and products restored.")
    print()
    print("  You are back at deployment start. Ready for another test run.")
    print()


def reset_to_client_handover():
    """Wipe products/suppliers/history/audit. Leave categories, settings, users."""
    db=sqlite3.connect(DB_PATH)
    db.execute("PRAGMA foreign_keys=ON")

    bk=_backup()
    print(f"\n  Backup created: {bk}")

    _wipe(db)
    db.commit()
    db.close()

    print()
    print("  ✓ Products, suppliers, price history and audit log cleared.")
    print("  ✓ Settings, categories, units and users preserved.")
    print()
    print("  The app is clean and ready for the client to add their products.")
    print(f"  (Backup: {bk} — delete once you are happy.)")
    print()


def main():
    if not os.path.exists(DB_PATH):
        print("\nERROR: prices.db not found. Start the app first to create it.\n")
        return

    db=sqlite3.connect(DB_PATH)
    counts=_counts(db)
    db.close()

    print()
    print("═"*58)
    print("  Farm Supplies App — Database Reset")
    print("═"*58)
    print()
    print("  Current database:")
    for label,n in counts.items():
        print(f"    {label+':':<16} {n}")
    print()
    print("  Choose reset mode:")
    print()
    print("  [1] Deployment start — clear everything and restore")
    print("      categories + training data (back to post-seed_deploy")
    print("      state). Use this during development / testing.")
    print()
    print("  [2] Client handover  — clear products, suppliers,")
    print("      history and audit log. Categories and settings kept.")
    print("      Use this once before handing to the client.")
    print()
    print("  [0] Cancel")
    print()

    choice=input("  Enter choice [0/1/2]: ").strip()
    if choice not in ("1","2"):
        print("\n  Cancelled — no changes made.\n")
        return

    mode_label="Deployment start" if choice=="1" else "Client handover"
    confirm=input(f"\n  Type 'RESET' to confirm {mode_label} reset: ").strip()
    if confirm!="RESET":
        print("\n  Cancelled — no changes made.\n")
        return

    if choice=="1":
        reset_to_deployment_start()
    else:
        reset_to_client_handover()


if __name__=="__main__":
    main()

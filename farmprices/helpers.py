"""
Shared helper functions: pricing, rounding, audit logging, snapshots.
"""
import json
import math
from datetime import datetime

from db import get_db


# ── Price calculations ────────────────────────────────────────────────────────

def apply_rounding(price: float, mode: str) -> float:
    """Round a sell price according to the shop's configured rounding mode."""
    if mode == "0.05":
        return round(round(price / 0.05) * 0.05, 2)
    elif mode == "0.10":
        return round(round(price / 0.10) * 0.10, 2)
    elif mode == "0.99":
        # Charm pricing: floor to nearest pound + 0.99 (but don't go below 0.99)
        floored = math.floor(price)
        return max(floored + 0.99, 0.99) if price > 0 else 0.0
    return round(price, 2)


def sell_price(cost: float, markup_pct, default_markup: float,
               rounding_mode: str = "none") -> float:
    """Calculate the sell price from cost, markup, and rounding mode."""
    m = markup_pct if markup_pct is not None else default_markup
    raw = cost * (1 + m / 100)
    return apply_rounding(raw, rounding_mode)


# ── Audit logging ─────────────────────────────────────────────────────────────

def log_event(db, event_type: str, product_id=None, product_name: str = "",
              changed_by: str = "", notes: str = "",
              old_data=None, new_data=None):
    """Write a row to audit_log. old_data / new_data should be dicts."""
    db.execute(
        """INSERT INTO audit_log
           (event_type, product_id, product_name, changed_by, notes,
            old_data, new_data, changed_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            event_type,
            product_id,
            product_name,
            changed_by,
            notes,
            json.dumps(old_data) if old_data is not None else None,
            json.dumps(new_data) if new_data is not None else None,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
    )


# ── Product snapshot ──────────────────────────────────────────────────────────

def product_snapshot(p) -> dict:
    """Return a plain-dict snapshot of a product row (for audit_log)."""
    return {
        "name":              p["name"],
        "category":          p["category"],
        "unit":              p["unit"],
        "supplier_name":     p["supplier_name"],
        "supplier_tel":      p["supplier_tel"],
        "cost_price":        p["cost_price"],
        "markup_pct":        p["markup_pct"],
        "notes":             p["notes"],
        "barcode":           p["barcode"],
        "quantity":          p["quantity"],
        "reorder_threshold": p["reorder_threshold"],
        "last_updated":      p["last_updated"],
    }


# ── Settings helpers ──────────────────────────────────────────────────────────

def get_setting(key: str, default: str = "") -> str:
    db = get_db()
    row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def get_pricing_config() -> tuple[float, str]:
    """Return (default_markup_float, rounding_mode_str)."""
    markup  = float(get_setting("default_markup", "30"))
    rounding = get_setting("price_rounding", "none")
    return markup, rounding


# ── Category tree ─────────────────────────────────────────────────────────────

def cat_tree(db) -> list:
    """Return list of parent category dicts each with a 'subcategories' list."""
    rows = db.execute("SELECT id,name,parent_id FROM categories ORDER BY name").fetchall()
    parents = [dict(r) for r in rows if r["parent_id"] is None]
    subs = {}
    for r in rows:
        if r["parent_id"] is not None:
            subs.setdefault(r["parent_id"], []).append(dict(r))
    for p in parents:
        p["subcategories"] = subs.get(p["id"], [])
    return parents

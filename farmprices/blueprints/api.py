"""
API blueprint — JSON endpoints consumed by the frontend JavaScript.
All state-changing endpoints require admin role.
"""
import sqlite3
from datetime import date

from flask import Blueprint, jsonify, request, session

from db import get_db
from decorators import require_admin, require_login
from helpers import get_pricing_config, get_setting, log_event, sell_price

bp = Blueprint("api", __name__, url_prefix="/api")


# ── Product search (any authenticated user) ───────────────────────────────────

@bp.route("/search")
@require_login
def search():
    q          = request.args.get("q",        "").strip()
    category   = request.args.get("category", "").strip()
    barcode    = request.args.get("barcode",  "").strip()
    db         = get_db()
    is_admin   = session.get("role") == "admin"

    default_markup, rounding = get_pricing_config()

    query  = """SELECT id, name, category, unit, cost_price, markup_pct,
                       last_updated, barcode, quantity, reorder_threshold
                FROM products WHERE active=1"""
    params = []

    if barcode:
        query += " AND barcode=?"
        params.append(barcode)
    else:
        if q:
            query += " AND name LIKE ?"
            params.append(f"%{q}%")
        if category:
            query += " AND category=?"
            params.append(category)

    query += " ORDER BY name"

    rows    = db.execute(query, params).fetchall()
    today   = date.today()
    results = []

    for r in rows:
        sp = sell_price(r["cost_price"], r["markup_pct"], default_markup, rounding)
        try:
            days_old         = (today - date.fromisoformat(r["last_updated"])).days
            recently_updated = days_old <= 7
        except Exception:
            recently_updated = False

        low_stock = (
            r["quantity"] is not None
            and r["reorder_threshold"] is not None
            and r["quantity"] <= r["reorder_threshold"]
        )

        item = {
            "id":               r["id"],
            "name":             r["name"],
            "category":         r["category"],
            "unit":             r["unit"],
            "sell_price":       sp,
            "last_updated":     r["last_updated"],
            "recently_updated": recently_updated,
            "barcode":          r["barcode"],
            "low_stock":        low_stock,
        }
        # Only expose cost_price to admin users
        if is_admin:
            item["cost_price"] = r["cost_price"]

        results.append(item)

    from flask import make_response
    resp = make_response(jsonify(results))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"]        = "no-cache"
    return resp


# ── Categories ────────────────────────────────────────────────────────────────

@bp.route("/categories", methods=["GET"])
def get_categories():
    db   = get_db()
    cats = [r["name"] for r in
            db.execute("SELECT name FROM categories ORDER BY name").fetchall()]
    return jsonify(cats)


@bp.route("/categories/add", methods=["POST"])
@require_admin
def add_category():
    db   = get_db()
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()[:60]
    if not name:
        return jsonify({"ok": False, "error": "Name required"}), 400
    try:
        db.execute("INSERT INTO categories (name) VALUES (?)", (name,))
        log_event(db, "category_added",
                  changed_by=session.get("username", ""),
                  notes=f"Category added: {name!r}")
        db.commit()
        return jsonify({"ok": True})
    except sqlite3.IntegrityError:
        return jsonify({"ok": False, "error": "Already exists"}), 409


@bp.route("/categories/delete", methods=["POST"])
@require_admin
def delete_category():
    db   = get_db()
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    count = db.execute(
        "SELECT COUNT(*) FROM products WHERE active=1 AND category=?", (name,)
    ).fetchone()[0]
    if count > 0:
        return jsonify({"ok": False,
                        "error": f"Cannot delete — {count} product(s) use this category"}), 409
    db.execute("DELETE FROM categories WHERE name=?", (name,))
    log_event(db, "category_deleted",
              changed_by=session.get("username", ""),
              notes=f"Category deleted: {name!r}")
    db.commit()
    return jsonify({"ok": True})


# ── Units ─────────────────────────────────────────────────────────────────────

@bp.route("/units/add", methods=["POST"])
@require_admin
def add_unit():
    db   = get_db()
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()[:40]
    if not name:
        return jsonify({"ok": False, "error": "Name required"}), 400
    try:
        db.execute("INSERT INTO units (name) VALUES (?)", (name,))
        log_event(db, "unit_added",
                  changed_by=session.get("username", ""),
                  notes=f"Unit added: {name!r}")
        db.commit()
        return jsonify({"ok": True})
    except sqlite3.IntegrityError:
        return jsonify({"ok": False, "error": "Already exists"}), 409


@bp.route("/units/delete", methods=["POST"])
@require_admin
def delete_unit():
    db   = get_db()
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    count = db.execute(
        "SELECT COUNT(*) FROM products WHERE active=1 AND unit=?", (name,)
    ).fetchone()[0]
    if count > 0:
        return jsonify({"ok": False,
                        "error": f"Cannot delete — {count} product(s) use this unit"}), 409
    db.execute("DELETE FROM units WHERE name=?", (name,))
    log_event(db, "unit_deleted",
              changed_by=session.get("username", ""),
              notes=f"Unit deleted: {name!r}")
    db.commit()
    return jsonify({"ok": True})


# ── Inline price update ───────────────────────────────────────────────────────

@bp.route("/products/<int:pid>/update_price", methods=["POST"])
@require_admin
def update_price(pid):
    db   = get_db()
    data = request.get_json(silent=True) or {}
    try:
        new_cost = float(data.get("cost_price", 0))
        if new_cost < 0:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Invalid price"}), 400

    note = data.get("note", "").strip()[:500]

    product = db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    if not product:
        return jsonify({"ok": False, "error": "Product not found"}), 404

    old_cost = product["cost_price"]

    if abs(new_cost - old_cost) > 0.001:
        db.execute(
            """INSERT INTO price_history
               (product_id, product_name, old_cost, new_cost, changed_by, notes, changed_at)
               VALUES (?,?,?,?,?,?,datetime('now'))""",
            (pid, product["name"], old_cost, new_cost,
             session.get("username", ""), note)
        )
        log_event(db, "price_changed",
                  product_id=pid, product_name=product["name"],
                  changed_by=session.get("username", ""),
                  notes=note,
                  old_data={"cost_price": old_cost},
                  new_data={"cost_price": new_cost})

    db.execute("UPDATE products SET cost_price=?, last_updated=date('now') WHERE id=?",
               (new_cost, pid))
    db.commit()

    default_markup, rounding = get_pricing_config()
    sp       = sell_price(new_cost, product["markup_pct"], default_markup, rounding)
    currency = get_setting("currency", "£")

    return jsonify({
        "ok":         True,
        "cost_price": new_cost,
        "sell_price": sp,
        "currency":   currency,
        "updated":    date.today().isoformat()
    })


# ── Suppliers autocomplete ────────────────────────────────────────────────────

@bp.route("/suppliers/suggest")
@require_admin
def suggest_suppliers():
    q  = request.args.get("q", "").strip()
    db = get_db()
    if not q:
        rows = db.execute("SELECT * FROM suppliers ORDER BY name LIMIT 20").fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM suppliers WHERE name LIKE ? ORDER BY name LIMIT 20",
            (f"%{q}%",)
        ).fetchall()
    return jsonify([dict(r) for r in rows])

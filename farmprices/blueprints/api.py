"""
API blueprint — JSON endpoints consumed by the frontend JavaScript.
All state-changing endpoints require admin role.
"""
import sqlite3
from datetime import date

from flask import Blueprint, jsonify, make_response, request, session

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
                       last_updated, barcode, quantity, reorder_threshold, weight_kg, volume_litres
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
            # Expand to include subcategories of the selected category
            sub_rows = db.execute(
                "SELECT name FROM categories WHERE parent_id=(SELECT id FROM categories WHERE name=?)",
                (category,)
            ).fetchall()
            all_cats = [category] + [r["name"] for r in sub_rows]
            query += f" AND category IN ({','.join('?'*len(all_cats))})"
            params.extend(all_cats)

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
            "weight_kg":        r["weight_kg"],
            "volume_litres":    r["volume_litres"],
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

    resp = make_response(jsonify(results))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"]        = "no-cache"
    return resp


# ── Categories ────────────────────────────────────────────────────────────────

@bp.route("/categories", methods=["GET"])
@require_login
def get_categories():
    db   = get_db()
    rows = db.execute("SELECT id,name,parent_id FROM categories ORDER BY name").fetchall()
    return jsonify([dict(r) for r in rows])


@bp.route("/categories/add", methods=["POST"])
@require_admin
def add_category():
    db   = get_db()
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()[:60]
    parent_id = data.get("parent_id") or None
    if not name:
        return jsonify({"ok": False, "error": "Name required"}), 400
    try:
        cur = db.execute("INSERT INTO categories (name, parent_id) VALUES (?,?)", (name, parent_id))
        log_event(db, "category_added",
                  changed_by=session.get("username", ""),
                  notes=f"Category added: {name!r}" + (f" (sub of id {parent_id})" if parent_id else ""))
        db.commit()
        return jsonify({"ok": True, "id": cur.lastrowid})
    except sqlite3.IntegrityError:
        return jsonify({"ok": False, "error": "Already exists"}), 409


@bp.route("/categories/delete", methods=["POST"])
@require_admin
def delete_category():
    db   = get_db()
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    # Check products
    count = db.execute(
        "SELECT COUNT(*) FROM products WHERE active=1 AND category=?", (name,)
    ).fetchone()[0]
    if count > 0:
        return jsonify({"ok": False,
                        "error": f"Cannot delete — {count} product(s) use this category"}), 409
    # Reassign subcategories to no parent
    db.execute("UPDATE categories SET parent_id=NULL WHERE parent_id=(SELECT id FROM categories WHERE name=?)", (name,))
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

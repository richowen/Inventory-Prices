"""
Tenbury Farm Supplies — Price Lookup App
Flask web application with SQLite backend
Session-based admin authentication with password stored in settings table
"""

import csv
import hashlib
import io
import json
import os
import sqlite3
from datetime import date, datetime
from functools import wraps

from flask import (
    Flask, render_template, request, jsonify,
    redirect, url_for, flash, g, make_response, session, Response
)

# ── App setup ─────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = "tenbury-farm-2024-secret-xK9mP"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, "prices.db")

DEFAULT_PASSWORD = "farm2024"


def _hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


def require_admin(f):
    """Decorator — redirects to login if not authenticated."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_logged_in"):
            flash("Please log in to access the admin panel.", "info")
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated


# ── Database helpers ──────────────────────────────────────────────────────────

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
    return g.db


@app.teardown_appcontext
def close_db(exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create tables if they don't exist and initialize defaults for production use."""
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")

    db.executescript("""

        CREATE TABLE IF NOT EXISTS categories (
            id    INTEGER PRIMARY KEY AUTOINCREMENT,
            name  TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS units (
            id    INTEGER PRIMARY KEY AUTOINCREMENT,
            name  TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS products (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT    NOT NULL,
            category      TEXT    NOT NULL DEFAULT 'Other',
            unit          TEXT    NOT NULL DEFAULT 'each',
            supplier_name TEXT    NOT NULL DEFAULT '',
            supplier_tel  TEXT    NOT NULL DEFAULT '',
            cost_price    REAL    NOT NULL DEFAULT 0.0,
            markup_pct    REAL,
            notes         TEXT    NOT NULL DEFAULT '',
            last_updated  TEXT    NOT NULL DEFAULT (date('now')),
            active        INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS price_history (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id    INTEGER NOT NULL REFERENCES products(id),
            product_name  TEXT    NOT NULL,
            old_cost      REAL    NOT NULL,
            new_cost      REAL    NOT NULL,
            changed_by    TEXT    NOT NULL DEFAULT '',
            notes         TEXT    NOT NULL DEFAULT '',
            changed_at    TEXT    NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type   TEXT    NOT NULL,
            product_id   INTEGER,
            product_name TEXT    NOT NULL DEFAULT '',
            changed_by   TEXT    NOT NULL DEFAULT '',
            notes        TEXT    NOT NULL DEFAULT '',
            old_data     TEXT,
            new_data     TEXT,
            changed_at   TEXT    NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        INSERT OR IGNORE INTO settings (key, value) VALUES
            ('shop_name',      'Tenbury Farm Supplies'),
            ('default_markup', '30'),
            ('currency',       '£');
    """)

    # Seed categories
    default_cats = ['Animal Feed','Bedding','Fencing','Seeds',
                    'Fertiliser','Tools','Vet Supplies','Other']
    for c in default_cats:
        db.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (c,))

    # Seed units
    default_units = ['each','bag','kg','litre','roll','box','metre','pair','set','pack']
    for u in default_units:
        db.execute("INSERT OR IGNORE INTO units (name) VALUES (?)", (u,))

    # Seed default admin password if not set
    hashed = _hash_password(DEFAULT_PASSWORD)
    db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('admin_password', ?)", (hashed,))

    # Migrate: if existing password is plaintext (not a 64-char hex hash), replace with hashed default
    existing_pw = db.execute("SELECT value FROM settings WHERE key='admin_password'").fetchone()
    if existing_pw and len(existing_pw[0]) != 64:
        db.execute("UPDATE settings SET value=? WHERE key='admin_password'", (hashed,))

    db.commit()
    db.close()


def get_setting(key, default=""):
    db = get_db()
    row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def sell_price(cost, markup_pct, default_markup):
    m = markup_pct if markup_pct is not None else default_markup
    return round(cost * (1 + m / 100), 2)


def log_event(db, event_type, product_id=None, product_name="",
              changed_by="", notes="", old_data=None, new_data=None):
    """Write a row to audit_log. old_data / new_data should be dicts (will be JSON-encoded)."""
    db.execute(
        """INSERT INTO audit_log
           (event_type, product_id, product_name, changed_by, notes, old_data, new_data, changed_at)
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


def product_snapshot(p) -> dict:
    """Return a plain dict snapshot of a product row."""
    return {
        "name":          p["name"],
        "category":      p["category"],
        "unit":          p["unit"],
        "supplier_name": p["supplier_name"],
        "supplier_tel":  p["supplier_tel"],
        "cost_price":    p["cost_price"],
        "markup_pct":    p["markup_pct"],
        "notes":         p["notes"],
        "last_updated":  p["last_updated"],
    }


# ══════════════════════════════════════════════════════════════════════════════
#  LOOKUP (public — staff-facing price search)
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    db = get_db()
    shop_name  = get_setting("shop_name", "Tenbury Farm Supplies")
    categories = [r["name"] for r in
                  db.execute("SELECT name FROM categories ORDER BY name").fetchall()]
    return render_template("lookup.html", shop_name=shop_name, categories=categories)


@app.route("/api/search")
def api_search():
    q        = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    db       = get_db()
    default_markup = float(get_setting("default_markup", "30"))

    query  = "SELECT id, name, category, unit, cost_price, markup_pct, last_updated FROM products WHERE active=1"
    params = []
    if q:
        query += " AND name LIKE ?"
        params.append(f"%{q}%")
    if category:
        query += " AND category=?"
        params.append(category)
    query += " ORDER BY name"

    rows = db.execute(query, params).fetchall()

    today = date.today().isoformat()
    results = []
    for r in rows:
        sp = sell_price(r["cost_price"], r["markup_pct"], default_markup)
        # Flag products updated in the last 7 days
        try:
            days_old = (date.today() - date.fromisoformat(r["last_updated"])).days
            recently_updated = days_old <= 7
        except Exception:
            recently_updated = False
        results.append({
            "id":               r["id"],
            "name":             r["name"],
            "category":         r["category"],
            "unit":             r["unit"],
            "cost_price":       r["cost_price"],
            "sell_price":       sp,
            "last_updated":     r["last_updated"],
            "recently_updated": recently_updated,
        })

    resp = make_response(jsonify(results))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp


# ── Print-friendly price list ─────────────────────────────────────────────────

@app.route("/pricelist")
def pricelist():
    db = get_db()
    default_markup = float(get_setting("default_markup", "30"))
    shop_name = get_setting("shop_name", "Tenbury Farm Supplies")

    rows = db.execute(
        "SELECT * FROM products WHERE active=1 ORDER BY category, name"
    ).fetchall()

    by_category = {}
    for p in rows:
        sp = sell_price(p["cost_price"], p["markup_pct"], default_markup)
        entry = dict(p) | {"sell_price": sp}
        by_category.setdefault(p["category"], []).append(entry)

    return render_template("pricelist.html",
                           by_category=by_category,
                           shop_name=shop_name,
                           generated=datetime.now().strftime("%d %B %Y %H:%M"))


# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN — authentication
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if session.get("admin_logged_in"):
        return redirect(url_for("admin_products"))

    if request.method == "POST":
        pw = request.form.get("password", "")
        stored_hash = get_setting("admin_password", _hash_password(DEFAULT_PASSWORD))
        if _hash_password(pw) == stored_hash:
            session["admin_logged_in"] = True
            log_event(get_db(), "admin_login", notes="Successful login")
            get_db().commit()
            flash("Logged in.", "success")
            return redirect(url_for("admin_products"))
        else:
            flash("Incorrect password.", "error")

    return render_template("admin_login.html",
                           shop_name=get_setting("shop_name", "Tenbury Farm Supplies"))


@app.route("/admin/logout")
def admin_logout():
    if session.get("admin_logged_in"):
        try:
            log_event(get_db(), "admin_logout", notes="Logged out")
            get_db().commit()
        except Exception:
            pass
    session.pop("admin_logged_in", None)
    flash("Logged out.", "info")
    return redirect(url_for("index"))


# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN — products
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/admin")
@app.route("/admin/products")
@require_admin
def admin_products():
    db = get_db()
    default_markup = float(get_setting("default_markup", "30"))
    category_filter = request.args.get("category", "")
    search_q        = request.args.get("q", "")

    query  = "SELECT * FROM products WHERE active=1"
    params = []
    if category_filter:
        query += " AND category=?"
        params.append(category_filter)
    if search_q:
        query += " AND name LIKE ?"
        params.append(f"%{search_q}%")
    query += " ORDER BY name"

    products   = db.execute(query, params).fetchall()
    categories = [r["name"] for r in
                  db.execute("SELECT name FROM categories ORDER BY name").fetchall()]

    enriched = []
    for p in products:
        sp = sell_price(p["cost_price"], p["markup_pct"], default_markup)
        enriched.append(dict(p) | {"sell_price": sp})

    return render_template("admin_products.html",
                           products=enriched,
                           categories=categories,
                           category_filter=category_filter,
                           search_q=search_q,
                           default_markup=default_markup,
                           shop_name=get_setting("shop_name"))


# ── Inline price update (AJAX — called from the products table) ───────────────

@app.route("/api/products/<int:pid>/update_price", methods=["POST"])
@require_admin
def api_update_price(pid):
    """Quick inline cost price update from the products list."""
    db = get_db()
    data = request.get_json() or {}
    try:
        new_cost = float(data.get("cost_price", 0))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Invalid price"}), 400
    changed_by = data.get("changed_by", "").strip()
    note       = data.get("note", "").strip()

    product = db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    if not product:
        return jsonify({"ok": False, "error": "Product not found"}), 404

    old_cost = product["cost_price"]

    if abs(new_cost - old_cost) > 0.001:
        # Legacy price_history entry
        db.execute(
            """INSERT INTO price_history
               (product_id, product_name, old_cost, new_cost, changed_by, notes, changed_at)
               VALUES (?,?,?,?,?,?,?)""",
            (pid, product["name"], old_cost, new_cost, changed_by, note,
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        # Audit log entry
        log_event(db, "price_changed",
                  product_id=pid, product_name=product["name"],
                  changed_by=changed_by, notes=note,
                  old_data={"cost_price": old_cost},
                  new_data={"cost_price": new_cost})

    db.execute(
        "UPDATE products SET cost_price=?, last_updated=? WHERE id=?",
        (new_cost, date.today().isoformat(), pid)
    )
    db.commit()

    default_markup = float(get_setting("default_markup", "30"))
    sp = sell_price(new_cost, product["markup_pct"], default_markup)

    return jsonify({
        "ok":         True,
        "cost_price": new_cost,
        "sell_price": sp,
        "updated":    date.today().isoformat()
    })


# ── Full product add ──────────────────────────────────────────────────────────

@app.route("/admin/products/add", methods=["GET", "POST"])
@require_admin
def admin_add_product():
    db = get_db()
    if request.method == "POST":
        name       = request.form["name"].strip()
        category   = request.form["category"].strip()
        unit       = request.form["unit"].strip()
        supplier   = request.form.get("supplier_name", "").strip()
        tel        = request.form.get("supplier_tel", "").strip()
        try:
            cost = float(request.form["cost_price"])
        except (TypeError, ValueError):
            flash("Invalid cost price.", "error")
            categories = [r["name"] for r in
                          db.execute("SELECT name FROM categories ORDER BY name").fetchall()]
            units      = [r["name"] for r in
                          db.execute("SELECT name FROM units ORDER BY name").fetchall()]
            return render_template("admin_product_form.html",
                                   product=None, action="Add",
                                   categories=categories, units=units,
                                   shop_name=get_setting("shop_name"))
        markup_str = request.form.get("markup_pct", "").strip()
        try:
            markup = float(markup_str) if markup_str else None
        except (TypeError, ValueError):
            markup = None
        notes      = request.form.get("notes", "").strip()
        changed_by = request.form.get("changed_by", "").strip()

        cursor = db.execute(
            """INSERT INTO products
               (name, category, unit, supplier_name, supplier_tel,
                cost_price, markup_pct, notes, last_updated)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (name, category, unit, supplier, tel, cost, markup, notes,
             date.today().isoformat())
        )
        new_id = cursor.lastrowid
        log_event(db, "product_added",
                  product_id=new_id, product_name=name,
                  changed_by=changed_by,
                  new_data={"name": name, "category": category, "unit": unit,
                            "supplier_name": supplier, "supplier_tel": tel,
                            "cost_price": cost, "markup_pct": markup, "notes": notes})
        db.commit()
        flash(f"'{name}' added.", "success")
        return redirect(url_for("admin_products"))

    categories = [r["name"] for r in
                  db.execute("SELECT name FROM categories ORDER BY name").fetchall()]
    units      = [r["name"] for r in
                  db.execute("SELECT name FROM units ORDER BY name").fetchall()]

    return render_template("admin_product_form.html",
                           product=None,
                           action="Add",
                           categories=categories,
                           units=units,
                           shop_name=get_setting("shop_name"))


# ── Full product edit ─────────────────────────────────────────────────────────

@app.route("/admin/products/<int:pid>/edit", methods=["GET", "POST"])
@require_admin
def admin_edit_product(pid):
    db = get_db()
    product = db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    if not product:
        flash("Product not found.", "error")
        return redirect(url_for("admin_products"))

    if request.method == "POST":
        name       = request.form["name"].strip()
        category   = request.form["category"].strip()
        unit       = request.form["unit"].strip()
        supplier   = request.form.get("supplier_name", "").strip()
        tel        = request.form.get("supplier_tel", "").strip()
        try:
            new_cost = float(request.form["cost_price"])
        except (TypeError, ValueError):
            flash("Invalid cost price.", "error")
            return redirect(url_for("admin_edit_product", pid=pid))
        markup_str = request.form.get("markup_pct", "").strip()
        try:
            markup = float(markup_str) if markup_str else None
        except (TypeError, ValueError):
            markup = None
        notes      = request.form.get("notes", "").strip()
        changed_by = request.form.get("changed_by", "").strip()
        change_note= request.form.get("change_note", "").strip()

        old_snap = product_snapshot(product)
        new_snap = {"name": name, "category": category, "unit": unit,
                    "supplier_name": supplier, "supplier_tel": tel,
                    "cost_price": new_cost, "markup_pct": markup, "notes": notes}

        old_cost = product["cost_price"]
        if abs(new_cost - old_cost) > 0.001:
            # Legacy price_history entry
            db.execute(
                """INSERT INTO price_history
                   (product_id, product_name, old_cost, new_cost, changed_by, notes, changed_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (pid, name, old_cost, new_cost, changed_by, change_note,
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            )

        # Build a human-readable diff for the notes field
        diff_parts = []
        for field in ("name", "category", "unit", "supplier_name", "supplier_tel",
                      "cost_price", "markup_pct", "notes"):
            ov = old_snap.get(field)
            nv = new_snap.get(field)
            if str(ov) != str(nv):
                diff_parts.append(f"{field}: {ov!r} → {nv!r}")
        diff_note = "; ".join(diff_parts) if diff_parts else "no changes"

        log_event(db, "product_edited",
                  product_id=pid, product_name=name,
                  changed_by=changed_by,
                  notes=change_note or diff_note,
                  old_data=old_snap,
                  new_data=new_snap)

        db.execute(
            """UPDATE products SET
               name=?, category=?, unit=?, supplier_name=?, supplier_tel=?,
               cost_price=?, markup_pct=?, notes=?, last_updated=?
               WHERE id=?""",
            (name, category, unit, supplier, tel, new_cost, markup, notes,
             date.today().isoformat(), pid)
        )
        db.commit()
        flash(f"'{name}' updated.", "success")
        return redirect(url_for("admin_products"))

    categories = [r["name"] for r in
                  db.execute("SELECT name FROM categories ORDER BY name").fetchall()]
    units      = [r["name"] for r in
                  db.execute("SELECT name FROM units ORDER BY name").fetchall()]

    return render_template("admin_product_form.html",
                           product=dict(product),
                           action="Edit",
                           categories=categories,
                           units=units,
                           shop_name=get_setting("shop_name"))


# ── Delete product ────────────────────────────────────────────────────────────

@app.route("/admin/products/<int:pid>/delete", methods=["POST"])
@require_admin
def admin_delete_product(pid):
    db = get_db()
    product = db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    if product:
        changed_by = request.form.get("changed_by", "").strip()
        log_event(db, "product_deleted",
                  product_id=pid, product_name=product["name"],
                  changed_by=changed_by,
                  notes=f"Product removed from active catalogue",
                  old_data=product_snapshot(product))
        db.execute("UPDATE products SET active=0 WHERE id=?", (pid,))
        db.commit()
        flash(f"'{product['name']}' removed.", "success")
    return redirect(url_for("admin_products"))


# ── Restore deleted product ───────────────────────────────────────────────────

@app.route("/admin/products/<int:pid>/restore", methods=["POST"])
@require_admin
def admin_restore_product(pid):
    db = get_db()
    product = db.execute("SELECT * FROM products WHERE id=? AND active=0", (pid,)).fetchone()
    if product:
        changed_by = request.form.get("changed_by", "").strip()
        db.execute("UPDATE products SET active=1, last_updated=? WHERE id=?",
                   (date.today().isoformat(), pid))
        log_event(db, "product_restored",
                  product_id=pid, product_name=product["name"],
                  changed_by=changed_by,
                  notes="Product restored to active catalogue")
        db.commit()
        flash(f"'{product['name']}' restored.", "success")
    return redirect(url_for("admin_deleted_products"))


# ── Deleted products view ─────────────────────────────────────────────────────

@app.route("/admin/deleted")
@require_admin
def admin_deleted_products():
    db = get_db()
    default_markup = float(get_setting("default_markup", "30"))
    products = db.execute(
        "SELECT * FROM products WHERE active=0 ORDER BY name"
    ).fetchall()
    enriched = []
    for p in products:
        sp = sell_price(p["cost_price"], p["markup_pct"], default_markup)
        enriched.append(dict(p) | {"sell_price": sp})
    return render_template("admin_deleted.html",
                           products=enriched,
                           shop_name=get_setting("shop_name"))


# ── Bulk markup update ────────────────────────────────────────────────────────

@app.route("/admin/products/bulk_markup", methods=["POST"])
@require_admin
def admin_bulk_markup():
    db = get_db()
    category   = request.form.get("bulk_category", "").strip()
    action     = request.form.get("bulk_action", "set")   # 'set' | 'increase' | 'decrease'
    try:
        pct = float(request.form.get("bulk_pct", "0"))
    except (TypeError, ValueError):
        flash("Invalid percentage.", "error")
        return redirect(url_for("admin_products"))
    changed_by = request.form.get("changed_by", "").strip()

    if not category:
        flash("Please select a category.", "error")
        return redirect(url_for("admin_products"))

    products = db.execute(
        "SELECT * FROM products WHERE active=1 AND category=?",
        (category,)
    ).fetchall()

    updated = 0
    for p in products:
        old_markup = p["markup_pct"]
        if action == "set":
            new_markup = pct
        elif action == "increase":
            base = old_markup if old_markup is not None else float(get_setting("default_markup", "30"))
            new_markup = base + pct
        elif action == "decrease":
            base = old_markup if old_markup is not None else float(get_setting("default_markup", "30"))
            new_markup = max(0, base - pct)
        else:
            new_markup = pct

        db.execute("UPDATE products SET markup_pct=?, last_updated=? WHERE id=?",
                   (new_markup, date.today().isoformat(), p["id"]))
        log_event(db, "product_edited",
                  product_id=p["id"], product_name=p["name"],
                  changed_by=changed_by,
                  notes=f"Bulk markup {action}: {old_markup}% → {new_markup}",
                  old_data={"markup_pct": old_markup},
                  new_data={"markup_pct": new_markup})
        updated += 1

    db.commit()
    flash(f"Markup updated for {updated} product(s) in '{category}'.", "success")
    return redirect(url_for("admin_products"))


# ── CSV export ────────────────────────────────────────────────────────────────

@app.route("/admin/export/csv")
@require_admin
def admin_export_csv():
    db = get_db()
    default_markup = float(get_setting("default_markup", "30"))
    shop_name = get_setting("shop_name", "Tenbury Farm Supplies")

    rows = db.execute(
        "SELECT * FROM products WHERE active=1 ORDER BY category, name"
    ).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Product Name", "Category", "Unit", "Supplier",
                     "Supplier Tel", "Cost Price (£)", "Markup %", "Sell Price (£)",
                     "Notes", "Last Updated"])
    for p in rows:
        sp = sell_price(p["cost_price"], p["markup_pct"], default_markup)
        markup = p["markup_pct"] if p["markup_pct"] is not None else default_markup
        writer.writerow([
            p["name"], p["category"], p["unit"],
            p["supplier_name"], p["supplier_tel"],
            f"{p['cost_price']:.2f}", f"{markup:.0f}",
            f"{sp:.2f}", p["notes"], p["last_updated"]
        ])

    filename = f"{shop_name.replace(' ', '_')}_prices_{date.today().isoformat()}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN — AUDIT HISTORY
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/admin/history")
@require_admin
def admin_history():
    db = get_db()
    event_filter   = request.args.get("event_type", "")
    product_filter = request.args.get("product", "").strip()
    date_from      = request.args.get("date_from", "").strip()
    date_to        = request.args.get("date_to", "").strip()

    query  = "SELECT * FROM audit_log WHERE 1=1"
    params = []
    if event_filter:
        query += " AND event_type=?"
        params.append(event_filter)
    if product_filter:
        query += " AND product_name LIKE ?"
        params.append(f"%{product_filter}%")
    if date_from:
        query += " AND changed_at >= ?"
        params.append(date_from + " 00:00:00")
    if date_to:
        query += " AND changed_at <= ?"
        params.append(date_to + " 23:59:59")
    query += " ORDER BY changed_at DESC LIMIT 500"

    rows = db.execute(query, params).fetchall()

    # Parse JSON fields for template use
    history = []
    for r in rows:
        entry = dict(r)
        try:
            entry["old_data"] = json.loads(r["old_data"]) if r["old_data"] else None
        except Exception:
            entry["old_data"] = None
        try:
            entry["new_data"] = json.loads(r["new_data"]) if r["new_data"] else None
        except Exception:
            entry["new_data"] = None
        history.append(entry)

    event_types = [
        "product_added", "product_edited", "product_deleted", "product_restored",
        "price_changed", "category_added", "category_deleted",
        "unit_added", "unit_deleted", "settings_changed",
        "admin_login", "admin_logout"
    ]

    return render_template("admin_history.html",
                           history=history,
                           event_types=event_types,
                           event_filter=event_filter,
                           product_filter=product_filter,
                           date_from=date_from,
                           date_to=date_to,
                           shop_name=get_setting("shop_name"))


# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN — SETTINGS (includes category + unit management)
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/admin/settings", methods=["GET", "POST"])
@require_admin
def admin_settings():
    db = get_db()
    if request.method == "POST":
        action = request.form.get("action", "save_settings")

        if action == "change_password":
            current_pw  = request.form.get("current_password", "")
            new_pw      = request.form.get("new_password", "").strip()
            confirm_pw  = request.form.get("confirm_password", "").strip()
            stored_hash = get_setting("admin_password", _hash_password(DEFAULT_PASSWORD))
            if _hash_password(current_pw) != stored_hash:
                flash("Current password is incorrect.", "error")
            elif len(new_pw) < 4:
                flash("New password must be at least 4 characters.", "error")
            elif new_pw != confirm_pw:
                flash("New passwords do not match.", "error")
            else:
                db.execute("UPDATE settings SET value=? WHERE key='admin_password'",
                           (_hash_password(new_pw),))
                log_event(db, "settings_changed", notes="Admin password changed")
                db.commit()
                flash("Password changed successfully.", "success")
            return redirect(url_for("admin_settings"))

        # Default: save general settings
        old_shop   = get_setting("shop_name")
        old_markup = get_setting("default_markup")
        shop_name      = request.form.get("shop_name", "").strip()
        default_markup = request.form.get("default_markup", "30").strip()
        db.execute("UPDATE settings SET value=? WHERE key='shop_name'",      (shop_name,))
        db.execute("UPDATE settings SET value=? WHERE key='default_markup'", (default_markup,))
        log_event(db, "settings_changed",
                  notes=f"shop_name: {old_shop!r}→{shop_name!r}; default_markup: {old_markup}→{default_markup}",
                  old_data={"shop_name": old_shop, "default_markup": old_markup},
                  new_data={"shop_name": shop_name, "default_markup": default_markup})
        db.commit()
        flash("Settings saved.", "success")
        return redirect(url_for("admin_settings"))

    settings   = {r["key"]: r["value"] for r in db.execute("SELECT * FROM settings").fetchall()}
    categories = [r["name"] for r in db.execute("SELECT name FROM categories ORDER BY name").fetchall()]
    units      = [r["name"] for r in db.execute("SELECT name FROM units ORDER BY name").fetchall()]

    return render_template("admin_settings.html",
                           settings=settings,
                           categories=categories,
                           units=units,
                           shop_name=settings.get("shop_name", ""))


# ── Category CRUD (AJAX) ──────────────────────────────────────────────────────

@app.route("/api/categories", methods=["GET"])
def api_get_categories():
    db = get_db()
    cats = [r["name"] for r in db.execute("SELECT name FROM categories ORDER BY name").fetchall()]
    return jsonify(cats)


@app.route("/api/categories/add", methods=["POST"])
@require_admin
def api_add_category():
    db = get_db()
    name = request.get_json().get("name", "").strip()
    if not name:
        return jsonify({"ok": False, "error": "Name required"}), 400
    try:
        db.execute("INSERT INTO categories (name) VALUES (?)", (name,))
        log_event(db, "category_added", notes=f"Category added: {name!r}")
        db.commit()
        return jsonify({"ok": True})
    except sqlite3.IntegrityError:
        return jsonify({"ok": False, "error": "Already exists"}), 409


@app.route("/api/categories/delete", methods=["POST"])
@require_admin
def api_delete_category():
    db = get_db()
    name = request.get_json().get("name", "").strip()
    # Check if any active products use this category
    count = db.execute(
        "SELECT COUNT(*) FROM products WHERE active=1 AND category=?",
        (name,)
    ).fetchone()[0]
    if count > 0:
        return jsonify({"ok": False, "error": f"Cannot delete — {count} product(s) use this category"}), 409
    db.execute("DELETE FROM categories WHERE name=?", (name,))
    log_event(db, "category_deleted", notes=f"Category deleted: {name!r}")
    db.commit()
    return jsonify({"ok": True})


# ── Unit CRUD (AJAX) ──────────────────────────────────────────────────────────

@app.route("/api/units/add", methods=["POST"])
@require_admin
def api_add_unit():
    db = get_db()
    name = request.get_json().get("name", "").strip()
    if not name:
        return jsonify({"ok": False, "error": "Name required"}), 400
    try:
        db.execute("INSERT INTO units (name) VALUES (?)", (name,))
        log_event(db, "unit_added", notes=f"Unit added: {name!r}")
        db.commit()
        return jsonify({"ok": True})
    except sqlite3.IntegrityError:
        return jsonify({"ok": False, "error": "Already exists"}), 409


@app.route("/api/units/delete", methods=["POST"])
@require_admin
def api_delete_unit():
    db = get_db()
    name = request.get_json().get("name", "").strip()
    count = db.execute(
        "SELECT COUNT(*) FROM products WHERE active=1 AND unit=?",
        (name,)
    ).fetchone()[0]
    if count > 0:
        return jsonify({"ok": False, "error": f"Cannot delete — {count} product(s) use this unit"}), 409
    db.execute("DELETE FROM units WHERE name=?", (name,))
    log_event(db, "unit_deleted", notes=f"Unit deleted: {name!r}")
    db.commit()
    return jsonify({"ok": True})


# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import socket
    init_db()
    # Try to get the local network IP for display
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        local_ip = "YOUR_IP"

    print("\n" + "="*55)
    print("  Tenbury Farm Supplies - Price Lookup App")
    print(f"  Local:     http://localhost:5000")
    print(f"  Network:   http://{local_ip}:5000")
    print(f"  Hostname:  http://farmprices.local:5000")
    print(f"  Password:  {DEFAULT_PASSWORD}  (change in Settings)")
    print("  Press Ctrl+C to stop")
    print("="*55 + "\n")
    app.run(host="0.0.0.0", port=5000, debug=False)

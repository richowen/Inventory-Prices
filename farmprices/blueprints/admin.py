"""
Admin blueprint — products, users, suppliers, history, settings, CSV import/export,
bulk markup, price review report.
"""
import csv
import io
import json
import os
from datetime import date, datetime

import bcrypt
from flask import (
    Blueprint, Response, flash, redirect, render_template,
    request, session, url_for, current_app
)

from db import get_db
from decorators import require_admin
from helpers import (
    cat_tree as _cat_tree_shared,
    get_pricing_config, get_setting, log_event,
    product_snapshot, sell_price, smart_title
)

bp = Blueprint("admin", __name__, url_prefix="/admin")

_MAX_NAME   = 120
_MAX_NOTES  = 500
_MAX_BARCODE = 60


# ── Helpers ───────────────────────────────────────────────────────────────────

def _current_user() -> str:
    return session.get("username", "")


def _auto_save_supplier(db, name: str, tel: str) -> bool:
    """Insert supplier if name is non-empty and not already in the table.
    Returns True if a new supplier was created."""
    if not name:
        return False
    existing = db.execute(
        "SELECT id FROM suppliers WHERE name=? COLLATE NOCASE", (name,)
    ).fetchone()
    if existing:
        return False
    db.execute(
        "INSERT INTO suppliers (name, tel) VALUES (?, ?)",
        (name, tel or "")
    )
    log_event(db, "supplier_added",
              changed_by=_current_user(),
              notes=f"Auto-saved from product form: {name!r}")
    return True


def _enrich(products, default_markup: float, rounding: str) -> list:
    return [dict(p) | {"sell_price": sell_price(p["cost_price"], p["markup_pct"],
                                                 default_markup, rounding)}
            for p in products]


def _cat_tree(db):
    """Return list of parent dicts each with a 'subcategories' list."""
    rows = db.execute("SELECT id,name,parent_id FROM categories ORDER BY name").fetchall()
    parents = [dict(r) for r in rows if r["parent_id"] is None]
    subs = {}
    for r in rows:
        if r["parent_id"] is not None:
            subs.setdefault(r["parent_id"], []).append(dict(r))
    for p in parents:
        p["subcategories"] = subs.get(p["id"], [])
    return parents


def _js_tree(tree):
    """Convert cat_tree to a JSON-serializable structure for the product form."""
    return [{"id": p["id"], "name": p["name"],
             "subs": [s["name"] for s in p["subcategories"]]} for p in tree]


def _resolve_cat(tree, cat_name):
    """Given a flat category name, return (cur_parent, cur_sub) for the form selectors."""
    for p in tree:
        if p["name"] == cat_name:
            return cat_name, ""
        for s in p["subcategories"]:
            if s["name"] == cat_name:
                return p["name"], cat_name
    return "", ""


def _flat_cats(db):
    return [r["name"] for r in db.execute("SELECT name FROM categories ORDER BY name").fetchall()]


# ── Products list ─────────────────────────────────────────────────────────────

@bp.route("")
@bp.route("/products")
@require_admin
def products():
    db                       = get_db()
    default_markup, rounding = get_pricing_config()
    category_filter          = request.args.get("category", "")
    supplier_filter          = request.args.get("supplier", "")
    search_q                 = request.args.get("q", "")

    q      = "SELECT * FROM products WHERE active=1"
    params = []
    if category_filter:
        sub_rows = db.execute(
            "SELECT name FROM categories WHERE parent_id=(SELECT id FROM categories WHERE name=?)",
            (category_filter,)
        ).fetchall()
        all_cats = [category_filter] + [r["name"] for r in sub_rows]
        q += f" AND category IN ({','.join('?'*len(all_cats))})"
        params.extend(all_cats)
    if supplier_filter:
        q += " AND supplier_name=?"
        params.append(supplier_filter)
    if search_q:
        q += " AND (name LIKE ? OR barcode LIKE ?)"
        params += [f"%{search_q}%", f"%{search_q}%"]
    q += " ORDER BY name"

    rows     = db.execute(q, params).fetchall()
    enriched = _enrich(rows, default_markup, rounding)
    currency = get_setting("currency", "£")
    tree     = _cat_tree(db)
    suppliers = [r["name"] for r in db.execute("SELECT name FROM suppliers ORDER BY name").fetchall()]

    return render_template("admin_products.html",
                           products=enriched,
                           cat_tree=tree,
                           categories=_flat_cats(db),
                           category_filter=category_filter,
                           supplier_filter=supplier_filter,
                           search_q=search_q,
                           default_markup=default_markup,
                           currency=currency,
                           suppliers=suppliers,
                           shop_name=get_setting("shop_name"))


# ── Add product ───────────────────────────────────────────────────────────────

@bp.route("/products/add", methods=["GET", "POST"])
@require_admin
def add_product():
    db         = get_db()
    categories = _flat_cats(db)
    units      = [r["name"] for r in db.execute("SELECT name FROM units ORDER BY name").fetchall()]
    suppliers  = [r["name"] for r in db.execute("SELECT name FROM suppliers ORDER BY name").fetchall()]
    tree       = _cat_tree(db)

    if request.method == "POST":
        name     = smart_title(request.form.get("name", "").strip())[:_MAX_NAME]
        category = request.form.get("category", "").strip()
        unit     = request.form.get("unit", "").strip()
        supplier = smart_title(request.form.get("supplier_name", "").strip())[:_MAX_NAME]
        notes    = request.form.get("notes", "").strip()[:_MAX_NOTES]
        # Auto-fill tel from suppliers table
        tel = ""
        if supplier:
            sup_row = db.execute("SELECT tel FROM suppliers WHERE name=? COLLATE NOCASE", (supplier,)).fetchone()
            if sup_row:
                tel = sup_row["tel"] or ""

        def _err(msg):
            flash(msg, "error")
            return render_template("admin_product_form.html",
                                   product=None, action="Add",
                                   categories=categories, units=units,
                                   suppliers=suppliers, cat_tree=tree,
                                   cat_tree_json=_js_tree(tree),
                                   cur_parent="", cur_sub="",
                                   shop_name=get_setting("shop_name"))

        if not name: return _err("Product name is required.")
        if category not in categories: return _err("Invalid category.")
        if unit not in units: return _err("Invalid unit.")

        try:
            cost = float(request.form["cost_price"])
            if cost < 0: raise ValueError
        except (TypeError, ValueError):
            return _err("Invalid cost price.")

        markup_str = request.form.get("markup_pct", "").strip()
        try:
            markup = float(markup_str) if markup_str else None
            if markup is not None and markup < 0: markup = 0.0
        except (TypeError, ValueError):
            markup = None

        try:
            qty = float(request.form.get("quantity","").strip()) if request.form.get("quantity","").strip() else None
        except (TypeError, ValueError):
            qty = None
        try:
            reorder = float(request.form.get("reorder_threshold","").strip()) if request.form.get("reorder_threshold","").strip() else None
        except (TypeError, ValueError):
            reorder = None
        try:
            weight_kg = float(request.form.get("weight_kg","").strip()) if request.form.get("weight_kg","").strip() else None
        except (TypeError, ValueError):
            weight_kg = None
        try:
            volume_litres = float(request.form.get("volume_litres","").strip()) if request.form.get("volume_litres","").strip() else None
        except (TypeError, ValueError):
            volume_litres = None

        barcode = request.form.get("barcode", "").strip()[:_MAX_BARCODE]
        cursor = db.execute(
            """INSERT INTO products
               (name, category, unit, supplier_name, supplier_tel,
                cost_price, markup_pct, notes, barcode,
                quantity, reorder_threshold, weight_kg, volume_litres, last_updated)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (name, category, unit, supplier, tel, cost, markup, notes,
             barcode, qty, reorder, weight_kg, volume_litres, date.today().isoformat())
        )
        new_id = cursor.lastrowid
        log_event(db, "product_added", product_id=new_id, product_name=name,
                  changed_by=_current_user(),
                  new_data={"name": name, "category": category, "unit": unit,
                            "cost_price": cost, "markup_pct": markup, "quantity": qty})
        new_supplier = _auto_save_supplier(db, supplier, tel)
        db.commit()
        msg = f"'{name}' added."
        if new_supplier:
            msg += f" Supplier '{supplier}' saved."
        flash(msg, "success")
        if request.form.get("submit_action") == "add_next":
            return redirect(url_for("admin.add_product",
                                    preset_category=category, preset_unit=unit,
                                    preset_supplier=supplier, preset_markup=markup_str))
        return redirect(url_for("admin.products"))

    preset = {
        "category": request.args.get("preset_category", ""),
        "unit":     request.args.get("preset_unit", ""),
        "supplier": request.args.get("preset_supplier", ""),
        "markup":   request.args.get("preset_markup", ""),
    }
    cur_cat = preset["category"]
    cur_parent, cur_sub = _resolve_cat(tree, cur_cat)
    return render_template("admin_product_form.html",
                           product=None, action="Add",
                           categories=categories, units=units,
                           suppliers=suppliers, cat_tree=tree,
                           cat_tree_json=_js_tree(tree),
                           cur_parent=cur_parent, cur_sub=cur_sub,
                           preset=preset,
                           shop_name=get_setting("shop_name"))


# ── Edit product ──────────────────────────────────────────────────────────────

@bp.route("/products/<int:pid>/edit", methods=["GET", "POST"])
@require_admin
def edit_product(pid):
    db      = get_db()
    product = db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    if not product:
        flash("Product not found.", "error")
        return redirect(url_for("admin.products"))

    categories = _flat_cats(db)
    units      = [r["name"] for r in db.execute("SELECT name FROM units ORDER BY name").fetchall()]
    suppliers  = [r["name"] for r in db.execute("SELECT name FROM suppliers ORDER BY name").fetchall()]
    tree       = _cat_tree(db)

    if request.method == "POST":
        name        = smart_title(request.form.get("name", "").strip())[:_MAX_NAME]
        category    = request.form.get("category", "").strip()
        unit        = request.form.get("unit", "").strip()
        supplier    = smart_title(request.form.get("supplier_name", "").strip())[:_MAX_NAME]
        notes       = request.form.get("notes", "").strip()[:_MAX_NOTES]
        change_note = request.form.get("change_note", "").strip()[:_MAX_NOTES]
        barcode     = request.form.get("barcode", "").strip()[:_MAX_BARCODE]
        if not barcode:
            barcode = product["barcode"] or ""  # fall back to existing if form is empty
        # Auto-fill tel from suppliers table
        tel = ""
        if supplier:
            sup_row = db.execute("SELECT tel FROM suppliers WHERE name=? COLLATE NOCASE", (supplier,)).fetchone()
            if sup_row:
                tel = sup_row["tel"] or ""
        # Fall back to existing tel on product if supplier unchanged
        if not tel and supplier == product["supplier_name"]:
            tel = product["supplier_tel"] or ""

        if not name:
            flash("Product name is required.", "error")
            return redirect(url_for("admin.edit_product", pid=pid))
        if category not in categories:
            flash("Invalid category.", "error")
            return redirect(url_for("admin.edit_product", pid=pid))
        if unit not in units:
            flash("Invalid unit.", "error")
            return redirect(url_for("admin.edit_product", pid=pid))

        try:
            new_cost = float(request.form["cost_price"])
            if new_cost < 0: raise ValueError
        except (TypeError, ValueError):
            flash("Invalid cost price.", "error")
            return redirect(url_for("admin.edit_product", pid=pid))

        markup_str = request.form.get("markup_pct", "").strip()
        try:
            markup = float(markup_str) if markup_str else None
            if markup is not None and markup < 0: markup = 0.0
        except (TypeError, ValueError):
            markup = None

        try:
            qty = float(request.form.get("quantity","").strip()) if request.form.get("quantity","").strip() else None
        except (TypeError, ValueError):
            qty = None
        try:
            reorder = float(request.form.get("reorder_threshold","").strip()) if request.form.get("reorder_threshold","").strip() else None
        except (TypeError, ValueError):
            reorder = None
        try:
            weight_kg = float(request.form.get("weight_kg","").strip()) if request.form.get("weight_kg","").strip() else None
        except (TypeError, ValueError):
            weight_kg = None
        try:
            volume_litres = float(request.form.get("volume_litres","").strip()) if request.form.get("volume_litres","").strip() else None
        except (TypeError, ValueError):
            volume_litres = None

        old_snap = product_snapshot(product)
        new_snap = {"name": name, "category": category, "unit": unit,
                    "supplier_name": supplier, "supplier_tel": tel,
                    "cost_price": new_cost, "markup_pct": markup,
                    "notes": notes, "barcode": barcode,
                    "quantity": qty, "reorder_threshold": reorder}

        old_cost = product["cost_price"]
        if abs(new_cost - old_cost) > 0.001:
            db.execute(
                """INSERT INTO price_history
                   (product_id, product_name, old_cost, new_cost, changed_by, notes, changed_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (pid, name, old_cost, new_cost, _current_user(), change_note,
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            )

        diff_parts = [f"{f}: {old_snap.get(f)!r} → {new_snap.get(f)!r}"
                      for f in old_snap if str(old_snap.get(f)) != str(new_snap.get(f))]
        log_event(db, "product_edited", product_id=pid, product_name=name,
                  changed_by=_current_user(),
                  notes=change_note or ("; ".join(diff_parts) or "no changes"),
                  old_data=old_snap, new_data=new_snap)

        db.execute(
            """UPDATE products SET
               name=?, category=?, unit=?, supplier_name=?, supplier_tel=?,
               cost_price=?, markup_pct=?, notes=?, barcode=?,
               quantity=?, reorder_threshold=?, weight_kg=?, volume_litres=?, last_updated=? WHERE id=?""",
            (name, category, unit, supplier, tel, new_cost, markup, notes,
             barcode, qty, reorder, weight_kg, volume_litres, date.today().isoformat(), pid)
        )
        new_supplier = _auto_save_supplier(db, supplier, tel)
        db.commit()
        msg = f"'{name}' updated."
        if new_supplier:
            msg += f" Supplier '{supplier}' saved."
        flash(msg, "success")
        return redirect(url_for("admin.products"))

    cur_parent, cur_sub = _resolve_cat(tree, product["category"] or "")
    return render_template("admin_product_form.html",
                           product=dict(product), action="Edit",
                           categories=categories, units=units,
                           suppliers=suppliers, cat_tree=tree,
                           cat_tree_json=_js_tree(tree),
                           cur_parent=cur_parent, cur_sub=cur_sub,
                           shop_name=get_setting("shop_name"))


# ── Delete product ────────────────────────────────────────────────────────────

@bp.route("/products/<int:pid>/delete", methods=["POST"])
@require_admin
def delete_product(pid):
    db      = get_db()
    product = db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    if product:
        log_event(db, "product_deleted",
                  product_id=pid, product_name=product["name"],
                  changed_by=_current_user(),
                  notes="Product removed from active catalogue",
                  old_data=product_snapshot(product))
        db.execute("UPDATE products SET active=0 WHERE id=?", (pid,))
        db.commit()
        flash(f"'{product['name']}' removed.", "success")
    return redirect(url_for("admin.products"))


# ── Restore product ───────────────────────────────────────────────────────────

@bp.route("/products/<int:pid>/restore", methods=["POST"])
@require_admin
def restore_product(pid):
    db      = get_db()
    product = db.execute("SELECT * FROM products WHERE id=? AND active=0", (pid,)).fetchone()
    if product:
        db.execute("UPDATE products SET active=1, last_updated=? WHERE id=?",
                   (date.today().isoformat(), pid))
        log_event(db, "product_restored",
                  product_id=pid, product_name=product["name"],
                  changed_by=_current_user(),
                  notes="Product restored to active catalogue")
        db.commit()
        flash(f"'{product['name']}' restored.", "success")
    return redirect(url_for("admin.deleted_products"))


# ── Deleted products view ─────────────────────────────────────────────────────

@bp.route("/deleted")
@require_admin
def deleted_products():
    db                       = get_db()
    default_markup, rounding = get_pricing_config()
    rows = db.execute("SELECT * FROM products WHERE active=0 ORDER BY name").fetchall()
    enriched = _enrich(rows, default_markup, rounding)
    return render_template("admin_deleted.html",
                           products=enriched,
                           shop_name=get_setting("shop_name"))


# ── Bulk markup ───────────────────────────────────────────────────────────────

@bp.route("/products/bulk_markup", methods=["POST"])
@require_admin
def bulk_markup():
    db       = get_db()
    category = request.form.get("bulk_category", "").strip()
    action   = request.form.get("bulk_action",   "set")
    try:
        pct = float(request.form.get("bulk_pct", "0"))
    except (TypeError, ValueError):
        flash("Invalid percentage.", "error")
        return redirect(url_for("admin.products"))

    if not category:
        flash("Please select a category.", "error")
        return redirect(url_for("admin.products"))

    default_markup, _ = get_pricing_config()
    rows    = db.execute(
        "SELECT * FROM products WHERE active=1 AND category=?", (category,)
    ).fetchall()
    updated = 0

    for p in rows:
        old_m = p["markup_pct"]
        if action == "set":
            new_m = pct
        elif action == "increase":
            base  = old_m if old_m is not None else default_markup
            new_m = base + pct
        elif action == "decrease":
            base  = old_m if old_m is not None else default_markup
            new_m = max(0.0, base - pct)
        else:
            new_m = pct

        db.execute("UPDATE products SET markup_pct=?, last_updated=? WHERE id=?",
                   (new_m, date.today().isoformat(), p["id"]))
        log_event(db, "product_edited",
                  product_id=p["id"], product_name=p["name"],
                  changed_by=_current_user(),
                  notes=f"Bulk markup {action}: {old_m}% → {new_m}%",
                  old_data={"markup_pct": old_m},
                  new_data={"markup_pct": new_m})
        updated += 1

    db.commit()
    flash(f"Markup updated for {updated} product(s) in '{category}'.", "success")
    return redirect(url_for("admin.products"))


# ── CSV export ────────────────────────────────────────────────────────────────

@bp.route("/export/csv")
@require_admin
def export_csv():
    db                       = get_db()
    default_markup, rounding = get_pricing_config()
    shop_name                = get_setting("shop_name", "Tenbury Farm Supplies")
    currency                 = get_setting("currency", "£")

    rows = db.execute(
        "SELECT * FROM products WHERE active=1 ORDER BY category, name"
    ).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Product Name", "Category", "Unit", "Supplier",
        "Supplier Tel", f"Cost Price ({currency})", "Markup %",
        f"Sell Price ({currency})", "Barcode", "Quantity",
        "Reorder Threshold", "Notes", "Last Updated"
    ])
    for p in rows:
        sp     = sell_price(p["cost_price"], p["markup_pct"], default_markup, rounding)
        markup = p["markup_pct"] if p["markup_pct"] is not None else default_markup
        writer.writerow([
            p["name"], p["category"], p["unit"],
            p["supplier_name"], p["supplier_tel"],
            f"{p['cost_price']:.2f}", f"{markup:.0f}",
            f"{sp:.2f}", p["barcode"] or "",
            p["quantity"] if p["quantity"] is not None else "",
            p["reorder_threshold"] if p["reorder_threshold"] is not None else "",
            p["notes"], p["last_updated"]
        ])

    safe_name = shop_name.replace(" ", "_").replace("/", "_")
    filename  = f"{safe_name}_prices_{date.today().isoformat()}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


# ── JSON export ───────────────────────────────────────────────────────────────

@bp.route("/export/json")
@require_admin
def export_json():
    db                       = get_db()
    default_markup, rounding = get_pricing_config()
    currency                 = get_setting("currency", "£")

    rows = db.execute(
        "SELECT * FROM products WHERE active=1 ORDER BY category, name"
    ).fetchall()

    out = []
    for p in rows:
        sp = sell_price(p["cost_price"], p["markup_pct"], default_markup, rounding)
        out.append({
            "id":          p["id"],
            "name":        p["name"],
            "category":    p["category"],
            "unit":        p["unit"],
            "barcode":     p["barcode"] or None,
            "sell_price":  sp,
            "currency":    currency,
            "last_updated": p["last_updated"],
        })

    from flask import jsonify
    resp = jsonify({"products": out, "count": len(out),
                    "exported_at": datetime.now().isoformat()})
    resp.headers["Content-Disposition"] = (
        f'attachment; filename="products_{date.today().isoformat()}.json"'
    )
    return resp


# ── CSV import ────────────────────────────────────────────────────────────────

@bp.route("/import", methods=["GET", "POST"])
@require_admin
def import_csv():
    db         = get_db()
    categories = [r["name"] for r in
                  db.execute("SELECT name FROM categories ORDER BY name").fetchall()]
    units      = [r["name"] for r in
                  db.execute("SELECT name FROM units ORDER BY name").fetchall()]

    if request.method == "GET":
        return render_template("admin_import.html",
                               shop_name=get_setting("shop_name"),
                               categories=categories, units=units)

    file = request.files.get("csv_file")
    if not file or not file.filename:
        flash("Please select a CSV file.", "error")
        return redirect(url_for("admin.import_csv"))

    if not file.filename.lower().endswith(".csv"):
        flash("File must be a .csv", "error")
        return redirect(url_for("admin.import_csv"))

    try:
        stream  = io.StringIO(file.stream.read().decode("utf-8-sig"))
        reader  = csv.DictReader(stream)
        rows    = list(reader)
    except Exception as e:
        flash(f"Could not parse CSV: {e}", "error")
        return redirect(url_for("admin.import_csv"))

    if not rows:
        flash("CSV file is empty.", "error")
        return redirect(url_for("admin.import_csv"))

    # Preview mode
    if request.form.get("action") == "preview":
        return render_template("admin_import.html",
                               shop_name=get_setting("shop_name"),
                               categories=categories, units=units,
                               preview_rows=rows[:20],
                               headers=list(rows[0].keys()),
                               total=len(rows))

    # Import mode
    default_cat  = request.form.get("default_category", "Other")
    default_unit = request.form.get("default_unit", "each")
    skip_dupes   = request.form.get("skip_duplicates") == "1"

    # Column mapping from form
    col = {
        "name":     request.form.get("col_name", "Product Name"),
        "category": request.form.get("col_category", "Category"),
        "unit":     request.form.get("col_unit", "Unit"),
        "supplier": request.form.get("col_supplier", "Supplier"),
        "tel":      request.form.get("col_tel", "Supplier Tel"),
        "cost":     request.form.get("col_cost", "Cost Price"),
        "markup":   request.form.get("col_markup", "Markup %"),
        "barcode":  request.form.get("col_barcode", "Barcode"),
        "notes":    request.form.get("col_notes", "Notes"),
    }

    imported = 0
    skipped  = 0
    errors   = []

    for i, row in enumerate(rows, start=2):
        name = row.get(col["name"], "").strip()[:_MAX_NAME]
        if not name:
            errors.append(f"Row {i}: missing product name — skipped")
            skipped += 1
            continue

        if skip_dupes:
            exists = db.execute(
                "SELECT id FROM products WHERE name=? AND active=1", (name,)
            ).fetchone()
            if exists:
                skipped += 1
                continue

        category = row.get(col["category"], "").strip() or default_cat
        if category not in categories:
            category = default_cat
        unit = row.get(col["unit"], "").strip() or default_unit
        if unit not in units:
            unit = default_unit

        try:
            cost = float(str(row.get(col["cost"], "0")).replace("£", "").replace(",", "").strip() or 0)
        except (ValueError, TypeError):
            cost = 0.0

        markup_raw = str(row.get(col["markup"], "")).strip()
        try:
            markup = float(markup_raw) if markup_raw else None
        except (ValueError, TypeError):
            markup = None

        supplier = row.get(col["supplier"], "").strip()[:_MAX_NAME]
        tel      = row.get(col["tel"],      "").strip()[:40]
        barcode  = row.get(col["barcode"],  "").strip()[:_MAX_BARCODE]
        notes    = row.get(col["notes"],    "").strip()[:_MAX_NOTES]

        cursor = db.execute(
            """INSERT INTO products
               (name, category, unit, supplier_name, supplier_tel,
                cost_price, markup_pct, notes, barcode, last_updated)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (name, category, unit, supplier, tel, cost, markup,
             notes, barcode, date.today().isoformat())
        )
        log_event(db, "product_added",
                  product_id=cursor.lastrowid, product_name=name,
                  changed_by=_current_user(),
                  notes="Imported via CSV")
        imported += 1

    db.commit()
    msg = f"Import complete: {imported} added"
    if skipped:
        msg += f", {skipped} skipped"
    if errors:
        msg += f", {len(errors)} error(s)"
    flash(msg, "success" if not errors else "info")
    if errors:
        for e in errors[:5]:
            flash(e, "error")
    return redirect(url_for("admin.products"))


# ── Price history chart data ──────────────────────────────────────────────────

@bp.route("/products/<int:pid>/price_history")
@require_admin
def price_history(pid):
    db      = get_db()
    product = db.execute("SELECT name FROM products WHERE id=?", (pid,)).fetchone()
    if not product:
        from flask import jsonify
        return jsonify({"error": "Not found"}), 404

    rows = db.execute(
        """SELECT changed_at, old_cost, new_cost
           FROM price_history WHERE product_id=?
           ORDER BY changed_at ASC""",
        (pid,)
    ).fetchall()

    history = [{"date": r["changed_at"], "old": r["old_cost"], "new": r["new_cost"]}
               for r in rows]

    # Add current price as last data point if there's any history
    product_full = db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    default_markup, rounding = get_pricing_config()
    currency = get_setting("currency", "£")
    sp = sell_price(product_full["cost_price"], product_full["markup_pct"],
                    default_markup, rounding)

    return render_template("admin_price_chart.html",
                           product=dict(product_full),
                           history=history,
                           sell_price=sp,
                           currency=currency,
                           default_markup=default_markup,
                           shop_name=get_setting("shop_name"))


# ── Audit history ─────────────────────────────────────────────────────────────

@bp.route("/history")
@require_admin
def history():
    db             = get_db()
    event_filter   = request.args.get("event_type", "")
    product_filter = request.args.get("product", "").strip()
    user_filter    = request.args.get("user", "").strip()
    date_from      = request.args.get("date_from", "").strip()
    date_to        = request.args.get("date_to", "").strip()
    page           = max(1, int(request.args.get("page", 1)))
    per_page       = 100

    where  = "WHERE 1=1"
    params = []
    if event_filter:
        where += " AND event_type=?"
        params.append(event_filter)
    if product_filter:
        where += " AND product_name LIKE ?"
        params.append(f"%{product_filter}%")
    if user_filter:
        where += " AND changed_by LIKE ?"
        params.append(f"%{user_filter}%")
    if date_from:
        where += " AND changed_at >= ?"
        params.append(date_from + " 00:00:00")
    if date_to:
        where += " AND changed_at <= ?"
        params.append(date_to + " 23:59:59")

    total = db.execute(f"SELECT COUNT(*) FROM audit_log {where}", params).fetchone()[0]
    q     = f"SELECT * FROM audit_log {where} ORDER BY changed_at DESC LIMIT ? OFFSET ?"
    rows = db.execute(q, params + [per_page, (page - 1) * per_page]).fetchall()

    hist = []
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
        hist.append(entry)

    event_types = [
        "product_added", "product_edited", "product_deleted", "product_restored",
        "price_changed", "category_added", "category_deleted",
        "unit_added", "unit_deleted", "settings_changed",
        "admin_login", "admin_logout", "login_failed",
        "user_added", "user_edited", "user_deleted",
        "supplier_added", "supplier_edited", "supplier_deleted",
    ]

    total_pages = max(1, (total + per_page - 1) // per_page)

    return render_template("admin_history.html",
                           history=hist,
                           event_types=event_types,
                           event_filter=event_filter,
                           product_filter=product_filter,
                           user_filter=user_filter,
                           date_from=date_from,
                           date_to=date_to,
                           page=page,
                           per_page=per_page,
                           total=total,
                           total_pages=total_pages,
                           shop_name=get_setting("shop_name"))


# ── Price review report ───────────────────────────────────────────────────────

@bp.route("/review")
@require_admin
def review():
    db       = get_db()
    cat_filter = request.args.get("category", "")
    try:
        days = int(request.args.get("days") or get_setting("review_days", "30"))
    except ValueError:
        days = 30

    default_markup, rounding = get_pricing_config()
    currency   = get_setting("currency", "£")
    categories = [r["name"] for r in
                  db.execute("SELECT name FROM categories ORDER BY name").fetchall()]

    q      = """SELECT * FROM products
                WHERE active=1
                AND (last_updated <= date('now', ? )
                     OR last_updated IS NULL)"""
    params = [f"-{days} days"]
    if cat_filter:
        q += " AND category=?"
        params.append(cat_filter)
    q += " ORDER BY last_updated ASC, name"

    rows     = db.execute(q, params).fetchall()
    enriched = _enrich(rows, default_markup, rounding)
    today    = date.today()
    for p in enriched:
        if p.get("last_updated"):
            try:
                p["days_old"] = (today - date.fromisoformat(p["last_updated"])).days
            except Exception:
                p["days_old"] = 999
        else:
            p["days_old"] = 999

    return render_template("admin_review.html",
                           products=enriched,
                           categories=categories,
                           cat_filter=cat_filter,
                           days=days,
                           currency=currency,
                           shop_name=get_setting("shop_name"))


# ── Settings ──────────────────────────────────────────────────────────────────

@bp.route("/settings", methods=["GET", "POST"])
@require_admin
def settings():
    db = get_db()

    if request.method == "POST":
        action = request.form.get("action", "save_settings")

        if action == "save_settings":
            old = {k: get_setting(k) for k in ("shop_name","default_markup","price_rounding","currency","review_days")}
            shop_name   = request.form.get("shop_name", "").strip()[:80]
            raw_markup  = request.form.get("default_markup", "30").strip()
            rounding    = request.form.get("price_rounding", "none")
            try:
                markup_val = float(raw_markup)
                if markup_val < 0:
                    raise ValueError
            except ValueError:
                flash("Default markup must be a non-negative number.", "error")
                return redirect(url_for("admin.settings"))

            currency    = request.form.get("currency", "£").strip()[:5]
            review_days = request.form.get("review_days", "30").strip()
            try:
                int(review_days)  # validate
            except ValueError:
                review_days = "30"

            new = {"shop_name": shop_name, "default_markup": str(markup_val),
                   "price_rounding": rounding, "currency": currency, "review_days": review_days}

            for key, val in new.items():
                db.execute("UPDATE settings SET value=? WHERE key=?", (val, key))

            diffs = [f"{k}: {old[k]!r}→{new[k]!r}" for k in new if old.get(k) != new[k]]
            log_event(db, "settings_changed",
                      changed_by=_current_user(),
                      notes="; ".join(diffs) or "no changes",
                      old_data=old, new_data=new)
            db.commit()
            flash("Settings saved.", "success")
            return redirect(url_for("admin.settings"))

        return redirect(url_for("admin.settings"))

    all_settings = {r["key"]: r["value"]
                    for r in db.execute("SELECT * FROM settings").fetchall()}
    categories   = [r["name"] for r in
                    db.execute("SELECT name FROM categories ORDER BY name").fetchall()]
    units        = [r["name"] for r in
                    db.execute("SELECT name FROM units ORDER BY name").fetchall()]

    return render_template("admin_settings.html",
                           settings=all_settings,
                           categories=categories,
                           units=units,
                           shop_name=all_settings.get("shop_name", ""))


# ── Users management ──────────────────────────────────────────────────────────

@bp.route("/users")
@require_admin
def users():
    db   = get_db()
    rows = db.execute(
        "SELECT id, username, role, active, created_at, last_login FROM users ORDER BY username"
    ).fetchall()
    return render_template("admin_users.html",
                           users=rows,
                           current_user_id=session.get("user_id"),
                           shop_name=get_setting("shop_name"))


@bp.route("/users/add", methods=["POST"])
@require_admin
def add_user():
    db       = get_db()
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    role     = request.form.get("role", "sales")

    if not username or not password:
        flash("Username and password are required.", "error")
        return redirect(url_for("admin.users"))
    if len(username) > 40:
        flash("Username must be 40 characters or less.", "error")
        return redirect(url_for("admin.users"))
    if len(password) < 6:
        flash("Password must be at least 6 characters.", "error")
        return redirect(url_for("admin.users"))
    if role not in ("admin", "sales"):
        role = "sales"

    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    try:
        db.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?,?,?)",
            (username, pw_hash, role)
        )
        log_event(db, "user_added",
                  changed_by=_current_user(),
                  notes=f"User '{username}' added with role '{role}'")
        db.commit()
        flash(f"User '{username}' created.", "success")
    except Exception:
        flash(f"Username '{username}' already exists.", "error")
    return redirect(url_for("admin.users"))


@bp.route("/users/<int:uid>/edit", methods=["POST"])
@require_admin
def edit_user(uid):
    db       = get_db()
    user     = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not user:
        flash("User not found.", "error")
        return redirect(url_for("admin.users"))

    action = request.form.get("action", "edit")

    if action == "toggle_active":
        # Cannot deactivate self
        if uid == session.get("user_id"):
            flash("You cannot deactivate your own account.", "error")
            return redirect(url_for("admin.users"))
        new_active = 0 if user["active"] else 1
        db.execute("UPDATE users SET active=? WHERE id=?", (new_active, uid))
        status = "activated" if new_active else "deactivated"
        log_event(db, "user_edited",
                  changed_by=_current_user(),
                  notes=f"User '{user['username']}' {status}")
        db.commit()
        flash(f"User '{user['username']}' {status}.", "success")
        return redirect(url_for("admin.users"))

    if action == "change_role":
        if uid == session.get("user_id"):
            flash("You cannot change your own role.", "error")
            return redirect(url_for("admin.users"))
        new_role = request.form.get("role", "sales")
        if new_role not in ("admin", "sales"):
            new_role = "sales"
        db.execute("UPDATE users SET role=? WHERE id=?", (new_role, uid))
        log_event(db, "user_edited",
                  changed_by=_current_user(),
                  notes=f"User '{user['username']}' role → {new_role}")
        db.commit()
        flash(f"'{user['username']}' is now {new_role}.", "success")
        return redirect(url_for("admin.users"))

    if action == "reset_password":
        new_pw = request.form.get("new_password", "")
        if len(new_pw) < 6:
            flash("Password must be at least 6 characters.", "error")
            return redirect(url_for("admin.users"))
        pw_hash = bcrypt.hashpw(new_pw.encode(), bcrypt.gensalt()).decode()
        db.execute("UPDATE users SET password_hash=? WHERE id=?", (pw_hash, uid))
        log_event(db, "user_edited",
                  changed_by=_current_user(),
                  notes=f"Password reset for user '{user['username']}'")
        db.commit()
        flash(f"Password updated for '{user['username']}'.", "success")
        return redirect(url_for("admin.users"))

    if action == "change_own_password":
        # Self-service password change
        current_pw = request.form.get("current_password", "")
        new_pw     = request.form.get("new_password", "")
        confirm_pw = request.form.get("confirm_password", "")

        if uid != session.get("user_id"):
            flash("You can only change your own password via this form.", "error")
            return redirect(url_for("admin.users"))
        if not bcrypt.checkpw(current_pw.encode(), user["password_hash"].encode()):
            flash("Current password is incorrect.", "error")
            return redirect(url_for("admin.users"))
        if len(new_pw) < 6:
            flash("New password must be at least 6 characters.", "error")
            return redirect(url_for("admin.users"))
        if new_pw != confirm_pw:
            flash("New passwords do not match.", "error")
            return redirect(url_for("admin.users"))

        pw_hash = bcrypt.hashpw(new_pw.encode(), bcrypt.gensalt()).decode()
        db.execute("UPDATE users SET password_hash=? WHERE id=?", (pw_hash, uid))
        log_event(db, "user_edited",
                  changed_by=_current_user(),
                  notes="Own password changed")
        db.commit()
        flash("Password changed.", "success")
        return redirect(url_for("admin.users"))

    flash("Unknown action.", "error")
    return redirect(url_for("admin.users"))


@bp.route("/users/<int:uid>/delete", methods=["POST"])
@require_admin
def delete_user(uid):
    db   = get_db()
    user = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if uid == session.get("user_id"):
        flash("You cannot delete your own account.", "error")
        return redirect(url_for("admin.users"))
    if user:
        db.execute("DELETE FROM users WHERE id=?", (uid,))
        log_event(db, "user_deleted",
                  changed_by=_current_user(),
                  notes=f"User '{user['username']}' deleted")
        db.commit()
        flash(f"User '{user['username']}' deleted.", "success")
    return redirect(url_for("admin.users"))


# ── Suppliers management ──────────────────────────────────────────────────────

@bp.route("/suppliers")
@require_admin
def suppliers():
    db   = get_db()
    rows = db.execute(
        """SELECT s.*, COUNT(p.id) AS product_count
           FROM suppliers s
           LEFT JOIN products p ON p.supplier_name=s.name AND p.active=1
           GROUP BY s.id ORDER BY s.name"""
    ).fetchall()
    return render_template("admin_suppliers.html",
                           suppliers=[dict(r) for r in rows],
                           shop_name=get_setting("shop_name"))


@bp.route("/suppliers/add", methods=["POST"])
@require_admin
def add_supplier():
    db    = get_db()
    name  = request.form.get("name", "").strip()[:100]
    tel   = request.form.get("tel",   "").strip()[:40]
    email = request.form.get("email", "").strip()[:100]
    notes = request.form.get("notes", "").strip()[:_MAX_NOTES]
    if not name:
        flash("Supplier name is required.", "error")
        return redirect(url_for("admin.suppliers"))
    try:
        db.execute("INSERT INTO suppliers (name, tel, email, notes) VALUES (?,?,?,?)", (name, tel, email, notes))
        log_event(db, "supplier_added", changed_by=_current_user(), notes=f"Supplier '{name}' added")
        db.commit()
        flash(f"Supplier '{name}' added.", "success")
    except Exception:
        flash(f"Supplier '{name}' already exists.", "error")
    return redirect(url_for("admin.suppliers"))


@bp.route("/suppliers/<int:sid>/edit", methods=["POST"])
@require_admin
def edit_supplier(sid):
    db   = get_db()
    old  = db.execute("SELECT * FROM suppliers WHERE id=?", (sid,)).fetchone()
    if not old:
        flash("Supplier not found.", "error")
        return redirect(url_for("admin.suppliers"))

    name  = request.form.get("name",  "").strip()[:100]
    tel   = request.form.get("tel",   "").strip()[:40]
    email = request.form.get("email", "").strip()[:100]
    notes = request.form.get("notes", "").strip()[:_MAX_NOTES]

    if not name:
        flash("Supplier name is required.", "error")
        return redirect(url_for("admin.suppliers"))

    db.execute(
        "UPDATE suppliers SET name=?, tel=?, email=?, notes=? WHERE id=?",
        (name, tel, email, notes, sid)
    )
    log_event(db, "supplier_edited",
              changed_by=_current_user(),
              notes=f"Supplier '{old['name']}' → '{name}'")
    db.commit()
    flash(f"Supplier '{name}' updated.", "success")
    return redirect(url_for("admin.suppliers"))


@bp.route("/suppliers/<int:sid>/delete", methods=["POST"])
@require_admin
def delete_supplier(sid):
    db       = get_db()
    supplier = db.execute("SELECT * FROM suppliers WHERE id=?", (sid,)).fetchone()
    if supplier:
        count = db.execute(
            "SELECT COUNT(*) FROM products WHERE supplier_name=? AND active=1",
            (supplier["name"],)
        ).fetchone()[0]
        if count > 0:
            flash(f"Cannot delete — {count} product(s) reference this supplier.", "error")
            return redirect(url_for("admin.suppliers"))
        db.execute("DELETE FROM suppliers WHERE id=?", (sid,))
        log_event(db, "supplier_deleted",
                  changed_by=_current_user(),
                  notes=f"Supplier '{supplier['name']}' deleted")
        db.commit()
        flash(f"Supplier '{supplier['name']}' deleted.", "success")
    return redirect(url_for("admin.suppliers"))


# ── Categories management ─────────────────────────────────────────────────────

@bp.route("/categories")
@require_admin
def categories():
    db = get_db()
    return render_template("admin_categories.html",
                           parents=_cat_tree(db),
                           shop_name=get_setting("shop_name"))


# ── Bulk select actions ───────────────────────────────────────────────────────

@bp.route("/products/bulk_action", methods=["POST"])
@require_admin
def bulk_action():
    db      = get_db()
    ids_raw = request.form.getlist("ids")
    ids = [int(i) for i in ids_raw if str(i).strip().isdigit()]
    if not ids:
        flash("No products selected.", "error")
        return redirect(url_for("admin.products"))
    action = request.form.get("bulk_action_type", "")
    if action == "delete":
        count = 0
        for pid in ids:
            p = db.execute("SELECT * FROM products WHERE id=? AND active=1", (pid,)).fetchone()
            if p:
                db.execute("UPDATE products SET active=0 WHERE id=?", (pid,))
                log_event(db, "product_deleted", product_id=pid, product_name=p["name"],
                          changed_by=_current_user(), notes="Bulk delete", old_data=product_snapshot(p))
                count += 1
        db.commit()
        flash(f"{count} product(s) removed.", "success")
    elif action == "set_category":
        cat = request.form.get("bulk_category_val", "").strip()
        if cat not in _flat_cats(db):
            flash("Invalid category.", "error")
            return redirect(url_for("admin.products"))
        for pid in ids:
            p = db.execute("SELECT * FROM products WHERE id=? AND active=1", (pid,)).fetchone()
            if not p: continue
            db.execute("UPDATE products SET category=?,last_updated=date('now') WHERE id=?", (cat, pid))
            log_event(db, "product_edited", product_id=pid, product_name=p["name"],
                      changed_by=_current_user(),
                      notes=f"Bulk category: {p['category']!r} → {cat!r}",
                      old_data={"category": p["category"]}, new_data={"category": cat})
        db.commit()
        flash(f"Category updated for {len(ids)} product(s).", "success")
    elif action == "set_supplier":
        sup = request.form.get("bulk_supplier_val", "").strip()
        tel = ""
        if sup:
            srow = db.execute("SELECT tel FROM suppliers WHERE name=? COLLATE NOCASE", (sup,)).fetchone()
            if srow: tel = srow["tel"] or ""
        for pid in ids:
            p = db.execute("SELECT * FROM products WHERE id=? AND active=1", (pid,)).fetchone()
            if not p: continue
            db.execute("UPDATE products SET supplier_name=?,supplier_tel=?,last_updated=date('now') WHERE id=?",
                       (sup, tel, pid))
            log_event(db, "product_edited", product_id=pid, product_name=p["name"],
                      changed_by=_current_user(),
                      notes=f"Bulk supplier: {p['supplier_name']!r} → {sup!r}",
                      old_data={"supplier_name": p["supplier_name"]}, new_data={"supplier_name": sup})
        db.commit()
        flash(f"Supplier updated for {len(ids)} product(s).", "success")
    elif action in ("set_markup", "increase_markup", "decrease_markup"):
        try:
            pct = float(request.form.get("bulk_markup_pct", "0"))
        except (TypeError, ValueError):
            flash("Invalid percentage.", "error")
            return redirect(url_for("admin.products"))
        default_markup, _ = get_pricing_config()
        for pid in ids:
            p = db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
            if not p: continue
            old_m = p["markup_pct"]
            base  = old_m if old_m is not None else default_markup
            new_m = pct if action == "set_markup" else (base+pct if action == "increase_markup" else max(0.0, base-pct))
            db.execute("UPDATE products SET markup_pct=?,last_updated=date('now') WHERE id=?", (new_m, pid))
            log_event(db, "product_edited", product_id=pid, product_name=p["name"],
                      changed_by=_current_user(), notes=f"Bulk markup {action}: {old_m}% → {new_m}%",
                      old_data={"markup_pct": old_m}, new_data={"markup_pct": new_m})
        db.commit()
        flash(f"Markup updated for {len(ids)} product(s).", "success")
    else:
        flash("Unknown action.", "error")
    return redirect(url_for("admin.products"))

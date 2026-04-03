"""
Public blueprint — price lookup (requires any login), print price list, shelf labels.
"""
from datetime import date, datetime

from flask import (
    Blueprint, render_template, request, session
)

from db import get_db
from decorators import require_login
from helpers import get_setting, get_pricing_config, sell_price

bp = Blueprint("public", __name__)


def _cat_tree(db):
    rows = db.execute("SELECT id,name,parent_id FROM categories ORDER BY name").fetchall()
    parents = [dict(r) for r in rows if r["parent_id"] is None]
    subs = {}
    for r in rows:
        if r["parent_id"] is not None:
            subs.setdefault(r["parent_id"], []).append(dict(r))
    for p in parents:
        p["subcategories"] = subs.get(p["id"], [])
    return parents

@bp.route("/")
@require_login
def index():
    db        = get_db()
    shop_name = get_setting("shop_name", "Tenbury Farm Supplies")
    tree      = _cat_tree(db)
    cat_tree_json = [{"name": p["name"], "subs": [s["name"] for s in p["subcategories"]]} for p in tree]
    is_admin  = session.get("role") == "admin"
    return render_template("lookup.html",
                           shop_name=shop_name,
                           cat_tree=tree,
                           cat_tree_json=cat_tree_json,
                           is_admin=is_admin,
                           username=session.get("username", ""))


@bp.route("/pricelist")
@require_login
def pricelist():
    from flask import redirect, url_for, flash
    if session.get("role") != "admin":
        flash("Admin access required.", "error")
        return redirect(url_for("public.index"))
    db                       = get_db()
    default_markup, rounding = get_pricing_config()
    shop_name                = get_setting("shop_name", "Tenbury Farm Supplies")
    currency                 = get_setting("currency", "£")
    rows = db.execute(
        "SELECT * FROM products WHERE active=1 ORDER BY category, name"
    ).fetchall()
    by_category: dict = {}
    for p in rows:
        sp    = sell_price(p["cost_price"], p["markup_pct"], default_markup, rounding)
        entry = dict(p) | {"sell_price": sp}
        by_category.setdefault(p["category"], []).append(entry)
    return render_template("pricelist.html",
                           by_category=by_category,
                           shop_name=shop_name,
                           currency=currency,
                           generated=datetime.now().strftime("%d %b %Y %H:%M"),
                           active_nav='pricelist',
                           current_username=session.get("username",""),
                           current_role=session.get("role",""))


@bp.route("/labels")
@require_login
def labels():
    if session.get("role") != "admin":
        from flask import redirect, url_for, flash
        flash("Admin access required.", "error")
        return redirect(url_for("public.index"))

    db                       = get_db()
    default_markup, rounding = get_pricing_config()
    shop_name                = get_setting("shop_name", "Tenbury Farm Supplies")
    currency                 = get_setting("currency", "£")
    cat_filter               = request.args.get("category", "")
    sup_filter               = request.args.get("supplier", "")

    tree = _cat_tree(db)
    # expand cat_filter to include subcategories
    cat_names = []
    if cat_filter:
        for p in tree:
            if p["name"] == cat_filter:
                cat_names = [p["name"]] + [s["name"] for s in p["subcategories"]]
                break
            for s in p["subcategories"]:
                if s["name"] == cat_filter:
                    cat_names = [s["name"]]
                    break
        if not cat_names:
            cat_names = [cat_filter]

    suppliers = [r["name"] for r in
                 db.execute("SELECT DISTINCT supplier_name AS name FROM products WHERE active=1 AND supplier_name!='' ORDER BY supplier_name").fetchall()]

    q      = "SELECT * FROM products WHERE active=1"
    params = []
    if cat_names:
        q += " AND category IN ({})".format(",".join("?"*len(cat_names)))
        params.extend(cat_names)
    if sup_filter:
        q += " AND supplier_name=?"
        params.append(sup_filter)
    q += " ORDER BY category, name"

    rows = db.execute(q, params).fetchall()
    products = []
    for p in rows:
        sp = sell_price(p["cost_price"], p["markup_pct"], default_markup, rounding)
        d  = dict(p) | {"sell_price": sp}
        if p["volume_litres"] and p["volume_litres"] > 0:
            d["price_per_100"] = sp / (p["volume_litres"] * 10)
            d["per_100_label"] = "per 100ml"
        elif p["weight_kg"] and p["weight_kg"] > 0:
            d["price_per_100"] = sp / (p["weight_kg"] * 10)
            d["per_100_label"] = "per 100g"
        else:
            d["price_per_100"] = None
            d["per_100_label"] = None
        products.append(d)

    return render_template("labels.html",
                           products=products,
                           cat_tree=tree,
                           cat_filter=cat_filter,
                           sup_filter=sup_filter,
                           suppliers=suppliers,
                           shop_name=shop_name,
                           currency=currency,
                           generated=date.today().strftime("%d %b %Y"),
                           active_nav='labels',
                           current_username=session.get("username",""),
                           current_role=session.get("role",""))

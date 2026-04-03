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
    db                       = get_db()
    default_markup, rounding = get_pricing_config()
    shop_name                = get_setting("shop_name", "Tenbury Farm Supplies")
    currency                 = get_setting("currency", "£")
    is_admin                 = session.get("role") == "admin"

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
                           is_admin=is_admin,
                           generated=datetime.now().strftime("%d %B %Y %H:%M"))


@bp.route("/labels")
@require_login
def labels():
    from decorators import require_admin as _ra
    # Labels are admin-only; sales users redirect home
    if session.get("role") != "admin":
        from flask import redirect, url_for, flash
        flash("Admin access required.", "error")
        return redirect(url_for("public.index"))

    db                       = get_db()
    default_markup, rounding = get_pricing_config()
    shop_name                = get_setting("shop_name", "Tenbury Farm Supplies")
    currency                 = get_setting("currency", "£")
    cat_filter               = request.args.get("category", "")

    categories = [r["name"] for r in
                  db.execute("SELECT name FROM categories ORDER BY name").fetchall()]

    q      = "SELECT * FROM products WHERE active=1"
    params = []
    if cat_filter:
        q += " AND category=?"
        params.append(cat_filter)
    q += " ORDER BY category, name"

    rows = db.execute(q, params).fetchall()
    products = []
    for p in rows:
        sp      = sell_price(p["cost_price"], p["markup_pct"], default_markup, rounding)
        products.append(dict(p) | {"sell_price": sp})

    return render_template("labels.html",
                           products=products,
                           categories=categories,
                           cat_filter=cat_filter,
                           shop_name=shop_name,
                           currency=currency,
                           generated=date.today().strftime("%d %b %Y"))

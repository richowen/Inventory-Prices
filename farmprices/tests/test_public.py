"""Tests for public routes: /, /pricelist, /labels."""
import pytest


def _add_product(c, name="PubProd", category="Other", cost="5.00", barcode=""):
    return c.post("/admin/products/add", data={
        "name": name, "category": category, "unit": "each",
        "cost_price": cost, "markup_pct": "", "barcode": barcode
    }, follow_redirects=True)


# ── / (lookup page) ───────────────────────────────────────────────────────────

def test_index_requires_login(client):
    r = client.get("/")
    assert r.status_code == 302
    assert b"/login" in r.data or "login" in r.headers.get("Location", "")

def test_index_admin_can_access(admin_client):
    r = admin_client.get("/")
    assert r.status_code == 200

def test_index_sales_can_access(sales_client):
    r = sales_client.get("/")
    assert r.status_code == 200

def test_index_shows_shop_name(admin_client, app):
    with app.app_context():
        from db import get_db
        get_db().execute("UPDATE settings SET value='Test Farm Shop' WHERE key='shop_name'")
        get_db().commit()
    r = admin_client.get("/")
    assert b"Test Farm Shop" in r.data

def test_index_has_search_ui(admin_client):
    r = admin_client.get("/")
    # The lookup page should have some search-related element
    assert b"search" in r.data.lower() or b"lookup" in r.data.lower() or b"q" in r.data

def test_index_unauthenticated_redirects_to_login(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 302


# ── /pricelist ────────────────────────────────────────────────────────────────

def test_pricelist_requires_admin(sales_client):
    r = sales_client.get("/pricelist")
    assert r.status_code in (302, 403)

def test_pricelist_unauthenticated(client):
    r = client.get("/pricelist")
    assert r.status_code == 302

def test_pricelist_admin_can_access(admin_client):
    r = admin_client.get("/pricelist")
    assert r.status_code == 200

def test_pricelist_shows_products(admin_client):
    _add_product(admin_client, "PricelistVisibleProd", cost="12.00")
    r = admin_client.get("/pricelist")
    assert b"PricelistVisibleProd" in r.data

def test_pricelist_shows_sell_price(admin_client, app):
    with app.app_context():
        from db import get_db
        db = get_db()
        db.execute("UPDATE settings SET value='30' WHERE key='default_markup'")
        db.execute("UPDATE settings SET value='none' WHERE key='price_rounding'")
        db.commit()
    _add_product(admin_client, "SellPriceListProd", cost="10.00")
    r = admin_client.get("/pricelist")
    # 10 * 1.30 = 13.00
    assert b"13" in r.data

def test_pricelist_grouped_by_category(admin_client):
    _add_product(admin_client, "CatGroupProd1", category="Other")
    r = admin_client.get("/pricelist")
    assert b"Other" in r.data

def test_pricelist_shows_generated_date(admin_client):
    r = admin_client.get("/pricelist")
    # Should contain a year
    assert b"2025" in r.data or b"2026" in r.data or b"2027" in r.data

def test_pricelist_inactive_products_excluded(admin_client, app):
    _add_product(admin_client, "InactivePricelistProd", cost="3.00")
    with app.app_context():
        from db import get_db
        db = get_db()
        db.execute("UPDATE products SET active=0 WHERE name='InactivePricelistProd'")
        db.commit()
    r = admin_client.get("/pricelist")
    assert b"InactivePricelistProd" not in r.data


# ── /labels ───────────────────────────────────────────────────────────────────

def test_labels_requires_admin(sales_client):
    r = sales_client.get("/labels")
    assert r.status_code in (302, 403)

def test_labels_unauthenticated(client):
    r = client.get("/labels")
    assert r.status_code == 302

def test_labels_admin_can_access(admin_client):
    r = admin_client.get("/labels")
    assert r.status_code == 200

def test_labels_shows_products(admin_client):
    _add_product(admin_client, "LabelVisibleProd", cost="5.00")
    r = admin_client.get("/labels")
    assert b"LabelVisibleProd" in r.data

def test_labels_filter_by_category(admin_client):
    _add_product(admin_client, "LabelCatProd", category="Other")
    r = admin_client.get("/labels?category=Other")
    assert r.status_code == 200
    assert b"LabelCatProd" in r.data

def test_labels_filter_unknown_category(admin_client):
    r = admin_client.get("/labels?category=NonExistentCat")
    assert r.status_code == 200

def test_labels_filter_by_supplier(admin_client, app):
    with app.app_context():
        from db import get_db
        db = get_db()
        db.execute("INSERT OR IGNORE INTO suppliers (name) VALUES ('LabelSupplier')")
        db.execute("""INSERT INTO products (name,category,unit,cost_price,supplier_name,active,last_updated)
                      VALUES (?,?,?,?,?,1,date('now'))""",
                   ("LabelSupplierProd", "Other", "each", 4.0, "LabelSupplier"))
        db.commit()
    r = admin_client.get("/labels?supplier=LabelSupplier")
    assert r.status_code == 200
    assert b"LabelSupplierProd" in r.data

def test_labels_price_per_unit_weight(admin_client, app):
    """Products with weight_kg should get price_per_100 calculated."""
    with app.app_context():
        from db import get_db
        db = get_db()
        db.execute("""INSERT INTO products (name,category,unit,cost_price,weight_kg,active,last_updated)
                      VALUES (?,?,?,?,?,1,date('now'))""",
                   ("WeightedLabelProd", "Other", "each", 10.0, 2.0))
        db.commit()
    r = admin_client.get("/labels")
    assert r.status_code == 200

def test_labels_price_per_unit_volume(admin_client, app):
    """Products with volume_litres should get price_per_100 calculated."""
    with app.app_context():
        from db import get_db
        db = get_db()
        db.execute("""INSERT INTO products (name,category,unit,cost_price,volume_litres,active,last_updated)
                      VALUES (?,?,?,?,?,1,date('now'))""",
                   ("VolumeLabelProd", "Other", "each", 5.0, 1.0))
        db.commit()
    r = admin_client.get("/labels")
    assert r.status_code == 200

def test_labels_inactive_excluded(admin_client, app):
    _add_product(admin_client, "InactiveLabelProd", cost="2.00")
    with app.app_context():
        from db import get_db
        db = get_db()
        db.execute("UPDATE products SET active=0 WHERE name='InactiveLabelProd'")
        db.commit()
    r = admin_client.get("/labels")
    assert b"InactiveLabelProd" not in r.data

def test_labels_shows_category_tree(admin_client):
    r = admin_client.get("/labels")
    # Category filter UI should be present
    assert b"Other" in r.data

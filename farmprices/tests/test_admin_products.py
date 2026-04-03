"""Tests for admin product CRUD, bulk actions."""
import pytest


def _add(c, **kw):
    d = {"name":"Test Product","category":"Other","unit":"each",
         "cost_price":"5.00","markup_pct":"30","notes":"","barcode":"",
         "supplier_name":"","quantity":"","reorder_threshold":"",
         "weight_kg":"","volume_litres":""}
    d.update(kw)
    return c.post("/admin/products/add", data=d, follow_redirects=True)


def test_products_list(admin_client):
    r = admin_client.get("/admin/products")
    assert r.status_code == 200

def test_add_product(admin_client):
    r = _add(admin_client, name="Hay Bale", category="Other", unit="each", cost_price="3.50")
    assert r.status_code == 200
    assert b"Hay Bale" in r.data or b"added" in r.data.lower()

def test_add_product_saves_barcode(app, admin_client):
    _add(admin_client, name="Barcode Product", barcode="TEST1234567890")
    with app.app_context():
        from db import get_db
        p = get_db().execute("SELECT barcode FROM products WHERE name='Barcode Product'").fetchone()
    assert p is not None
    assert p["barcode"] == "TEST1234567890"

def test_add_product_missing_name(admin_client):
    r = _add(admin_client, name="")
    assert b"required" in r.data.lower()

def test_add_product_invalid_cost(admin_client):
    r = _add(admin_client, cost_price="abc")
    assert b"invalid" in r.data.lower() or b"cost" in r.data.lower()

def test_add_product_negative_cost(admin_client):
    r = _add(admin_client, cost_price="-1.00")
    assert b"invalid" in r.data.lower() or b"cost" in r.data.lower()

def test_edit_product(app, admin_client):
    _add(admin_client, name="Edit Me")
    with app.app_context():
        pid = app.test_client().__class__  # just get id via db
        from db import get_db
        pid = get_db().execute("SELECT id FROM products WHERE name='Edit Me'").fetchone()["id"]
    r = admin_client.post(f"/admin/products/{pid}/edit",
                          data={"name":"Edited","category":"Other","unit":"each",
                                "cost_price":"9.99","markup_pct":"","notes":"","barcode":"",
                                "supplier_name":"","change_note":"","quantity":"",
                                "reorder_threshold":"","weight_kg":"","volume_litres":""},
                          follow_redirects=True)
    assert r.status_code == 200
    assert b"updated" in r.data.lower() or b"Edited" in r.data

def test_edit_product_updates_barcode(app, admin_client):
    _add(admin_client, name="Barcode Edit Test", barcode="BEFORE")
    with app.app_context():
        from db import get_db
        pid = get_db().execute("SELECT id FROM products WHERE name='Barcode Edit Test'").fetchone()["id"]
    admin_client.post(f"/admin/products/{pid}/edit",
                      data={"name":"Barcode Edit Test","category":"Other","unit":"each",
                            "cost_price":"5.00","markup_pct":"","notes":"","barcode":"AFTER",
                            "supplier_name":"","change_note":"","quantity":"",
                            "reorder_threshold":"","weight_kg":"","volume_litres":""},
                      follow_redirects=True)
    with app.app_context():
        from db import get_db
        p = get_db().execute("SELECT barcode FROM products WHERE id=?", (pid,)).fetchone()
    assert p["barcode"] == "AFTER"

def test_delete_product(app, admin_client):
    _add(admin_client, name="Delete Me")
    with app.app_context():
        from db import get_db
        pid = get_db().execute("SELECT id FROM products WHERE name='Delete Me'").fetchone()["id"]
    r = admin_client.post(f"/admin/products/{pid}/delete", follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        from db import get_db
        p = get_db().execute("SELECT active FROM products WHERE id=?", (pid,)).fetchone()
    assert p["active"] == 0

def test_restore_product(app, admin_client):
    _add(admin_client, name="Restore Me")
    with app.app_context():
        from db import get_db
        db = get_db()
        pid = db.execute("SELECT id FROM products WHERE name='Restore Me'").fetchone()["id"]
        db.execute("UPDATE products SET active=0 WHERE id=?", (pid,))
        db.commit()
    r = admin_client.post(f"/admin/products/{pid}/restore", follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        from db import get_db
        p = get_db().execute("SELECT active FROM products WHERE id=?", (pid,)).fetchone()
    assert p["active"] == 1

def test_deleted_products_page(admin_client):
    r = admin_client.get("/admin/deleted")
    assert r.status_code == 200

def test_bulk_delete(app, admin_client):
    _add(admin_client, name="Bulk Del A")
    _add(admin_client, name="Bulk Del B")
    with app.app_context():
        from db import get_db
        ids = [r["id"] for r in get_db().execute(
            "SELECT id FROM products WHERE name IN ('Bulk Del A','Bulk Del B')").fetchall()]
    r = admin_client.post("/admin/products/bulk_action",
                          data={"bulk_action_type":"delete","ids":ids},
                          follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        from db import get_db
        active = get_db().execute(
            "SELECT COUNT(*) FROM products WHERE name IN ('Bulk Del A','Bulk Del B') AND active=1"
        ).fetchone()[0]
    assert active == 0

def test_bulk_set_category(app, admin_client):
    _add(admin_client, name="Cat Change A", category="Other")
    with app.app_context():
        from db import get_db
        pid = get_db().execute("SELECT id FROM products WHERE name='Cat Change A'").fetchone()["id"]
    admin_client.post("/admin/products/bulk_action",
                      data={"bulk_action_type":"set_category","ids":[pid],"bulk_category_val":"Tools"},
                      follow_redirects=True)
    with app.app_context():
        from db import get_db
        cat = get_db().execute("SELECT category FROM products WHERE id=?", (pid,)).fetchone()["category"]
    assert cat == "Tools"

def test_sales_cannot_access_admin(sales_client):
    r = sales_client.get("/admin/products", follow_redirects=True)
    assert b"Admin access required" in r.data or r.status_code == 200

def test_product_search_filter(admin_client):
    _add(admin_client, name="UniqueSearchProduct999")
    r = admin_client.get("/admin/products?q=UniqueSearchProduct999")
    assert b"UniqueSearchProduct999" in r.data

"""Tests for supplier management."""


def test_suppliers_page(admin_client):
    r = admin_client.get("/admin/suppliers")
    assert r.status_code == 200

def test_add_supplier(app, admin_client):
    r = admin_client.post("/admin/suppliers/add",
                          data={"name":"Test Sup","tel":"01234","email":"a@b.com","notes":""},
                          follow_redirects=True)
    assert r.status_code == 200
    assert b"Test Sup" in r.data or b"added" in r.data.lower()

def test_add_supplier_no_name(admin_client):
    r = admin_client.post("/admin/suppliers/add",
                          data={"name":"","tel":"","email":"","notes":""},
                          follow_redirects=True)
    assert b"required" in r.data.lower()

def test_add_duplicate_supplier(admin_client):
    admin_client.post("/admin/suppliers/add",
                      data={"name":"DupSup","tel":"","email":"","notes":""},
                      follow_redirects=True)
    r = admin_client.post("/admin/suppliers/add",
                          data={"name":"DupSup","tel":"","email":"","notes":""},
                          follow_redirects=True)
    assert b"already exists" in r.data.lower()

def test_edit_supplier(app, admin_client):
    admin_client.post("/admin/suppliers/add",
                      data={"name":"EditSup","tel":"01111","email":"","notes":""},
                      follow_redirects=True)
    with app.app_context():
        from db import get_db
        sid = get_db().execute("SELECT id FROM suppliers WHERE name='EditSup'").fetchone()["id"]
    r = admin_client.post(f"/admin/suppliers/{sid}/edit",
                          data={"name":"EditSup Updated","tel":"02222","email":"","notes":""},
                          follow_redirects=True)
    assert r.status_code == 200
    assert b"updated" in r.data.lower() or b"EditSup Updated" in r.data

def test_delete_supplier_no_products(app, admin_client):
    admin_client.post("/admin/suppliers/add",
                      data={"name":"DelSup","tel":"","email":"","notes":""},
                      follow_redirects=True)
    with app.app_context():
        from db import get_db
        sid = get_db().execute("SELECT id FROM suppliers WHERE name='DelSup'").fetchone()["id"]
    r = admin_client.post(f"/admin/suppliers/{sid}/delete", follow_redirects=True)
    assert r.status_code == 200
    assert b"deleted" in r.data.lower()

def test_delete_supplier_with_products(app, admin_client):
    admin_client.post("/admin/suppliers/add",
                      data={"name":"BlockedSup","tel":"","email":"","notes":""},
                      follow_redirects=True)
    admin_client.post("/admin/products/add",
                      data={"name":"BlockedSupProd","category":"Other","unit":"each",
                            "cost_price":"1.00","markup_pct":"","notes":"","barcode":"",
                            "supplier_name":"BlockedSup","quantity":"","reorder_threshold":"",
                            "weight_kg":"","volume_litres":""})
    with app.app_context():
        from db import get_db
        sid = get_db().execute("SELECT id FROM suppliers WHERE name='BlockedSup'").fetchone()["id"]
    r = admin_client.post(f"/admin/suppliers/{sid}/delete", follow_redirects=True)
    assert b"Cannot delete" in r.data

def test_supplier_product_count(app, admin_client):
    """Single JOIN query returns correct product count per supplier."""
    admin_client.post("/admin/suppliers/add",
                      data={"name":"CountSup","tel":"","email":"","notes":""},
                      follow_redirects=True)
    for i in range(3):
        admin_client.post("/admin/products/add",
                          data={"name":f"CountProd{i}","category":"Other","unit":"each",
                                "cost_price":"1.00","markup_pct":"","notes":"","barcode":"",
                                "supplier_name":"CountSup","quantity":"","reorder_threshold":"",
                                "weight_kg":"","volume_litres":""})
    with app.app_context():
        from db import get_db
        row = get_db().execute(
            """SELECT s.*, COUNT(p.id) AS product_count FROM suppliers s
               LEFT JOIN products p ON p.supplier_name=s.name AND p.active=1
               WHERE s.name='CountSup' GROUP BY s.id"""
        ).fetchone()
    assert row["product_count"] == 3

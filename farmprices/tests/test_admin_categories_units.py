"""Tests for category and unit management via API endpoints."""
import json


def _post(c, url, data):
    return c.post(url, data=json.dumps(data), content_type="application/json",
                  follow_redirects=True)


def test_categories_page(admin_client):
    r = admin_client.get("/admin/categories")
    assert r.status_code == 200

def test_add_category(admin_client):
    r = _post(admin_client, "/api/categories/add", {"name": "TestCat99"})
    assert r.status_code == 200
    assert json.loads(r.data)["ok"] is True

def test_add_duplicate_category(admin_client):
    _post(admin_client, "/api/categories/add", {"name": "DupCat"})
    r = _post(admin_client, "/api/categories/add", {"name": "DupCat"})
    assert r.status_code == 409

def test_add_category_no_name(admin_client):
    r = _post(admin_client, "/api/categories/add", {"name": ""})
    assert r.status_code == 400

def test_delete_category_in_use(app, admin_client):
    """Cannot delete a category that has active products."""
    _post(admin_client, "/api/categories/add", {"name": "InUseCat"})
    admin_client.post("/admin/products/add",
                      data={"name":"InUseProd","category":"InUseCat","unit":"each",
                            "cost_price":"1.00","markup_pct":"","notes":"","barcode":"",
                            "supplier_name":"","quantity":"","reorder_threshold":"",
                            "weight_kg":"","volume_litres":""})
    r = _post(admin_client, "/api/categories/delete", {"name": "InUseCat"})
    assert r.status_code == 409

def test_delete_empty_category(admin_client):
    _post(admin_client, "/api/categories/add", {"name": "EmptyCat"})
    r = _post(admin_client, "/api/categories/delete", {"name": "EmptyCat"})
    assert json.loads(r.data)["ok"] is True

def test_add_unit(admin_client):
    r = _post(admin_client, "/api/units/add", {"name": "tonne"})
    assert r.status_code == 200
    assert json.loads(r.data)["ok"] is True

def test_add_duplicate_unit(admin_client):
    _post(admin_client, "/api/units/add", {"name": "dupunit"})
    r = _post(admin_client, "/api/units/add", {"name": "dupunit"})
    assert r.status_code == 409

def test_delete_unit_in_use(app, admin_client):
    _post(admin_client, "/api/units/add", {"name": "specialunit"})
    admin_client.post("/admin/products/add",
                      data={"name":"UnitUseProd","category":"Other","unit":"specialunit",
                            "cost_price":"1.00","markup_pct":"","notes":"","barcode":"",
                            "supplier_name":"","quantity":"","reorder_threshold":"",
                            "weight_kg":"","volume_litres":""})
    r = _post(admin_client, "/api/units/delete", {"name": "specialunit"})
    assert r.status_code == 409

def test_delete_unused_unit(admin_client):
    _post(admin_client, "/api/units/add", {"name": "unusedunit77"})
    r = _post(admin_client, "/api/units/delete", {"name": "unusedunit77"})
    assert json.loads(r.data)["ok"] is True

def test_categories_require_login(client):
    r = _post(client, "/api/categories/add", {"name": "X"})
    assert r.status_code in (302, 401, 403) or b"log in" in r.data.lower()

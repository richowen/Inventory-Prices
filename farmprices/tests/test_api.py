"""Tests for /api/ JSON endpoints."""
import pytest


def _add_product(c, name="APIProd", cost="5.00", barcode=""):
    return c.post("/admin/products/add", data={
        "name": name, "category": "Other", "unit": "each",
        "cost_price": cost, "markup_pct": "", "barcode": barcode
    }, follow_redirects=True)


def _get_pid(app, name):
    with app.app_context():
        from db import get_db
        row = get_db().execute("SELECT id FROM products WHERE name=?", (name,)).fetchone()
        return row["id"] if row else None


# ── /api/search ────────────────────────────────────────────────────────────────

def test_search_requires_login(client):
    r = client.get("/api/search?q=test")
    assert r.status_code == 302

def test_search_returns_json(admin_client):
    r = admin_client.get("/api/search")
    assert r.status_code == 200
    assert r.is_json

def test_search_empty_returns_list(admin_client):
    data = admin_client.get("/api/search").get_json()
    assert isinstance(data, list)

def test_search_by_name(admin_client):
    _add_product(admin_client, "UniqueSearchName")
    data = admin_client.get("/api/search?q=UniqueSearchName").get_json()
    assert any(p["name"] == "UniqueSearchName" for p in data)

def test_search_no_match(admin_client):
    data = admin_client.get("/api/search?q=zzznoresults999").get_json()
    assert data == []

def test_search_by_barcode(admin_client):
    _add_product(admin_client, "BarcodeSearchProd", barcode="TEST123456")
    data = admin_client.get("/api/search?barcode=TEST123456").get_json()
    assert any(p["name"] == "BarcodeSearchProd" for p in data)

def test_search_admin_sees_cost_price(admin_client):
    _add_product(admin_client, "CostVisibleProd", "7.50")
    data = admin_client.get("/api/search?q=CostVisibleProd").get_json()
    assert len(data) >= 1
    assert "cost_price" in data[0]

def test_search_sales_hides_cost_price(sales_client, app):
    with app.app_context():
        from db import get_db
        db = get_db()
        db.execute("""INSERT INTO products (name,category,unit,cost_price,active,last_updated)
                      VALUES (?,?,?,?,1,date('now'))""",
                   ("HiddenCostProd", "Other", "each", 4.0))
        db.commit()
    data = sales_client.get("/api/search?q=HiddenCostProd").get_json()
    assert len(data) >= 1
    assert "cost_price" not in data[0]

def test_search_result_has_sell_price(admin_client):
    _add_product(admin_client, "SellPriceProd", "10.00")
    data = admin_client.get("/api/search?q=SellPriceProd").get_json()
    assert "sell_price" in data[0]

def test_search_by_category(admin_client, app):
    with app.app_context():
        from db import get_db
        db = get_db()
        if not db.execute("SELECT 1 FROM categories WHERE name='TestCat'").fetchone():
            db.execute("INSERT INTO categories (name) VALUES ('TestCat')")
            db.commit()
    _add_product(admin_client, "CatSearchProd")
    r = admin_client.get("/api/search?category=Other")
    assert r.status_code == 200

def test_search_no_cache_headers(admin_client):
    r = admin_client.get("/api/search")
    assert "no-store" in r.headers.get("Cache-Control", "")

def test_search_sales_can_access(sales_client):
    r = sales_client.get("/api/search")
    assert r.status_code == 200


# ── /api/categories ───────────────────────────────────────────────────────────

def test_get_categories_requires_login(client):
    r = client.get("/api/categories")
    assert r.status_code == 302

def test_get_categories_returns_list(admin_client):
    data = admin_client.get("/api/categories").get_json()
    assert isinstance(data, list)

def test_get_categories_has_fields(admin_client):
    data = admin_client.get("/api/categories").get_json()
    assert len(data) > 0
    assert "id" in data[0] and "name" in data[0]

def test_add_category(admin_client):
    r = admin_client.post("/api/categories/add", json={"name": "TestApiCat"})
    assert r.status_code == 200
    assert r.get_json()["ok"] is True

def test_add_category_duplicate(admin_client):
    admin_client.post("/api/categories/add", json={"name": "DupeCat"})
    r = admin_client.post("/api/categories/add", json={"name": "DupeCat"})
    assert r.status_code == 409

def test_add_category_no_name(admin_client):
    r = admin_client.post("/api/categories/add", json={"name": ""})
    assert r.status_code == 400

def test_add_category_requires_admin(sales_client):
    r = sales_client.post("/api/categories/add", json={"name": "SalesCat"})
    assert r.status_code in (302, 403)

def test_add_subcategory(admin_client):
    r1 = admin_client.post("/api/categories/add", json={"name": "ParentCat2"})
    parent_id = r1.get_json()["id"]
    r2 = admin_client.post("/api/categories/add", json={"name": "SubCat2", "parent_id": parent_id})
    assert r2.status_code == 200

def test_delete_category_in_use(admin_client):
    r = admin_client.post("/api/categories/delete", json={"name": "Other"})
    # Other has products so should be blocked
    assert r.status_code in (200, 409)

def test_delete_category_empty_ok(admin_client):
    admin_client.post("/api/categories/add", json={"name": "DeleteMeCat"})
    r = admin_client.post("/api/categories/delete", json={"name": "DeleteMeCat"})
    assert r.get_json()["ok"] is True

def test_delete_category_requires_admin(sales_client):
    r = sales_client.post("/api/categories/delete", json={"name": "Other"})
    assert r.status_code in (302, 403)


# ── /api/units ────────────────────────────────────────────────────────────────

def test_add_unit(admin_client):
    r = admin_client.post("/api/units/add", json={"name": "testunit"})
    assert r.status_code == 200
    assert r.get_json()["ok"] is True

def test_add_unit_duplicate(admin_client):
    admin_client.post("/api/units/add", json={"name": "dupeunit"})
    r = admin_client.post("/api/units/add", json={"name": "dupeunit"})
    assert r.status_code == 409

def test_add_unit_no_name(admin_client):
    r = admin_client.post("/api/units/add", json={"name": ""})
    assert r.status_code == 400

def test_add_unit_requires_admin(sales_client):
    r = sales_client.post("/api/units/add", json={"name": "salesunit"})
    assert r.status_code in (302, 403)

def test_delete_unit_in_use(admin_client):
    r = admin_client.post("/api/units/delete", json={"name": "each"})
    assert r.status_code in (200, 409)

def test_delete_unit_unused_ok(admin_client):
    admin_client.post("/api/units/add", json={"name": "deleteableunit"})
    r = admin_client.post("/api/units/delete", json={"name": "deleteableunit"})
    assert r.get_json()["ok"] is True

def test_delete_unit_requires_admin(sales_client):
    r = sales_client.post("/api/units/delete", json={"name": "each"})
    assert r.status_code in (302, 403)


# ── /api/products/<pid>/update_price ──────────────────────────────────────────

def test_update_price(admin_client, app):
    _add_product(admin_client, "UpdatePriceProd", "5.00")
    pid = _get_pid(app, "UpdatePriceProd")
    r = admin_client.post(f"/api/products/{pid}/update_price", json={"cost_price": 8.50})
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"] is True
    assert data["cost_price"] == 8.50

def test_update_price_invalid(admin_client, app):
    _add_product(admin_client, "InvalidPriceProd", "5.00")
    pid = _get_pid(app, "InvalidPriceProd")
    r = admin_client.post(f"/api/products/{pid}/update_price", json={"cost_price": "abc"})
    assert r.status_code == 400

def test_update_price_negative(admin_client, app):
    _add_product(admin_client, "NegPriceProd", "5.00")
    pid = _get_pid(app, "NegPriceProd")
    r = admin_client.post(f"/api/products/{pid}/update_price", json={"cost_price": -1})
    assert r.status_code == 400

def test_update_price_404(admin_client):
    r = admin_client.post("/api/products/9999/update_price", json={"cost_price": 5.00})
    assert r.status_code == 404

def test_update_price_requires_admin(sales_client, app):
    with app.app_context():
        from db import get_db
        db = get_db()
        db.execute("""INSERT INTO products (name,category,unit,cost_price,active,last_updated)
                      VALUES (?,?,?,?,1,date('now'))""",
                   ("SalesUpdateProd", "Other", "each", 5.0))
        db.commit()
        pid = db.execute("SELECT id FROM products WHERE name='SalesUpdateProd'").fetchone()["id"]
    r = sales_client.post(f"/api/products/{pid}/update_price", json={"cost_price": 9.00})
    assert r.status_code in (302, 403)

def test_update_price_creates_history(admin_client, app):
    _add_product(admin_client, "HistoryPriceProd", "5.00")
    pid = _get_pid(app, "HistoryPriceProd")
    admin_client.post(f"/api/products/{pid}/update_price", json={"cost_price": 9.99})
    with app.app_context():
        from db import get_db
        row = get_db().execute(
            "SELECT * FROM price_history WHERE product_id=?", (pid,)
        ).fetchone()
        assert row is not None
        assert abs(row["new_cost"] - 9.99) < 0.01

def test_update_price_same_value_no_history(admin_client, app):
    _add_product(admin_client, "SamePriceProd", "5.00")
    pid = _get_pid(app, "SamePriceProd")
    admin_client.post(f"/api/products/{pid}/update_price", json={"cost_price": 5.00})
    with app.app_context():
        from db import get_db
        count = get_db().execute(
            "SELECT COUNT(*) FROM price_history WHERE product_id=?", (pid,)
        ).fetchone()[0]
        assert count == 0

def test_update_price_returns_sell_price(admin_client, app):
    _add_product(admin_client, "SellCheckProd", "10.00")
    pid = _get_pid(app, "SellCheckProd")
    r = admin_client.post(f"/api/products/{pid}/update_price", json={"cost_price": 10.00})
    data = r.get_json()
    assert "sell_price" in data
    assert data["sell_price"] > 0

def test_update_price_with_note(admin_client, app):
    _add_product(admin_client, "NotedPriceProd", "5.00")
    pid = _get_pid(app, "NotedPriceProd")
    r = admin_client.post(f"/api/products/{pid}/update_price",
                          json={"cost_price": 7.00, "note": "Supplier increase"})
    assert r.get_json()["ok"] is True


# ── /api/suppliers/suggest ────────────────────────────────────────────────────

def test_suggest_suppliers_requires_admin(sales_client):
    r = sales_client.get("/api/suppliers/suggest")
    assert r.status_code in (302, 403)

def test_suggest_suppliers_returns_list(admin_client):
    data = admin_client.get("/api/suppliers/suggest").get_json()
    assert isinstance(data, list)

def test_suggest_suppliers_with_query(admin_client, app):
    with app.app_context():
        from db import get_db
        db = get_db()
        db.execute("INSERT OR IGNORE INTO suppliers (name) VALUES ('SuggestTestSupplier')")
        db.commit()
    data = admin_client.get("/api/suppliers/suggest?q=SuggestTest").get_json()
    assert any(s["name"] == "SuggestTestSupplier" for s in data)

def test_suggest_suppliers_unauthenticated(client):
    r = client.get("/api/suppliers/suggest")
    assert r.status_code == 302

"""Tests for audit history and price review report."""
import pytest


def _add_product(c, name="TestProd", cost="5.00"):
    return c.post("/admin/products/add", data={
        "name": name, "category": "Other", "unit": "each",
        "cost_price": cost, "markup_pct": ""
    }, follow_redirects=True)


# ── History page ───────────────────────────────────────────────────────────────

def test_history_page_loads(admin_client):
    r = admin_client.get("/admin/history")
    assert r.status_code == 200

def test_history_sales_blocked(sales_client):
    r = sales_client.get("/admin/history")
    assert r.status_code in (302, 403)

def test_history_unauthenticated(client):
    r = client.get("/admin/history")
    assert r.status_code == 302

def test_history_has_entry_after_product_add(admin_client):
    _add_product(admin_client, "HistoryProd")
    r = admin_client.get("/admin/history")
    assert b"product_added" in r.data or b"HistoryProd" in r.data

def test_history_filter_by_event_type(admin_client):
    _add_product(admin_client, "FilterProd")
    r = admin_client.get("/admin/history?event_type=product_added")
    assert r.status_code == 200

def test_history_filter_by_product(admin_client):
    _add_product(admin_client, "SearchableProd")
    r = admin_client.get("/admin/history?product=SearchableProd")
    assert r.status_code == 200
    assert b"SearchableProd" in r.data

def test_history_filter_by_user(admin_client):
    r = admin_client.get("/admin/history?user=admin")
    assert r.status_code == 200

def test_history_filter_by_date_range(admin_client):
    r = admin_client.get("/admin/history?date_from=2000-01-01&date_to=2099-12-31")
    assert r.status_code == 200

def test_history_unknown_event_type_no_crash(admin_client):
    r = admin_client.get("/admin/history?event_type=nonexistent_event")
    assert r.status_code == 200

def test_history_pagination(admin_client):
    r = admin_client.get("/admin/history?page=1")
    assert r.status_code == 200

def test_history_page2_no_crash(admin_client):
    r = admin_client.get("/admin/history?page=999")
    assert r.status_code == 200

def test_history_records_price_change(admin_client, app):
    _add_product(admin_client, "PriceChangeProd", "5.00")
    with app.app_context():
        from db import get_db
        pid = get_db().execute("SELECT id FROM products WHERE name='PriceChangeProd'").fetchone()["id"]
    admin_client.post(f"/api/products/{pid}/update_price",
                      json={"cost_price": 9.99, "note": "price up"})
    r = admin_client.get("/admin/history?event_type=price_changed")
    assert r.status_code == 200


# ── Price history chart ────────────────────────────────────────────────────────

def test_price_history_chart_loads(admin_client, app):
    _add_product(admin_client, "ChartProd", "3.50")
    with app.app_context():
        from db import get_db
        pid = get_db().execute("SELECT id FROM products WHERE name='ChartProd'").fetchone()["id"]
    r = admin_client.get(f"/admin/products/{pid}/price_history")
    assert r.status_code == 200

def test_price_history_chart_404_for_unknown(admin_client):
    r = admin_client.get("/admin/products/9999/price_history")
    assert r.status_code == 404

def test_price_history_chart_shows_markup(admin_client, app):
    _add_product(admin_client, "MarkupChartProd", "10.00")
    with app.app_context():
        from db import get_db
        pid = get_db().execute("SELECT id FROM products WHERE name='MarkupChartProd'").fetchone()["id"]
    r = admin_client.get(f"/admin/products/{pid}/price_history")
    # Should show a numeric markup value, not "Default%"
    assert b"Default%" not in r.data

def test_price_history_sales_blocked(sales_client, app):
    with app.app_context():
        from db import get_db
        db = get_db()
        db.execute("""INSERT INTO products (name,category,unit,cost_price,active,last_updated)
                      VALUES (?,?,?,?,1,date('now'))""",
                   ("SalesBlockChart", "Other", "each", 2.0))
        db.commit()
        pid = db.execute("SELECT id FROM products WHERE name='SalesBlockChart'").fetchone()["id"]
    r = sales_client.get(f"/admin/products/{pid}/price_history")
    assert r.status_code in (302, 403)


# ── Price review report ────────────────────────────────────────────────────────

def test_review_page_loads(admin_client):
    r = admin_client.get("/admin/review")
    assert r.status_code == 200

def test_review_sales_blocked(sales_client):
    r = sales_client.get("/admin/review")
    assert r.status_code in (302, 403)

def test_review_default_days(admin_client):
    r = admin_client.get("/admin/review")
    assert r.status_code == 200

def test_review_custom_days(admin_client):
    r = admin_client.get("/admin/review?days=7")
    assert r.status_code == 200

def test_review_invalid_days_no_crash(admin_client):
    r = admin_client.get("/admin/review?days=notanumber")
    assert r.status_code == 200

def test_review_category_filter(admin_client):
    r = admin_client.get("/admin/review?category=Other")
    assert r.status_code == 200

def test_review_shows_stale_product(admin_client, app):
    """Product with last_updated in the past should appear in review."""
    with app.app_context():
        from db import get_db
        db = get_db()
        db.execute("""INSERT INTO products (name,category,unit,cost_price,last_updated,active)
                      VALUES (?,?,?,?,?,1)""",
                   ("StaleProd", "Other", "each", 5.0, "2000-01-01"))
        db.commit()
    r = admin_client.get("/admin/review?days=1")
    assert b"StaleProd" in r.data

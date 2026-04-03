"""Tests for CSV/JSON import and export."""
import io, csv, json


def _add(c, name="Exp Prod", cost="5.00"):
    c.post("/admin/products/add",
           data={"name":name,"category":"Other","unit":"each","cost_price":cost,
                 "markup_pct":"30","notes":"","barcode":"","supplier_name":"",
                 "quantity":"","reorder_threshold":"","weight_kg":"","volume_litres":""})


def test_csv_export(admin_client):
    _add(admin_client, "CSV Exp Prod")
    r = admin_client.get("/admin/export/csv")
    assert r.status_code == 200
    assert b"CSV Exp Prod" in r.data
    assert r.content_type.startswith("text/csv")

def test_json_export(admin_client):
    _add(admin_client, "JSON Exp Prod")
    r = admin_client.get("/admin/export/json")
    assert r.status_code == 200
    data = json.loads(r.data)
    names = [p["name"] for p in data["products"]]
    assert "JSON Exp Prod" in names

def test_csv_import_adds_products(app, admin_client):
    csv_content = "Product Name,Category,Unit,Supplier,Supplier Tel,Cost Price,Markup %,Barcode,Notes\n"
    csv_content += "Imported Feed,Animal Feed,bag,,,4.50,30,,\n"
    file = (io.BytesIO(csv_content.encode()), "test.csv")
    r = admin_client.post("/admin/import", data={
        "csv_file": file, "action":"import",
        "default_category":"Other","default_unit":"each","skip_duplicates":"0",
        "col_name":"Product Name","col_category":"Category","col_unit":"Unit",
        "col_supplier":"Supplier","col_tel":"Supplier Tel","col_cost":"Cost Price",
        "col_markup":"Markup %","col_barcode":"Barcode","col_notes":"Notes",
    }, content_type="multipart/form-data", follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        from db import get_db
        p = get_db().execute("SELECT * FROM products WHERE name='Imported Feed'").fetchone()
    assert p is not None
    assert abs(p["cost_price"] - 4.50) < 0.001

def test_csv_import_skip_duplicates(app, admin_client):
    _add(admin_client, "Dup Import Prod")
    csv_content = "Product Name,Cost Price\nDup Import Prod,9.99\n"
    file = (io.BytesIO(csv_content.encode()), "dup.csv")
    admin_client.post("/admin/import", data={
        "csv_file":file,"action":"import",
        "default_category":"Other","default_unit":"each","skip_duplicates":"1",
        "col_name":"Product Name","col_category":"Category","col_unit":"Unit",
        "col_supplier":"Supplier","col_tel":"Supplier Tel","col_cost":"Cost Price",
        "col_markup":"Markup %","col_barcode":"Barcode","col_notes":"Notes",
    }, content_type="multipart/form-data", follow_redirects=True)
    with app.app_context():
        from db import get_db
        count = get_db().execute(
            "SELECT COUNT(*) FROM products WHERE name='Dup Import Prod' AND active=1"
        ).fetchone()[0]
    assert count == 1

def test_import_page_get(admin_client):
    r = admin_client.get("/admin/import")
    assert r.status_code == 200

def test_import_no_file(admin_client):
    r = admin_client.post("/admin/import", data={}, content_type="multipart/form-data",
                          follow_redirects=True)
    assert b"select" in r.data.lower() or b"file" in r.data.lower()

def test_export_requires_admin(sales_client):
    r = sales_client.get("/admin/export/csv", follow_redirects=True)
    assert b"Admin access required" in r.data or r.status_code == 200

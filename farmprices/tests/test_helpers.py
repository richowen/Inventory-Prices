"""Tests for helpers.py: pricing, rounding, cat_tree, settings."""
import pytest
from helpers import apply_rounding, sell_price, cat_tree, get_setting, product_snapshot


def test_apply_rounding_none():
    assert apply_rounding(5.678, "none") == 5.68

def test_apply_rounding_005():
    assert apply_rounding(5.63, "0.05") == 5.65
    assert apply_rounding(5.61, "0.05") == 5.60

def test_apply_rounding_010():
    assert apply_rounding(5.64, "0.10") == 5.60
    assert apply_rounding(5.65, "0.10") == 5.70

def test_apply_rounding_099():
    assert apply_rounding(5.10, "0.99") == 5.99
    assert apply_rounding(0.50, "0.99") == 0.99
    assert apply_rounding(0.0,  "0.99") == 0.0

def test_sell_price_with_explicit_markup():
    assert sell_price(10.0, 50.0, 30.0, "none") == 15.0

def test_sell_price_uses_default_when_none():
    assert sell_price(10.0, None, 30.0, "none") == 13.0

def test_sell_price_zero_cost():
    assert sell_price(0.0, 50.0, 30.0, "none") == 0.0

def test_cat_tree(app):
    with app.app_context():
        from db import get_db
        db = get_db()
        tree = cat_tree(db)
    assert isinstance(tree, list)
    assert all("subcategories" in p for p in tree)
    names = [p["name"] for p in tree]
    assert "Animal Feed" in names

def test_get_setting(app):
    with app.app_context():
        val = get_setting("shop_name")
    assert isinstance(val, str)
    assert len(val) > 0

def test_get_setting_default(app):
    with app.app_context():
        val = get_setting("nonexistent_key_xyz", "fallback")
    assert val == "fallback"

def test_product_snapshot():
    class FakeRow(dict):
        def __getitem__(self, k): return super().__getitem__(k)
    row = FakeRow({
        "name":"Test","category":"Other","unit":"each",
        "supplier_name":"X","supplier_tel":"","cost_price":1.0,
        "markup_pct":None,"notes":"","barcode":"","quantity":None,
        "reorder_threshold":None,"last_updated":"2025-01-01"
    })
    snap = product_snapshot(row)
    assert snap["name"] == "Test"
    assert "cost_price" in snap

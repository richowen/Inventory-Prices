"""Tests for settings page."""


def test_settings_page(admin_client):
    r = admin_client.get("/admin/settings")
    assert r.status_code == 200

def test_save_settings(admin_client):
    r = admin_client.post("/admin/settings",
                          data={"action":"save_settings","shop_name":"Test Shop",
                                "default_markup":"35","price_rounding":"none",
                                "currency":"£","review_days":"30"},
                          follow_redirects=True)
    assert r.status_code == 200
    assert b"saved" in r.data.lower()

def test_invalid_markup_rejected(admin_client):
    r = admin_client.post("/admin/settings",
                          data={"action":"save_settings","shop_name":"X",
                                "default_markup":"abc","price_rounding":"none",
                                "currency":"£","review_days":"30"},
                          follow_redirects=True)
    assert b"non-negative" in r.data.lower() or b"invalid" in r.data.lower()

def test_negative_markup_rejected(admin_client):
    r = admin_client.post("/admin/settings",
                          data={"action":"save_settings","shop_name":"X",
                                "default_markup":"-5","price_rounding":"none",
                                "currency":"£","review_days":"30"},
                          follow_redirects=True)
    assert b"non-negative" in r.data.lower() or b"invalid" in r.data.lower()

def test_settings_persisted(app, admin_client):
    admin_client.post("/admin/settings",
                      data={"action":"save_settings","shop_name":"Persisted Shop",
                            "default_markup":"42","price_rounding":"none",
                            "currency":"€","review_days":"14"},
                      follow_redirects=True)
    with app.app_context():
        from helpers import get_setting
        assert get_setting("shop_name") == "Persisted Shop"
        assert get_setting("default_markup") == "42.0"
        assert get_setting("currency") == "€"
        assert get_setting("review_days") == "14"

def test_rounding_applied_to_sell_price():
    from helpers import sell_price
    assert sell_price(3.00, 30.0, 30.0, "0.99") == 3.99
    assert sell_price(3.00, 30.0, 30.0, "0.05") == 3.90

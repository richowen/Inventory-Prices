"""Tests for auth blueprint: login, logout, session."""
import pytest


def test_login_page_get(client):
    r = client.get("/login")
    assert r.status_code == 200
    assert b"Login" in r.data or b"login" in r.data

def test_login_success_admin(client):
    r = client.post("/login", data={"username":"admin","password":"testpass"},
                    follow_redirects=True)
    assert r.status_code == 200
    assert b"admin" in r.data.lower() or b"product" in r.data.lower()

def test_login_wrong_password(client):
    r = client.post("/login", data={"username":"admin","password":"wrong"},
                    follow_redirects=True)
    assert b"Incorrect" in r.data

def test_login_wrong_username(client):
    r = client.post("/login", data={"username":"nobody","password":"testpass"},
                    follow_redirects=True)
    assert b"Incorrect" in r.data

def test_login_empty_fields(client):
    r = client.post("/login", data={"username":"","password":""},
                    follow_redirects=True)
    assert b"required" in r.data.lower()

def test_login_inactive_user(app, client):
    import bcrypt
    with app.app_context():
        from db import get_db
        db = get_db()
        pw = bcrypt.hashpw(b"pass123", bcrypt.gensalt()).decode()
        db.execute("INSERT INTO users (username,password_hash,role,active) VALUES (?,?,?,0)",
                   ("inactive1", pw, "sales"))
        db.commit()
    r = client.post("/login", data={"username":"inactive1","password":"pass123"},
                    follow_redirects=True)
    assert b"Incorrect" in r.data

def test_logout(admin_client):
    r = admin_client.get("/logout", follow_redirects=True)
    assert r.status_code == 200
    assert b"logged out" in r.data.lower()

def test_protected_redirects_to_login(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in r.headers["Location"]

def test_admin_area_redirects_to_login(client):
    r = client.get("/admin/products", follow_redirects=False)
    assert r.status_code == 302

def test_session_set_after_login(client):
    with client.session_transaction() as sess:
        assert "user_id" not in sess
    client.post("/login", data={"username":"admin","password":"testpass"})
    with client.session_transaction() as sess:
        assert sess.get("user_id") is not None
        assert sess.get("role") == "admin"

def test_session_cleared_after_logout(admin_client):
    admin_client.get("/logout")
    with admin_client.session_transaction() as sess:
        assert "user_id" not in sess

def test_already_logged_in_redirects(admin_client):
    r = admin_client.get("/login", follow_redirects=False)
    assert r.status_code == 302

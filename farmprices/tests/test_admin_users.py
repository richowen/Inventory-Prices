"""Tests for user management."""
import bcrypt


def _add_user(c, username, password="pass1234", role="sales"):
    return c.post("/admin/users/add",
                  data={"username":username,"password":password,"role":role},
                  follow_redirects=True)


def test_users_page(admin_client):
    r = admin_client.get("/admin/users")
    assert r.status_code == 200

def test_add_user(admin_client):
    r = _add_user(admin_client, "newuser1")
    assert r.status_code == 200
    assert b"created" in r.data.lower() or b"newuser1" in r.data

def test_add_duplicate_user(admin_client):
    _add_user(admin_client, "dupuser")
    r = _add_user(admin_client, "dupuser")
    assert b"already exists" in r.data.lower()

def test_add_user_short_password(admin_client):
    r = _add_user(admin_client, "shortpwuser", password="abc")
    assert b"6 characters" in r.data or b"least 6" in r.data.lower()

def test_add_user_missing_fields(admin_client):
    r = admin_client.post("/admin/users/add", data={"username":"","password":"","role":"sales"},
                          follow_redirects=True)
    assert b"required" in r.data.lower()

def test_toggle_active(app, admin_client):
    _add_user(admin_client, "toggleuser")
    with app.app_context():
        from db import get_db
        uid = get_db().execute("SELECT id FROM users WHERE username='toggleuser'").fetchone()["id"]
    r = admin_client.post(f"/admin/users/{uid}/edit",
                          data={"action":"toggle_active"}, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        from db import get_db
        active = get_db().execute("SELECT active FROM users WHERE id=?", (uid,)).fetchone()["active"]
    assert active == 0

def test_change_role(app, admin_client):
    _add_user(admin_client, "roleuser", role="sales")
    with app.app_context():
        from db import get_db
        uid = get_db().execute("SELECT id FROM users WHERE username='roleuser'").fetchone()["id"]
    admin_client.post(f"/admin/users/{uid}/edit",
                      data={"action":"change_role","role":"admin"}, follow_redirects=True)
    with app.app_context():
        from db import get_db
        role = get_db().execute("SELECT role FROM users WHERE id=?", (uid,)).fetchone()["role"]
    assert role == "admin"

def test_reset_password(app, admin_client):
    _add_user(admin_client, "resetpwuser")
    with app.app_context():
        from db import get_db
        uid = get_db().execute("SELECT id FROM users WHERE username='resetpwuser'").fetchone()["id"]
    admin_client.post(f"/admin/users/{uid}/edit",
                      data={"action":"reset_password","new_password":"newpass99"},
                      follow_redirects=True)
    with app.app_context():
        from db import get_db
        row = get_db().execute("SELECT password_hash FROM users WHERE id=?", (uid,)).fetchone()
    assert bcrypt.checkpw(b"newpass99", row["password_hash"].encode())

def test_cannot_delete_self(app, admin_client):
    with admin_client.session_transaction() as sess:
        uid = sess["user_id"]
    r = admin_client.post(f"/admin/users/{uid}/delete", follow_redirects=True)
    assert b"cannot delete" in r.data.lower()

def test_delete_user(app, admin_client):
    _add_user(admin_client, "deleteuser")
    with app.app_context():
        from db import get_db
        uid = get_db().execute("SELECT id FROM users WHERE username='deleteuser'").fetchone()["id"]
    r = admin_client.post(f"/admin/users/{uid}/delete", follow_redirects=True)
    assert b"deleted" in r.data.lower()
    with app.app_context():
        from db import get_db
        u = get_db().execute("SELECT id FROM users WHERE username='deleteuser'").fetchone()
    assert u is None

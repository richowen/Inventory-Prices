"""Shared pytest fixtures."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import bcrypt
from app import create_app


def _make_config(db_path):
    class TestConfig:
        SECRET_KEY = "test-secret"
        TESTING = True
        WTF_CSRF_ENABLED = False
        RATELIMIT_ENABLED = False
        DB_PATH = db_path
        UPLOAD_FOLDER = "/tmp/farmprices_test_uploads"
        MAX_CONTENT_LENGTH = 4 * 1024 * 1024
        SESSION_COOKIE_HTTPONLY = True
        SESSION_COOKIE_SAMESITE = "Lax"
        PERMANENT_SESSION_LIFETIME = 28800
        RATELIMIT_STORAGE_URI = "memory://"
        RATELIMIT_DEFAULT = "9999 per minute"
        DEFAULT_PASSWORD = "testpass"
    return TestConfig


@pytest.fixture()
def app(tmp_path):
    db_file = str(tmp_path / "test.db")
    a = create_app(_make_config(db_file))
    yield a


@pytest.fixture()
def client(app):
    return app.test_client()


def _login(client, username, password):
    return client.post("/login", data={"username": username, "password": password},
                       follow_redirects=True)


@pytest.fixture()
def admin_client(client):
    _login(client, "admin", "testpass")
    return client


@pytest.fixture()
def sales_client(app, client):
    with app.app_context():
        from db import get_db
        pw = bcrypt.hashpw(b"salespass", bcrypt.gensalt()).decode()
        db = get_db()
        db.execute("INSERT OR IGNORE INTO users (username,password_hash,role) VALUES (?,?,?)",
                   ("sales1", pw, "sales"))
        db.commit()
    _login(client, "sales1", "salespass")
    return client

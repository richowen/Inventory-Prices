"""
Database helpers: connection management, schema creation, migration.
"""
import math
import sqlite3

from flask import current_app, g


# ── Connection management ─────────────────────────────────────────────────────

def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DB_PATH"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


def close_db(exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


# ── Schema ────────────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT    NOT NULL,
    role          TEXT    NOT NULL DEFAULT 'sales' CHECK(role IN ('admin','sales')),
    active        INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    last_login    TEXT
);

CREATE TABLE IF NOT EXISTS suppliers (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT NOT NULL UNIQUE,
    tel   TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS categories (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS units (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS products (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT    NOT NULL,
    category          TEXT    NOT NULL DEFAULT 'Other',
    unit              TEXT    NOT NULL DEFAULT 'each',
    supplier_name     TEXT    NOT NULL DEFAULT '',
    supplier_tel      TEXT    NOT NULL DEFAULT '',
    cost_price        REAL    NOT NULL DEFAULT 0.0,
    markup_pct        REAL,
    notes             TEXT    NOT NULL DEFAULT '',
    barcode           TEXT    NOT NULL DEFAULT '',
    quantity          REAL,
    reorder_threshold REAL,
    last_updated      TEXT    NOT NULL DEFAULT (date('now')),
    active            INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS price_history (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id    INTEGER NOT NULL REFERENCES products(id),
    product_name  TEXT    NOT NULL,
    old_cost      REAL    NOT NULL,
    new_cost      REAL    NOT NULL,
    changed_by    TEXT    NOT NULL DEFAULT '',
    notes         TEXT    NOT NULL DEFAULT '',
    changed_at    TEXT    NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS audit_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type   TEXT    NOT NULL,
    product_id   INTEGER,
    product_name TEXT    NOT NULL DEFAULT '',
    changed_by   TEXT    NOT NULL DEFAULT '',
    notes        TEXT    NOT NULL DEFAULT '',
    old_data     TEXT,
    new_data     TEXT,
    changed_at   TEXT    NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

INSERT OR IGNORE INTO settings (key, value) VALUES
    ('shop_name',      'Tenbury Farm Supplies'),
    ('default_markup', '30'),
    ('currency',       '£'),
    ('price_rounding', 'none'),
    ('review_days',    '30');

CREATE INDEX IF NOT EXISTS idx_products_active          ON products(active);
CREATE INDEX IF NOT EXISTS idx_products_active_category ON products(active, category);
CREATE INDEX IF NOT EXISTS idx_audit_log_changed_at     ON audit_log(changed_at DESC);
CREATE INDEX IF NOT EXISTS idx_price_history_product    ON price_history(product_id, changed_at DESC);
"""

_DEFAULT_CATS  = ['Animal Feed', 'Bedding', 'Fencing', 'Seeds',
                  'Fertiliser', 'Tools', 'Vet Supplies', 'Other']
_DEFAULT_UNITS = ['each', 'bag', 'kg', 'litre', 'roll', 'box',
                  'metre', 'pair', 'set', 'pack']


def init_db(app=None):
    """Create tables, seed defaults, run migrations.  Safe to call on every start."""
    import bcrypt as _bcrypt
    from config import Config

    db_path = (app.config["DB_PATH"] if app else Config.DB_PATH)
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript(_SCHEMA)

    # ── Seed categories & units ───────────────────────────────────────────────
    for c in _DEFAULT_CATS:
        db.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (c,))
    for u in _DEFAULT_UNITS:
        db.execute("INSERT OR IGNORE INTO units (name) VALUES (?)", (u,))

    # ── Migration: add new columns to products if they don't exist ────────────
    existing_cols = {row[1] for row in db.execute("PRAGMA table_info(products)")}
    for col, definition in [
        ("barcode",           "TEXT    NOT NULL DEFAULT ''"),
        ("quantity",          "REAL"),
        ("reorder_threshold", "REAL"),
    ]:
        if col not in existing_cols:
            db.execute(f"ALTER TABLE products ADD COLUMN {col} {definition}")

    # Barcode index created here (after migration) so it works on existing DBs
    # that just had the column added above as well as fresh installs.
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_products_barcode "
        "ON products(barcode) WHERE barcode != ''"
    )

    # ── Migration: users table — migrate single admin password ────────────────
    user_count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if user_count == 0:
        default_pw = (app.config["DEFAULT_PASSWORD"] if app else Config.DEFAULT_PASSWORD)
        # Try to pull existing password hash from settings
        row = db.execute(
            "SELECT value FROM settings WHERE key='admin_password'"
        ).fetchone()

        if row and len(row["value"]) == 64:
            # Old SHA-256 hash present — can't convert, use default and force change
            pw_hash = _bcrypt.hashpw(default_pw.encode(), _bcrypt.gensalt()).decode()
            print(
                "  !! Existing SHA-256 password migrated to bcrypt.\n"
                f"     Default password restored to: {default_pw}\n"
                "     Please change it in Admin > Users immediately."
            )
        else:
            pw_hash = _bcrypt.hashpw(default_pw.encode(), _bcrypt.gensalt()).decode()

        db.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?,?,?)",
            ("admin", pw_hash, "admin")
        )
        db.execute("DELETE FROM settings WHERE key='admin_password'")

    db.commit()
    db.close()

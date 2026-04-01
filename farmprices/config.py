"""
Application configuration loaded from environment / .env file.
"""
import os
import secrets

from dotenv import load_dotenv

load_dotenv()

_SECRET = os.environ.get("SECRET_KEY", "").strip()


class Config:
    # ── Security ───────────────────────────────────────────────────────────────
    # In production SECRET_KEY must be set in .env — we refuse to start without it.
    SECRET_KEY: str = _SECRET or secrets.token_hex(32)  # dev fallback only

    SESSION_COOKIE_HTTPONLY: bool = True
    SESSION_COOKIE_SAMESITE: str  = "Lax"
    # 8-hour session lifetime (seconds)
    PERMANENT_SESSION_LIFETIME: int = 8 * 60 * 60

    # ── Database ───────────────────────────────────────────────────────────────
    BASE_DIR: str = os.path.dirname(os.path.abspath(__file__))
    DB_PATH: str  = os.environ.get("DB_PATH") or os.path.join(BASE_DIR, "prices.db")

    # ── Server ─────────────────────────────────────────────────────────────────
    PORT: int = int(os.environ.get("PORT", 5000))

    # ── CSRF ───────────────────────────────────────────────────────────────────
    WTF_CSRF_ENABLED: bool = True

    # ── Rate limiting ──────────────────────────────────────────────────────────
    RATELIMIT_STORAGE_URI: str = "memory://"
    RATELIMIT_DEFAULT: str     = "200 per minute"

    # ── Uploads (CSV import) ───────────────────────────────────────────────────
    UPLOAD_FOLDER: str   = os.path.join(BASE_DIR, "uploads")
    MAX_CONTENT_LENGTH: int = 4 * 1024 * 1024  # 4 MB

    # ── App defaults ───────────────────────────────────────────────────────────
    DEFAULT_PASSWORD: str = "farm2024"


def warn_if_insecure():
    """Print a warning at startup if the default secret key is in use."""
    if not _SECRET:
        print("\n  ⚠  WARNING: SECRET_KEY not set in .env — using a random key.")
        print("     Sessions will be invalidated on every restart.")
        print("     Set SECRET_KEY in .env for production use.\n")

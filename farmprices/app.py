"""
Tenbury Farm Supplies — Price Lookup App
Flask application factory.
"""
import os
import socket

from flask import Flask

from config import Config, warn_if_insecure
from db import init_db, close_db
from extensions import csrf, limiter


def create_app(config_class=Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)

    # ── Extensions ─────────────────────────────────────────────────────────────
    csrf.init_app(app)
    limiter.init_app(app)

    # ── Database teardown ──────────────────────────────────────────────────────
    app.teardown_appcontext(close_db)

    # ── Make session permanent by default ─────────────────────────────────────
    @app.before_request
    def make_session_permanent():
        from flask import session
        session.permanent = True

    # ── Blueprints ─────────────────────────────────────────────────────────────
    from blueprints.auth   import bp as auth_bp
    from blueprints.public import bp as public_bp
    from blueprints.admin  import bp as admin_bp
    from blueprints.api    import bp as api_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)

    # ── Rate limit login endpoint ──────────────────────────────────────────────
    limiter.limit("10 per minute")(app.view_functions["auth.login"])

    # ── Jinja2 globals ─────────────────────────────────────────────────────────
    @app.context_processor
    def inject_globals():
        from flask import session as _sess
        return {
            "current_username": _sess.get("username", ""),
            "current_role":     _sess.get("role", ""),
        }

    # ── Initialise / migrate DB ────────────────────────────────────────────────
    # Called here so gunicorn workers initialise the DB on startup without
    # needing a separate ExecStartPre command in the systemd unit.
    # init_db is fully idempotent (CREATE IF NOT EXISTS / INSERT OR IGNORE).
    with app.app_context():
        init_db(app)

    return app


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    warn_if_insecure()
    os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)

    app = create_app()

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        local_ip = "YOUR_IP"

    print("\n" + "=" * 58)
    print("  Tenbury Farm Supplies — Price Lookup App")
    print(f"  Local:    http://localhost:{Config.PORT}")
    print(f"  Network:  http://{local_ip}:{Config.PORT}")
    print(f"  Login:    username=admin  password={Config.DEFAULT_PASSWORD}")
    print("            (change in Admin → Users)")
    print("  Press Ctrl+C to stop")
    print("=" * 58 + "\n")

    app.run(host="0.0.0.0", port=Config.PORT, debug=False)

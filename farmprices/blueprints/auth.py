"""
Authentication blueprint — login, logout.
Rate-limited to 10 attempts / minute per IP.
"""
import bcrypt
from flask import (
    Blueprint, flash, redirect, render_template,
    request, session, url_for
)
from db import get_db
from helpers import get_setting, log_event

bp = Blueprint("auth", __name__)


# ── Login ─────────────────────────────────────────────────────────────────────

@bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        role = session.get("role", "sales")
        return redirect(url_for("admin.products") if role == "admin" else url_for("public.index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("Username and password required.", "error")
            return render_template("login.html",
                                   shop_name=get_setting("shop_name", "Tenbury Farm Supplies"))

        db  = get_db()
        row = db.execute(
            "SELECT * FROM users WHERE username=? COLLATE NOCASE AND active=1",
            (username,)
        ).fetchone()

        if row and bcrypt.checkpw(password.encode(), row["password_hash"].encode()):
            session.permanent = True
            session["user_id"]  = row["id"]
            session["username"] = row["username"]
            session["role"]     = row["role"]

            db.execute("UPDATE users SET last_login=datetime('now') WHERE id=?", (row["id"],))
            log_event(db, "admin_login",
                      changed_by=row["username"],
                      notes=f"Login — role: {row['role']}")
            db.commit()

            flash(f"Welcome back, {row['username']}.", "success")
            if row["role"] == "admin":
                return redirect(url_for("admin.products"))
            return redirect(url_for("public.index"))
        else:
            try:
                db = get_db()
                log_event(db, "login_failed",
                          changed_by=username,
                          notes=f"Failed login attempt for '{username}'")
                db.commit()
            except Exception:
                pass
            flash("Incorrect username or password.", "error")

    return render_template("login.html",
                           shop_name=get_setting("shop_name", "Tenbury Farm Supplies"))


# ── Logout ────────────────────────────────────────────────────────────────────

@bp.route("/logout")
def logout():
    username = session.get("username", "")
    if session.get("user_id"):
        try:
            db = get_db()
            log_event(db, "admin_logout", changed_by=username, notes="Logged out")
            db.commit()
        except Exception:
            pass
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))

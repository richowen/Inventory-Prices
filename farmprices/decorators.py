"""
Authentication decorators for route protection.
"""
from functools import wraps

from flask import flash, redirect, session, url_for


def require_login(f):
    """Require any authenticated user (admin or sales)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in to continue.", "info")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


def require_admin(f):
    """Require an admin-role session."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in to access the admin panel.", "info")
            return redirect(url_for("auth.login"))
        if session.get("role") != "admin":
            flash("Admin access required.", "error")
            return redirect(url_for("public.index"))
        return f(*args, **kwargs)
    return decorated

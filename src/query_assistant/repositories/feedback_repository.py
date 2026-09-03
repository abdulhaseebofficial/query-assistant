"""Storing and reading what people say about the app.

Two things this deliberately does not do.

It doesn't email anything anywhere: that needs a mail service, credentials, and a
place for them, and it would fail silently the first time any of the three was
missing. Rows in a table can't fail silently.

And it isn't reachable from the SQL editor or the AI engine. `feedback` lives in
the same database as the demo tables and holds addresses people typed in â€” so, like
`users`, it stays off every whitelist. Reading it goes through `recent()` and the
one route that requires being the admin.
"""

import os

from flask import current_app, has_app_context

from query_assistant.infrastructure.database import connection as db
from query_assistant.infrastructure.database import initialization as database

# `database.DB_NAME` is read at call time rather than imported by value. Modules that
# bind it at import have to be repointed one by one whenever the database moves â€” the
# test suite keeps a list of them â€” and a module added later is a module somebody
# forgets to add to that list. Reading it through the module has no such cost.

# Feedback is a free-text box on a public page. These caps are what stop one
# submission filling the disk; the rate limit on the route stops many of them.
MAX_MESSAGE = 4000
MAX_EMAIL = 254
MAX_PAGE = 200


def admin_username():
    """Whose account may read the feedback, or None if nobody's been named."""
    return os.environ.get("ADMIN_USERNAME", "").strip() or None


def is_admin(user):
    """True only when an admin has been configured and this is them.

    Unset means nobody, rather than everybody: a deployment that forgot to set it
    should show the feedback to no one, not to the first person who signs up.
    """
    name = admin_username()
    return bool(name) and getattr(user, "is_authenticated", False) and user.username == name


def save(message, email=None, user_id=None, page=None):
    """Record one piece of feedback. Returns False if there was nothing to record."""
    message = (message or "").strip()
    if not message:
        return False

    path = current_app.config["DATABASE_PATH"] if has_app_context() else database.DB_NAME
    conn = db.connect(path)
    try:
        conn.execute(
            "INSERT INTO feedback (user_id, email, message, page) VALUES (?, ?, ?, ?)",
            (
                user_id,
                (email or "").strip()[:MAX_EMAIL] or None,
                message[:MAX_MESSAGE],
                (page or "").strip()[:MAX_PAGE] or None,
            ),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def recent(limit=200):
    """The most recent feedback, newest first, with the sender's username if any."""
    path = current_app.config["DATABASE_PATH"] if has_app_context() else database.DB_NAME
    conn = db.connect(path)
    try:
        rows = conn.execute(
            "SELECT f.message, f.email, f.page, f.created_at, u.username "
            "FROM feedback f LEFT JOIN users u ON u.id = f.user_id "
            "ORDER BY f.id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def count():
    path = current_app.config["DATABASE_PATH"] if has_app_context() else database.DB_NAME
    conn = db.connect(path)
    try:
        return conn.execute("SELECT COUNT(*) AS n FROM feedback").fetchone()[0]
    finally:
        conn.close()

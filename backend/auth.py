import sqlite3

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from backend.database import DB_NAME


class User(UserMixin):
    def __init__(self, id, username, email):
        self.id = str(id)
        self.username = username
        self.email = email


def _connect():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def _row_to_user(row):
    return User(row["id"], row["username"], row["email"]) if row else None


def find_by_id(user_id):
    conn = _connect()
    try:
        row = conn.execute("SELECT id, username, email FROM users WHERE id = ?", (user_id,)).fetchone()
        return _row_to_user(row)
    finally:
        conn.close()


def find_by_username(username):
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT id, username, email FROM users WHERE username = ?", (username,)
        ).fetchone()
        return _row_to_user(row)
    finally:
        conn.close()


def verify_password(username, password):
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT id, username, email, password_hash FROM users WHERE username = ?", (username,)
        ).fetchone()
        if row is None or not check_password_hash(row["password_hash"], password):
            return None
        return _row_to_user(row)
    finally:
        conn.close()


def create_user(username, email, password):
    conn = _connect()
    try:
        existing = conn.execute(
            "SELECT id FROM users WHERE username = ? OR email = ?", (username, email)
        ).fetchone()
        if existing:
            raise ValueError("That username or email is already taken.")

        cur = conn.execute(
            "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
            (username, email, generate_password_hash(password)),
        )
        conn.commit()
        return _row_to_user({"id": cur.lastrowid, "username": username, "email": email})
    finally:
        conn.close()


def record_query(user_id, source, query_text, sql_text, engine):
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO query_history (user_id, source, query_text, sql_text, engine) VALUES (?, ?, ?, ?, ?)",
            (user_id, source, query_text, sql_text, engine),
        )
        conn.commit()
    finally:
        conn.close()


def get_history(user_id, limit=100):
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT source, query_text, sql_text, engine, created_at FROM query_history "
            "WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

"""Lets a user attach an external SQLite file (data/uploads/connected.db) and
query it the same way as the built-in database. Only one external SQLite or
PostgreSQL connection is active at a time — see backend/app.py:get_active_source.
"""

import os
import sqlite3

from backend.config import CONNECTED_DB_PATH, UPLOAD_DIR
from backend.db import quote_ident

SQLITE_MAGIC = b"SQLite format 3\x00"
SYSTEM_TABLES = {"sqlite_sequence", "sqlite_stat1", "custom_data", "custom_meta"}


def is_connected():
    return os.path.exists(CONNECTED_DB_PATH)


def save_connected_db(file_stream, original_filename):
    header = file_stream.read(16)
    if header != SQLITE_MAGIC:
        raise ValueError(
            "That doesn't look like a SQLite database file. "
            "Only .db / .sqlite / .sqlite3 files created by SQLite are supported."
        )

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    file_stream.seek(0)
    with open(CONNECTED_DB_PATH, "wb") as out:
        out.write(file_stream.read())

    tables = list_tables()
    if not tables:
        os.remove(CONNECTED_DB_PATH)
        raise ValueError("That database file doesn't contain any tables.")

    return {"filename": original_filename, "tables": tables}


def get_connection():
    if not is_connected():
        return None
    conn = sqlite3.connect(CONNECTED_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _table_names(conn):
    """Just the names — no row counts, no columns."""
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    return [r[0] for r in rows if r[0] not in SYSTEM_TABLES and not r[0].startswith("sqlite_")]


def _describe(conn, name):
    ident = quote_ident(name)
    count = conn.execute(f"SELECT COUNT(*) FROM {ident}").fetchone()[0]
    col_info = conn.execute(f"PRAGMA table_info({ident})").fetchall()
    return {
        "name": name,
        "row_count": count,
        "columns": [r[1] for r in col_info],
        "types": [r[2] or "TEXT" for r in col_info],
    }


def list_tables():
    """Every table with its row count and columns — for the connect page, which shows them."""
    conn = get_connection()
    if conn is None:
        return []
    try:
        return [_describe(conn, name) for name in _table_names(conn)]
    finally:
        conn.close()


def get_table(table_name):
    """Validate table_name against the real schema and return its info, or None.

    Describes only the table asked for. This runs on every question and every
    export, and it used to go through list_tables() — counting the rows of every
    other table in the database first, which on a connected database of any size
    meant a full scan per table before a single question could be answered.
    """
    conn = get_connection()
    if conn is None:
        return None
    try:
        # Still checked against the live catalogue: that check is what keeps an
        # arbitrary name from reaching the SQL below.
        if table_name not in _table_names(conn):
            return None
        return _describe(conn, table_name)
    finally:
        conn.close()


def clear_connection():
    if is_connected():
        os.remove(CONNECTED_DB_PATH)

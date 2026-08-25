"""Lets a user attach an external SQLite file (data/uploads/connected.db) and
query it the same way as the built-in database. Only one external SQLite or
PostgreSQL connection is active at a time — see backend/app.py:get_active_source.
"""

import os
import sqlite3

from backend.config import CONNECTED_DB_PATH, UPLOAD_DIR

SQLITE_MAGIC = b"SQLite format 3\x00"
SYSTEM_TABLES = {"sqlite_sequence", "sqlite_stat1", "custom_data", "custom_meta"}


def _quote_ident(name):
    """Quote a schema-supplied identifier for interpolation into SQL.

    Table names can't be bound as parameters, so they get interpolated — and a
    table name is not automatically safe just because it came from the database's
    own catalogue. Both SQLite and PostgreSQL allow a double quote inside an
    identifier, which would otherwise close the quoting early and let the rest of
    the name be read as SQL. Doubling the quote is the escape both engines define.
    """
    return '"' + name.replace('"', '""') + '"'


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


def list_tables():
    conn = get_connection()
    if conn is None:
        return []
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        names = [r[0] for r in rows if r[0] not in SYSTEM_TABLES and not r[0].startswith("sqlite_")]

        tables = []
        for name in names:
            ident = _quote_ident(name)
            count = conn.execute(f"SELECT COUNT(*) FROM {ident}").fetchone()[0]
            col_info = conn.execute(f"PRAGMA table_info({ident})").fetchall()
            columns = [r[1] for r in col_info]
            types = [r[2] or "TEXT" for r in col_info]
            tables.append({"name": name, "row_count": count, "columns": columns, "types": types})
        return tables
    finally:
        conn.close()


def get_table(table_name):
    """Validate table_name against the real schema and return its info, or None."""
    for table in list_tables():
        if table["name"] == table_name:
            return table
    return None


def clear_connection():
    if is_connected():
        os.remove(CONNECTED_DB_PATH)

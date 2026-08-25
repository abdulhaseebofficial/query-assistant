"""Lets a user attach an external PostgreSQL database via a connection string
and query it the same way as the built-in database.

The DSN is persisted as plain text in data/uploads/postgres_connection.json so
the app can reconnect across requests. That's a known, documented trade-off —
see the "Known limitations" section in README.md — not something to "fix" by
guessing at a different storage scheme.
"""

import json
import os

import psycopg2
import psycopg2.extras

from backend.config import POSTGRES_CONFIG_PATH as CONFIG_PATH
from backend.config import UPLOAD_DIR


def is_connected():
    return os.path.exists(CONFIG_PATH)


def _friendly_connection_error(exc):
    message = str(exc).lower()
    if "password authentication failed" in message or "authentication failed" in message:
        return "Authentication failed — check the username and password in your connection string."
    if "could not translate host name" in message or "name or service not known" in message:
        return "Couldn't resolve the host — check the host part of your connection string."
    if "timeout expired" in message or "timed out" in message:
        return "Connection timed out — check the host/port, and that your network can reach it."
    if "connection refused" in message:
        return "Connection refused — check the host and port are correct and the database is reachable."
    if 'database "' in message and "does not exist" in message:
        return "That database name doesn't exist on this server — check the connection string."
    return "Couldn't connect to that database. Double-check your connection string and try again."


def _connect(dsn):
    try:
        return psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor, connect_timeout=8)
    except psycopg2.OperationalError as exc:
        raise ValueError(_friendly_connection_error(exc)) from exc


def _list_tables_with(conn):
    cur = conn.cursor()
    cur.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
        "ORDER BY table_name"
    )
    names = [row["table_name"] for row in cur.fetchall()]

    tables = []
    for name in names:
        cur.execute(f'SELECT COUNT(*) AS count FROM "{name}"')
        count = cur.fetchone()["count"]
        cur.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s ORDER BY ordinal_position",
            (name,),
        )
        col_rows = cur.fetchall()
        tables.append({
            "name": name,
            "row_count": count,
            "columns": [r["column_name"] for r in col_rows],
            "types": [r["data_type"] for r in col_rows],
        })
    cur.close()
    return tables


def save_connection(dsn):
    dsn = dsn.strip()
    if not dsn:
        raise ValueError("Please paste a connection string.")

    conn = _connect(dsn)
    try:
        tables = _list_tables_with(conn)
    finally:
        conn.close()

    if not tables:
        raise ValueError(
            "Connected successfully, but no tables were found in the 'public' schema."
        )

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({"dsn": dsn}, f)

    return tables


def get_connection():
    if not is_connected():
        return None
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)
    return _connect(config["dsn"])


def list_tables():
    conn = get_connection()
    if conn is None:
        return []
    try:
        return _list_tables_with(conn)
    finally:
        conn.close()


def get_table(table_name):
    for table in list_tables():
        if table["name"] == table_name:
            return table
    return None


def clear_connection():
    if is_connected():
        os.remove(CONFIG_PATH)

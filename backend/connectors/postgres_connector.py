"""Lets a user attach an external PostgreSQL database via a connection string
and query it the same way as the built-in database.

The DSN is persisted as plain text in data/uploads/postgres_connection.json so
the app can reconnect across requests. That's a known, documented trade-off —
see the "Known limitations" section in README.md — not something to "fix" by
guessing at a different storage scheme.
"""

import ipaddress
import json
import os
import socket
from urllib.parse import unquote, urlparse

import psycopg2
import psycopg2.extras

from backend.config import POSTGRES_CONFIG_PATH as CONFIG_PATH
from backend.config import UPLOAD_DIR
from backend.connectors import quote_ident

# Connecting to a private address is normal when you run Postgres on your own
# machine, and a server-side request forgery primitive when the app is reachable
# by anyone else. Off by default; set ALLOW_PRIVATE_DB_HOSTS=true for local use.
ALLOW_PRIVATE_HOSTS = os.environ.get("ALLOW_PRIVATE_DB_HOSTS", "").strip().lower() in ("1", "true", "yes")


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


def _host_from_dsn(dsn):
    """Pull the host out of either DSN form psycopg2 accepts."""
    if "://" in dsn:
        parsed = urlparse(dsn)
        return unquote(parsed.hostname) if parsed.hostname else None

    # keyword/value form: "host=db.example.com port=5432 dbname=..."
    for part in dsn.split():
        key, sep, value = part.partition("=")
        if sep and key.strip().lower() == "host":
            return value.strip().strip("'\"")
    return None


def _resolves_to_private_address(host):
    """True if `host` points anywhere inside this machine or its private network.

    Resolution happens here rather than trusting the literal text, so a hostname
    that an attacker points at 127.0.0.1 is caught too. A host that doesn't
    resolve is treated as non-private — the connection attempt will fail on its
    own, and refusing to look it up would just produce a worse error message.
    """
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False

    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return True
    return False


def check_dsn_target(dsn):
    """Raise ValueError if this DSN points at an address we refuse to dial.

    Without this, /connect-db/postgres is an open port scanner: anyone who can
    reach the app can aim it at 127.0.0.1, a RFC1918 range, or 169.254.169.254
    (cloud instance metadata) and read the network's shape off the distinct
    "connection refused" / "timed out" / "authentication failed" replies.
    """
    if ALLOW_PRIVATE_HOSTS:
        return

    host = _host_from_dsn(dsn)
    if host is None:
        # No host at all means a local Unix socket / default localhost connection.
        raise ValueError(
            "That connection string has no host. Connecting to a local database is "
            "disabled by default — set ALLOW_PRIVATE_DB_HOSTS=true to allow it."
        )

    if _resolves_to_private_address(host):
        raise ValueError(
            f"Refusing to connect to '{host}': it resolves to a private or loopback "
            "address. If you're running the database on this machine or network, set "
            "ALLOW_PRIVATE_DB_HOSTS=true in your .env to allow it."
        )


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
        cur.execute(f"SELECT COUNT(*) AS count FROM {quote_ident(name)}")
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

    check_dsn_target(dsn)
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

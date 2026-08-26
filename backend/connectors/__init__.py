"""Adapters for databases the user attaches at runtime."""

from backend.db import quote_ident

__all__ = ["active_source", "quote_ident"]


def active_source():
    """(connector, placeholder, label) for whatever is attached, or three Nones.

    Only one external database is connected at a time. This lived in two places —
    app.py for the routes and sql_console.py for the editor — which is how a
    connector added to one would have gone missing from the other.
    """
    from backend.connectors import postgres_connector, sqlite_connector

    if postgres_connector.is_connected():
        return postgres_connector, "%s", "PostgreSQL"
    if sqlite_connector.is_connected():
        return sqlite_connector, "?", "SQLite"
    return None, None, None

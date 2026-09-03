"""Adapters for databases attached by a user."""

from query_assistant.infrastructure.database.connection import quote_ident

__all__ = ["active_source", "quote_ident"]


def active_source():
    from query_assistant.infrastructure.database.connectors import postgresql, sqlite

    if postgresql.is_connected():
        return postgresql, "%s", "PostgreSQL"
    if sqlite.is_connected():
        return sqlite, "?", "SQLite"
    return None, None, None

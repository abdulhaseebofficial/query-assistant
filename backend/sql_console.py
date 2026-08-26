"""Running SQL somebody typed themselves.

The rest of the app writes the SQL for you. This is the other direction: you have a
query and want to run it, against the demo schema, a CSV you uploaded, or a database
you connected.

It is deliberately the same guarded path the AI engine uses. `check_select` decides
what may run — one read-only SELECT, tables from a whitelist — and a query typed by
hand goes through it exactly as a query written by a model does. Anything else would
mean the app's central guarantee held only for the half of the traffic that didn't
arrive through a text box.

What differs is only the reporting. A model gets None and falls back; a person gets
told which rule they ran into, because they're the one who can fix it.
"""

from backend import connectors
from backend.db import quote_ident
from backend.engines.ai_engine import BUILTIN_TABLES, check_select
from backend.engines.csv_engine import get_dataset_info

DEMO = "demo"
DATASET = "dataset"
CONNECTED = "connected"


def available_sources(conn):
    """The sources that can be queried right now, most specific first.

    Each is a dict of: key, label, and tables (name -> columns).
    """
    sources = []

    dataset = get_dataset_info(conn)
    if dataset:
        sources.append({
            "key": DATASET,
            "label": f"{dataset['name']} (uploaded)",
            "tables": {"custom_data": list(dataset["columns"])},
        })

    external, _placeholder, kind = connectors.active_source()
    if external is not None:
        tables = {t["name"]: list(t["columns"]) for t in external.list_tables()}
        if tables:
            sources.append({
                "key": CONNECTED,
                "label": f"Connected {kind}",
                "tables": tables,
            })

    sources.append({
        "key": DEMO,
        "label": "Demo company database",
        "tables": _demo_tables(conn),
    })
    return sources


def _demo_tables(conn):
    """The demo tables and their columns, read from the database.

    Listing them by hand here would have been a fourth copy of a schema that
    already exists as DDL — and the copy shown to somebody writing a query is the
    worst one to let drift. LIMIT 0 costs nothing and works on both dialects.
    """
    tables = {}
    for name in sorted(BUILTIN_TABLES):
        cursor = conn.execute(f"SELECT * FROM {quote_ident(name)} LIMIT 0")
        tables[name] = [column[0] for column in cursor.description]
    return tables


def pick_source(sources, key):
    """The requested source, or the first available one."""
    for source in sources:
        if source["key"] == key:
            return source
    return sources[0] if sources else None


def run(source, sql, demo_conn):
    """Run `sql` against `source`.

    Returns a dict with either `rows`/`columns`, or `error` explaining what stopped
    it. Never raises for a bad query: a typo is an ordinary outcome here, not a
    server fault.
    """
    allowed = BUILTIN_TABLES if source["key"] == DEMO else set(source["tables"])

    statement, reason = check_select(sql, allowed)
    if statement is None:
        return {"error": reason, "sql": sql}

    try:
        rows = _execute(source, statement, demo_conn)
    except Exception as exc:  # the database's own complaint, shown as-is
        return {"error": _readable(exc), "sql": statement}

    columns = list(rows[0].keys()) if rows else []
    return {"rows": rows, "columns": columns, "sql": statement}


def _execute(source, statement, demo_conn):
    if source["key"] == CONNECTED:
        external, _placeholder, _kind = connectors.active_source()
        connection = external.get_connection()
        try:
            cursor = connection.cursor()
            try:
                cursor.execute(statement)
                return [dict(row) for row in cursor.fetchall()]
            finally:
                cursor.close()
        finally:
            connection.close()

    # The demo tables and an uploaded dataset live in the same database.
    return [dict(row) for row in demo_conn.execute(statement).fetchall()]


def _readable(exc):
    """The database's error, tidied enough to act on.

    Drivers prefix their messages differently and none of it helps the person who
    typed the query, so only the sentence itself is kept.
    """
    message = str(exc).strip().splitlines()[0] if str(exc).strip() else "The query failed."
    message = message.removeprefix("(psycopg2.errors.").strip()
    return message[:200] if message else "The query failed."

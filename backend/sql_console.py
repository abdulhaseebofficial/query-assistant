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

from backend.connectors import postgres_connector, sqlite_connector
from backend.engines.ai_engine import BUILTIN_TABLES, check_select
from backend.engines.csv_engine import get_dataset_info

DEMO = "demo"
DATASET = "dataset"
CONNECTED = "connected"


def available_sources(conn):
    """The sources that can be queried right now, most specific first.

    Each is a dict of: key, label, tables (name -> columns), and the placeholder
    style its driver expects.
    """
    sources = []

    dataset = get_dataset_info(conn)
    if dataset:
        sources.append({
            "key": DATASET,
            "label": f"{dataset['name']} (uploaded)",
            "tables": {"custom_data": list(dataset["columns"])},
            "placeholder": "?",
        })

    external, placeholder, kind = _external()
    if external is not None:
        tables = {t["name"]: list(t["columns"]) for t in external.list_tables()}
        if tables:
            sources.append({
                "key": CONNECTED,
                "label": f"Connected {kind}",
                "tables": tables,
                "placeholder": placeholder,
            })

    sources.append({
        "key": DEMO,
        "label": "Demo company database",
        "tables": _demo_tables(),
        "placeholder": "?",
    })
    return sources


def _external():
    if postgres_connector.is_connected():
        return postgres_connector, "%s", "PostgreSQL"
    if sqlite_connector.is_connected():
        return sqlite_connector, "?", "SQLite"
    return None, None, None


def _demo_tables():
    return {
        "departments": ["id", "name", "location", "manager_name"],
        "employees": ["id", "name", "department_id", "position", "salary", "email", "hire_date"],
        "products": ["id", "name", "category", "price", "stock_quantity"],
        "customers": ["id", "name", "email", "city", "phone"],
        "orders": ["id", "customer_id", "product_id", "quantity", "order_date",
                   "total_amount", "status"],
    }


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
        external, _placeholder, _kind = _external()
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

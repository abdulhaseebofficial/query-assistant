"""Claude-powered natural-language-to-SQL generation, used ahead of the rule-based engines.

Every query this module produces is validated before it is ever handed back to the
caller: it must be a single read-only SELECT, and it may only reference tables the
caller explicitly whitelisted. That second check matters because the built-in demo
database (data/company.db) also stores the app's own `users` and `query_history`
tables — without a table whitelist, a cleverly-worded question (or a prompt-injection
attempt) could trick the model into generating `SELECT * FROM users` and the app
would execute it without a second thought.
"""

import os
import re

from dotenv import load_dotenv

load_dotenv()

FORBIDDEN_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|ATTACH|DETACH|PRAGMA|CREATE|REPLACE|VACUUM|GRANT|REVOKE)\b",
    re.IGNORECASE,
)

# Only tables listed here (or explicitly passed as `allowed_tables`) may ever appear
# in AI-generated SQL — this is what keeps generated queries away from `users` /
# `query_history`, which live in the same physical database file.
BUILTIN_TABLES = frozenset({"departments", "employees", "products", "customers", "orders"})

BUILTIN_SCHEMA = """\
departments(id, name, location, manager_name)
employees(id, name, department_id -> departments.id, position, salary, email, hire_date)
products(id, name, category, price, stock_quantity)
customers(id, name, email, city, phone)
orders(id, customer_id -> customers.id, product_id -> products.id, quantity, order_date, total_amount, status)
"""

# Matches the table name immediately following FROM/JOIN so generated SQL can be
# checked against the caller's allow-list. Deliberately simple: it only needs to
# extract candidate identifiers, not fully parse the statement.
_TABLE_REF_PATTERN = re.compile(r'\b(?:FROM|JOIN)\s+"?([A-Za-z_][A-Za-z0-9_]*)"?', re.IGNORECASE)

TOOL_SCHEMA = {
    "name": "generate_sql",
    "description": "Return the SQL query that answers the user's question.",
    "input_schema": {
        "type": "object",
        "properties": {
            "sql": {
                "type": "string",
                "description": "A single, complete, read-only SELECT statement that answers the question.",
            },
            "explanation": {
                "type": "string",
                "description": "One plain-English sentence explaining what the query does.",
            },
            "chart_type": {
                "type": "string",
                "enum": ["bar", "line", "pie", "none"],
                "description": "The best chart type to visualize the result, or 'none' if it isn't chartable.",
            },
        },
        "required": ["sql", "explanation", "chart_type"],
    },
}

_client = None
_client_checked = False


def _get_client():
    global _client, _client_checked
    if _client_checked:
        return _client
    _client_checked = True
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic
        _client = anthropic.Anthropic()
    except Exception:
        _client = None
    return _client


def build_schema_description(columns, types=None, table_name="data"):
    if types:
        cols = ", ".join(f"{c} ({t})" for c, t in zip(columns, types, strict=True))
    else:
        cols = ", ".join(columns)
    return f"{table_name}({cols})"


def _referenced_tables(sql):
    return {name.lower() for name in _TABLE_REF_PATTERN.findall(sql)}


def _validate_select(sql, allowed_tables):
    if not sql:
        return None
    cleaned = sql.strip().rstrip(";").strip()
    if not cleaned or ";" in cleaned:
        return None
    if not re.match(r"^\s*SELECT\b", cleaned, re.IGNORECASE):
        return None
    if FORBIDDEN_KEYWORDS.search(cleaned):
        return None

    allowed = {t.lower() for t in allowed_tables}
    referenced = _referenced_tables(cleaned)
    if not referenced or not referenced.issubset(allowed):
        return None

    return cleaned + ";"


def generate_sql(user_input, schema_description, dialect="SQLite", table_name=None, allowed_tables=None):
    """Ask Claude for a SELECT statement, or return None to signal the caller
    should fall back to its rule-based engine.

    allowed_tables restricts which table names the generated SQL may reference.
    When omitted it defaults to {table_name} for a single-table caller, or
    BUILTIN_TABLES for the built-in multi-table schema (table_name=None).
    """
    client = _get_client()
    if client is None or not user_input.strip():
        return None

    if allowed_tables is None:
        allowed_tables = {table_name} if table_name else BUILTIN_TABLES

    scope = f"the table {table_name}" if table_name else "the database"
    system = (
        f"You translate plain-English questions into a single read-only {dialect} SELECT "
        f"query against {scope}.\n\nSchema:\n{schema_description}\n\n"
        "Rules: output exactly one SELECT statement (no other statement types, no comments, "
        "no trailing explanation in the sql field), use only the tables/columns listed above, "
        "and prefer LIMIT 200 for queries that could return many rows unless the user asked for "
        "an aggregate (COUNT/SUM/AVG)."
    )

    try:
        response = client.messages.create(
            model="claude-opus-5",
            max_tokens=1024,
            system=system,
            tools=[TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": "generate_sql"},
            output_config={"effort": "medium"},
            messages=[{"role": "user", "content": user_input}],
        )
    except Exception:
        return None

    tool_use = next((b for b in response.content if b.type == "tool_use"), None)
    if tool_use is None:
        return None

    data = tool_use.input
    sql = _validate_select(data.get("sql", ""), allowed_tables)
    if sql is None:
        return None

    chart_type = data.get("chart_type", "none")
    if chart_type not in ("bar", "line", "pie", "none"):
        chart_type = "none"

    return {
        "sql": sql,
        "explanation": data.get("explanation") or "Answers the question using the data above.",
        "chart_type": chart_type,
    }

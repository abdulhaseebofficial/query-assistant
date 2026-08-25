import os
import re

from dotenv import load_dotenv

load_dotenv()

FORBIDDEN_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|ATTACH|DETACH|PRAGMA|CREATE|REPLACE|VACUUM|GRANT|REVOKE)\b",
    re.IGNORECASE,
)

BUILTIN_SCHEMA = """\
departments(id, name, location, manager_name)
employees(id, name, department_id -> departments.id, position, salary, email, hire_date)
products(id, name, category, price, stock_quantity)
customers(id, name, email, city, phone)
orders(id, customer_id -> customers.id, product_id -> products.id, quantity, order_date, total_amount, status)
"""

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
        cols = ", ".join(f"{c} ({t})" for c, t in zip(columns, types))
    else:
        cols = ", ".join(columns)
    return f"{table_name}({cols})"


def _validate_select(sql):
    if not sql:
        return None
    cleaned = sql.strip().rstrip(";").strip()
    if not cleaned or ";" in cleaned:
        return None
    if not re.match(r"^\s*SELECT\b", cleaned, re.IGNORECASE):
        return None
    if FORBIDDEN_KEYWORDS.search(cleaned):
        return None
    return cleaned + ";"


def generate_sql(user_input, schema_description, dialect="SQLite", table_name=None):
    client = _get_client()
    if client is None or not user_input.strip():
        return None

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
    sql = _validate_select(data.get("sql", ""))
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

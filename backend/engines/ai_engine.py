"""AI-powered natural-language-to-SQL generation, used ahead of the rule-based engines.

Two providers are supported — Google Gemini and Anthropic Claude — and which one runs
is decided by whichever API key you've configured (see `_configured_provider`). Neither
is required: with no key at all, `generate_sql` returns None and every caller falls back
to its rule-based engine, so the app never hard-fails on a missing key.

Every query this module produces is validated before it is ever handed back to the
caller, *whichever provider generated it*: it must be a single read-only SELECT, and it
may only reference tables the caller explicitly whitelisted. That second check matters
because the built-in demo database (data/company.db) also stores the app's own `users`
and `query_history` tables — without a table whitelist, a cleverly-worded question (or a
prompt-injection attempt) could trick the model into generating `SELECT * FROM users`
and the app would execute it without a second thought.
"""

import json
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

PROVIDERS = ("gemini", "anthropic")

# Overridable so a newer model can be picked up without a code change.
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-5")

CHART_TYPES = ("bar", "line", "pie", "none")

_SQL_FIELD_DESC = "A single, complete, read-only SELECT statement that answers the question."
_EXPLANATION_FIELD_DESC = "One plain-English sentence explaining what the query does."
_CHART_FIELD_DESC = "The best chart type to visualize the result, or 'none' if it isn't chartable."

# Anthropic's tool-use schema and Gemini's structured-output schema describe the same
# three fields; only the wrapper shape differs between the two SDKs.
TOOL_SCHEMA = {
    "name": "generate_sql",
    "description": "Return the SQL query that answers the user's question.",
    "input_schema": {
        "type": "object",
        "properties": {
            "sql": {"type": "string", "description": _SQL_FIELD_DESC},
            "explanation": {"type": "string", "description": _EXPLANATION_FIELD_DESC},
            "chart_type": {
                "type": "string",
                "enum": list(CHART_TYPES),
                "description": _CHART_FIELD_DESC,
            },
        },
        "required": ["sql", "explanation", "chart_type"],
    },
}

GEMINI_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "sql": {"type": "string", "description": _SQL_FIELD_DESC},
        "explanation": {"type": "string", "description": _EXPLANATION_FIELD_DESC},
        "chart_type": {
            "type": "string",
            "enum": list(CHART_TYPES),
            "description": _CHART_FIELD_DESC,
        },
    },
    "required": ["sql", "explanation", "chart_type"],
    "propertyOrdering": ["sql", "explanation", "chart_type"],
}

_clients = {}


def reset_client_cache():
    """Forget any cached SDK clients.

    Clients are built once and reused, so changing an API key or AI_PROVIDER at
    runtime has no effect until the cache is dropped. Tests rely on this.
    """
    _clients.clear()


def _gemini_api_key():
    # GOOGLE_API_KEY is what the Google SDK itself falls back to, so accept both
    # rather than making people rename a key they already have set.
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


def _configured_provider():
    """Which provider to use, or None to fall back to the rule-based engines.

    An explicit AI_PROVIDER always wins, so you can keep both keys in .env and still
    pin which one runs. An unrecognised value returns None rather than quietly
    picking a provider you didn't ask for.
    """
    explicit = os.environ.get("AI_PROVIDER", "").strip().lower()
    if explicit:
        return explicit if explicit in PROVIDERS else None

    if _gemini_api_key():
        return "gemini"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    return None


def _get_client(provider):
    """Build (and cache) the SDK client for a provider, or None if unavailable.

    Returns None rather than raising when the key is missing or the SDK isn't
    installed — an unavailable provider is a fallback condition, not an error.
    """
    if provider in _clients:
        return _clients[provider]

    client = None
    try:
        if provider == "gemini":
            api_key = _gemini_api_key()
            if api_key:
                from google import genai

                client = genai.Client(api_key=api_key)
        elif provider == "anthropic":
            if os.environ.get("ANTHROPIC_API_KEY"):
                import anthropic

                client = anthropic.Anthropic()
    except Exception:
        client = None

    _clients[provider] = client
    return client


def is_available():
    """True when a provider is configured and its client could be built.

    The UI uses this to explain *why* a question went unanswered — "add an API
    key" and "the model couldn't write that query" need different advice.
    """
    provider = _configured_provider()
    return provider is not None and _get_client(provider) is not None


def active_provider_name():
    """Human-readable name of the provider in use, or None."""
    return {"gemini": "Gemini", "anthropic": "Claude"}.get(_configured_provider())


def build_schema_description(columns, types=None, table_name="data"):
    if types:
        cols = ", ".join(f"{c} ({t})" for c, t in zip(columns, types, strict=True))
    else:
        cols = ", ".join(columns)
    return f"{table_name}({cols})"


def _referenced_tables(sql):
    return {name.lower() for name in _TABLE_REF_PATTERN.findall(sql)}


def check_select(sql, allowed_tables):
    """Validate `sql`, returning (statement, None) or (None, reason).

    The rules live here alone. A model's SQL and a person's typed SQL are checked
    by exactly the same code — two copies of a security rule is two chances to
    weaken one of them. The difference is only that a person gets told *why*: the
    model has no use for the reason, but someone who just typed the query does.
    """
    if not sql or not sql.strip():
        return None, "There's no query here."

    cleaned = sql.strip().rstrip(";").strip()
    if not cleaned:
        return None, "There's no query here."

    if ";" in cleaned:
        return None, "Only one statement at a time — remove the semicolon in the middle."

    if not re.match(r"^\s*SELECT\b", cleaned, re.IGNORECASE):
        return None, "Only SELECT queries can run here. This one starts with something else."

    forbidden = FORBIDDEN_KEYWORDS.search(cleaned)
    if forbidden:
        word = forbidden.group(0).upper()
        return None, f"{word} would change the data. Only read-only queries can run here."

    allowed = {t.lower() for t in allowed_tables}
    referenced = _referenced_tables(cleaned)
    if not referenced:
        return None, "No table found in the query — a SELECT here has to read from one."

    unknown = sorted(referenced - allowed)
    if unknown:
        listed = ", ".join(sorted(allowed))
        return None, f"No table called '{unknown[0]}' here. Available: {listed}."

    return cleaned + ";", None


def _validate_select(sql, allowed_tables):
    """The statement, or None. Used where the reason isn't needed."""
    statement, _reason = check_select(sql, allowed_tables)
    return statement


def _build_instructions(schema_description, dialect, table_name):
    scope = f"the table {table_name}" if table_name else "the database"
    return (
        f"You translate plain-English questions into a single read-only {dialect} SELECT "
        f"query against {scope}.\n\nSchema:\n{schema_description}\n\n"
        "Rules: output exactly one SELECT statement (no other statement types, no comments, "
        "no trailing explanation in the sql field), use only the tables/columns listed above, "
        "and prefer LIMIT 200 for queries that could return many rows unless the user asked for "
        "an aggregate (COUNT/SUM/AVG)."
    )


def _generate_with_gemini(client, user_input, instructions):
    """Ask Gemini for the three fields as JSON, or return None on any failure."""
    from google.genai import types

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=user_input,
            config=types.GenerateContentConfig(
                system_instruction=instructions,
                response_mime_type="application/json",
                response_schema=GEMINI_RESPONSE_SCHEMA,
                max_output_tokens=1024,
                temperature=0,
                # We want JSON back, not a tool call the SDK executes for us. Saying so
                # explicitly also silences the SDK's "don't use AFC here" warning, which
                # would otherwise print on every single question a user asks.
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            ),
        )
    except Exception:
        return None

    try:
        data = json.loads(response.text)
    except (AttributeError, TypeError, ValueError):
        return None

    return data if isinstance(data, dict) else None


def _generate_with_anthropic(client, user_input, instructions):
    """Ask Claude for the three fields via tool use, or return None on any failure."""
    try:
        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=1024,
            system=instructions,
            tools=[TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": "generate_sql"},
            output_config={"effort": "medium"},
            messages=[{"role": "user", "content": user_input}],
        )
    except Exception:
        return None

    tool_use = next((b for b in response.content if b.type == "tool_use"), None)
    return tool_use.input if tool_use is not None else None


_GENERATORS = {
    "gemini": _generate_with_gemini,
    "anthropic": _generate_with_anthropic,
}


def generate_sql(user_input, schema_description, dialect="SQLite", table_name=None, allowed_tables=None):
    """Ask the configured provider for a SELECT statement, or return None to signal
    the caller should fall back to its rule-based engine.

    allowed_tables restricts which table names the generated SQL may reference.
    When omitted it defaults to {table_name} for a single-table caller, or
    BUILTIN_TABLES for the built-in multi-table schema (table_name=None).
    """
    if not user_input.strip():
        return None

    provider = _configured_provider()
    if provider is None:
        return None

    client = _get_client(provider)
    if client is None:
        return None

    if allowed_tables is None:
        allowed_tables = {table_name} if table_name else BUILTIN_TABLES

    instructions = _build_instructions(schema_description, dialect, table_name)
    data = _GENERATORS[provider](client, user_input, instructions)
    if not data:
        return None

    # The same validation runs regardless of which model wrote the SQL — a provider
    # is never trusted to have followed the "one read-only SELECT" instruction.
    sql = _validate_select(data.get("sql", ""), allowed_tables)
    if sql is None:
        return None

    chart_type = data.get("chart_type", "none")
    if chart_type not in CHART_TYPES:
        chart_type = "none"

    return {
        "sql": sql,
        "explanation": data.get("explanation") or "Answers the question using the data above.",
        "chart_type": chart_type,
        "provider": provider,
    }

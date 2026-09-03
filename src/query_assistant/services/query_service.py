"""Natural-language query use cases."""

from flask import current_app, has_app_context

from query_assistant.domain.query import rule_engine
from query_assistant.domain.query.csv_engine import build_custom_query
from query_assistant.infrastructure.ai import providers
from query_assistant.infrastructure.database import connection
from query_assistant.infrastructure.database.initialization import DB_NAME
from query_assistant.utilities import charts


def get_connection():
    path = current_app.config["DATABASE_PATH"] if has_app_context() else DB_NAME
    return connection.connect(path)


def run_with_ai_fallback(execute, question, schema, table_name, dialect, fallback):
    ai_result = providers.generate_sql(question, schema, dialect=dialect, table_name=table_name)
    rows = None
    if ai_result is not None:
        try:
            rows = execute(ai_result["sql"], [])
        except Exception:
            ai_result = None
    if ai_result is not None:
        columns = list(rows[0].keys()) if rows else []
        return {"sql": ai_result["sql"], "params": [], "explanation": ai_result["explanation"],
                "is_aggregate": len(rows) <= 1 and len(columns) == 1, "rows": rows,
                "columns": columns, "engine": "ai", "dialect": dialect,
                "chart_hint": ai_result["chart_type"]}
    built = fallback()
    if built is None:
        return None
    sql, params, explanation, is_aggregate = built
    rows = execute(sql, params)
    return {"sql": sql, "params": params, "explanation": explanation,
            "is_aggregate": is_aggregate, "rows": rows,
            "columns": list(rows[0].keys()) if rows else [], "engine": "rule",
            "dialect": dialect, "chart_hint": "none"}


def run_builtin(question):
    conn = get_connection()
    try:
        def execute(sql, params):
            return [dict(row) for row in conn.execute(sql, params).fetchall()]

        def fallback():
            result = rule_engine.interpret(question, conn)
            if result is None:
                return None
            return result["sql"], result["params"], result["explanation"], result["aggregate"] is not None

        outcome = run_with_ai_fallback(execute, question, providers.BUILTIN_SCHEMA, None,
                                       connection.DIALECT, fallback)
        if outcome:
            outcome["chart"] = charts.build_chart_data(outcome["columns"], outcome["rows"],
                                                       outcome.pop("chart_hint"))
        return outcome
    finally:
        conn.close()


def describe_failure(question):
    text = question.strip().lower()
    conn = get_connection()
    try:
        names = rule_engine.reference_names(rule_engine.get_reference_data(conn))
    finally:
        conn.close()
    return {"on_topic": rule_engine.detect_domain(text) is not None,
            "wants_overview": rule_engine.wants_overview(text),
            "constraints": rule_engine.unsupported_constraints(text, names),
            "ai_available": providers.is_available(), "provider": providers.active_provider_name()}


def run_table(question, meta, source=None, placeholder="?", dialect=None):
    table_name = meta.get("name", "custom_data")
    schema = providers.build_schema_description(meta["columns"], meta["types"], table_name=table_name)
    conn = source.get_connection() if source else get_connection()
    try:
        def execute(sql, params):
            cursor = conn.cursor()
            try:
                cursor.execute(sql, params)
                return [dict(row) for row in cursor.fetchall()]
            finally:
                cursor.close()
        outcome = run_with_ai_fallback(
            execute, question, schema, table_name, dialect or connection.DIALECT,
            lambda: build_custom_query(question, meta["columns"], table_name, placeholder, types=meta["types"]),
        )
    finally:
        conn.close()
    outcome["label_map"] = dict(zip(meta["columns"], meta.get("labels", meta["columns"]), strict=True))
    outcome["chart"] = charts.build_chart_data(outcome["columns"], outcome["rows"], outcome.pop("chart_hint"))
    return outcome

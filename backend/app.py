import csv
import io
import os
import re
import sqlite3

from flask import Flask, Response, redirect, render_template, request, url_for
from flask_login import LoginManager, current_user, login_required, login_user, logout_user
from markupsafe import escape

from backend import auth
from backend.config import STATIC_DIR, TEMPLATE_DIR
from backend.connectors import postgres_connector, sqlite_connector
from backend.content.learn_content import CONCEPTS, FAQS
from backend.database import DB_NAME
from backend.engines import ai_engine
from backend.engines.csv_engine import build_custom_query, clear_dataset, get_dataset_info, load_csv
from backend.engines.rule_engine import interpret
from backend.utils import chart_utils

app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STATIC_DIR)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB upload cap
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
app.jinja_env.filters["zip"] = zip

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)


@login_manager.user_loader
def load_user(user_id):
    return auth.find_by_id(user_id)

EXAMPLE_QUERIES = [
    "employees in the IT department",
    "highest paid employees",
    "products low on stock",
    "customers in Lahore",
    "total revenue this month",
    "pending orders",
]

SQL_KEYWORDS = (
    "LEFT JOIN", "GROUP BY", "ORDER BY",
    "SELECT", "FROM", "WHERE", "JOIN", "ON", "AND", "OR",
    "LIMIT", "COUNT", "SUM", "AVG", "AS", "DESC", "ASC",
)
KEYWORD_PATTERN = re.compile(r"\b(" + "|".join(re.escape(k) for k in SQL_KEYWORDS) + r")\b")


def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def sql_for_display(sql, params):
    display = str(escape(sql))
    for value in params:
        display = display.replace("?", f"<span class=\"sql-str\">'{escape(value)}'</span>", 1)
    return KEYWORD_PATTERN.sub(r'<span class="sql-kw">\1</span>', display)


@app.template_filter("highlight")
def highlight_filter(sql):
    return KEYWORD_PATTERN.sub(r'<span class="sql-kw">\1</span>', str(escape(sql)))


@app.route("/favicon.ico")
def favicon():
    return Response(status=204)


@app.errorhandler(413)
def file_too_large(_exc):
    conn = get_connection()
    current = get_dataset_info(conn)
    conn.close()
    return render_template(
        "upload.html",
        error="That file is too large. Please keep uploads under 5 MB.",
        current=current,
    ), 413


@app.template_filter("commas")
def commas_filter(value):
    try:
        if isinstance(value, float):
            value = int(value) if value.is_integer() else round(value, 2)
        return f"{value:,}"
    except (ValueError, TypeError):
        return value


def _run_with_ai_fallback(execute_fn, user_input, schema_desc, table_name, dialect, fallback_fn):
    """Try the AI engine first; fall back to a rule-based builder on any failure.

    fallback_fn() -> (sql, params, explanation, is_aggregate) or None
    execute_fn(sql, params) -> list[dict]
    """
    ai_result = ai_engine.generate_sql(user_input, schema_desc, dialect=dialect, table_name=table_name)
    rows = None
    if ai_result is not None:
        try:
            rows = execute_fn(ai_result["sql"], [])
        except Exception:
            ai_result = None

    if ai_result is not None:
        columns = list(rows[0].keys()) if rows else []
        return {
            "sql": ai_result["sql"],
            "params": [],
            "explanation": ai_result["explanation"],
            "is_aggregate": len(rows) <= 1 and len(columns) == 1,
            "rows": rows,
            "columns": columns,
            "engine": "ai",
            "chart_hint": ai_result["chart_type"],
        }

    fallback = fallback_fn()
    if fallback is None:
        return None
    sql, params, explanation, is_aggregate = fallback
    rows = execute_fn(sql, params)
    return {
        "sql": sql,
        "params": params,
        "explanation": explanation,
        "is_aggregate": is_aggregate,
        "rows": rows,
        "columns": list(rows[0].keys()) if rows else [],
        "engine": "rule",
        "chart_hint": "none",
    }


def run_query(user_input):
    conn = get_connection()
    try:
        def execute_fn(sql, params):
            return [dict(row) for row in conn.execute(sql, params).fetchall()]

        def fallback_fn():
            interpretation = interpret(user_input, conn)
            if interpretation is None:
                return None
            return (
                interpretation["sql"],
                interpretation["params"],
                interpretation["explanation"],
                interpretation["aggregate"] is not None,
            )

        outcome = _run_with_ai_fallback(
            execute_fn, user_input, ai_engine.BUILTIN_SCHEMA, None, "SQLite", fallback_fn
        )
        if outcome is None:
            return None
        outcome["chart"] = chart_utils.build_chart_data(
            outcome["columns"], outcome["rows"], outcome.pop("chart_hint")
        )
        return outcome
    finally:
        conn.close()


@app.route("/", methods=["GET"])
def index():
    user_input = request.args.get("q", "").strip()
    result = None

    if user_input:
        outcome = run_query(user_input)
        if outcome is None:
            result = {"understood": False}
        else:
            outcome["understood"] = True
            outcome["sql_display"] = sql_for_display(outcome["sql"], outcome["params"])
            result = outcome
            if current_user.is_authenticated:
                auth.record_query(current_user.id, "/", user_input, outcome["sql"], outcome["engine"])

    return render_template(
        "index.html",
        query=user_input,
        searched=bool(user_input),
        result=result,
        examples=EXAMPLE_QUERIES,
    )


@app.route("/export", methods=["GET"])
def export():
    user_input = request.args.get("q", "").strip()
    outcome = run_query(user_input) if user_input else None

    if outcome is None:
        return Response("Couldn't understand that question — nothing to export.", status=404, mimetype="text/plain")
    if not outcome["rows"]:
        return Response("No matching data to export.", status=404, mimetype="text/plain")

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=outcome["columns"])
    writer.writeheader()
    writer.writerows(outcome["rows"])

    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=query_results.csv"},
    )


@app.route("/upload", methods=["GET", "POST"])
def upload():
    error = None

    if request.method == "POST":
        file = request.files.get("file")
        dataset_name = request.form.get("dataset_name", "").strip() or "My Dataset"

        if not file or file.filename == "":
            error = "Please choose a CSV file first."
        elif not file.filename.lower().endswith(".csv"):
            error = "Only .csv files are supported."
        else:
            conn = get_connection()
            try:
                load_csv(file.stream, conn, dataset_name)
                success = True
            except ValueError as exc:
                error = str(exc)
                success = False
            except Exception:
                error = "Something went wrong reading that file. Please check it's a valid CSV and try again."
                success = False
            finally:
                conn.close()
            if success:
                return redirect(url_for("dataset"))

    conn = get_connection()
    current = get_dataset_info(conn)
    conn.close()
    return render_template("upload.html", error=error, current=current)


@app.route("/dataset/clear", methods=["POST"])
def dataset_clear():
    conn = get_connection()
    clear_dataset(conn)
    conn.close()
    return redirect(url_for("upload"))


def run_custom_query(user_input, meta):
    schema_desc = ai_engine.build_schema_description(
        meta["columns"], meta["types"], table_name="custom_data"
    )
    conn = get_connection()
    try:
        def execute_fn(sql, params):
            return [dict(row) for row in conn.execute(sql, params).fetchall()]

        def fallback_fn():
            return build_custom_query(user_input, meta["columns"])

        outcome = _run_with_ai_fallback(
            execute_fn, user_input, schema_desc, "custom_data", "SQLite", fallback_fn
        )
    finally:
        conn.close()

    outcome["label_map"] = dict(zip(meta["columns"], meta["labels"]))
    outcome["chart"] = chart_utils.build_chart_data(
        outcome["columns"], outcome["rows"], outcome.pop("chart_hint")
    )
    return outcome


def get_active_source():
    """Returns (backend_module, sql_placeholder, kind_label) for whichever external
    database is currently connected, or (None, None, None) if neither is."""
    if postgres_connector.is_connected():
        return postgres_connector, "%s", "PostgreSQL"
    if sqlite_connector.is_connected():
        return sqlite_connector, "?", "SQLite"
    return None, None, None


def fetch_rows(conn, sql, params):
    cur = conn.cursor()
    try:
        cur.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]
    finally:
        cur.close()


def run_connected_query(source, placeholder, kind, table, user_input):
    schema_desc = ai_engine.build_schema_description(
        table["columns"], table["types"], table_name=table["name"]
    )
    conn = source.get_connection()
    try:
        def execute_fn(sql, params):
            return fetch_rows(conn, sql, params)

        def fallback_fn():
            return build_custom_query(user_input, table["columns"], table["name"], placeholder)

        outcome = _run_with_ai_fallback(
            execute_fn, user_input, schema_desc, table["name"], kind, fallback_fn
        )
    finally:
        conn.close()

    outcome["label_map"] = {c: c for c in table["columns"]}
    outcome["chart"] = chart_utils.build_chart_data(
        outcome["columns"], outcome["rows"], outcome.pop("chart_hint")
    )
    return outcome


@app.route("/connect-db", methods=["GET", "POST"])
def connect_db():
    error = None

    if request.method == "POST":
        file = request.files.get("file")

        if not file or file.filename == "":
            error = "Please choose a database file first."
        elif not file.filename.lower().endswith((".db", ".sqlite", ".sqlite3")):
            error = "Only .db, .sqlite, or .sqlite3 files are supported."
        else:
            try:
                sqlite_connector.save_connected_db(file.stream, file.filename)
                postgres_connector.clear_connection()
                return redirect(url_for("connect_db"))
            except ValueError as exc:
                error = str(exc)
            except Exception:
                error = "Something went wrong reading that file. Please check it's a valid SQLite database."

    source, _, kind = get_active_source()
    tables = source.list_tables() if source else []
    return render_template("connect.html", error=error, tables=tables, connected=source is not None, kind=kind)


@app.route("/connect-db/postgres", methods=["POST"])
def connect_db_postgres():
    dsn = request.form.get("dsn", "")
    error = None

    try:
        postgres_connector.save_connection(dsn)
        sqlite_connector.clear_connection()
        return redirect(url_for("connect_db"))
    except ValueError as exc:
        error = str(exc)
    except Exception:
        error = "Something went wrong connecting to that database. Please check the connection string."

    source, _, kind = get_active_source()
    tables = source.list_tables() if source else []
    return render_template("connect.html", error=error, tables=tables, connected=source is not None, kind=kind)


@app.route("/connect-db/clear", methods=["POST"])
def connect_db_clear():
    sqlite_connector.clear_connection()
    postgres_connector.clear_connection()
    return redirect(url_for("connect_db"))


@app.route("/connect-db/<table_name>", methods=["GET"])
def connect_db_table(table_name):
    source, placeholder, kind = get_active_source()
    table = source.get_table(table_name) if source else None
    if table is None:
        return redirect(url_for("connect_db"))

    user_input = request.args.get("q", "").strip()
    result = None

    if user_input:
        outcome = run_connected_query(source, placeholder, kind, table, user_input)
        outcome["sql_display"] = sql_for_display(outcome["sql"], outcome["params"])
        result = outcome
        if current_user.is_authenticated:
            auth.record_query(
                current_user.id, f"/connect-db/{table_name}", user_input, outcome["sql"], outcome["engine"]
            )

    return render_template(
        "connect_table.html",
        table=table,
        query=user_input,
        searched=bool(user_input),
        result=result,
    )


@app.route("/connect-db/<table_name>/export", methods=["GET"])
def connect_db_table_export(table_name):
    source, placeholder, kind = get_active_source()
    table = source.get_table(table_name) if source else None
    if table is None:
        return Response("Table not found.", status=404, mimetype="text/plain")

    user_input = request.args.get("q", "").strip()
    if not user_input:
        return Response("No data to export.", status=404, mimetype="text/plain")

    outcome = run_connected_query(source, placeholder, kind, table, user_input)
    if not outcome["rows"]:
        return Response("No matching data to export.", status=404, mimetype="text/plain")

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=outcome["columns"])
    writer.writeheader()
    writer.writerows(outcome["rows"])

    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={table_name}_results.csv"},
    )


@app.route("/dataset", methods=["GET"])
def dataset():
    conn = get_connection()
    meta = get_dataset_info(conn)
    conn.close()

    if meta is None:
        return redirect(url_for("upload"))

    user_input = request.args.get("q", "").strip()
    result = None

    if user_input:
        outcome = run_custom_query(user_input, meta)
        outcome["sql_display"] = sql_for_display(outcome["sql"], outcome["params"])
        result = outcome
        if current_user.is_authenticated:
            auth.record_query(current_user.id, "/dataset", user_input, outcome["sql"], outcome["engine"])

    return render_template(
        "dataset.html",
        meta=meta,
        query=user_input,
        searched=bool(user_input),
        result=result,
    )


@app.route("/dataset/export", methods=["GET"])
def dataset_export():
    conn = get_connection()
    meta = get_dataset_info(conn)
    conn.close()
    if meta is None:
        return Response("No dataset uploaded.", status=404, mimetype="text/plain")

    user_input = request.args.get("q", "").strip()
    if not user_input:
        return Response("No data to export.", status=404, mimetype="text/plain")

    outcome = run_custom_query(user_input, meta)
    if not outcome["rows"]:
        return Response("No matching data to export.", status=404, mimetype="text/plain")

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=outcome["columns"])
    writer.writeheader()
    writer.writerows(outcome["rows"])

    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=dataset_results.csv"},
    )


@app.route("/learn", methods=["GET"])
def learn():
    grouped = {
        level: [c for c in CONCEPTS if c["level"] == level]
        for level in ("Basic", "Intermediate", "Advanced")
    }
    return render_template("learn.html", grouped=grouped, faqs=FAQS)


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        if not re.match(r"^[a-zA-Z0-9_]{3,30}$", username):
            error = "Username must be 3-30 characters: letters, numbers, underscores only."
        elif "@" not in email or "." not in email:
            error = "Please enter a valid email address."
        elif len(password) < 6:
            error = "Password must be at least 6 characters."
        else:
            try:
                user = auth.create_user(username, email, password)
                login_user(user)
                return redirect(url_for("index"))
            except ValueError as exc:
                error = str(exc)

    return render_template("register.html", error=error)


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = auth.verify_password(username, password)
        if user is None:
            error = "Incorrect username or password."
        else:
            login_user(user)
            return redirect(url_for("index"))

    return render_template("login.html", error=error)


@app.route("/logout", methods=["POST"])
def logout():
    logout_user()
    return redirect(url_for("index"))


@app.route("/history", methods=["GET"])
@login_required
def history():
    entries = auth.get_history(current_user.id)
    return render_template("history.html", entries=entries)

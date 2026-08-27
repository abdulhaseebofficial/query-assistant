"""Query Assistant — Flask web app.

Turns a plain-English (or Roman Urdu) question into SQL, runs it against the
built-in demo database, an uploaded CSV, or an externally connected
SQLite/PostgreSQL database, and renders the result as a table, chart, and CSV
export. See README.md for the request flow and the production checklist.
"""

import os
import re
import secrets
from datetime import datetime

from flask import Flask, Response, abort, redirect, render_template, request, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager, current_user, login_required, login_user, logout_user
from flask_wtf import CSRFProtect
from markupsafe import escape

from backend import auth, connectors, db, feedback, greeting, sql_console
from backend.config import STATIC_DIR, TEMPLATE_DIR
from backend.connectors import postgres_connector, sqlite_connector
from backend.content.learn_content import CONCEPTS, FAQS
from backend.database import DB_NAME
from backend.engines import ai_engine, rule_engine
from backend.engines.csv_engine import build_custom_query, clear_dataset, get_dataset_info, load_csv
from backend.engines.rule_engine import interpret
from backend.utils import chart_utils
from backend.utils.csv_export import build_csv

app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STATIC_DIR)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB upload cap

# Fall back to a random per-process key instead of a hardcoded default: sessions
# won't survive a restart if SECRET_KEY isn't set in the environment, but an
# attacker can no longer forge session cookies against a key baked into the source.
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
# Only marked Secure when explicitly told we're behind HTTPS — defaulting this on
# would silently break login over local http:// during development.
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("SESSION_COOKIE_SECURE", "false").strip().lower() in (
    "1", "true", "yes",
)

app.jinja_env.filters["zip"] = zip

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)

# Protects every POST/PUT/PATCH/DELETE request with a per-session token; forms
# must include {{ csrf_token() }} (auto-exposed in Jinja by CSRFProtect).
CSRFProtect(app)

# A generous global ceiling against scripted abuse, with tighter limits on the
# auth endpoints below to slow down credential-stuffing / brute-force attempts.
limiter = Limiter(get_remote_address, app=app, default_limits=["200 per minute"], storage_uri="memory://")

# Asking a question can mean a billable AI API call, and exporting re-runs the whole
# query — so the 200/minute default is far too loose for these. Uploading and
# connecting are rarer still, and each one writes to disk or opens an outbound
# connection, so they get the tightest ceiling.
QUERY_LIMIT = "30 per minute"
EXPORT_LIMIT = "20 per minute"
DATASOURCE_LIMIT = "10 per minute"


@app.after_request
def set_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # Nothing in this app uses a camera, mic, or location — say so, so a future
    # injected script can't quietly ask for them either.
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"

    # Only sent when we've been told we're behind HTTPS. Sending HSTS over plain
    # http:// during local development would pin the browser to https://localhost
    # and make the app unreachable until the user cleared the policy by hand.
    if app.config["SESSION_COOKIE_SECURE"]:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'"
    )
    return response


@app.context_processor
def inject_feedback_admin():
    """Whether to offer the "feedback received" link, which only the admin can open."""
    return {"feedback_admin": feedback.is_admin(current_user)}


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
    return db.connect(DB_NAME)


def describe_failure(user_input):
    """Explain why a question went unanswered, so the page can give real advice.

    Four situations need four different messages: the question asks for the whole
    database at once; it isn't about this data at all; it is, but it asks for
    something only a model can express and no API key is configured; or a model was
    asked and still couldn't produce a valid query. Collapsing them into one
    "couldn't tell what you're asking for" is what made the app feel broken.
    """
    text = user_input.strip().lower()
    # The same reference data interpret() checks against, so the reason given here
    # is the reason it actually refused — a product named "Laptop Pro 15" must not
    # be reported back as the question asking for "a specific number".
    conn = get_connection()
    try:
        known_names = rule_engine.reference_names(rule_engine.get_reference_data(conn))
    finally:
        conn.close()

    return {
        "on_topic": rule_engine.detect_domain(text) is not None,
        "wants_overview": rule_engine.wants_overview(text),
        "constraints": rule_engine.unsupported_constraints(text, known_names),
        "ai_available": ai_engine.is_available(),
        "provider": ai_engine.active_provider_name(),
    }


def _attachment_header(filename):
    """Build a Content-Disposition value that can't break out of the header.

    Table names come from the connected database's own schema, and SQLite happily
    allows quotes, semicolons, and newlines in them — none of which belong in a
    response header. Anything outside a conservative set is replaced.
    """
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", filename)
    # Collapse dot runs and drop leading dots so the result can't read as a
    # relative path or a hidden file wherever the browser saves it.
    safe = re.sub(r"\.{2,}", ".", safe).lstrip(".")[:100] or "results.csv"
    return f'attachment; filename="{safe}"'


def _plain(message, status=404):
    return Response(message, status=status, mimetype="text/plain")


def _csv_file(outcome, filename):
    """Send an outcome as a download, or refuse it when there's nothing in it.

    All three export routes ended with these same eight lines; the two that
    weren't serving a connected table also skipped _attachment_header.
    """
    if outcome is None or not outcome["rows"]:
        return _plain("No matching data to export.")
    return Response(
        build_csv(outcome["columns"], outcome["rows"]),
        mimetype="text/csv",
        headers={"Content-Disposition": _attachment_header(filename)},
    )


@app.template_filter("highlight")
def sql_for_display(sql, params=()):
    """Escape a query, put its parameter values back in, and colour the keywords."""
    display = str(escape(sql))
    for value in params:
        display = display.replace("?", f"<span class=\"sql-str\">'{escape(value)}'</span>", 1)
    return KEYWORD_PATTERN.sub(r'<span class="sql-kw">\1</span>', display)


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
            "dialect": dialect,
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
        "dialect": dialect,
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
            execute_fn, user_input, ai_engine.BUILTIN_SCHEMA, None, db.DIALECT, fallback_fn
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
@limiter.limit(QUERY_LIMIT)
def index():
    user_input = request.args.get("q", "").strip()
    result = None

    if user_input:
        outcome = run_query(user_input)
        if outcome is None:
            result = {"understood": False, **describe_failure(user_input)}
        else:
            outcome["understood"] = True
            outcome["sql_display"] = sql_for_display(outcome["sql"], outcome["params"])
            result = outcome
            if current_user.is_authenticated:
                auth.record_query(current_user.id, "/", user_input, outcome["sql"], outcome["engine"])

    name = current_user.username if current_user.is_authenticated else None
    return render_template(
        "index.html",
        query=user_input,
        searched=bool(user_input),
        result=result,
        examples=EXAMPLE_QUERIES,
        greeting=greeting.greet(datetime.now().hour, name),
        greeting_by_hour=greeting.phrases_by_hour(),
        greeting_name=name,
    )


@app.route("/export", methods=["GET"])
@limiter.limit(EXPORT_LIMIT)
def export():
    user_input = request.args.get("q", "").strip()
    outcome = run_query(user_input) if user_input else None
    if outcome is None:
        return _plain("Couldn't understand that question — nothing to export.")
    return _csv_file(outcome, "query_results.csv")


@app.route("/upload", methods=["GET", "POST"])
@limiter.limit(DATASOURCE_LIMIT, methods=["POST"])
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
            return build_custom_query(user_input, meta["columns"], types=meta["types"])

        outcome = _run_with_ai_fallback(
            execute_fn, user_input, schema_desc, "custom_data", db.DIALECT, fallback_fn
        )
    finally:
        conn.close()

    outcome["label_map"] = dict(zip(meta["columns"], meta["labels"], strict=True))
    outcome["chart"] = chart_utils.build_chart_data(
        outcome["columns"], outcome["rows"], outcome.pop("chart_hint")
    )
    return outcome


def get_active_source():
    """(connector, placeholder, label) for whichever external database is attached."""
    return connectors.active_source()


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
            return build_custom_query(
                user_input, table["columns"], table["name"], placeholder, types=table["types"]
            )

        outcome = _run_with_ai_fallback(
            execute_fn, user_input, schema_desc, table["name"], kind, fallback_fn
        )
    finally:
        conn.close()

    # Deliberately an identity map: these are someone else's column names, so
    # they're shown exactly as the schema spells them rather than prettified.
    outcome["label_map"] = {c: c for c in table["columns"]}
    outcome["chart"] = chart_utils.build_chart_data(
        outcome["columns"], outcome["rows"], outcome.pop("chart_hint")
    )
    return outcome


@app.route("/connect-db", methods=["GET", "POST"])
@limiter.limit(DATASOURCE_LIMIT, methods=["POST"])
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
@limiter.limit(DATASOURCE_LIMIT)
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
@limiter.limit(QUERY_LIMIT)
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
@limiter.limit(EXPORT_LIMIT)
def connect_db_table_export(table_name):
    source, placeholder, kind = get_active_source()
    table = source.get_table(table_name) if source else None
    if table is None:
        return _plain("Table not found.")

    user_input = request.args.get("q", "").strip()
    if not user_input:
        return _plain("No data to export.")

    outcome = run_connected_query(source, placeholder, kind, table, user_input)
    return _csv_file(outcome, f"{table_name}_results.csv")


@app.route("/dataset", methods=["GET"])
@limiter.limit(QUERY_LIMIT)
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
@limiter.limit(EXPORT_LIMIT)
def dataset_export():
    conn = get_connection()
    meta = get_dataset_info(conn)
    conn.close()
    if meta is None:
        return _plain("No dataset uploaded.")

    user_input = request.args.get("q", "").strip()
    if not user_input:
        return _plain("No data to export.")

    return _csv_file(run_custom_query(user_input, meta), "dataset_results.csv")


@app.route("/sql", methods=["GET", "POST"])
@limiter.limit(QUERY_LIMIT)
def sql_console_page():
    """Write and run your own SQL, against whichever source you pick.

    The form POSTs, because a query is a body of text and a long one doesn't survive
    a URL. `?sql=` also runs, so a query can be linked to or bookmarked — running a
    SELECT changes nothing, which is exactly what GET is for.

    The same validator that guards model-written SQL guards this.
    """
    conn = get_connection()
    try:
        sources = sql_console.available_sources(conn)
        chosen_key = request.form.get("source") or request.args.get("source", "")
        source = sql_console.pick_source(sources, chosen_key)

        typed = request.form.get("sql") or request.args.get("sql", "")
        result = sql_console.run(source, typed, conn) if typed.strip() else None
    finally:
        conn.close()

    if result and result.get("rows"):
        result["chart"] = chart_utils.build_chart_data(result["columns"], result["rows"])

    if result and current_user.is_authenticated and not result.get("error"):
        auth.record_query(current_user.id, "/sql", typed, result["sql"], "manual")

    return render_template(
        "sql.html",
        sources=sources,
        source=source,
        sql=typed,
        result=result,
    )


FEEDBACK_LIMIT = "5 per minute"


@app.route("/feedback", methods=["GET", "POST"])
@limiter.limit(FEEDBACK_LIMIT, methods=["POST"])
def feedback_page():
    """Say what's wrong, or missing, or working.

    Open to anyone: the people most able to say a thing is confusing are the ones
    who haven't signed up. The email box is optional and only there so a reply is
    possible — nothing is sent to it automatically.
    """
    sent = False
    error = None

    if request.method == "POST":
        message = request.form.get("message", "")
        if not message.strip():
            error = "Please write something first."
        else:
            sent = feedback.save(
                message,
                email=request.form.get("email"),
                user_id=current_user.id if current_user.is_authenticated else None,
                page=request.form.get("page"),
            )

    return render_template("feedback.html", sent=sent, error=error,
                           came_from=request.args.get("from", ""))


@app.route("/feedback/all", methods=["GET"])
@login_required
def feedback_all():
    """Read what people sent. Only the account named by ADMIN_USERNAME."""
    if not feedback.is_admin(current_user):
        abort(404)
    return render_template("feedback_all.html", entries=feedback.recent(),
                           total=feedback.count())


@app.route("/learn", methods=["GET"])
def learn():
    grouped = {
        level: [c for c in CONCEPTS if c["level"] == level]
        for level in ("Basic", "Intermediate", "Advanced")
    }
    return render_template("learn.html", grouped=grouped, faqs=FAQS)


@app.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
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
        elif len(password) < 8:
            error = "Password must be at least 8 characters."
        else:
            try:
                user = auth.create_user(username, email, password)
                login_user(user)
                return redirect(url_for("index"))
            except ValueError as exc:
                error = str(exc)

    return render_template("register.html", error=error)


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
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

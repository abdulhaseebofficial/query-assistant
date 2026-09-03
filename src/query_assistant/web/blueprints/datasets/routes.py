"""Uploaded CSV and connected-database routes."""

from flask import Blueprint, redirect, render_template, request, url_for
from flask_login import current_user

from query_assistant.extensions import limiter
from query_assistant.infrastructure.database import connectors
from query_assistant.infrastructure.database.connectors import postgresql, sqlite
from query_assistant.repositories import user_repository
from query_assistant.services import dataset_service, query_service
from query_assistant.web.presentation import csv_file, plain, sql_for_display

blueprint = Blueprint("datasets", __name__)


@blueprint.route("/upload", methods=["GET", "POST"], endpoint="upload")
@limiter.limit("10 per minute", methods=["POST"])
def upload():
    error = None
    if request.method == "POST":
        file = request.files.get("file")
        name = request.form.get("dataset_name", "").strip() or "My Dataset"
        if not file or file.filename == "":
            error = "Please choose a CSV file first."
        elif not file.filename.lower().endswith(".csv"):
            error = "Only .csv files are supported."
        else:
            try:
                dataset_service.upload_dataset(file.stream, name)
                return redirect(url_for("datasets.dataset"))
            except ValueError as exc:
                error = str(exc)
            except Exception:
                error = "Something went wrong reading that file. Please check it's a valid CSV and try again."
    return render_template("datasets/upload.html", error=error, current=dataset_service.get_current_dataset())


@blueprint.post("/dataset/clear", endpoint="dataset_clear")
def dataset_clear():
    dataset_service.remove_dataset()
    return redirect(url_for("datasets.upload"))


@blueprint.get("/dataset", endpoint="dataset")
@limiter.limit("30 per minute")
def dataset():
    meta = dataset_service.get_current_dataset()
    if meta is None:
        return redirect(url_for("datasets.upload"))
    question = request.args.get("q", "").strip()
    result = None
    if question:
        result = dataset_service.query_dataset(question, meta)
        result["sql_display"] = sql_for_display(result["sql"], result["params"])
        if current_user.is_authenticated:
            user_repository.record_query(current_user.id, "/dataset", question, result["sql"], result["engine"])
    return render_template("datasets/dataset.html", meta=meta, query=question, searched=bool(question), result=result)


@blueprint.get("/dataset/export", endpoint="dataset_export")
@limiter.limit("20 per minute")
def dataset_export():
    meta = dataset_service.get_current_dataset()
    if meta is None:
        return plain("No dataset uploaded.")
    question = request.args.get("q", "").strip()
    if not question:
        return plain("No data to export.")
    return csv_file(dataset_service.query_dataset(question, meta), "dataset_results.csv")


@blueprint.route("/connect-db", methods=["GET", "POST"], endpoint="connect_db")
@limiter.limit("10 per minute", methods=["POST"])
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
                sqlite.save_connected_db(file.stream, file.filename)
                postgresql.clear_connection()
                return redirect(url_for("datasets.connect_db"))
            except ValueError as exc:
                error = str(exc)
            except Exception:
                error = "Something went wrong reading that file. Please check it's a valid SQLite database."
    source, _, kind = connectors.active_source()
    return render_template("datasets/connect.html", error=error, tables=source.list_tables() if source else [],
                           connected=source is not None, kind=kind)


@blueprint.post("/connect-db/postgres", endpoint="connect_db_postgres")
@limiter.limit("10 per minute")
def connect_db_postgres():
    error = None
    try:
        postgresql.save_connection(request.form.get("dsn", ""))
        sqlite.clear_connection()
        return redirect(url_for("datasets.connect_db"))
    except ValueError as exc:
        error = str(exc)
    except Exception:
        error = "Something went wrong connecting to that database. Please check the connection string."
    source, _, kind = connectors.active_source()
    return render_template("datasets/connect.html", error=error, tables=source.list_tables() if source else [],
                           connected=source is not None, kind=kind)


@blueprint.post("/connect-db/clear", endpoint="connect_db_clear")
def connect_db_clear():
    sqlite.clear_connection()
    postgresql.clear_connection()
    return redirect(url_for("datasets.connect_db"))


@blueprint.get("/connect-db/<table_name>", endpoint="connect_db_table")
@limiter.limit("30 per minute")
def connect_db_table(table_name):
    source, placeholder, kind = connectors.active_source()
    table = source.get_table(table_name) if source else None
    if table is None:
        return redirect(url_for("datasets.connect_db"))
    question = request.args.get("q", "").strip()
    result = query_service.run_table(question, table, source, placeholder, kind) if question else None
    if result:
        result["sql_display"] = sql_for_display(result["sql"], result["params"])
        if current_user.is_authenticated:
            user_repository.record_query(current_user.id, f"/connect-db/{table_name}", question,
                                         result["sql"], result["engine"])
    return render_template("datasets/connect_table.html", table=table, query=question,
                           searched=bool(question), result=result)


@blueprint.get("/connect-db/<table_name>/export", endpoint="connect_db_table_export")
@limiter.limit("20 per minute")
def connect_db_table_export(table_name):
    source, placeholder, kind = connectors.active_source()
    table = source.get_table(table_name) if source else None
    if table is None:
        return plain("Table not found.")
    question = request.args.get("q", "").strip()
    if not question:
        return plain("No data to export.")
    return csv_file(query_service.run_table(question, table, source, placeholder, kind), f"{table_name}_results.csv")

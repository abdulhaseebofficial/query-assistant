"""Read-only SQL console route."""

from flask import Blueprint, render_template, request
from flask_login import current_user

from query_assistant.extensions import limiter
from query_assistant.repositories import user_repository
from query_assistant.services import query_service, sql_console_service
from query_assistant.utilities import charts

blueprint = Blueprint("sql_console", __name__)


@blueprint.route("/sql", methods=["GET", "POST"], endpoint="sql_console_page")
@limiter.limit("30 per minute")
def sql_console_page():
    conn = query_service.get_connection()
    try:
        sources = sql_console_service.available_sources(conn)
        chosen = request.form.get("source") or request.args.get("source", "")
        source = sql_console_service.pick_source(sources, chosen)
        typed = request.form.get("sql") or request.args.get("sql", "")
        result = sql_console_service.run(source, typed, conn) if typed.strip() else None
    finally:
        conn.close()
    if result and result.get("rows"):
        result["chart"] = charts.build_chart_data(result["columns"], result["rows"])
    if result and current_user.is_authenticated and not result.get("error"):
        user_repository.record_query(current_user.id, "/sql", typed, result["sql"], "manual")
    return render_template("sql_console/index.html", sources=sources, source=source, sql=typed, result=result)

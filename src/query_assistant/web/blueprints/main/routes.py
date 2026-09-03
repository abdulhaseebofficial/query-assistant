"""Home-page query routes."""

from datetime import datetime

from flask import Blueprint, Response, render_template, request
from flask_login import current_user

from query_assistant.extensions import limiter
from query_assistant.repositories import user_repository
from query_assistant.services import greeting_service, query_service
from query_assistant.web.presentation import csv_file, plain, sql_for_display

blueprint = Blueprint("main", __name__)
EXAMPLE_QUERIES = ["employees in the IT department", "highest paid employees",
                   "products low on stock", "customers in Lahore",
                   "total revenue this month", "pending orders"]


@blueprint.get("/favicon.ico", endpoint="favicon")
def favicon():
    return Response(status=204)


@blueprint.get("/", endpoint="index")
@limiter.limit("30 per minute")
def index():
    question = request.args.get("q", "").strip()
    result = None
    if question:
        outcome = query_service.run_builtin(question)
        if outcome is None:
            result = {"understood": False, **query_service.describe_failure(question)}
        else:
            outcome["understood"] = True
            outcome["sql_display"] = sql_for_display(outcome["sql"], outcome["params"])
            result = outcome
            if current_user.is_authenticated:
                user_repository.record_query(current_user.id, "/", question, outcome["sql"], outcome["engine"])
    name = current_user.username if current_user.is_authenticated else None
    return render_template("main/index.html", query=question, searched=bool(question), result=result,
                           examples=EXAMPLE_QUERIES,
                           greeting=greeting_service.greet(datetime.now().hour, name),
                           greeting_by_hour=greeting_service.phrases_by_hour(), greeting_name=name)


@blueprint.get("/export", endpoint="export")
@limiter.limit("20 per minute")
def export():
    question = request.args.get("q", "").strip()
    outcome = query_service.run_builtin(question) if question else None
    if outcome is None:
        return plain("Couldn't understand that question â€” nothing to export.")
    return csv_file(outcome, "query_results.csv")

"""Feedback submission and administration routes."""

from flask import Blueprint, abort, render_template, request
from flask_login import current_user, login_required

from query_assistant.extensions import limiter
from query_assistant.repositories import feedback_repository
from query_assistant.services import feedback_service

blueprint = Blueprint("feedback", __name__)


@blueprint.route("/feedback", methods=["GET", "POST"], endpoint="feedback_page")
@limiter.limit("5 per minute", methods=["POST"])
def feedback_page():
    sent, error = False, None
    if request.method == "POST":
        try:
            sent = feedback_service.submit(
                request.form.get("message", ""), email=request.form.get("email"),
                user_id=current_user.id if current_user.is_authenticated else None,
                page=request.form.get("page"),
            )
        except ValueError as exc:
            error = str(exc)
    return render_template("feedback/form.html", sent=sent, error=error, came_from=request.args.get("from", ""))


@blueprint.get("/feedback/all", endpoint="feedback_all")
@login_required
def feedback_all():
    if not feedback_repository.is_admin(current_user):
        abort(404)
    return render_template("feedback/list.html", entries=feedback_repository.recent(),
                           total=feedback_repository.count())

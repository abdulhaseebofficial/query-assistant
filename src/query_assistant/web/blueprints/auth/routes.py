"""Authentication and query-history routes."""

from flask import Blueprint, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from query_assistant.extensions import limiter
from query_assistant.repositories import user_repository
from query_assistant.services import auth_service

blueprint = Blueprint("auth", __name__)


@blueprint.route("/register", methods=["GET", "POST"], endpoint="register")
@limiter.limit("5 per minute", methods=["POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    error = None
    if request.method == "POST":
        try:
            user = auth_service.register(request.form.get("username", ""), request.form.get("email", ""),
                                         request.form.get("password", ""))
            login_user(user)
            return redirect(url_for("main.index"))
        except ValueError as exc:
            error = str(exc)
    return render_template("auth/register.html", error=error)


@blueprint.route("/login", methods=["GET", "POST"], endpoint="login")
@limiter.limit("10 per minute", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    error = None
    if request.method == "POST":
        user = auth_service.authenticate(request.form.get("username", ""), request.form.get("password", ""))
        if user is None:
            error = "Incorrect username or password."
        else:
            login_user(user)
            return redirect(url_for("main.index"))
    return render_template("auth/login.html", error=error)


@blueprint.post("/logout", endpoint="logout")
def logout():
    logout_user()
    return redirect(url_for("main.index"))


@blueprint.get("/history", endpoint="history")
@login_required
def history():
    return render_template("auth/history.html", entries=user_repository.get_history(current_user.id))

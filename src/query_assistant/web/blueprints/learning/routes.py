"""SQL learning routes."""

from flask import Blueprint, render_template

from query_assistant.content.learning import CONCEPTS, FAQS

blueprint = Blueprint("learning", __name__)


@blueprint.get("/learn", endpoint="learn")
def learn():
    grouped = {level: [concept for concept in CONCEPTS if concept["level"] == level]
               for level in ("Basic", "Intermediate", "Advanced")}
    return render_template("learning/index.html", grouped=grouped, faqs=FAQS)

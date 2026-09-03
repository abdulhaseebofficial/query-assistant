"""Central HTTP error handlers."""

from flask import render_template


def file_too_large(_exc):
    from query_assistant.services.dataset_service import get_current_dataset

    return render_template(
        "datasets/upload.html",
        error="That file is too large. Please keep uploads under 5 MB.",
        current=get_current_dataset(),
    ), 413


def register_error_handlers(app):
    app.register_error_handler(413, file_too_large)

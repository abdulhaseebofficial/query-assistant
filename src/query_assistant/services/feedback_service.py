"""Feedback submission use cases."""

from query_assistant.exceptions import ValidationError
from query_assistant.repositories import feedback_repository


def submit(message, email=None, user_id=None, page=None):
    if not (message or "").strip():
        raise ValidationError("Please write something first.")
    return feedback_repository.save(message, email=email, user_id=user_id, page=page)

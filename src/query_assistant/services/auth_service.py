"""Authentication validation and account use cases."""

import re

from query_assistant.exceptions import ValidationError
from query_assistant.repositories import user_repository


def register(username, email, password):
    username, email = username.strip(), email.strip()
    if not re.match(r"^[a-zA-Z0-9_]{3,30}$", username):
        raise ValidationError("Username must be 3-30 characters: letters, numbers, underscores only.")
    if "@" not in email or "." not in email:
        raise ValidationError("Please enter a valid email address.")
    if len(password) < 8:
        raise ValidationError("Password must be at least 8 characters.")
    return user_repository.create_user(username, email, password)


def authenticate(username, password):
    return user_repository.verify_password(username.strip(), password)

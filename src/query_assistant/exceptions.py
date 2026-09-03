"""Application exceptions that may be translated at the web boundary."""


class ValidationError(ValueError):
    """Input failed explicit application validation."""

"""Shared rendering and response helpers."""

import re

from flask import Response
from flask_login import current_user
from markupsafe import escape

from query_assistant.repositories import feedback_repository
from query_assistant.utilities.csv_export import build_csv

SQL_KEYWORDS = ("LEFT JOIN", "GROUP BY", "ORDER BY", "SELECT", "FROM", "WHERE", "JOIN",
                "ON", "AND", "OR", "LIMIT", "COUNT", "SUM", "AVG", "AS", "DESC", "ASC")
KEYWORD_PATTERN = re.compile(r"\b(" + "|".join(re.escape(k) for k in SQL_KEYWORDS) + r")\b")


def inject_feedback_admin():
    return {"feedback_admin": feedback_repository.is_admin(current_user)}


def sql_for_display(sql, params=()):
    display = str(escape(sql))
    for value in params:
        display = display.replace("?", f"<span class=\"sql-str\">'{escape(value)}'</span>", 1)
    return KEYWORD_PATTERN.sub(r'<span class="sql-kw">\1</span>', display)


def commas_filter(value):
    try:
        if isinstance(value, float):
            value = int(value) if value.is_integer() else round(value, 2)
        return f"{value:,}"
    except (ValueError, TypeError):
        return value


def plain(message, status=404):
    return Response(message, status=status, mimetype="text/plain")


def attachment_header(filename):
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", filename)
    safe = re.sub(r"\.{2,}", ".", safe).lstrip(".")[:100] or "results.csv"
    return f'attachment; filename="{safe}"'


def csv_file(outcome, filename):
    if outcome is None or not outcome["rows"]:
        return plain("No matching data to export.")
    return Response(build_csv(outcome["columns"], outcome["rows"]), mimetype="text/csv",
                    headers={"Content-Disposition": attachment_header(filename)})

"""Framework-independent guardrails for every generated or manually entered query."""

import re

FORBIDDEN_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|ATTACH|DETACH|PRAGMA|CREATE|REPLACE|VACUUM|GRANT|REVOKE)\b",
    re.IGNORECASE,
)
BUILTIN_TABLES = frozenset({"departments", "employees", "products", "customers", "orders"})
_TABLE_REF_PATTERN = re.compile(r'\b(?:FROM|JOIN)\s+"?([A-Za-z_][A-Za-z0-9_]*)"?', re.IGNORECASE)


def referenced_tables(sql):
    return {name.lower() for name in _TABLE_REF_PATTERN.findall(sql)}


def check_select(sql, allowed_tables):
    """Return a normalized read-only statement or a user-facing refusal reason."""
    if not sql or not sql.strip():
        return None, "There's no query here."
    cleaned = sql.strip().rstrip(";").strip()
    if not cleaned:
        return None, "There's no query here."
    if ";" in cleaned:
        return None, "Only one statement at a time — remove the semicolon in the middle."
    if not re.match(r"^\s*SELECT\b", cleaned, re.IGNORECASE):
        return None, "Only SELECT queries can run here. This one starts with something else."
    forbidden = FORBIDDEN_KEYWORDS.search(cleaned)
    if forbidden:
        return None, f"{forbidden.group(0).upper()} would change the data. Only read-only queries can run here."
    allowed = {table.lower() for table in allowed_tables}
    referenced = referenced_tables(cleaned)
    if not referenced:
        return None, "No table found in the query — a SELECT here has to read from one."
    unknown = sorted(referenced - allowed)
    if unknown:
        return None, f"No table called '{unknown[0]}' here. Available: {', '.join(sorted(allowed))}."
    return cleaned + ";", None


def validate_select(sql, allowed_tables):
    statement, _reason = check_select(sql, allowed_tables)
    return statement

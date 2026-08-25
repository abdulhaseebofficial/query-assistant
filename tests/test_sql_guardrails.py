"""The AI engine executes model-generated SQL, so _validate_select() is the
security boundary between "the model said so" and "the app ran it".
"""

import pytest

from backend.engines.ai_engine import BUILTIN_TABLES, _validate_select


def validate(sql):
    return _validate_select(sql, BUILTIN_TABLES)


def test_a_plain_select_is_accepted_and_normalised():
    assert validate("SELECT name FROM employees") == "SELECT name FROM employees;"


def test_a_trailing_semicolon_is_preserved_not_doubled():
    assert validate("SELECT name FROM employees;") == "SELECT name FROM employees;"


def test_joins_across_whitelisted_tables_are_accepted():
    sql = "SELECT e.name, d.name FROM employees e JOIN departments d ON e.department_id = d.id"
    assert validate(sql) is not None


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM employees",
        "UPDATE employees SET salary = 0",
        "INSERT INTO employees (name) VALUES ('x')",
        "DROP TABLE employees",
        "ALTER TABLE employees ADD COLUMN x TEXT",
        "PRAGMA table_info(employees)",
        "ATTACH DATABASE '/etc/passwd' AS leak",
        "CREATE TABLE evil (id INT)",
        "VACUUM",
    ],
)
def test_write_and_admin_statements_are_rejected(sql):
    assert validate(sql) is None


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM employees; DROP TABLE employees",
        "SELECT * FROM employees; SELECT * FROM users",
    ],
)
def test_stacked_statements_are_rejected(sql):
    assert validate(sql) is None


@pytest.mark.parametrize("table", ["users", "query_history", "sqlite_master"])
def test_tables_outside_the_whitelist_are_rejected(table):
    """`users` and `query_history` live in the same database file as the demo
    data — the whitelist is the only thing keeping generated SQL away from them."""
    assert validate(f"SELECT * FROM {table}") is None


def test_a_join_that_smuggles_in_a_non_whitelisted_table_is_rejected():
    sql = "SELECT e.name, u.password_hash FROM employees e JOIN users u ON e.id = u.id"
    assert validate(sql) is None


@pytest.mark.parametrize("sql", ["", "   ", None])
def test_empty_input_is_rejected(sql):
    assert validate(sql) is None


def test_a_select_referencing_no_table_at_all_is_rejected():
    assert validate("SELECT 1") is None


def test_generate_sql_returns_none_without_an_api_key(monkeypatch):
    """No key configured means the caller must fall back to the rule engine."""
    import backend.engines.ai_engine as ai_engine

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(ai_engine, "_client", None)
    monkeypatch.setattr(ai_engine, "_client_checked", False)

    assert ai_engine.generate_sql("employees in IT", ai_engine.BUILTIN_SCHEMA) is None

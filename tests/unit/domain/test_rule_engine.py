"""The rule-based engine is the fallback that runs when no ANTHROPIC_API_KEY is
set, so it has to work on its own for the demo schema."""

import pytest

from query_assistant.domain.query.rule_engine import detect_aggregate, detect_domain, interpret


@pytest.mark.parametrize(
    "question, expected_domain",
    [
        ("employees in the IT department", "employees"),
        ("show me all departments", "departments"),
        ("products low on stock", "products"),
        ("customers in Lahore", "customers"),
        ("pending orders", "orders"),
    ],
)
def test_detect_domain_routes_question_to_the_right_table(question, expected_domain):
    assert detect_domain(question) == expected_domain


def test_detect_domain_returns_none_for_an_unrelated_question():
    assert detect_domain("what is the weather in karachi") is None


@pytest.mark.parametrize(
    "question, expected",
    [
        ("how many employees are there", "count"),
        ("total revenue this month", "sum"),
        ("average salary in sales", "avg"),
        ("list all employees", None),
    ],
)
def test_detect_aggregate(question, expected):
    assert detect_aggregate(question) == expected


def test_interpret_builds_a_runnable_select(conn):
    result = interpret("employees in the IT department", conn)

    assert result is not None
    assert result["sql"].lstrip().upper().startswith("SELECT")
    assert result["explanation"]

    rows = conn.execute(result["sql"], result["params"]).fetchall()
    assert rows, "the seeded demo database should contain IT employees"


def test_interpret_uses_bound_parameters_not_string_interpolation(conn):
    """User input must never be concatenated into the SQL text."""
    result = interpret("customers in Lahore", conn)

    assert result is not None
    assert "Lahore" not in result["sql"]
    assert "Lahore" in result["params"]


def test_interpret_returns_none_when_it_cannot_understand(conn):
    assert interpret("tell me a joke", conn) is None


def test_aggregate_query_returns_a_single_value(conn):
    result = interpret("how many employees are there", conn)

    assert result is not None
    assert result["aggregate"] == "count"
    rows = conn.execute(result["sql"], result["params"]).fetchall()
    assert len(rows) == 1


@pytest.mark.parametrize(
    "question, expected_column",
    [
        ("average salary in the IT department", "average"),
        ("total salary of all employees", "total"),
    ],
)
def test_salary_aggregates_produce_valid_sql(conn, question, expected_column):
    result = interpret(question, conn)

    assert result is not None
    rows = conn.execute(result["sql"], result["params"]).fetchall()
    assert len(rows) == 1
    assert rows[0][expected_column] is not None

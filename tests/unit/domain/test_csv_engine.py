"""Uploaded CSVs become real SQLite tables, so column names coming from an
arbitrary file have to be made safe before they reach a CREATE TABLE."""

import io

import pytest

from query_assistant.domain.query.csv_engine import (
    build_custom_query,
    clear_dataset,
    get_dataset_info,
    infer_type,
    load_csv,
    sample_rows,
    sanitize_column_name,
)

SAMPLE_CSV = b"""City,Sales Total,Units Sold
Karachi,15000,120
Lahore,22500,180
Islamabad,9800,75
"""


def test_sanitize_strips_characters_that_would_break_sql():
    used = set()
    assert sanitize_column_name("Sales Total ($)", 0, used) == "sales_total"


def test_sanitize_prefixes_names_that_start_with_a_digit():
    used = set()
    assert sanitize_column_name("2024 revenue", 0, used) == "col_2024_revenue"


def test_sanitize_falls_back_to_the_column_index_when_nothing_survives():
    used = set()
    assert sanitize_column_name("!!!", 3, used) == "col_3"


def test_sanitize_deduplicates_colliding_headers():
    used = set()
    first = sanitize_column_name("Name", 0, used)
    second = sanitize_column_name("name", 1, used)
    assert (first, second) == ("name", "name_2")


@pytest.mark.parametrize(
    "values, expected",
    [
        (["1", "2", "3"], "INTEGER"),
        (["1.5", "2", "3.25"], "REAL"),
        (["a", "1", "b"], "TEXT"),
        ([], "TEXT"),
    ],
)
def test_infer_type(values, expected):
    assert infer_type(values) == expected


def test_sample_rows_never_returns_more_than_requested():
    rows = list(range(100))
    assert len(sample_rows(rows, 10)) == 10
    assert sample_rows([1, 2], 10) == [1, 2]


def test_load_csv_round_trips_through_the_database(conn):
    info = load_csv(io.BytesIO(SAMPLE_CSV), conn, "Regional Sales")

    assert info is not None
    stored = get_dataset_info(conn)
    assert stored is not None
    assert stored["name"] == "Regional Sales"

    clear_dataset(conn)
    assert get_dataset_info(conn) is None


def test_build_custom_query_binds_search_terms_as_parameters():
    sql, params, _explanation, is_count = build_custom_query("karachi", ["city", "sales_total"])

    assert sql.lstrip().upper().startswith("SELECT")
    assert "karachi" not in sql.lower()
    assert params == ["%karachi%", "%karachi%"]
    assert is_count is False


def test_build_custom_query_detects_a_count_question():
    sql, _params, _explanation, is_count = build_custom_query("how many rows", ["city"])

    assert is_count is True
    assert "COUNT(*)" in sql


def test_build_custom_query_ignores_stopwords():
    """"show me the" carries no filter â€” it should not become a LIKE clause."""
    sql, params, _explanation, _is_count = build_custom_query("show me the data", ["city"])

    assert "WHERE" not in sql
    assert params == []

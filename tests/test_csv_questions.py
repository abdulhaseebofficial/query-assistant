"""Questions asked about an uploaded CSV.

The demo schema has an engine that knows what a salary is. An uploaded spreadsheet
has no such engine — csv_engine only knows the column names and their types — so the
same question has to be answered from much less. It was answering badly:

    sab dikhao          -> 0 rows, "Lists matching rows"
    revenue kitna hai   -> 0 rows, "Lists matching rows"
    highest revenue     -> 0 rows, "Lists matching rows"

Every one of those searched the *values* for words that were never values. "sab"
isn't in the data, and "revenue" is the name of a column rather than something stored
in one. Zero rows under "Lists matching rows" reads as "your data is empty", which is
a worse answer than an error.
"""

import io

import pytest

from backend.engines.csv_engine import (
    _column_tokens,
    _names_a_column,
    build_custom_query,
    get_dataset_info,
    load_csv,
)

CSV = b"""City,Product,Units Sold,Revenue
Karachi,Laptop,120,150000
Lahore,Mouse,300,7500
Karachi,Monitor,45,14400
Islamabad,Laptop,60,75000
"""

TOTAL_REVENUE = 150000 + 7500 + 14400 + 75000
ROW_COUNT = 4


@pytest.fixture
def dataset(conn):
    load_csv(io.BytesIO(CSV), conn, "Sales")
    conn.commit()
    return get_dataset_info(conn)


def run(conn, dataset, question):
    sql, params, explanation, is_aggregate = build_custom_query(
        question, dataset["columns"], types=dataset["types"]
    )
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    return rows, explanation, is_aggregate


class TestColumnNamesAreNotSearchedAsValues:
    def test_a_column_name_is_recognised(self, dataset):
        tokens = _column_tokens(dataset["columns"])
        for word in ("city", "product", "revenue", "units", "sold", "units_sold"):
            assert _names_a_column(word, tokens)

    @pytest.mark.parametrize("word", ["products", "cities"])
    def test_plurals_are_recognised_too(self, dataset, word):
        """A column headed "Product" gets asked about as "products" at least as often."""
        assert _names_a_column(word, _column_tokens(dataset["columns"]))

    def test_an_actual_value_is_not_mistaken_for_a_column(self, dataset):
        assert not _names_a_column("karachi", _column_tokens(dataset["columns"]))


class TestShowEverything:
    @pytest.mark.parametrize(
        "question", ["sab dikhao", "show me everything", "sara data dikhao", "show all"]
    )
    def test_asking_for_the_whole_table_returns_the_whole_table(self, conn, dataset, question):
        rows, explanation, _ = run(conn, dataset, question)

        assert len(rows) == ROW_COUNT
        assert "every row" in explanation

    def test_a_real_search_term_still_filters(self, conn, dataset):
        rows, _explanation, _ = run(conn, dataset, "karachi")
        assert len(rows) == 2


class TestAggregates:
    def test_totalling_a_named_column(self, conn, dataset):
        rows, explanation, is_aggregate = run(conn, dataset, "total revenue")

        assert is_aggregate
        assert rows[0]["total"] == TOTAL_REVENUE
        assert "total revenue" in explanation

    def test_averaging_a_named_column(self, conn, dataset):
        rows, _explanation, _ = run(conn, dataset, "average revenue")
        assert rows[0]["average"] == pytest.approx(TOTAL_REVENUE / ROW_COUNT)

    def test_how_much_is_a_sum_not_a_count(self, conn, dataset):
        """"revenue kitna hai" asks how much, and "kitna" is a counting word — but
        the question named an amount, so it's a total."""
        rows, explanation, _ = run(conn, dataset, "revenue kitna hai")

        assert rows[0]["total"] == TOTAL_REVENUE
        assert "total" in explanation

    def test_how_many_is_still_a_count_when_no_amount_is_named(self, conn, dataset):
        for question in ("kitne rows hain", "how many rows", "kitne products hain", "how many cities"):
            rows, _explanation, _ = run(conn, dataset, question)
            assert rows[0]["count"] == ROW_COUNT, question

    def test_a_multi_word_column_can_be_totalled(self, conn, dataset):
        rows, explanation, _ = run(conn, dataset, "total units sold")

        assert rows[0]["total"] == 120 + 300 + 45 + 60
        assert "units sold" in explanation

    def test_a_filter_and_an_aggregate_combine(self, conn, dataset):
        rows, _explanation, _ = run(conn, dataset, "karachi ka total revenue")
        assert rows[0]["total"] == 150000 + 14400


class TestRanking:
    def test_highest_returns_the_top_rows_in_order(self, conn, dataset):
        rows, explanation, _ = run(conn, dataset, "highest revenue")

        assert rows[0]["revenue"] == 150000
        assert [r["revenue"] for r in rows] == sorted((r["revenue"] for r in rows), reverse=True)
        assert "highest revenue" in explanation

    def test_lowest_reverses_the_order(self, conn, dataset):
        rows, _explanation, _ = run(conn, dataset, "lowest revenue")
        assert rows[0]["revenue"] == 7500

    @pytest.mark.parametrize("question", ["highest revenue sirf aik", "highest revenue only one"])
    def test_asking_for_one_returns_one(self, conn, dataset, question):
        rows, explanation, _ = run(conn, dataset, question)

        assert len(rows) == 1
        assert rows[0]["revenue"] == 150000
        assert "The row with" in explanation

    def test_roman_urdu_ranking(self, conn, dataset):
        rows, _explanation, _ = run(conn, dataset, "sabse zyada revenue")
        assert rows[0]["revenue"] == 150000

    def test_ranking_beats_the_sum_when_both_could_match(self, conn, dataset):
        """"revenue" alone used to read as "total the revenue", which turned every
        ranking question into a single number."""
        rows, explanation, is_aggregate = run(conn, dataset, "highest revenue")

        assert not is_aggregate
        assert "Adds up" not in explanation

    def test_a_non_numeric_column_is_not_ranked(self, conn, dataset):
        """There's no meaningful "highest city"; it falls back to a search."""
        _rows, explanation, _ = run(conn, dataset, "highest city")
        assert "highest city" not in explanation


class TestSearchStillWorks:
    @pytest.mark.parametrize(
        "question, expected", [("karachi", 2), ("laptop", 2), ("lahore", 1), ("karachi ka data", 2)]
    )
    def test_values_are_matched(self, conn, dataset, question, expected):
        rows, _explanation, _ = run(conn, dataset, question)
        assert len(rows) == expected

    def test_search_terms_are_bound_not_interpolated(self, dataset):
        sql, params, _explanation, _ = build_custom_query(
            "karachi", dataset["columns"], types=dataset["types"]
        )
        assert "karachi" not in sql.lower()
        assert any("karachi" in str(p) for p in params)

    def test_a_term_matching_nothing_returns_nothing(self, conn, dataset):
        rows, _explanation, _ = run(conn, dataset, "peshawar")
        assert rows == []


class TestWithoutColumnTypes:
    """app.py has the types, but the signature keeps them optional — without them the
    builder must still work, just without the aggregate and ranking readings."""

    def test_a_search_still_works(self, conn, dataset):
        sql, params, _explanation, _ = build_custom_query("karachi", dataset["columns"])
        assert len(conn.execute(sql, params).fetchall()) == 2

    def test_an_aggregate_question_degrades_to_a_listing(self, conn, dataset):
        sql, params, _explanation, is_aggregate = build_custom_query(
            "total revenue", dataset["columns"]
        )
        assert not is_aggregate
        conn.execute(sql, params).fetchall()


class TestTheStreamTheRouteActuallyGets:
    """Werkzeug hands the upload route a SpooledTemporaryFile, not a BytesIO.

    Before Python 3.11 that isn't an io.IOBase and has no readable(), so wrapping
    it in io.TextIOWrapper raised AttributeError — every upload failed on 3.10 and
    passed on every other version. The tests all used BytesIO and never saw it.
    """

    def _spooled(self, data):
        import tempfile

        stream = tempfile.SpooledTemporaryFile()
        stream.write(data)
        stream.seek(0)
        return stream

    def test_a_spooled_file_loads(self, conn):
        info = load_csv(self._spooled(CSV), conn, "Spooled")

        assert info["row_count"] == ROW_COUNT
        assert info["name"] == "Spooled"

    def test_a_bytes_stream_still_loads(self, conn):
        assert load_csv(io.BytesIO(CSV), conn, "Bytes")["row_count"] == ROW_COUNT

    def test_a_byte_order_mark_is_stripped(self, conn):
        """Spreadsheets export UTF-8 with a BOM; it must not become part of a name."""
        info = load_csv(self._spooled(b"\xef\xbb\xbf" + CSV), conn, "BOM")
        assert info["columns"][0] == "city"

    def test_undecodable_bytes_do_not_raise(self, conn):
        """A mislabelled file should give a usable table, not a stack trace."""
        info = load_csv(self._spooled(b"City,Note\nKarachi,\xff\xfe bad\n"), conn, "Bad")
        assert info["row_count"] == 1

    def test_an_empty_file_is_reported_not_crashed(self, conn):
        with pytest.raises(ValueError, match="empty"):
            load_csv(self._spooled(b""), conn, "Empty")

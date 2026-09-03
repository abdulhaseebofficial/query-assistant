"""Work that grows with the size of the data, on paths that run per request.

Neither of these was slow enough to notice against the demo database â€” five tables
and eighteen employees hides a lot. Against a connected database of any real size
they were the difference between an answer and a timeout, so the counts are pinned
here rather than left to be rediscovered.
"""

import sqlite3

import pytest


class CountingConnection(sqlite3.Connection):
    """A connection that records how many statements it was asked to run."""

    count = 0

    def execute(self, *args, **kwargs):
        CountingConnection.count += 1
        return super().execute(*args, **kwargs)

    @classmethod
    def reset(cls):
        cls.count = 0


class TestReferenceDataIsOneQuery:
    """rule_engine needs five lists of names to match a question against. Fetching
    them one query at a time made the database the most expensive part of answering."""

    def test_a_single_round_trip(self, test_database):
        from query_assistant.domain.query.rule_engine import get_reference_data

        conn = sqlite3.connect(test_database, factory=CountingConnection)
        conn.row_factory = sqlite3.Row
        try:
            CountingConnection.reset()
            get_reference_data(conn)
            assert CountingConnection.count == 1
        finally:
            conn.close()

    def test_every_list_is_still_returned(self, conn):
        from query_assistant.domain.query.rule_engine import REFERENCE_KINDS, get_reference_data

        data = get_reference_data(conn)

        assert set(data) == set(REFERENCE_KINDS)
        assert "IT" in data["departments"]
        assert "Lahore" in data["cities"]
        assert any("Laptop" in name for name in data["product_names"])

    def test_the_lists_are_not_cached_across_a_change(self, conn):
        """A department added a moment ago has to be matchable now."""
        from query_assistant.domain.query.rule_engine import get_reference_data

        conn.execute(
            "INSERT INTO departments (name, location, manager_name) VALUES (?, ?, ?)",
            ("Legal", "Karachi", "Someone"),
        )
        conn.commit()
        try:
            assert "Legal" in get_reference_data(conn)["departments"]
        finally:
            conn.execute("DELETE FROM departments WHERE name = 'Legal'")
            conn.commit()


class TestDescribingOneTableDoesNotTouchTheOthers:
    """get_table() runs before every question and every export against a connected
    database. It used to go through list_tables(), so answering one question meant
    a COUNT(*) over every table in the database first."""

    @pytest.fixture
    def connected_db(self, tmp_path, monkeypatch):
        import query_assistant.infrastructure.database.connectors.sqlite as sqlite_connector

        def build(table_count):
            path = tmp_path / f"connected_{table_count}.db"
            setup = sqlite3.connect(path)
            for i in range(table_count):
                setup.execute(f"CREATE TABLE t{i:02d} (id INTEGER, name TEXT, amount REAL)")
                setup.executemany(
                    f"INSERT INTO t{i:02d} VALUES (?, ?, ?)",
                    [(n, f"row{n}", n * 1.5) for n in range(50)],
                )
            setup.commit()
            setup.close()

            def connect():
                conn = sqlite3.connect(path, factory=CountingConnection)
                conn.row_factory = sqlite3.Row
                return conn

            monkeypatch.setattr(sqlite_connector, "get_connection", connect)
            monkeypatch.setattr(sqlite_connector, "is_connected", lambda: True)
            return sqlite_connector

        return build

    def test_the_cost_does_not_grow_with_the_table_count(self, connected_db):
        """Five tables or fifty, describing one of them costs the same."""
        counts = []
        for table_count in (5, 50):
            connector = connected_db(table_count)
            CountingConnection.reset()
            connector.get_table("t01")
            counts.append(CountingConnection.count)

        assert counts[0] == counts[1], f"cost scaled with table count: {counts}"

    def test_describing_one_table_is_a_handful_of_queries(self, connected_db):
        connector = connected_db(30)

        CountingConnection.reset()
        connector.get_table("t15")

        assert CountingConnection.count <= 4, "still walking every table"

    def test_an_unknown_table_stops_at_the_catalogue(self, connected_db):
        connector = connected_db(30)

        CountingConnection.reset()
        assert connector.get_table("no_such_table") is None
        assert CountingConnection.count == 1

    def test_the_described_table_is_unchanged(self, connected_db):
        """The speed-up must not have cost any of the information."""
        connector = connected_db(6)

        one = connector.get_table("t03")
        from_listing = next(t for t in connector.list_tables() if t["name"] == "t03")

        assert one == from_listing

    def test_a_name_outside_the_catalogue_never_reaches_sql(self, connected_db):
        """The catalogue check is a security boundary, not only a lookup."""
        connector = connected_db(3)

        assert connector.get_table('t01"; DROP TABLE t02; --') is None
        assert len(connector.list_tables()) == 3

    def test_listing_every_table_still_describes_every_table(self, connected_db):
        connector = connected_db(8)

        tables = connector.list_tables()

        assert len(tables) == 8
        assert all(t["row_count"] == 50 for t in tables)
        assert all(t["columns"] == ["id", "name", "amount"] for t in tables)


class TestPatternsAreBuiltOnce:
    """The word lists are module constants. Rebuilding a regex for each of them on
    every question meant re-escaping the same strings thousands of times a second."""

    def test_the_same_word_list_yields_the_same_compiled_pattern(self):
        from query_assistant.domain.query.rule_engine import EMPLOYEE_WORDS, _any_of_pattern

        first = _any_of_pattern(tuple(sorted(EMPLOYEE_WORDS)))
        second = _any_of_pattern(tuple(sorted(EMPLOYEE_WORDS)))

        assert first is second

    def test_matching_is_unchanged_by_the_alternation(self):
        """One pattern for the whole list must answer what many patterns did."""
        from query_assistant.domain.query.rule_engine import EMPLOYEE_WORDS, any_word_in, word_in

        for text in ("employees in IT", "kitne log", "nothing relevant here", "a teamster"):
            expected = any(word_in(w, text) for w in EMPLOYEE_WORDS)
            assert any_word_in(EMPLOYEE_WORDS, text) == expected, text

    def test_a_word_is_not_matched_inside_a_longer_one(self):
        from query_assistant.domain.query.rule_engine import any_word_in

        assert not any_word_in(("min", "max"), "administration and maximal")
        assert any_word_in(("min", "max"), "the min value")

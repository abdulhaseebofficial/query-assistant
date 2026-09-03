"""Questions asked against a database the user attached at runtime.

This path had no tests. It shares `build_custom_query` with the CSV path but
reaches it through different routes and a different template, which is exactly how
it came to be broken: when the query builder learned to total and average a column,
`connect_table.html` was still reading the answer out of a hardcoded `count` key.
The explanation said "Adds up the total revenue" and the number underneath it was
blank.
"""

import io
import re
import sqlite3

import pytest

ROWS = [
    (1, "Karachi", "Laptop", 120, 150000.0),
    (2, "Lahore", "Mouse", 300, 7500.0),
    (3, "Karachi", "Monitor", 45, 14400.0),
    (4, "Islamabad", "Laptop", 60, 75000.0),
    (5, "Lahore", "Keyboard", 80, 6800.0),
]
TOTAL_REVENUE = sum(r[4] for r in ROWS)


@pytest.fixture
def connected(client, tmp_path, monkeypatch):
    """A SQLite database attached through the real /connect-db route."""
    import query_assistant.infrastructure.database.connectors.sqlite as sqlite_connector

    monkeypatch.setattr(sqlite_connector, "CONNECTED_DB_PATH", str(tmp_path / "connected.db"))
    monkeypatch.setattr(sqlite_connector, "UPLOAD_DIR", str(tmp_path))

    source = tmp_path / "shop.db"
    setup = sqlite3.connect(source)
    setup.execute(
        "CREATE TABLE sales (id INTEGER, city TEXT, product TEXT, units INTEGER, revenue REAL)"
    )
    setup.executemany("INSERT INTO sales VALUES (?, ?, ?, ?, ?)", ROWS)
    setup.execute("CREATE TABLE staff (id INTEGER, name TEXT)")
    setup.execute("INSERT INTO staff VALUES (1, 'Ali')")
    setup.commit()
    setup.close()

    response = client.post(
        "/connect-db",
        data={"file": (io.BytesIO(source.read_bytes()), "shop.db")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 302, "the database did not attach"
    return client


def ask(client, question, table="sales"):
    return client.get(f"/connect-db/{table}", query_string={"q": question}).get_data(as_text=True)


def stat_of(body):
    """The single value and its label from an aggregate answer."""
    value = re.search(r'class="stat-value">\s*([^<\s][^<]*?)\s*</span>', body)
    label = re.search(r'class="stat-label">\s*([^<]*?)\s*</span>', body)
    return (value.group(1) if value else None, label.group(1) if label else None)


def row_count(body):
    match = re.search(r"(\d+) rows? found", body)
    return int(match.group(1)) if match else None


class TestAttaching:
    def test_the_tables_are_listed_after_connecting(self, connected):
        page = connected.get("/connect-db").get_data(as_text=True)

        assert "sales" in page
        assert "staff" in page

    def test_a_table_page_opens(self, connected):
        assert connected.get("/connect-db/sales").status_code == 200

    def test_a_table_that_isnt_there_redirects_rather_than_erroring(self, connected):
        response = connected.get("/connect-db/no_such_table")
        assert response.status_code == 302


class TestAggregatesRender:
    """The bug this file was written for: the value was computed and then dropped
    on the way to the page, because the template read a `count` key that a sum or
    an average doesn't have."""

    def test_a_total_shows_its_number(self, connected):
        value, label = stat_of(ask(connected, "total revenue"))

        assert value == f"{int(TOTAL_REVENUE):,}"
        assert label == "total"

    def test_an_average_shows_its_number(self, connected):
        value, label = stat_of(ask(connected, "average revenue"))

        assert value == f"{int(TOTAL_REVENUE / len(ROWS)):,}"
        assert label == "average"

    def test_a_count_still_shows_its_number(self, connected):
        """The case that used to work, so the fix can't have traded one for another."""
        value, label = stat_of(ask(connected, "kitne rows hain"))

        assert value == str(len(ROWS))
        assert label == "count"

    def test_how_much_reads_as_a_total(self, connected):
        value, _label = stat_of(ask(connected, "revenue kitna hai"))
        assert value == f"{int(TOTAL_REVENUE):,}"

    def test_an_aggregate_never_renders_an_empty_box(self, connected):
        """Blank under a confident explanation is the failure being pinned here."""
        for question in ("total revenue", "average revenue", "kitne rows hain"):
            value, _label = stat_of(ask(connected, question))
            assert value, f"{question!r} rendered no value"


class TestListingAndFiltering:
    def test_show_everything_returns_every_row(self, connected):
        assert row_count(ask(connected, "sab dikhao")) == len(ROWS)

    def test_a_search_term_filters(self, connected):
        assert row_count(ask(connected, "karachi")) == 2

    def test_a_term_matching_nothing_says_so(self, connected):
        body = ask(connected, "peshawar")

        assert "No matching rows" in body
        assert row_count(body) is None

    def test_ranking_orders_the_rows(self, connected):
        body = ask(connected, "highest revenue")

        assert "highest revenue" in body
        assert row_count(body) == len(ROWS)

    def test_asking_for_one_returns_one(self, connected):
        assert row_count(ask(connected, "highest revenue sirf aik")) == 1


class TestChart:
    def test_a_listing_with_numbers_offers_a_chart(self, connected):
        body = ask(connected, "sab dikhao")
        assert "chart-toggle" in body or "Chart</button>" in body

    def test_an_aggregate_shows_a_single_value_rather_than_a_chart(self, connected):
        """One number is a stat, not a series."""
        body = ask(connected, "total revenue")

        assert stat_of(body)[0]
        assert "chart-toggle" not in body


class TestExport:
    def test_a_filtered_result_downloads_as_csv(self, connected):
        response = connected.get(
            "/connect-db/sales/export", query_string={"q": "karachi"}
        )

        assert response.status_code == 200
        assert response.mimetype == "text/csv"
        assert "attachment" in response.headers["Content-Disposition"]

    def test_the_export_carries_the_matching_rows(self, connected):
        body = connected.get(
            "/connect-db/sales/export", query_string={"q": "karachi"}
        ).get_data(as_text=True)

        assert len(body.strip().splitlines()) == 3  # header + two Karachi rows

    def test_a_formula_in_the_connected_data_is_neutralised(self, connected, tmp_path):
        """The data belongs to whoever attached the database, so the CSV-injection
        guard has to cover this path too, not only uploads."""
        import query_assistant.infrastructure.database.connectors.sqlite as sqlite_connector

        conn = sqlite3.connect(sqlite_connector.CONNECTED_DB_PATH)
        conn.execute(
            "INSERT INTO sales VALUES (?, ?, ?, ?, ?)",
            (6, "Quetta", "=cmd|'/c calc.exe'!A0", 1, 1.0),
        )
        conn.commit()
        conn.close()

        body = connected.get(
            "/connect-db/sales/export", query_string={"q": "quetta"}
        ).get_data(as_text=True)

        assert "'=cmd" in body
        assert ",=cmd" not in body


class TestAwkwardTableNames:
    @pytest.fixture
    def odd_table(self, connected):
        import query_assistant.infrastructure.database.connectors.sqlite as sqlite_connector

        conn = sqlite3.connect(sqlite_connector.CONNECTED_DB_PATH)
        conn.execute('CREATE TABLE "wei rd-name" (id INTEGER, note TEXT)')
        conn.execute('INSERT INTO "wei rd-name" VALUES (1, \'hello\')')
        conn.commit()
        conn.close()
        return connected

    def test_a_name_with_spaces_and_dashes_can_be_queried(self, odd_table):
        assert odd_table.get("/connect-db/wei rd-name").status_code == 200

    def test_its_export_gets_a_safe_filename(self, odd_table):
        response = odd_table.get(
            "/connect-db/wei rd-name/export", query_string={"q": "hello"}
        )

        assert response.status_code == 200
        disposition = response.headers["Content-Disposition"]
        assert " " not in disposition.split("filename=")[1]


class TestHostileColumnNames:
    """A connected database's *columns* reach the SQL as identifiers too.

    Table names were escaped; column names were not, and uploads hid it because a
    CSV's headers get sanitised on the way in. A connected database's don't â€” and
    a column named with a double quote in it closed the quoting early, which meant
    a 500 on every question asked of that table.
    """

    @pytest.fixture
    def quoted_column(self, connected):
        import query_assistant.infrastructure.database.connectors.sqlite as sqlite_connector

        quote = chr(34)
        conn = sqlite3.connect(sqlite_connector.CONNECTED_DB_PATH)
        conn.execute(f"CREATE TABLE odd ({quote}we{quote}{quote}ird{quote} TEXT, n INTEGER)")
        conn.executemany("INSERT INTO odd VALUES (?, ?)", [("alpha", 1), ("beta", 2)])
        conn.commit()
        conn.close()
        return connected

    def test_the_column_name_is_read_back_intact(self, quoted_column):
        from query_assistant.infrastructure.database.connectors import sqlite as sqlite_connector

        assert sqlite_connector.get_table("odd")["columns"] == ['we"ird', "n"]

    @pytest.mark.parametrize("question", ["sab dikhao", "alpha", "total n", "highest n"])
    def test_questions_do_not_crash(self, quoted_column, question):
        response = quoted_column.get("/connect-db/odd", query_string={"q": question})
        assert response.status_code == 200

    def test_the_generated_sql_escapes_the_quote(self, quoted_column):
        from query_assistant.domain.query.csv_engine import build_custom_query
        from query_assistant.infrastructure.database.connectors import sqlite as sqlite_connector

        columns = sqlite_connector.get_table("odd")["columns"]
        sql, _params, _explanation, _is_aggregate = build_custom_query("alpha", columns, "odd")

        assert '"we""ird"' in sql

    def test_a_column_name_cannot_smuggle_in_sql(self, tmp_path):
        """The quoter is a security control, not only a crash fix.

        Asserted by running the generated SQL rather than by inspecting it: the
        escaping being tested is a doubled quote, and any string check clever enough
        to ignore that is clever enough to ignore a real escape too.
        """
        from query_assistant.domain.query.csv_engine import build_custom_query

        quote = chr(34)
        hostile = f"x{quote}; DROP TABLE victim; --"

        db_path = tmp_path / "hostile.db"
        conn = sqlite3.connect(db_path)
        conn.execute(f"CREATE TABLE t ({quote}{hostile.replace(quote, quote * 2)}{quote} TEXT)")
        conn.execute("INSERT INTO t VALUES ('term')")
        conn.execute("CREATE TABLE victim (id INTEGER)")
        conn.commit()

        sql, params, _explanation, _is_aggregate = build_custom_query("term", [hostile], "t")
        conn.execute(sql, params).fetchall()

        survived = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='victim'"
        ).fetchall()
        conn.close()

        assert survived, "the column name executed as SQL"

    def test_the_export_survives_it_too(self, quoted_column):
        response = quoted_column.get("/connect-db/odd/export", query_string={"q": "alpha"})
        assert response.status_code == 200


class TestGeneratedSqlSurvivesAnyIdentifier:
    """A connected database's column names are whatever its owner chose. The query
    builder interpolates them, so every shape has to come out as valid SQL â€” in
    both dialects, since a connected database can be PostgreSQL and there's no
    PostgreSQL server here to try it against."""

    QUOTE = chr(34)
    NAMES = [
        "normal_col",
        "with space",
        "with-dash",
        f"we{QUOTE}ird",
        f"x{QUOTE}; DROP TABLE victim; --",
        "select",
        "UPPER_Case",
        "Ø´ÛØ±",
    ]

    @pytest.mark.parametrize("name", NAMES)
    def test_the_identifier_is_quoted_and_balanced(self, name):
        from query_assistant.infrastructure.database.connection import quote_ident

        quoted = quote_ident(name)

        assert quoted.startswith(self.QUOTE) and quoted.endswith(self.QUOTE)
        # Every quote inside the name is doubled, so the total count stays even.
        assert quoted.count(self.QUOTE) % 2 == 0

    @pytest.mark.parametrize("name", NAMES)
    @pytest.mark.parametrize("placeholder, dialect", [("?", "sqlite"), ("%s", "postgres")])
    def test_a_search_parses_in_both_dialects(self, name, placeholder, dialect):
        sqlglot = pytest.importorskip("sqlglot")
        from query_assistant.domain.query.csv_engine import build_custom_query

        sql, _params, _explanation, _is_aggregate = build_custom_query(
            "term", [name, "n"], "tbl", placeholder
        )
        sqlglot.parse(sql.replace("%s", "?"), dialect=dialect)

    @pytest.mark.parametrize("question", ["total n", "highest n", "average n"])
    def test_aggregates_and_rankings_parse_as_postgres(self, question):
        sqlglot = pytest.importorskip("sqlglot")
        from query_assistant.domain.query.csv_engine import build_custom_query

        sql, _params, _explanation, _is_aggregate = build_custom_query(
            question, [f"we{self.QUOTE}ird", "n"], "tbl", "%s", types=["TEXT", "INTEGER"]
        )
        sqlglot.parse(sql.replace("%s", "?"), dialect="postgres")

    def test_the_postgres_connector_uses_the_same_quoter(self):
        """One quoter for the app: two would drift, and this one is a security control."""
        from query_assistant.infrastructure.database.connection import quote_ident
        from query_assistant.infrastructure.database.connectors import postgresql as postgres_connector
        from query_assistant.infrastructure.database.connectors import sqlite as sqlite_connector

        assert sqlite_connector.quote_ident is quote_ident
        assert postgres_connector.quote_ident is quote_ident

"""The app runs on SQLite locally and PostgreSQL when DATABASE_URL is set.

There's no PostgreSQL server in CI, so these tests do the next best thing: build
the SQL the app would send and parse it with sqlglot's PostgreSQL dialect. That
catches the failures dialect bugs actually produce â€” an identity column written in
SQLite's syntax, a `strftime` that doesn't exist, a `?` where `%s` belongs â€” all of
which would otherwise only surface as a 500 on the deployment.

Reloading query_assistant.infrastructure.database.connection under a patched environment is unavoidable: it reads
DATABASE_URL once at import, which is what makes the rest of the app able to treat
the dialect as a constant.
"""

import importlib
import sqlite3

import pytest

sqlglot = pytest.importorskip("sqlglot")

PG_URL = "postgresql://user:pass@example.com:5432/appdb"


@pytest.fixture
def postgres_modules(monkeypatch):
    """Database modules reloaded as they would be with ``DATABASE_URL`` set."""
    import query_assistant.infrastructure.database.connection
    import query_assistant.infrastructure.database.initialization

    monkeypatch.setenv("DATABASE_URL", PG_URL)
    db = importlib.reload(query_assistant.infrastructure.database.connection)
    database = importlib.reload(query_assistant.infrastructure.database.initialization)
    try:
        yield db, database
    finally:
        monkeypatch.delenv("DATABASE_URL", raising=False)
        importlib.reload(query_assistant.infrastructure.database.connection)
        importlib.reload(query_assistant.infrastructure.database.initialization)
        importlib.reload(importlib.import_module("query_assistant.domain.query.rule_engine"))


def parses_as_postgres(sql):
    sqlglot.parse(sql, dialect="postgres")
    return True


class TestDialectSelection:
    def test_sqlite_is_the_default(self):
        from query_assistant.infrastructure.database import connection as db

        assert db.IS_POSTGRES is False
        assert db.DIALECT == "SQLite"

    def test_a_database_url_switches_everything_over(self, postgres_modules):
        db, _ = postgres_modules

        assert db.IS_POSTGRES is True
        assert db.DIALECT == "PostgreSQL"


class TestPlaceholderTranslation:
    def test_placeholders_are_left_alone_on_sqlite(self):
        from query_assistant.infrastructure.database import connection as db

        assert db.to_dialect("SELECT * FROM users WHERE id = ?") == "SELECT * FROM users WHERE id = ?"

    def test_placeholders_are_rewritten_for_postgres(self, postgres_modules):
        db, _ = postgres_modules

        assert db.to_dialect("SELECT * FROM users WHERE id = ?") == "SELECT * FROM users WHERE id = %s"
        assert db.to_dialect("INSERT INTO t VALUES (?, ?, ?)") == "INSERT INTO t VALUES (%s, %s, %s)"

    def test_a_question_mark_inside_a_string_literal_is_not_a_placeholder(self, postgres_modules):
        """It's data. Rewriting it would corrupt the value being stored or matched."""
        db, _ = postgres_modules

        translated = db.to_dialect("SELECT * FROM t WHERE note = 'what? really' AND id = ?")
        assert translated == "SELECT * FROM t WHERE note = 'what? really' AND id = %s"


class TestSchemaIsValidInBothDialects:
    def test_the_schema_parses_as_sqlite(self):
        from query_assistant.infrastructure.database import initialization as database

        for statement in database.SCHEMA.split(";"):
            if statement.strip():
                sqlglot.parse(statement, dialect="sqlite")

    def test_the_schema_parses_as_postgres(self, postgres_modules):
        _, database = postgres_modules

        for statement in database.SCHEMA.split(";"):
            if statement.strip():
                assert parses_as_postgres(statement)

    def test_postgres_gets_an_identity_column_not_autoincrement(self, postgres_modules):
        """AUTOINCREMENT is SQLite-only and is a syntax error on PostgreSQL."""
        db, database = postgres_modules

        assert "AUTOINCREMENT" not in database.SCHEMA
        assert "IDENTITY" in db.IDENTITY_PK

    def test_postgres_stores_order_date_as_a_real_date(self, postgres_modules):
        """The date filters compare it with date functions, so TEXT won't do."""
        _, database = postgres_modules

        assert "order_date DATE NOT NULL" in database.SCHEMA

    def test_the_schema_still_creates_every_table(self, postgres_modules):
        _, database = postgres_modules

        for table in ("departments", "employees", "products", "customers",
                      "orders", "users", "query_history"):
            assert f"CREATE TABLE IF NOT EXISTS {table}" in database.SCHEMA


class TestDateFilters:
    def test_each_filter_is_valid_postgres(self, postgres_modules):
        db, _ = postgres_modules

        for name, expression in db.DATE_FILTERS.items():
            assert parses_as_postgres(f"SELECT 1 FROM orders o WHERE {expression}"), name

    def test_each_filter_is_valid_sqlite(self):
        from query_assistant.infrastructure.database import connection as db

        for expression in db.DATE_FILTERS.values():
            sqlglot.parse(f"SELECT 1 FROM orders o WHERE {expression}", dialect="sqlite")

    def test_postgres_does_not_use_strftime(self, postgres_modules):
        """strftime is SQLite's; PostgreSQL has no such function."""
        db, _ = postgres_modules

        assert not any("strftime" in e for e in db.DATE_FILTERS.values())

    def test_the_same_four_periods_exist_in_both(self, postgres_modules):
        db, _ = postgres_modules
        pg_keys = set(db.DATE_FILTERS)

        import query_assistant.infrastructure.database.connection

        importlib.reload(query_assistant.infrastructure.database.connection)
        assert pg_keys == set(query_assistant.infrastructure.database.connection.DATE_FILTERS)


class TestGeneratedQueriesAreValidPostgres:
    """Whatever the rule engine builds has to run on whichever backend is configured."""

    QUESTIONS = [
        "employees in the IT department",
        "highest paid employees",
        "newest employees",
        "how many employees are there",
        "average salary in sales",
        "products low on stock",
        "most expensive products",
        "customers in Lahore",
        "pending orders",
        "total revenue this month",
        "orders placed today",
        "show me all departments",
    ]

    @pytest.fixture
    def pg_rule_engine(self, postgres_modules, test_database):
        """The rule engine rebound to the PostgreSQL dialect, plus a SQLite
        connection to read reference data (department names, cities) from."""
        import query_assistant.domain.query.rule_engine as rule_engine

        rule_engine = importlib.reload(rule_engine)
        connection = sqlite3.connect(test_database)
        connection.row_factory = sqlite3.Row
        try:
            yield rule_engine, connection
        finally:
            connection.close()

    @pytest.mark.parametrize("question", QUESTIONS)
    def test_the_sql_parses_as_postgres(self, pg_rule_engine, question):
        rule_engine, connection = pg_rule_engine

        result = rule_engine.interpret(question, connection)
        assert result is not None, "the question stopped being understood"
        assert parses_as_postgres(rule_engine.db.to_dialect(result["sql"]))

    def test_a_date_question_produces_postgres_date_syntax(self, pg_rule_engine):
        rule_engine, connection = pg_rule_engine

        sql = rule_engine.interpret("total revenue this month", connection)["sql"]
        assert "date_trunc" in sql
        assert "strftime" not in sql


class TestInsertReturningId:
    def test_sqlite_uses_lastrowid(self, test_database):
        from query_assistant.infrastructure.database import connection as db

        conn = db.connect(test_database)
        try:
            new_id = db.insert_returning_id(
                conn,
                "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
                ("dialect_probe", "dialect_probe@example.com", "x"),
            )
            conn.commit()
            assert isinstance(new_id, int)

            row = conn.execute("SELECT username FROM users WHERE id = ?", (new_id,)).fetchone()
            assert row["username"] == "dialect_probe"

            conn.execute("DELETE FROM users WHERE id = ?", (new_id,))
            conn.commit()
        finally:
            conn.close()

    def test_postgres_appends_returning_id(self, postgres_modules):
        """psycopg2 has no lastrowid, so the id has to be asked for in the statement."""
        db, _ = postgres_modules
        captured = {}

        class FakeConn:
            def execute(self, sql, params):
                captured["sql"] = sql
                return self

            def fetchone(self):
                return [42]

        assert db.insert_returning_id(FakeConn(), "INSERT INTO users (a) VALUES (?)", ("x",)) == 42
        assert captured["sql"].endswith(" RETURNING id")

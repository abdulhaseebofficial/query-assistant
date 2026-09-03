"""Running SQL somebody typed themselves.

The rest of the app writes the query for you; this is the other direction. That
makes it the one place where arbitrary SQL arrives from outside, so most of this
file is about what must *not* run â€” and about the fact that it's the same check the
AI engine uses, not a second one written for typed input.
"""

import io
import re
import sqlite3

import pytest

from query_assistant.domain.validation.sql_guardrails import BUILTIN_TABLES, check_select


def post(client, sql, source="demo"):
    return client.post("/sql", data={"sql": sql, "source": source}).get_data(as_text=True)


def rows_returned(body):
    match = re.search(r"(\d+) rows? returned", body)
    return int(match.group(1)) if match else None


def error_in(body):
    """The reason a query was refused, or None.

    Matched on the error heading specifically: an empty result set uses the same
    block, and treating "no rows" as an error would hide the difference between a
    query that was rejected and one that simply matched nothing.
    """
    match = re.search(r"That query didn't run</p>\s*<p>([^<]*)</p>", body, re.S)
    return match.group(1).strip() if match else None


class TestRunningAQuery:
    def test_the_page_opens(self, client):
        assert client.get("/sql").status_code == 200

    @pytest.mark.parametrize(
        "sql, expected",
        [
            ("SELECT name FROM employees ORDER BY salary DESC LIMIT 5", 5),
            ("SELECT name FROM products WHERE price > 100", 7),
            ("SELECT * FROM customers WHERE city = 'Lahore'", 3),
            ("select name from employees limit 2", 2),  # lower case
        ],
    )
    def test_a_valid_select_returns_rows(self, client, sql, expected):
        assert rows_returned(post(client, sql)) == expected

    def test_a_join_runs(self, client):
        body = post(
            client,
            "SELECT d.name, COUNT(e.id) AS n FROM departments d "
            "LEFT JOIN employees e ON e.department_id = d.id GROUP BY d.id",
        )
        assert rows_returned(body) == 5

    def test_a_trailing_semicolon_is_fine(self, client):
        assert rows_returned(post(client, "SELECT name FROM employees LIMIT 3;")) == 3

    def test_a_query_matching_nothing_is_not_an_error(self, client):
        body = post(client, "SELECT name FROM employees WHERE name = 'Nobody'")

        assert error_in(body) is None
        assert "No rows" in body

    def test_an_empty_box_just_shows_the_editor(self, client):
        body = post(client, "   ")
        assert error_in(body) is None
        assert "Write your own SQL" in body


class TestWhatMustNotRun:
    """This is the one route where arbitrary SQL arrives from outside."""

    @pytest.mark.parametrize(
        "sql",
        [
            "DROP TABLE employees",
            "DELETE FROM employees",
            "UPDATE employees SET salary = 0",
            "INSERT INTO employees (name) VALUES ('x')",
            "ALTER TABLE employees ADD COLUMN x TEXT",
            "PRAGMA table_info(employees)",
            "ATTACH DATABASE '/etc/passwd' AS leak",
            "CREATE TABLE evil (id INT)",
        ],
    )
    def test_anything_that_writes_is_refused(self, client, sql):
        assert error_in(post(client, sql))

    def test_stacked_statements_are_refused(self, client):
        assert "one statement" in error_in(post(client, "SELECT * FROM employees; DROP TABLE x"))

    def test_the_apps_own_tables_are_out_of_reach(self, client):
        """users and query_history live in the same file as the demo tables."""
        for table in ("users", "query_history", "sqlite_master"):
            assert "No table called" in error_in(post(client, f"SELECT * FROM {table}"))

    def test_a_refused_query_does_not_execute(self, client, conn):
        """The strongest form of the assertion: the table is still there afterwards."""
        before = conn.execute("SELECT COUNT(*) AS c FROM employees").fetchone()["c"]

        post(client, "DELETE FROM employees")
        post(client, "DROP TABLE employees")

        assert conn.execute("SELECT COUNT(*) AS c FROM employees").fetchone()["c"] == before

    def test_a_smuggled_table_in_a_join_is_refused(self, client):
        body = post(
            client,
            "SELECT e.name, u.password_hash FROM employees e JOIN users u ON e.id = u.id",
        )
        assert error_in(body)


class TestTheErrorsAreUsable:
    """A person who just typed the query is the one who can fix it, so the reason
    has to name the rule rather than only refuse."""

    @pytest.mark.parametrize(
        "sql, fragment",
        [
            ("DELETE FROM employees", "Only SELECT"),
            ("SELECT * FROM employees; DROP TABLE x", "one statement"),
            ("SELECT * FROM nowhere", "No table called"),
            ("SELECT 1", "No table found"),
        ],
    )
    def test_the_reason_names_the_rule(self, client, sql, fragment):
        assert fragment in error_in(post(client, sql))

    def test_the_available_tables_are_listed(self, client):
        message = error_in(post(client, "SELECT * FROM nowhere"))
        assert "employees" in message and "products" in message

    def test_a_database_error_is_passed_through(self, client):
        """A typo in a column is the database's complaint, and it's useful."""
        message = error_in(post(client, "SELECT no_such_column FROM employees"))

        assert message
        assert "no_such_column" in message

    def test_a_syntax_error_does_not_500(self, client):
        response = client.post("/sql", data={"sql": "SELCT * FROM employees", "source": "demo"})
        assert response.status_code == 200


class TestSourcesAreSeparate:
    """Each source gets its own whitelist. Picking one must not open the others."""

    @pytest.fixture
    def with_dataset(self, client, conn):
        csv = b"City,Product,Revenue\nKarachi,Laptop,150000\nLahore,Mouse,7500\n"
        client.post(
            "/upload",
            data={"dataset_name": "Sales", "file": (io.BytesIO(csv), "s.csv")},
            content_type="multipart/form-data",
        )
        return client

    @pytest.fixture
    def with_connection(self, client, tmp_path, monkeypatch):
        import query_assistant.infrastructure.database.connectors.sqlite as sqlite_connector

        monkeypatch.setattr(sqlite_connector, "CONNECTED_DB_PATH", str(tmp_path / "c.db"))
        monkeypatch.setattr(sqlite_connector, "UPLOAD_DIR", str(tmp_path))

        path = tmp_path / "shop.db"
        setup = sqlite3.connect(path)
        setup.execute("CREATE TABLE sales (id INTEGER, city TEXT, revenue REAL)")
        setup.executemany("INSERT INTO sales VALUES (?, ?, ?)",
                          [(1, "Karachi", 150000.0), (2, "Lahore", 7500.0)])
        setup.commit()
        setup.close()
        client.post(
            "/connect-db",
            data={"file": (io.BytesIO(path.read_bytes()), "shop.db")},
            content_type="multipart/form-data",
        )
        return client

    def test_the_uploaded_dataset_can_be_queried(self, with_dataset):
        assert rows_returned(post(with_dataset, "SELECT * FROM custom_data", "dataset")) == 2

    def test_the_dataset_source_cannot_reach_the_demo_tables(self, with_dataset):
        message = error_in(post(with_dataset, "SELECT * FROM employees", "dataset"))
        assert "No table called" in message
        assert "custom_data" in message

    def test_the_connected_database_can_be_queried(self, with_connection):
        assert rows_returned(post(with_connection, "SELECT * FROM sales", "connected")) == 2

    def test_the_connected_source_cannot_reach_the_demo_tables(self, with_connection):
        assert "No table called" in error_in(post(with_connection, "SELECT * FROM employees",
                                                  "connected"))

    def test_writing_to_a_connected_database_is_refused(self, with_connection):
        assert error_in(post(with_connection, "DROP TABLE sales", "connected"))

    def test_only_the_demo_source_exists_on_its_own(self, client):
        body = client.get("/sql").get_data(as_text=True)
        assert re.findall(r'<option value="(\w+)"', body) == ["demo"]

    def test_every_attached_source_is_offered(self, with_dataset):
        body = with_dataset.get("/sql").get_data(as_text=True)
        assert set(re.findall(r'<option value="(\w+)"', body)) == {"dataset", "demo"}


class TestOneSetOfRules:
    """A model's SQL and a person's SQL go through the same function. Two copies of
    a security rule is two chances to weaken one of them."""

    def test_the_console_uses_the_engines_validator(self):
        from query_assistant.services import sql_console_service as sql_console

        assert sql_console.check_select is check_select

    @pytest.mark.parametrize(
        "sql",
        ["DROP TABLE employees", "SELECT * FROM users", "SELECT * FROM a; SELECT * FROM b"],
    )
    def test_both_callers_agree(self, sql):
        from query_assistant.domain.validation.sql_guardrails import validate_select

        statement, reason = check_select(sql, BUILTIN_TABLES)

        assert statement is None
        assert reason
        assert validate_select(sql, BUILTIN_TABLES) is None

    def test_an_accepted_query_is_identical_either_way(self):
        from query_assistant.domain.validation.sql_guardrails import validate_select

        sql = "SELECT name FROM employees"
        statement, reason = check_select(sql, BUILTIN_TABLES)

        assert reason is None
        assert statement == validate_select(sql, BUILTIN_TABLES)


class TestHistory:
    def test_a_run_query_is_recorded(self, client):
        import uuid

        name = f"console{uuid.uuid4().hex[:6]}"
        client.post("/register", data={"username": name, "email": f"{name}@e.com",
                                       "password": "a-good-password"})

        post(client, "SELECT name FROM employees LIMIT 1")

        assert "SELECT name FROM employees" in client.get("/history").get_data(as_text=True)

    def test_a_refused_query_is_not_recorded(self, client):
        import uuid

        name = f"console{uuid.uuid4().hex[:6]}"
        client.post("/register", data={"username": name, "email": f"{name}@e.com",
                                       "password": "a-good-password"})

        post(client, "DROP TABLE employees")

        assert "DROP TABLE" not in client.get("/history").get_data(as_text=True)

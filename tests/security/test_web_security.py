"""Regression tests for the specific attacks this app is built to survive.

Each test here maps to a real finding, so a failure means a defence has been
removed rather than a style rule broken. SQL-injection coverage lives next door in
test_sql_guardrails.py; this file covers everything else.
"""

import io

import pytest

from query_assistant.domain.query.csv_engine import load_csv
from query_assistant.infrastructure.database.connectors import postgresql as postgres_connector
from query_assistant.infrastructure.database.connectors import sqlite as sqlite_connector
from query_assistant.utilities.csv_export import _neutralise_formula, build_csv


class TestCsvFormulaInjection:
    """A cell starting with = + - @ is executed as a formula by Excel and Sheets.

    Query results can come from an uploaded CSV or a connected database, so an
    attacker can choose that cell's contents and the export hands it to whoever
    clicks "Download CSV".
    """

    @pytest.mark.parametrize(
        "payload",
        [
            "=cmd|'/c calc.exe'!A0",
            "+cmd|'/c calc.exe'!A0",
            "-2+3+cmd|'/c calc.exe'!A0",
            "@SUM(1+9)*cmd|'/c calc'!A0",
            "=HYPERLINK(\"http://evil.test\",\"click\")",
            "\t=1+1",
            "\r=1+1",
        ],
    )
    def test_formula_payloads_are_neutralised(self, payload):
        assert _neutralise_formula(payload).startswith("'")

    @pytest.mark.parametrize("value", ["Karachi", "employee=manager", "", "a=b"])
    def test_ordinary_text_is_left_alone(self, value):
        assert _neutralise_formula(value) == value

    @pytest.mark.parametrize("value", [-5, 3.2, 0, None, True])
    def test_real_numbers_and_nulls_pass_through_untouched(self, value):
        assert _neutralise_formula(value) == value

    @pytest.mark.parametrize("value", ["-5", "+3.2", "-0.001"])
    def test_numeric_looking_strings_are_not_mangled(self, value):
        """A text column full of negative numbers shouldn't gain stray quotes."""
        assert _neutralise_formula(value) == value

    def test_build_csv_neutralises_a_payload_end_to_end(self):
        rows = [{"city": "Karachi", "note": "=cmd|'/c calc.exe'!A0"}]
        output = build_csv(["city", "note"], rows)

        assert "'=cmd" in output
        assert ",=cmd" not in output

    def test_build_csv_keeps_the_header_and_every_column(self):
        rows = [{"a": 1, "b": 2}, {"a": 3, "b": 4}]
        lines = build_csv(["a", "b"], rows).strip().splitlines()

        assert lines[0] == "a,b"
        assert len(lines) == 3

    def test_export_route_serves_a_neutralised_file(self, client, conn):
        """The whole path: upload a hostile CSV, then download it back."""
        evil = b'city,note\nKarachi,"=cmd|\'/c calc.exe\'!A0"\n'
        load_csv(io.BytesIO(evil), conn, "hostile")
        conn.commit()

        response = client.get("/dataset/export", query_string={"q": "karachi"})

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "'=cmd" in body, "formula reached the file unescaped"


class TestPostgresSsrfGuard:
    """/connect-db/postgres dials whatever host it's given.

    Unguarded, that turns the app into an internal port scanner for anyone who can
    reach it: the distinct "refused" / "timed out" / "auth failed" replies map out
    the network behind it.
    """

    @pytest.fixture(autouse=True)
    def block_private_hosts(self, monkeypatch):
        monkeypatch.setattr(postgres_connector, "ALLOW_PRIVATE_HOSTS", False)

    @pytest.mark.parametrize(
        "dsn",
        [
            "postgresql://u:p@127.0.0.1:5432/db",
            "postgresql://u:p@localhost:5432/db",
            "postgresql://u:p@192.168.1.10:5432/db",
            "postgresql://u:p@10.0.0.5:5432/db",
            "postgresql://u:p@172.16.0.1:5432/db",
            "postgresql://u:p@169.254.169.254:80/db",
            "postgresql://u:p@[::1]:5432/db",
            "host=127.0.0.1 port=5432 dbname=db user=u",
        ],
    )
    def test_private_and_loopback_targets_are_refused(self, dsn):
        with pytest.raises(ValueError):
            postgres_connector.check_dsn_target(dsn)

    def test_cloud_metadata_is_named_in_the_error(self):
        """The message should tell the user what happened, not just fail."""
        with pytest.raises(ValueError, match="169.254.169.254"):
            postgres_connector.check_dsn_target("postgresql://u:p@169.254.169.254:80/db")

    def test_a_dsn_with_no_host_is_refused(self):
        """No host means a local socket, which is the thing being blocked."""
        with pytest.raises(ValueError):
            postgres_connector.check_dsn_target("dbname=db user=u")

    def test_a_public_host_is_allowed(self):
        postgres_connector.check_dsn_target("postgresql://u:p@db.example.com:5432/db")

    def test_the_guard_can_be_opted_out_of_for_local_development(self, monkeypatch):
        monkeypatch.setattr(postgres_connector, "ALLOW_PRIVATE_HOSTS", True)
        postgres_connector.check_dsn_target("postgresql://u:p@127.0.0.1:5432/db")

    @pytest.mark.parametrize(
        "dsn, expected",
        [
            ("postgresql://u:p@db.example.com:5432/x", "db.example.com"),
            ("host=db.example.com port=5432", "db.example.com"),
            ("host='db.example.com' port=5432", "db.example.com"),
            ("dbname=x user=u", None),
        ],
    )
    def test_the_host_is_extracted_from_both_dsn_forms(self, dsn, expected):
        assert postgres_connector._host_from_dsn(dsn) == expected


class TestIdentifierQuoting:
    """Table names can't be bound as parameters, so they get interpolated.

    A name from the database's own catalogue is still attacker-influenced when the
    database itself was uploaded by an attacker.
    """

    @pytest.mark.parametrize(
        "name, expected",
        [
            ("employees", '"employees"'),
            ('ev"il', '"ev""il"'),
            ('x" ; DROP TABLE users --', '"x"" ; DROP TABLE users --"'),
        ],
    )
    def test_embedded_quotes_are_doubled_not_dropped(self, name, expected):
        assert sqlite_connector.quote_ident(name) == expected
        assert postgres_connector.quote_ident(name) == expected


class TestResponseHeaders:
    @pytest.mark.parametrize(
        "header, expected",
        [
            ("X-Content-Type-Options", "nosniff"),
            ("X-Frame-Options", "DENY"),
            ("Referrer-Policy", "strict-origin-when-cross-origin"),
        ],
    )
    def test_the_baseline_headers_are_present(self, client, header, expected):
        assert client.get("/").headers[header] == expected

    def test_permissions_policy_denies_hardware_access(self, client):
        policy = client.get("/").headers["Permissions-Policy"]
        for feature in ("camera=()", "microphone=()", "geolocation=()"):
            assert feature in policy

    def test_hsts_is_absent_over_plain_http(self, client):
        """Sending HSTS during local http:// development would lock the app out."""
        assert "Strict-Transport-Security" not in client.get("/").headers

    def test_hsts_appears_once_the_app_is_told_it_is_behind_https(self, client):
        flask_app = client.application
        flask_app.config["SESSION_COOKIE_SECURE"] = True
        try:
            header = client.get("/").headers["Strict-Transport-Security"]
        finally:
            flask_app.config["SESSION_COOKIE_SECURE"] = False

        assert "max-age=31536000" in header

    def test_the_csp_forbids_framing_and_foreign_origins(self, client):
        csp = client.get("/").headers["Content-Security-Policy"]
        assert "default-src 'self'" in csp
        assert "frame-ancestors 'none'" in csp


class TestAttachmentFilename:
    """Table names reach Content-Disposition, and SQLite allows quotes and newlines
    in them â€” neither belongs in a response header."""

    @pytest.mark.parametrize(
        "raw",
        ['evil"; drop.csv', "line\r\nX-Injected: yes.csv", "../../etc/passwd", "a" * 400],
    )
    def test_dangerous_characters_never_reach_the_header(self, raw):
        from query_assistant.web.presentation import attachment_header

        header = attachment_header(raw)

        assert "\r" not in header and "\n" not in header
        assert header.count('"') == 2  # exactly the pair wrapping the filename
        assert "/" not in header and ".." not in header
        assert len(header) < 150

    def test_an_ordinary_name_survives(self):
        from query_assistant.web.presentation import attachment_header

        assert attachment_header("sales_results.csv") == 'attachment; filename="sales_results.csv"'


class TestRateLimits:
    def test_repeated_logins_are_throttled(self, rate_limited_client):
        """Brute-forcing a password shouldn't be limited only by network speed."""
        codes = [
            rate_limited_client.post(
                "/login", data={"username": "victim", "password": f"guess-{i}"}
            ).status_code
            for i in range(15)
        ]
        assert 429 in codes, "login accepted 15 attempts in a row"

    def test_asking_questions_is_throttled(self, rate_limited_client):
        """With an AI key configured, every one of these is a billable call."""
        codes = [
            rate_limited_client.get("/", query_string={"q": f"employees {i}"}).status_code
            for i in range(40)
        ]
        assert 429 in codes

    def test_a_normal_amount_of_use_is_not_throttled(self, rate_limited_client):
        codes = [rate_limited_client.get("/").status_code for _ in range(10)]
        assert codes == [200] * 10

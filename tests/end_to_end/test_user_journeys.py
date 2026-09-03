"""Whole flows, in order, sharing state between the steps.

Every other test file isolates its subject with a fresh fixture, which is the right
way to test a unit and the wrong way to notice that clearing a dataset leaves the
page it fed still claiming to have one. These run the sequences a person actually
performs â€” upload, ask, export, clear â€” and assert the state after each step, so a
step that fails to undo the one before it shows up here rather than in use.
"""

import io
import sqlite3
import uuid

import pytest

CSV = (
    b"City,Product,Units Sold,Revenue\n"
    b"Karachi,Laptop,120,150000\n"
    b"Lahore,Mouse,300,7500\n"
    b"Karachi,Monitor,45,14400\n"
    b"Islamabad,Laptop,60,75000\n"
)
CSV_TOTAL = 150000 + 7500 + 14400 + 75000


def text(response):
    return response.get_data(as_text=True)


class TestUploadJourney:
    """Upload a spreadsheet, ask it things, take it away again."""

    def test_the_whole_flow(self, client):
        # 1. nothing uploaded yet
        assert client.get("/dataset").status_code == 302

        # 2. upload
        response = client.post(
            "/upload",
            data={"dataset_name": "Sales", "file": (io.BytesIO(CSV), "sales.csv")},
            content_type="multipart/form-data",
        )
        assert response.status_code == 302
        assert "Sales" in text(client.get("/dataset"))

        # 3. ask it things
        assert "4 row" in text(client.get("/dataset", query_string={"q": "sab dikhao"}))
        assert f"{CSV_TOTAL:,}" in text(
            client.get("/dataset", query_string={"q": "total revenue"})
        )
        assert "2 row" in text(client.get("/dataset", query_string={"q": "karachi"}))

        # 4. export what was asked for
        export = client.get("/dataset/export", query_string={"q": "karachi"})
        assert export.status_code == 200
        assert len(text(export).strip().splitlines()) == 3

        # 5. clear, and it's actually gone
        assert client.post("/dataset/clear").status_code == 302
        after = client.get("/dataset")
        assert after.status_code == 302
        assert "/upload" in after.headers["Location"]

    def test_a_second_upload_replaces_the_first(self, client):
        """One active dataset at a time â€” the second must not be queryable alongside."""
        client.post(
            "/upload",
            data={"dataset_name": "First", "file": (io.BytesIO(CSV), "a.csv")},
            content_type="multipart/form-data",
        )
        client.post(
            "/upload",
            data={
                "dataset_name": "Second",
                "file": (io.BytesIO(b"Town,Amount\nQuetta,42\nMultan,7\n"), "b.csv"),
            },
            content_type="multipart/form-data",
        )

        page = text(client.get("/dataset", query_string={"q": "sab dikhao"}))
        assert "Second" in page
        assert "Quetta" in page
        assert "Karachi" not in page, "the replaced dataset is still being queried"


class TestConnectedDatabaseJourney:
    @pytest.fixture
    def shop_db(self, tmp_path, monkeypatch):
        import query_assistant.infrastructure.database.connectors.sqlite as sqlite_connector

        monkeypatch.setattr(sqlite_connector, "CONNECTED_DB_PATH", str(tmp_path / "conn.db"))
        monkeypatch.setattr(sqlite_connector, "UPLOAD_DIR", str(tmp_path))

        path = tmp_path / "shop.db"
        setup = sqlite3.connect(path)
        setup.execute("CREATE TABLE sales (id INTEGER, city TEXT, revenue REAL)")
        setup.executemany(
            "INSERT INTO sales VALUES (?, ?, ?)",
            [(1, "Karachi", 150000.0), (2, "Lahore", 7500.0), (3, "Karachi", 14400.0)],
        )
        setup.commit()
        setup.close()
        return path

    def test_the_whole_flow(self, client, shop_db):
        # 1. nothing connected
        assert "sales" not in text(client.get("/connect-db"))

        # 2. attach
        response = client.post(
            "/connect-db",
            data={"file": (io.BytesIO(shop_db.read_bytes()), "shop.db")},
            content_type="multipart/form-data",
        )
        assert response.status_code == 302
        assert "sales" in text(client.get("/connect-db"))

        # 3. ask it things
        assert "3 row" in text(client.get("/connect-db/sales", query_string={"q": "sab dikhao"}))
        assert "171,900" in text(
            client.get("/connect-db/sales", query_string={"q": "total revenue"})
        )

        # 4. export
        export = client.get("/connect-db/sales/export", query_string={"q": "karachi"})
        assert export.status_code == 200

        # 5. disconnect, and the table is no longer reachable
        assert client.post("/connect-db/clear").status_code == 302
        assert "sales" not in text(client.get("/connect-db"))
        assert client.get("/connect-db/sales").status_code == 302

    def test_a_rejected_connection_leaves_the_previous_one_alone(self, client, shop_db):
        """A failed attach must not disconnect what was working."""
        client.post(
            "/connect-db",
            data={"file": (io.BytesIO(shop_db.read_bytes()), "shop.db")},
            content_type="multipart/form-data",
        )

        client.post(
            "/connect-db",
            data={"file": (io.BytesIO(b"this is not a database"), "bad.db")},
            content_type="multipart/form-data",
        )

        assert "sales" in text(client.get("/connect-db"))


class TestAccountJourney:
    def test_history_survives_a_round_trip_through_logout(self, client):
        name = f"journey{uuid.uuid4().hex[:6]}"
        password = "a-good-password"

        client.post(
            "/register",
            data={"username": name, "email": f"{name}@example.com", "password": password},
        )
        client.get("/", query_string={"q": "highest paid employees"})
        assert "highest paid employees" in text(client.get("/history"))

        client.post("/logout")
        assert client.get("/history").status_code == 302

        client.post("/login", data={"username": name, "password": password})
        assert "highest paid employees" in text(client.get("/history"))

    def test_one_users_history_is_not_anothers(self, client):
        """The obvious way to get this wrong is to record queries without a user."""
        first = f"one{uuid.uuid4().hex[:6]}"
        second = f"two{uuid.uuid4().hex[:6]}"
        password = "a-good-password"

        client.post("/register", data={"username": first, "email": f"{first}@e.com",
                                       "password": password})
        client.get("/", query_string={"q": "products low on stock"})
        client.post("/logout")

        client.post("/register", data={"username": second, "email": f"{second}@e.com",
                                       "password": password})
        page = text(client.get("/history"))

        assert "products low on stock" not in page

    def test_an_anonymous_question_is_not_recorded_against_anyone(self, client):
        name = f"anon{uuid.uuid4().hex[:6]}"

        client.get("/", query_string={"q": "customers in Lahore"})
        client.post("/register", data={"username": name, "email": f"{name}@e.com",
                                       "password": "a-good-password"})

        assert "customers in Lahore" not in text(client.get("/history"))


class TestSwitchingBetweenSources:
    """The three sources share one active slot. Switching has to actually switch."""

    def test_connecting_a_database_does_not_erase_an_uploaded_dataset(self, client, tmp_path,
                                                                     monkeypatch):
        import query_assistant.infrastructure.database.connectors.sqlite as sqlite_connector

        monkeypatch.setattr(sqlite_connector, "CONNECTED_DB_PATH", str(tmp_path / "conn.db"))
        monkeypatch.setattr(sqlite_connector, "UPLOAD_DIR", str(tmp_path))

        client.post(
            "/upload",
            data={"dataset_name": "Sales", "file": (io.BytesIO(CSV), "sales.csv")},
            content_type="multipart/form-data",
        )

        path = tmp_path / "shop.db"
        setup = sqlite3.connect(path)
        setup.execute("CREATE TABLE t (id INTEGER, v TEXT)")
        setup.execute("INSERT INTO t VALUES (1, 'x')")
        setup.commit()
        setup.close()
        client.post(
            "/connect-db",
            data={"file": (io.BytesIO(path.read_bytes()), "shop.db")},
            content_type="multipart/form-data",
        )

        assert "4 row" in text(client.get("/dataset", query_string={"q": "sab dikhao"}))

    def test_the_demo_database_keeps_answering_throughout(self, client):
        """Whatever else is attached, the built-in data stays queryable."""
        client.post(
            "/upload",
            data={"dataset_name": "Sales", "file": (io.BytesIO(CSV), "sales.csv")},
            content_type="multipart/form-data",
        )

        page = text(client.get("/", query_string={"q": "highest paid employees"}))
        assert "Fatima Sheikh" in page

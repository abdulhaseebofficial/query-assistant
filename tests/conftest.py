"""Shared pytest fixtures.

The suite runs against a throwaway SQLite file in a temp directory rather than
the developer's real data/company.db, so running the tests never adds test
users or clobbers an uploaded dataset. `DB_NAME` is imported by value into
backend.app and backend.auth, so all three modules have to be repointed.
"""

import os
import sqlite3
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope="session", autouse=True)
def test_database():
    """Point every module that opens the database at a temp file, then seed it."""
    import backend.app
    import backend.auth
    import backend.database

    tmp_dir = tempfile.mkdtemp(prefix="query-assistant-tests-")
    db_path = os.path.join(tmp_dir, "test_company.db")

    for module in (backend.database, backend.app, backend.auth):
        module.DB_NAME = db_path

    backend.database.init_db()
    yield db_path


@pytest.fixture
def client():
    from backend.app import app as flask_app

    flask_app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with flask_app.test_client() as test_client:
        yield test_client


@pytest.fixture
def conn(test_database):
    connection = sqlite3.connect(test_database)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()

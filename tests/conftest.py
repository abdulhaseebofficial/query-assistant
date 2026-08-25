"""Shared pytest fixtures.

Two things are isolated here so the suite is deterministic and free to run:

1. The database. Tests use a throwaway SQLite file in a temp directory rather than
   the developer's real data/company.db, so running them never adds test users or
   clobbers an uploaded dataset. `DB_NAME` is imported by value into backend.app
   and backend.auth, so all three modules have to be repointed.

2. The AI providers. ai_engine calls load_dotenv() at import, so a developer with a
   real key in .env would otherwise have the suite firing off live API requests —
   slow, billable, and non-deterministic. Every test runs with those keys cleared,
   which also means the assertions exercise the rule-based fallback path.
"""

import os
import sqlite3
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

AI_ENV_VARS = ("GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "AI_PROVIDER")


@pytest.fixture(autouse=True)
def no_ai_keys(monkeypatch):
    """Run every test as if no AI provider were configured.

    Requested by name in tests that are specifically about the no-key path; applied
    everywhere else automatically so nothing in the suite can reach a live API.
    """
    import backend.engines.ai_engine as ai_engine

    for var in AI_ENV_VARS:
        monkeypatch.delenv(var, raising=False)

    ai_engine.reset_client_cache()
    yield
    ai_engine.reset_client_cache()


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

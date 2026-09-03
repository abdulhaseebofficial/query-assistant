"""Shared pytest fixtures.

Two things are isolated here so the suite is deterministic and free to run:

1. The database. Tests use a throwaway SQLite file in a temp directory rather than
   the developer's real data/company.db, so running them never adds test users or
   clobbers an uploaded dataset. `DB_NAME` is imported by value into query_assistant.app
   and query_assistant.repositories.user_repository, so all three modules have to be repointed.

2. The AI providers. ai_engine calls load_dotenv() at import, so a developer with a
   real key in .env would otherwise have the suite firing off live API requests â€”
   slow, billable, and non-deterministic. Every test runs with those keys cleared,
   which also means the assertions exercise the rule-based fallback path.
"""

import os
import sqlite3
import tempfile

import pytest

AI_ENV_VARS = ("GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "AI_PROVIDER")

# How many tests this run collected, and whether it was the whole suite. The README
# badge quotes a number, and a number written in prose drifts every time the suite
# grows â€” so one test checks it, and that test has to know what the real count is.
COLLECTION = {}


def pytest_collection_modifyitems(session, config, items):
    COLLECTION["count"] = len(items)
    # `pytest tests/test_x.py` or `-k something` collects a subset, and only a run
    # of everything can speak for the total. A bare `pytest` still arrives here with
    # args set â€” pyproject's testpaths fills them in â€” so compare against those
    # rather than checking for empty.
    testpaths = list(config.getini("testpaths") or [])
    COLLECTION["whole_suite"] = (
        not config.option.keyword
        and list(config.args) in ([], testpaths)
    )


@pytest.fixture
def collection_info():
    """What this run collected.

    A fixture rather than an import: pytest loads this file as the plugin module
    `conftest`, so `from tests.conftest import COLLECTION` builds a *second* module
    object with its own empty dict and the hook never touches it.
    """
    return COLLECTION


@pytest.fixture(autouse=True)
def no_ai_keys(monkeypatch):
    """Run every test as if no AI provider were configured.

    Requested by name in tests that are specifically about the no-key path; applied
    everywhere else automatically so nothing in the suite can reach a live API.
    """
    import query_assistant.infrastructure.ai.providers as ai_engine

    for var in AI_ENV_VARS:
        monkeypatch.delenv(var, raising=False)

    ai_engine.reset_client_cache()
    yield
    ai_engine.reset_client_cache()


@pytest.fixture(scope="session")
def test_database():
    import query_assistant.infrastructure.database.initialization
    import query_assistant.repositories.feedback_repository
    import query_assistant.repositories.user_repository
    import query_assistant.services.query_service

    tmp_dir = tempfile.mkdtemp(prefix="query-assistant-tests-")
    db_path = os.path.join(tmp_dir, "test_company.db")

    query_assistant.infrastructure.database.initialization.init_db(db_path)
    query_assistant.infrastructure.database.initialization.DB_NAME = db_path
    query_assistant.repositories.feedback_repository.database.DB_NAME = db_path
    query_assistant.repositories.user_repository.DB_NAME = db_path
    query_assistant.services.query_service.DB_NAME = db_path
    yield db_path


@pytest.fixture(scope="session")
def app(test_database):
    from query_assistant import create_app

    return create_app({"TESTING": True, "WTF_CSRF_ENABLED": False,
                       "DATABASE_PATH": test_database})


@pytest.fixture(autouse=True)
def application_context(app):
    """Keep every repository and service bound to the isolated test database."""
    with app.app_context():
        yield


@pytest.fixture(autouse=True)
def no_uploaded_dataset(test_database):
    """Start every test with no CSV attached.

    The database is shared for the whole session, and an uploaded dataset lives in
    it as `custom_data`/`custom_meta`. Without this, a test that uploads one leaves
    it behind and the next test that assumes a clean slate fails â€” but only when the
    two run in that order, which is the kind of failure that shows up in CI and not
    on the machine that introduced it.
    """
    import sqlite3

    from query_assistant.domain.query.csv_engine import clear_dataset

    connection = sqlite3.connect(test_database)
    try:
        clear_dataset(connection)
    finally:
        connection.close()
    yield


@pytest.fixture
def client(app):
    """A test client with rate limiting off.

    The limits are per-IP and every test shares one, so leaving them on would make
    the suite's pass/fail depend on how many tests happened to run before it.
    `rate_limited_client` turns them back on for the tests that are about the
    limits themselves.
    """
    from query_assistant.extensions import limiter

    limiter.enabled = False
    try:
        with app.test_client() as test_client:
            yield test_client
    finally:
        limiter.enabled = True


@pytest.fixture
def rate_limited_client(app):
    """A test client with rate limiting on, and a clean counter to start from."""
    from query_assistant.extensions import limiter

    limiter.enabled = True
    limiter.reset()
    try:
        with app.test_client() as test_client:
            yield test_client
    finally:
        limiter.reset()


@pytest.fixture
def conn(test_database):
    connection = sqlite3.connect(test_database)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()

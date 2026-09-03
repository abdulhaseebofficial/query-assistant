"""Which AI provider runs, and what happens when none is available.

These tests never make a network call: they check the selection logic and the
failure paths around it. ``no_ai_keys`` (autouse, see conftest.py) has already
cleared every provider variable before each test, so each one sets exactly the
environment it's describing.
"""

import pytest

import query_assistant.infrastructure.ai.providers as ai_engine


@pytest.fixture(autouse=True)
def clear_client_cache():
    """Clients are cached, so env changes need the cache dropped to take effect."""
    ai_engine.reset_client_cache()
    yield
    ai_engine.reset_client_cache()


def test_no_keys_means_no_provider():
    assert ai_engine._configured_provider() is None


def test_a_gemini_key_selects_gemini(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    assert ai_engine._configured_provider() == "gemini"


def test_google_api_key_is_accepted_as_well(monkeypatch):
    """The Google SDK's own variable name works, so an existing key needs no rename."""
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    assert ai_engine._configured_provider() == "gemini"


def test_an_anthropic_key_selects_anthropic(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    assert ai_engine._configured_provider() == "anthropic"


def test_gemini_wins_when_both_keys_are_present(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    assert ai_engine._configured_provider() == "gemini"


def test_ai_provider_overrides_key_based_detection(monkeypatch):
    """Both keys can live in .env while AI_PROVIDER pins which one actually runs."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("AI_PROVIDER", "anthropic")
    assert ai_engine._configured_provider() == "anthropic"


@pytest.mark.parametrize("value", ["GEMINI", "  gemini  ", "Gemini"])
def test_ai_provider_is_case_and_whitespace_insensitive(monkeypatch, value):
    monkeypatch.setenv("AI_PROVIDER", value)
    assert ai_engine._configured_provider() == "gemini"


def test_an_unknown_ai_provider_disables_ai_rather_than_guessing(monkeypatch):
    """Silently falling back to a provider the user didn't name would hide a typo."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("AI_PROVIDER", "openai")
    assert ai_engine._configured_provider() is None


def test_a_named_provider_without_its_key_yields_no_client(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "anthropic")
    assert ai_engine._configured_provider() == "anthropic"
    assert ai_engine._get_client("anthropic") is None


def test_generate_sql_returns_none_when_the_provider_has_no_client(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    assert ai_engine.generate_sql("employees in IT", ai_engine.BUILTIN_SCHEMA) is None


def test_generate_sql_ignores_an_empty_question(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    assert ai_engine.generate_sql("   ", ai_engine.BUILTIN_SCHEMA) is None


def test_a_provider_returning_nothing_falls_back(monkeypatch):
    """An API error or an empty response must not raise â€” the caller needs None."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(ai_engine, "_get_client", lambda provider: object())
    monkeypatch.setitem(ai_engine._GENERATORS, "gemini", lambda *args: None)

    assert ai_engine.generate_sql("employees in IT", ai_engine.BUILTIN_SCHEMA) is None


def test_generated_sql_is_validated_no_matter_which_provider_wrote_it(monkeypatch):
    """The guardrail is not the model's job â€” a DROP from either provider is dropped."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(ai_engine, "_get_client", lambda provider: object())
    monkeypatch.setitem(
        ai_engine._GENERATORS,
        "gemini",
        lambda *args: {"sql": "DROP TABLE employees", "explanation": "x", "chart_type": "none"},
    )

    assert ai_engine.generate_sql("delete everything", ai_engine.BUILTIN_SCHEMA) is None


def test_a_valid_response_is_returned_with_the_provider_named(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(ai_engine, "_get_client", lambda provider: object())
    monkeypatch.setitem(
        ai_engine._GENERATORS,
        "gemini",
        lambda *args: {
            "sql": "SELECT name FROM employees",
            "explanation": "Lists employee names.",
            "chart_type": "bar",
        },
    )

    result = ai_engine.generate_sql("list employees", ai_engine.BUILTIN_SCHEMA)

    assert result["sql"] == "SELECT name FROM employees;"
    assert result["chart_type"] == "bar"
    assert result["provider"] == "gemini"


def test_an_unrecognised_chart_type_becomes_none(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(ai_engine, "_get_client", lambda provider: object())
    monkeypatch.setitem(
        ai_engine._GENERATORS,
        "gemini",
        lambda *args: {
            "sql": "SELECT name FROM employees",
            "explanation": "Lists employee names.",
            "chart_type": "sunburst",
        },
    )

    assert ai_engine.generate_sql("list employees", ai_engine.BUILTIN_SCHEMA)["chart_type"] == "none"


def test_a_missing_explanation_gets_a_default(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(ai_engine, "_get_client", lambda provider: object())
    monkeypatch.setitem(
        ai_engine._GENERATORS,
        "gemini",
        lambda *args: {"sql": "SELECT name FROM employees", "explanation": "", "chart_type": "none"},
    )

    assert ai_engine.generate_sql("list employees", ai_engine.BUILTIN_SCHEMA)["explanation"]


def test_both_providers_are_given_the_same_instructions():
    """The schema, the dialect, and the one-SELECT rule must not drift per provider."""
    instructions = ai_engine._build_instructions(ai_engine.BUILTIN_SCHEMA, "PostgreSQL", None)

    assert "PostgreSQL" in instructions
    assert "employees" in instructions
    assert "exactly one SELECT statement" in instructions


def test_a_single_table_caller_scopes_the_instructions_to_that_table():
    instructions = ai_engine._build_instructions("data(a, b)", "SQLite", "custom_data")
    assert "the table custom_data" in instructions

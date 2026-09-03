# Contributing

Thanks for taking a look. This is a small project, so the process is short.

## Getting set up

```bash
git clone https://github.com/abdulhaseebofficial/query-assistant.git
cd query-assistant
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env             # Windows: copy .env.example .env
python run.py
```

The app comes up at <http://127.0.0.1:5000> and seeds `data/company.db` on first run, so
there is nothing else to install or configure.

AI keys are optional. Without `GEMINI_API_KEY` or `ANTHROPIC_API_KEY` the app uses its
rule-based engines, which is also how CI runs â€” so a contribution never requires an API
key, and the test suite clears those variables anyway so it can't make a live call.

## Before you open a pull request

```bash
pytest          # the whole suite, ~18 seconds, no network needed
ruff check .    # lint
```

Both run in CI against Python 3.10 through 3.13, plus a smoke job that boots the app and
makes a real HTTP request. If those pass locally they will almost certainly pass there.

## How the code is laid out

Start with the [architecture guide](docs/architecture/PROJECT_STRUCTURE.md), which walks
through the package, request flow, ownership boundaries, and testing strategy.

The short version:

| If you're changing... | Look at |
|---|---|
| Routes, page logic | `src/query_assistant/web/blueprints/` |
| How a question becomes SQL | `src/query_assistant/domain/query/` |
| Connecting an external database | `src/query_assistant/infrastructure/database/connectors/` |
| Pages and styling | `src/query_assistant/web/templates/`, `src/query_assistant/web/static/css/` |
| Demo data and schema | `src/query_assistant/infrastructure/database/initialization.py` |

## Conventions worth knowing

**Never build SQL by string-concatenating user input.** Every engine returns
`(sql, params)` and the value goes in as a bound parameter. There are tests asserting
this specifically â€” if you find yourself f-stringing a user's words into a query, that's
the thing to avoid.

**AI-generated SQL is validated before it runs.** `validate_select()` in
`src/query_assistant/domain/validation/sql_guardrails.py` enforces single read-only `SELECT` statements against a
table whitelist. That whitelist is what keeps generated queries away from the `users`
table, which lives in the same SQLite file as the demo data. If you touch that function,
`tests/security/test_sql_guardrails.py` is the file that will tell you whether you broke it.

**Comments explain why, not what.** The existing code follows this; please match it.

**Tests describe behaviour.** Test names read as sentences â€” `test_interpret_uses_bound_
parameters_not_string_interpolation` rather than `test_interpret_2`.

## Commit messages

Plain sentences in the imperative: "Add a Postgres connection timeout", not "added timeout"
or "fix stuff". One logical change per commit where it's practical.

## Reporting a security issue

Please don't open a public issue â€” see [SECURITY.md](SECURITY.md).

# tests/

The automated checks that run on every push and pull request. 240 tests, about seven seconds,
no network access and no API key required.

```bash
pytest              # run everything
pytest -v           # one line per test
pytest tests/test_sql_guardrails.py    # just one file
```

## What's in each file

**`conftest.py`** — shared setup. The important bit: the whole suite runs against a
throwaway SQLite file in a temp directory, not your real `data/company.db`. Running the
tests will never add junk users to your dev database or wipe a dataset you uploaded.
(`DB_NAME` gets imported by value into `backend.app` and `backend.auth`, so all three
modules have to be repointed — that's what the `test_database` fixture does.)

**`test_rule_engine.py`** — the rule-based engine, which is what runs when no
no AI key is set. Checks that a question lands on the right table, that
aggregates are detected, and — importantly — that filter values go in as bound parameters
instead of being pasted into the SQL text.

**`test_sql_guardrails.py`** — the security boundary. The AI engine executes SQL that a
language model wrote, so `_validate_select()` is what stands between "the model said so"
and "the app ran it". These tests throw `DROP TABLE`, stacked statements, `PRAGMA`,
`ATTACH`, and sneaky joins onto the `users` table at it and assert every one is rejected.
If you change that function, this file is the one that will tell you.

**`test_csv_engine.py`** — uploaded CSVs become real SQLite tables, so arbitrary column
headers from someone's file end up inside a `CREATE TABLE`. These tests cover sanitising
those headers, deduplicating collisions, inferring column types, and a full round trip
through the database.

**`test_chart_utils.py`** — when a result set is worth drawing and when it isn't. Notably:
`id` columns are numeric but plotting them is meaningless, and a single row is not a chart.

**`test_deployment.py`** — the serverless setup. Vercel's deployment directory is
read-only and its `/tmp` is wiped between cold starts, so these check that `vercel.json`
routes every path to the one function, that `DATA_DIR` moves every written path somewhere
writable, and that importing `api/index.py` into an empty directory seeds the database and
serves a real answer. The cold-start tests run in a subprocess because `config.py` reads
the environment once at import.

**`test_honest_answers.py`** — the rule engine must decline what it can't express.
Every builder ends in a catch-all "list everything" branch, so before this was gated the
engine answered questions it hadn't understood — "employees earning more than 100000"
returned all 18 employees, explained as "Lists all employees, sorted by name". The tests
pin both halves: a list of questions that must be refused (with the reason named, since
the page shows it), and a list that must still be answered, so the gate can't be
over-applied into refusing everything.

**`test_security.py`** — one test per real finding, so a failure means a defence was
removed rather than a style rule broken. Covers CSV formula injection (a cell like
`=cmd|'/c calc.exe'!A0` executing when someone opens the downloaded file), the SSRF guard
that stops the Postgres connector being aimed at `127.0.0.1` or cloud metadata,
quote-escaping of table names taken from an uploaded database, header injection through
`Content-Disposition`, the response security headers, and the rate limits.

**`test_ai_providers.py`** — which AI provider gets picked, and every path where one is
unavailable. No network calls: the selection logic and failure handling are what's under
test.

**`test_app.py`** — the routes themselves, through Flask's test client. Pages render,
CSV export returns an attachment, the security headers are on every response, `/history`
redirects anonymous visitors to the login page, and a registered user's queries are
actually recorded.

## Adding a test

Name it as a sentence describing the behaviour —
`test_interpret_returns_none_when_it_cannot_understand`, not `test_interpret_3`. When
the test reads like a claim about the app, a failure tells you what broke without having
to open the file.

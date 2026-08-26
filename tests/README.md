# tests/

The automated checks that run on every push and pull request. 532 tests, about sixteen seconds,
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

**`test_postgres_dialect.py`** — the app runs on SQLite locally and PostgreSQL when
`DATABASE_URL` is set, and there's no PostgreSQL server in CI. So these build the SQL the
app would actually send and parse it with sqlglot's PostgreSQL dialect, which catches what
dialect bugs really look like: an identity column in SQLite's syntax, a `strftime` that
doesn't exist in PostgreSQL, a `?` where `%s` belongs. Each of those would otherwise only
show up as a 500 on the deployment.

**`test_query_efficiency.py`** — work that grows with the size of the data, on paths
that run once per request. Neither problem was visible against the demo database — five
tables and eighteen employees hides a lot — but `get_table()` used to `COUNT(*)` every
table in a connected database before answering a single question. These pin the query
counts so it can't creep back.

**`test_deployment.py`** — the serverless setup. Vercel's deployment directory is
read-only and its `/tmp` is wiped between cold starts, so these check that `vercel.json`
routes every path to the one function, that `DATA_DIR` moves every written path somewhere
writable, and that importing `api/index.py` into an empty directory seeds the database and
serves a real answer. The cold-start tests run in a subprocess because `config.py` reads
the environment once at import.

**`test_sql_console.py`** — the `/sql` editor, where somebody types the query
themselves. That makes it the one route arbitrary SQL arrives on, so most of the file is
about what must *not* run: writes, stacked statements, and the app's own `users` table,
which lives in the same file as the demo data. The strongest of them asserts by outcome —
send `DROP TABLE employees`, then count the employees. It also pins that the console and
the AI engine call the same validator, since two copies of a security rule is two chances
to weaken one.

**`test_user_journeys.py`** — whole flows, in order, sharing state between the steps.
Every other file isolates its subject with a fresh fixture, which is the right way to test a
unit and the wrong way to notice that clearing a dataset leaves the page it fed still
claiming to have one. These run the sequences a person performs — upload, ask, export,
clear — and check the state after each step.

**`test_connected_database.py`** — questions asked against a database someone attached
at runtime. This path had no tests at all, and it shares its query builder with the CSV
path while reaching it through different routes and a different template — which is
exactly how it broke: the builder learned to total and average a column, and
`connect_table.html` was still reading the answer out of a hardcoded `count` key, so the
explanation said "Adds up the total revenue" with nothing underneath it. Also covers what a
connected database can carry that an upload can't: column names with quotes, spaces,
reserved words and non-Latin script, since a CSV's headers are sanitised on the way in and
a connected database's are not.

**`test_csv_questions.py`** — the same questions, asked about an uploaded spreadsheet
instead of the demo schema. csv_engine knows only the column names and their types, and it
was answering from even less than that: "sab dikhao" and "highest revenue" both searched
the *values* for words that were never values, returned nothing, and said "Lists matching
rows" — which reads as "your data is empty".

**`test_roman_urdu.py`** — questions asked the way they're actually asked here, in
Roman Urdu or mixed with English. Every case in it was found by asking the running app a
real question and noticing the answer was wrong. Three kinds of wrong: refused because a
word like "grahak" wasn't in the vocabulary; answered from the wrong table; or — the
dangerous one — answered from the right table with the filter silently dropped, so "IT
walay employees" returned all eighteen employees under the explanation "Lists all
employees".

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

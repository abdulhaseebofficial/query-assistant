# Security Policy

## Reporting a vulnerability

Please report security issues privately rather than in a public issue.

- **Preferred:** [open a private security advisory](https://github.com/abdulhaseebofficial/query-assistant/security/advisories/new)
- **Or email:** abdul.haseeb4924@gmail.com

Include what you found, how to reproduce it, and what an attacker could do with it.
Expect a first reply within a few days. This is a personal project maintained in spare
time, so there is no formal SLA â€” but security reports get looked at first.

Please don't run automated scanners against anyone else's deployment of this app.

## Supported versions

The `master` branch is the only supported version.

## What this project already does

These are deliberate, and there are tests covering them â€” worth knowing before you file
a report.

| Concern | How it's handled | Where |
|---|---|---|
| SQL injection via user questions | Every engine returns `(sql, params)`; values are always bound parameters, never concatenated | `src/query_assistant/domain/query/`, `tests/unit/domain/test_rule_engine.py` |
| Model-generated SQL doing damage | `_validate_select()` allows a single read-only `SELECT` only â€” no stacked statements, no `INSERT`/`UPDATE`/`DELETE`/`DROP`/`ATTACH`/`PRAGMA`. It runs on the output of **every** provider, so swapping models can't route around it | `src/query_assistant/infrastructure/ai/providers.py`, `tests/security/test_sql_guardrails.py` |
| Generated SQL reaching the `users` table | A table whitelist; the demo tables and the app's own auth tables share one SQLite file, so the whitelist is the boundary | `src/query_assistant/infrastructure/ai/providers.py` |
| CSRF | `CSRFProtect` on every state-changing request | `src/query_assistant/app.py` |
| Session cookie forgery | `SECRET_KEY` from the environment; a random per-process key if unset, never a hardcoded default | `src/query_assistant/app.py` |
| Brute-forcing logins | Rate limits: 10/min on `/login`, 5/min on `/register`, 200/min globally | `src/query_assistant/app.py` |
| Username enumeration by timing | Password verification runs against a dummy hash when the user doesn't exist | `src/query_assistant/repositories/user_repository.py` |
| Password storage | `werkzeug.security` hashing â€” plaintext passwords are never stored | `src/query_assistant/repositories/user_repository.py` |
| Clickjacking / MIME sniffing / XSS | `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, and a Content-Security-Policy on every response | `src/query_assistant/app.py`, `tests/integration/routes/test_app.py` |
| Spreadsheet formula injection in CSV exports | Cells beginning `=` `+` `-` `@` `	` `` are prefixed with `'`, so Excel/Sheets read them as text instead of executing them | `src/query_assistant/utilities/csv_export.py`, `tests/security/test_web_security.py` |
| SSRF / internal port scanning via a Postgres DSN | Hostnames are resolved and refused if they land on loopback, RFC1918, link-local, or `169.254.169.254`; opt out with `ALLOW_PRIVATE_DB_HOSTS=true` | `src/query_assistant/infrastructure/database/connectors/postgresql.py`, `tests/security/test_web_security.py` |
| SQL identifier injection from a hostile schema | Table names from an uploaded database are quote-escaped before interpolation â€” a name can legally contain `"` | `src/query_assistant/infrastructure/database/connectors/`, `tests/security/test_web_security.py` |
| Response-header injection via a table name | `Content-Disposition` filenames are stripped to `[A-Za-z0-9._-]`, dot runs collapsed, length capped | `src/query_assistant/app.py`, `tests/security/test_web_security.py` |
| Cost and capacity abuse | Per-endpoint limits above the global ceiling: 30/min on querying (each one can be a billable AI call), 20/min on exports, 10/min on uploads and database connections | `src/query_assistant/app.py` |
| Downgrade to plain HTTP | `Strict-Transport-Security` once `SESSION_COOKIE_SECURE=true`; omitted otherwise so local `http://` still works | `src/query_assistant/app.py` |
| Unwanted device access | `Permissions-Policy` denies camera, microphone, geolocation, payment, and USB | `src/query_assistant/app.py` |
| Oversized uploads | 5 MB request cap, handled with a friendly 413 page rather than a stack trace | `src/query_assistant/app.py` |
| Arbitrary code execution via the debugger | `FLASK_DEBUG` defaults to `false` and must be opted into explicitly | `run.py` |

## Known limitations

Be aware of these before deploying this anywhere public:

- **Rate limiting is in-memory.** Limits are per-process and reset on restart. Behind
  multiple workers or a load balancer, configure a shared `storage_uri` (Redis) instead.
- **The CSP allows `'unsafe-inline'`** for scripts and styles, because the chart partial
  and page styles are inlined. Tightening this to nonces is a genuine improvement if you
  want to send a PR.
- **Connected database credentials are stored on disk** in `instance/uploads/` as plain JSON.
  That folder is git-ignored, but it is not encrypted â€” use a read-only database user for
  any PostgreSQL connection you set up.
- **`SESSION_COOKIE_SECURE` defaults to `false`** so local `http://` development works.
  Set it to `true` once you're serving over HTTPS.
- **Your AI provider sees your schema and your questions.** When `GEMINI_API_KEY` or
  `ANTHROPIC_API_KEY` is set, the table/column names of the active data source and the
  text you type are sent to that provider. Row data is never sent â€” the model writes the
  query, the app runs it locally â€” but treat schema names as disclosed. Leave both keys
  unset to keep everything on your machine.
- **API keys live in `.env`,** which is git-ignored but unencrypted. Rotate a key
  immediately if it's ever pasted into a chat, a screenshot, or a commit.
- **The data-source endpoints are open to anonymous visitors.** `/upload`,
  `/connect-db`, `/dataset/clear`, and `/connect-db/clear` deliberately work without an
  account, because the whole app is usable logged-out. On a public deployment that means
  *any* visitor can replace or wipe the active dataset for everyone else. `/history` is
  the only route behind a login. If you deploy this somewhere reachable, put it behind
  authentication at the proxy, or add `@login_required` to those four routes.
- **There is no multi-tenancy.** An uploaded CSV replaces the previous one for everyone
  using that instance. This is built as a single-user / demo app.
- **`ALLOW_PRIVATE_DB_HOSTS=true` re-opens the SSRF path.** It's the right setting for a
  laptop talking to a local Postgres, and the wrong one for anything internet-facing.

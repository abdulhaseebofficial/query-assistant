# Security Policy

## Reporting a vulnerability

Please report security issues privately rather than in a public issue.

- **Preferred:** [open a private security advisory](https://github.com/abdulhaseebofficial/query-assistant/security/advisories/new)
- **Or email:** abdul.haseeb4924@gmail.com

Include what you found, how to reproduce it, and what an attacker could do with it.
Expect a first reply within a few days. This is a personal project maintained in spare
time, so there is no formal SLA — but security reports get looked at first.

Please don't run automated scanners against anyone else's deployment of this app.

## Supported versions

The `master` branch is the only supported version.

## What this project already does

These are deliberate, and there are tests covering them — worth knowing before you file
a report.

| Concern | How it's handled | Where |
|---|---|---|
| SQL injection via user questions | Every engine returns `(sql, params)`; values are always bound parameters, never concatenated | `backend/engines/`, `tests/test_rule_engine.py` |
| Model-generated SQL doing damage | `_validate_select()` allows a single read-only `SELECT` only — no stacked statements, no `INSERT`/`UPDATE`/`DELETE`/`DROP`/`ATTACH`/`PRAGMA`. It runs on the output of **every** provider, so swapping models can't route around it | `backend/engines/ai_engine.py`, `tests/test_sql_guardrails.py` |
| Generated SQL reaching the `users` table | A table whitelist; the demo tables and the app's own auth tables share one SQLite file, so the whitelist is the boundary | `backend/engines/ai_engine.py` |
| CSRF | `CSRFProtect` on every state-changing request | `backend/app.py` |
| Session cookie forgery | `SECRET_KEY` from the environment; a random per-process key if unset, never a hardcoded default | `backend/app.py` |
| Brute-forcing logins | Rate limits: 10/min on `/login`, 5/min on `/register`, 200/min globally | `backend/app.py` |
| Username enumeration by timing | Password verification runs against a dummy hash when the user doesn't exist | `backend/auth.py` |
| Password storage | `werkzeug.security` hashing — plaintext passwords are never stored | `backend/auth.py` |
| Clickjacking / MIME sniffing / XSS | `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, and a Content-Security-Policy on every response | `backend/app.py`, `tests/test_app.py` |
| Oversized uploads | 5 MB request cap, handled with a friendly 413 page rather than a stack trace | `backend/app.py` |
| Arbitrary code execution via the debugger | `FLASK_DEBUG` defaults to `false` and must be opted into explicitly | `run.py` |

## Known limitations

Be aware of these before deploying this anywhere public:

- **Rate limiting is in-memory.** Limits are per-process and reset on restart. Behind
  multiple workers or a load balancer, configure a shared `storage_uri` (Redis) instead.
- **The CSP allows `'unsafe-inline'`** for scripts and styles, because the chart partial
  and page styles are inlined. Tightening this to nonces is a genuine improvement if you
  want to send a PR.
- **Connected database credentials are stored on disk** in `data/uploads/` as plain JSON.
  That folder is git-ignored, but it is not encrypted — use a read-only database user for
  any PostgreSQL connection you set up.
- **`SESSION_COOKIE_SECURE` defaults to `false`** so local `http://` development works.
  Set it to `true` once you're serving over HTTPS.
- **Your AI provider sees your schema and your questions.** When `GEMINI_API_KEY` or
  `ANTHROPIC_API_KEY` is set, the table/column names of the active data source and the
  text you type are sent to that provider. Row data is never sent — the model writes the
  query, the app runs it locally — but treat schema names as disclosed. Leave both keys
  unset to keep everything on your machine.
- **API keys live in `.env`,** which is git-ignored but unencrypted. Rotate a key
  immediately if it's ever pasted into a chat, a screenshot, or a commit.
- **There is no multi-tenancy.** An uploaded CSV replaces the previous one for everyone
  using that instance. This is built as a single-user / demo app.

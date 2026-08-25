# Query Assistant

Ask questions about your data in plain English (or Roman Urdu) — the app translates them into SQL, runs the query, and shows you both the result and the generated SQL. Works against a built-in demo database, an uploaded CSV, or an external SQLite/PostgreSQL database.

## Project Structure

Every folder below has its own `README.md` with a plain-English explanation of what's inside it and why — click through to whichever folder you're curious about.

```
sql-project/
├── backend/                 # Flask application (Python) — see backend/README.md
│   ├── app.py                # Routes, request handling, view logic
│   ├── config.py             # Central path configuration
│   ├── database.py           # Demo database schema + seed data
│   ├── auth.py                # User accounts, login, query history
│   ├── engines/               # Natural-language → SQL engines — see backend/engines/README.md
│   │   ├── ai_engine.py          # Claude-powered SQL generation (optional)
│   │   ├── rule_engine.py        # Rule-based fallback for the demo schema
│   │   └── csv_engine.py         # Query builder for uploaded CSV data
│   ├── connectors/            # External data source adapters — see backend/connectors/README.md
│   │   ├── sqlite_connector.py   # Connect an uploaded .db/.sqlite file
│   │   └── postgres_connector.py # Connect via a PostgreSQL DSN
│   ├── content/                # see backend/content/README.md
│   │   └── learn_content.py      # Static content for the "Learn SQL" page
│   └── utils/                  # see backend/utils/README.md
│       └── chart_utils.py        # Turns query results into chart-ready data
│
├── frontend/                 # Everything rendered in the browser — see frontend/README.md
│   ├── templates/             # Jinja2 HTML templates
│   │   └── partials/             # Shared fragments (_nav.html, _chart.html)
│   └── static/
│       └── css/                  # Stylesheets
│
├── data/                     # Runtime data, git-ignored — see data/README.md
│   ├── company.db                # Demo SQLite database
│   └── uploads/                   # Uploaded CSVs / connected databases
│
├── run.py                    # Application entry point
├── requirements.txt
├── .env.example
└── .gitignore
```

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # then fill in SECRET_KEY (and ANTHROPIC_API_KEY if you want AI-generated SQL)
python run.py
```

The app starts at **http://127.0.0.1:5000** and seeds `data/company.db` automatically on first run.

## Environment Variables

| Variable | Required | Purpose |
|---|---|---|
| `SECRET_KEY` | Yes (for production) | Flask session signing key. If unset, a random key is generated at startup — sessions won't survive a restart until this is set. |
| `ANTHROPIC_API_KEY` | No | Enables Claude-based SQL generation; the app falls back to the rule-based engine when unset. |
| `FLASK_DEBUG` | No (default `false`) | Enables Flask's debugger and auto-reload. Never set to `true` in production — the debugger allows arbitrary code execution if exposed. |
| `SESSION_COOKIE_SECURE` | No (default `false`) | Set to `true` once the app is served over HTTPS, so the session cookie is marked `Secure`. |

## How a Query Is Answered

1. **AI engine** (`backend/engines/ai_engine.py`) is tried first if `ANTHROPIC_API_KEY` is set — it asks Claude for a SQL statement, then validates it before running: single statement, read-only `SELECT` only, no forbidden keywords (`INSERT`/`DROP`/`ATTACH`/`PRAGMA`/...), and every referenced table must be on an explicit allow-list scoped to the caller (e.g. only the 5 business tables for the built-in schema — never the app's own `users` or `query_history` tables, even though they live in the same database file).
2. If that's unavailable or fails, the matching **rule-based engine** takes over:
   - `rule_engine.py` for the built-in company schema
   - `csv_engine.py` for an uploaded CSV
   - `sqlite_connector.py` / `postgres_connector.py` for an externally connected database
3. Results are rendered as a table, with an optional chart (`chart_utils.py`) and a CSV export option.

All SQL execution uses parameterized queries for values; AI-generated SQL is additionally validated as described above.

## Security

- **Passwords** — hashed with Werkzeug's `generate_password_hash` (PBKDF2), never stored or logged in plain text.
- **Login timing** — `verify_password` runs a dummy hash comparison even when the username doesn't exist, so response time can't be used to enumerate valid usernames.
- **CSRF** — every state-changing form is protected by Flask-WTF's `CSRFProtect`; a request without a valid token is rejected.
- **Rate limiting** — `/login` and `/register` are throttled (Flask-Limiter) to slow down credential-stuffing and account-enumeration attempts.
- **Session cookies** — `HttpOnly` and `SameSite=Lax` always; `Secure` when `SESSION_COOKIE_SECURE=true`.
- **Security headers** — `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, and a `Content-Security-Policy` are set on every response.
- **File uploads** — capped at 5 MB; CSVs are capped at 5,000 rows; SQLite uploads are verified by magic-byte header before being accepted.

### Known limitations (accepted trade-offs, not oversights)

- **PostgreSQL connection strings are stored in plain text** at `data/uploads/postgres_connection.json` so the app can reconnect across requests. This is a single-user/local-tool design choice — don't point it at a production database with a shared secret you can't rotate. Encrypting this file (e.g. via `cryptography`'s Fernet, keyed off `SECRET_KEY`) would be the next step for a multi-tenant deployment.
- **No CAPTCHA / device fingerprinting** on registration — the rate limiter is in-memory and per-process, which is enough to deter casual abuse but not a determined, distributed attacker.
- **Content-Security-Policy allows `'unsafe-inline'`** for scripts/styles because the chart renderer and theme toggle currently use inline `<script>` blocks. Moving those into `frontend/static/js/` files and switching to a nonce-based CSP would let this be tightened further.

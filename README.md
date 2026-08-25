# Query Assistant

Ask questions about your data in plain English (or Roman Urdu) — the app translates them into SQL, runs the query, and shows you both the result and the generated SQL. Works against a built-in demo database, an uploaded CSV, or an external SQLite/PostgreSQL database.

## Project Structure

```
sql-project/
├── backend/                 # Flask application (Python)
│   ├── app.py                # Routes, request handling, view logic
│   ├── config.py             # Central path configuration
│   ├── database.py           # Demo database schema + seed data
│   ├── auth.py                # User accounts, login, query history
│   ├── engines/               # Natural-language → SQL engines
│   │   ├── ai_engine.py          # Claude-powered SQL generation (optional)
│   │   ├── rule_engine.py        # Rule-based fallback for the demo schema
│   │   └── csv_engine.py         # Query builder for uploaded CSV data
│   ├── connectors/            # External data source adapters
│   │   ├── sqlite_connector.py   # Connect an uploaded .db/.sqlite file
│   │   └── postgres_connector.py # Connect via a PostgreSQL DSN
│   ├── content/
│   │   └── learn_content.py      # Static content for the "Learn SQL" page
│   └── utils/
│       └── chart_utils.py        # Turns query results into chart-ready data
│
├── frontend/                 # Everything rendered in the browser
│   ├── templates/             # Jinja2 HTML templates
│   │   └── partials/             # Shared fragments (_nav.html, _chart.html)
│   └── static/
│       └── css/                  # Stylesheets
│
├── data/                     # Runtime data (git-ignored, generated locally)
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
| `SECRET_KEY` | Yes (for production) | Flask session signing key |
| `ANTHROPIC_API_KEY` | No | Enables Claude-based SQL generation; the app falls back to the rule-based engine when unset |

## How a Query Is Answered

1. **AI engine** (`backend/engines/ai_engine.py`) is tried first if `ANTHROPIC_API_KEY` is set — it asks Claude for a single validated `SELECT` statement.
2. If that's unavailable or fails, the matching **rule-based engine** takes over:
   - `rule_engine.py` for the built-in company schema
   - `csv_engine.py` for an uploaded CSV
   - `sqlite_connector.py` / `postgres_connector.py` for an externally connected database
3. Results are rendered as a table, with an optional chart (`chart_utils.py`) and a CSV export option.

All SQL execution uses parameterized queries; AI-generated SQL is additionally validated to be a single read-only `SELECT`.

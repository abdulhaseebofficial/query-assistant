# backend/connectors/

A **connector** is code that lets the app connect to a database that is *not* the built-in demo database — for example, a database file you upload, or a PostgreSQL server you already have.

Only one external connection can be active at a time. Connecting a new one automatically disconnects the old one.

## What's in this folder

| File | What it does |
|---|---|
| `sqlite_connector.py` | Lets a user upload their own SQLite database file (`.db`, `.sqlite`, `.sqlite3`) and query it. The app checks the file really is a SQLite database before accepting it, and saves it to `data/uploads/connected.db`. |
| `postgres_connector.py` | Lets a user paste a PostgreSQL (or Supabase) connection string and query that database directly, without copying any data. The connection string is saved to `data/uploads/postgres_connection.json` so the app can reconnect on the next request. |

## Good to know

- Both files offer the same set of functions — `is_connected()`, `list_tables()`, `get_table()`, `get_connection()`, `clear_connection()` — so the rest of the app (`backend/app.py`) can use either one without needing to know which database type it's actually talking to.
- The PostgreSQL connection string is stored as plain text on disk. That's fine for personal or local use, but it's not something you'd want to do for a shared, production database — see the "Known limitations" section in the project's main [README.md](../../README.md) for more on this.

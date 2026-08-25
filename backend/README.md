# backend/

This folder holds **all the Python code** — everything that runs on the server. If `frontend/` is what you *see* in the browser, `backend/` is what does the thinking behind the scenes.

The app doesn't start here directly — it's started by `run.py` in the project's root folder, which imports `app.py` from this folder and runs it.

## What's in this folder

| File | What it does |
|---|---|
| `app.py` | The main file. It defines every URL the website has (like `/`, `/login`, `/upload`) and decides what happens when someone visits them. |
| `config.py` | Keeps track of important folder paths (like where the database file lives) in one place, so every other file can ask this file instead of guessing. |
| `database.py` | Creates the demo database and fills it with sample data (departments, employees, products, etc.) the first time the app runs. |
| `auth.py` | Handles user accounts — signing up, logging in, and remembering what questions a user has asked before. |

## Subfolders

Each subfolder groups related code together, so it's easier to find things. Every subfolder also has its own small README explaining it in more detail.

- **`engines/`** — the code that turns a plain-English question into an SQL query.
- **`connectors/`** — the code that lets the app talk to a database outside the demo one (an uploaded SQLite file, or a PostgreSQL server).
- **`content/`** — plain text/data used by the "Learn SQL" page.
- **`utils/`** — small helper code, like turning query results into chart data.

## How a request flows through this folder

1. A visitor opens a page or types a question — this hits a URL defined in `app.py`.
2. `app.py` calls the right engine (from `engines/`) to turn the question into SQL.
3. The SQL runs against the database — either the demo one (`database.py`), an uploaded CSV, or an external database (`connectors/`).
4. `app.py` sends the results to a page in `frontend/templates/` to be displayed.

For the bigger picture (security notes, setup steps, environment variables), see the [README.md](../README.md) in the project root.

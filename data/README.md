# data/

This folder holds everything the app **creates or receives while running** — nothing here is source code, and nothing here needs to be written by hand.

It's excluded from git (see `.gitignore`) because it's local, generated data, not part of the project itself. On a fresh checkout, this folder starts empty and fills up as you use the app.

## What's in this folder

| Item | What it is |
|---|---|
| `company.db` | The demo SQLite database (departments, employees, products, customers, orders, plus user accounts and query history). Created automatically the first time you run `python run.py` — safe to delete, it will just be rebuilt with fresh sample data. |
| `uploads/` | Holds files created when someone connects an external database from the website: `connected.db` (an uploaded SQLite file) and/or `postgres_connection.json` (a saved PostgreSQL connection string). Empty until you use the "Connect a Database" page. |

If you ever want to reset the app back to a clean, empty state, you can safely delete `company.db` and everything inside `uploads/` — just restart the app afterwards so `company.db` gets recreated.

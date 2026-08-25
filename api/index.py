"""Serverless entry point.

Vercel turns every .py file under api/ into a function and looks for a module-level
`app`; vercel.json then rewrites every path here, so this one function serves the
whole site. `run.py` is the equivalent for running locally and is not used here.

Two things differ from a normal server and both are handled by configuration rather
than by anything special in this file:

1. The deployment directory is read-only — only /tmp can be written — so vercel.json
   points DATA_DIR there and every path the app writes moves with it.

2. /tmp doesn't survive a cold start and isn't shared between instances, so it is not
   somewhere data can live. That's what DATABASE_URL is for: set it and accounts,
   query history, the demo tables and uploaded CSVs all live in PostgreSQL instead,
   and the deployment behaves like any other. Leave it unset and the app still runs,
   but everything resets on each cold start and the UI says so — see
   EPHEMERAL_STORAGE in backend/config.py.

init_db() runs here rather than in a request because a cold start may be the first
time this database has been seen. It is idempotent, so a warm instance pays nothing
and an existing database is left alone.
"""

from backend.app import app
from backend.database import init_db

init_db()

# Vercel's Python runtime serves whatever WSGI application this name points at.
__all__ = ["app"]

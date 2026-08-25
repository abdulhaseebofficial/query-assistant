"""Serverless entry point.

Vercel turns every .py file under api/ into a function and looks for a module-level
`app`; vercel.json then rewrites every path here, so this one function serves the
whole site. `run.py` is the equivalent for running locally and is not used here.

Two things differ from a normal server and are worth understanding before reading
any bug report from a deployment:

1. The deployment directory is read-only. Only /tmp is writable, so DATA_DIR is
   pointed there (in vercel.json) and everything the app writes goes with it.

2. /tmp does not survive a cold start, and separate instances don't share one.
   So the demo database is re-seeded here on import — init_db() is idempotent, so
   a warm instance pays nothing — and registered accounts, saved query history,
   and uploaded CSVs last only as long as the instance that received them. That's
   why the deployment sets EPHEMERAL_STORAGE=true, which puts a notice in the UI
   instead of letting someone register an account that quietly vanishes.

For a deployment where that data has to persist, run this on a host that gives the
process a real disk (see the deployment section in README.md) rather than working
around it here.
"""

from backend.app import app
from backend.database import init_db

init_db()

# Vercel's Python runtime serves whatever WSGI application this name points at.
__all__ = ["app"]

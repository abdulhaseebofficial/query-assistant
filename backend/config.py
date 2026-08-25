"""Central path configuration shared by every backend module.

Keeping filesystem paths in one place means the data/ and frontend/
folders can be moved or renamed without touching the modules that use them.

`DATA_DIR` is overridable because not every host lets an app write next to its
own source. On a serverless platform the deployment directory is read-only and
only /tmp can be written, so the deployment sets DATA_DIR=/tmp/... — see
api/index.py and the deployment notes in README.md. Everything the app writes
(the demo database, uploaded CSVs, connected-database files) lives under it.
"""

import os

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)

FRONTEND_DIR = os.path.join(PROJECT_ROOT, "frontend")
TEMPLATE_DIR = os.path.join(FRONTEND_DIR, "templates")
STATIC_DIR = os.path.join(FRONTEND_DIR, "static")

DATA_DIR = os.environ.get("DATA_DIR") or os.path.join(PROJECT_ROOT, "data")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")

DB_PATH = os.path.join(DATA_DIR, "company.db")
CONNECTED_DB_PATH = os.path.join(UPLOAD_DIR, "connected.db")
POSTGRES_CONFIG_PATH = os.path.join(UPLOAD_DIR, "postgres_connection.json")

# True only when the app's data genuinely doesn't survive a restart, so the UI can
# say so rather than let someone register an account that silently disappears.
#
# Two things have to be true for that: the deployment has declared its disk
# temporary (serverless /tmp), *and* there's no external database holding the data
# instead. Combining them here means a deployment that adds DATABASE_URL stops
# showing the warning on its own, rather than needing a second variable flipped and
# lying to its users until someone remembers.
_DECLARED_TEMPORARY = os.environ.get("EPHEMERAL_STORAGE", "").strip().lower() in ("1", "true", "yes")
EPHEMERAL_STORAGE = _DECLARED_TEMPORARY and not os.environ.get("DATABASE_URL", "").strip()

os.makedirs(UPLOAD_DIR, exist_ok=True)

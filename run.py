"""Entry point — starts the Query Assistant Flask app.

Usage:
    python run.py

Debug mode (auto-reload + interactive tracebacks) is OFF by default because
Flask's debugger allows arbitrary code execution if it's ever exposed to the
network. Set FLASK_DEBUG=true in your local .env to turn it on.
"""

import os

from backend.app import app
from backend.database import init_db

if __name__ == "__main__":
    init_db()
    debug = os.environ.get("FLASK_DEBUG", "false").strip().lower() in ("1", "true", "yes")
    app.run(debug=debug)

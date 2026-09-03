"""Entry point â€” starts the Query Assistant Flask app.

Usage:
    python run.py

Debug mode (auto-reload + interactive tracebacks) is OFF by default because
Flask's debugger allows arbitrary code execution if it's ever exposed to the
network. Set FLASK_DEBUG=true in your local .env to turn it on.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from query_assistant import create_app

app = create_app()

if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "false").strip().lower() in ("1", "true", "yes")
    app.run(debug=debug)

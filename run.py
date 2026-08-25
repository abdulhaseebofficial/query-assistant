"""Entry point — starts the Query Assistant Flask app.

Usage:
    python run.py
"""

from backend.app import app
from backend.database import init_db

if __name__ == "__main__":
    init_db()
    app.run(debug=True)

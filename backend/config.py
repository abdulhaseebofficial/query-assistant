"""Central path configuration shared by every backend module.

Keeping filesystem paths in one place means the data/ and frontend/
folders can be moved or renamed without touching the modules that use them.
"""

import os

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)

FRONTEND_DIR = os.path.join(PROJECT_ROOT, "frontend")
TEMPLATE_DIR = os.path.join(FRONTEND_DIR, "templates")
STATIC_DIR = os.path.join(FRONTEND_DIR, "static")

DATA_DIR = os.path.join(PROJECT_ROOT, "data")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")

DB_PATH = os.path.join(DATA_DIR, "company.db")
CONNECTED_DB_PATH = os.path.join(UPLOAD_DIR, "connected.db")
POSTGRES_CONFIG_PATH = os.path.join(UPLOAD_DIR, "postgres_connection.json")

os.makedirs(UPLOAD_DIR, exist_ok=True)

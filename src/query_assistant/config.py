"""Central application configuration with side-effect-free path resolution."""

import os
import secrets
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parents[1]
DEFAULT_INSTANCE_DIR = PROJECT_ROOT / "instance"


def _truthy(name: str, default: str = "false") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes"}


class Config:
    """Defaults shared by local, test, CI, and serverless application instances."""

    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _truthy("SESSION_COOKIE_SECURE")
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")


def runtime_paths(instance_path: str | Path | None = None) -> dict[str, Path]:
    """Resolve writable paths without creating files or directories at import time.

    ``DATA_DIR`` remains fully compatible. When it is absent, Flask's instance
    directory is used; this moves new local runtime data out of the source tree.
    Existing ``data/company.db`` is selected when present so upgrades never strand
    user data silently.
    """
    explicit = os.environ.get("DATA_DIR")
    legacy = PROJECT_ROOT / "data"
    default = Path(instance_path) if instance_path else DEFAULT_INSTANCE_DIR
    data_dir = Path(explicit).expanduser() if explicit else default
    if not explicit and (legacy / "company.db").exists():
        data_dir = legacy
    upload_dir = data_dir / "uploads"
    return {
        "data_dir": data_dir,
        "upload_dir": upload_dir,
        "database": data_dir / "company.db",
        "connected_database": upload_dir / "connected.db",
        "postgres_config": upload_dir / "postgres_connection.json",
    }


# Compatibility constants for non-Flask domain/infrastructure code. They are
# resolved only; directory creation belongs to create_app()/storage.
_PATHS = runtime_paths()
DATA_DIR = str(_PATHS["data_dir"])
UPLOAD_DIR = str(_PATHS["upload_dir"])
DB_PATH = str(_PATHS["database"])
CONNECTED_DB_PATH = str(_PATHS["connected_database"])
POSTGRES_CONFIG_PATH = str(_PATHS["postgres_config"])

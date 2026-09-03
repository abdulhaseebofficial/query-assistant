"""Import both entry points and verify essential application resources."""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from query_assistant import create_app  # noqa: E402


def main():
    with tempfile.TemporaryDirectory(prefix="query-assistant-deploy-") as temp_dir:
        os.environ["DATA_DIR"] = temp_dir
        app = create_app({"TESTING": True, "DATABASE_PATH": str(Path(temp_dir) / "local.db"),
                          "UPLOAD_DIR": str(Path(temp_dir) / "uploads")})
        routes = {rule.rule for rule in app.url_map.iter_rules()}
        required = {"/", "/login", "/upload", "/connect-db", "/feedback", "/learn", "/sql"}
        missing = required - routes
        if missing:
            raise RuntimeError(f"Missing routes: {sorted(missing)}")
        with app.test_client() as client:
            response = client.get("/")
            if response.status_code != 200 or client.get("/static/css/base.css").status_code != 200:
                raise RuntimeError("Template or static asset smoke check failed")
        from api.index import app as vercel_app

        if vercel_app is None:
            raise RuntimeError("Vercel WSGI application was not created")
    print("Local factory, templates, static assets, routes, and Vercel entry point passed.")


if __name__ == "__main__":
    main()

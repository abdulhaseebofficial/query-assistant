"""The serverless deployment differs from a local run in two ways that have both
broken it before: the source directory is read-only, and the data directory is
temporary. These tests pin the configuration that accounts for that.
"""

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

import pytest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def vercel_config():
    return json.loads((PROJECT_ROOT / "vercel.json").read_text(encoding="utf-8"))


class TestVercelConfig:
    def test_framework_entry_point_exists_at_the_project_root(self, vercel_config):
        """Modern Vercel discovers root index.py and preserves Flask request paths."""
        assert (PROJECT_ROOT / "index.py").is_file()
        assert "rewrites" not in vercel_config

    def test_the_data_directory_is_moved_somewhere_writable(self, vercel_config):
        """The deployment directory is read-only; only /tmp can be written."""
        assert vercel_config["env"]["DATA_DIR"].startswith("/tmp/")

    def test_the_entry_point_exists_where_the_rewrite_points(self):
        assert (PROJECT_ROOT / "api" / "index.py").is_file()


class TestDataDirOverride:
    def test_data_dir_defaults_to_the_repo(self):
        from query_assistant import config

        assert pathlib.Path(config.DATA_DIR).name == "data"

    def test_every_written_path_moves_with_data_dir(self):
        """A path left behind pointing at the read-only source tree is the bug this
        catches â€” it wouldn't fail until something tried to write to it."""
        from query_assistant import config

        for path in (config.UPLOAD_DIR, config.DB_PATH, config.CONNECTED_DB_PATH,
                     config.POSTGRES_CONFIG_PATH):
            assert path.startswith(config.DATA_DIR)


class TestColdStart:
    """Vercel imports api/index.py into a fresh container with an empty /tmp. The
    subprocess is the point: it's the only way to test import-time behaviour with a
    different DATA_DIR, since config.py reads the environment once at import."""

    @pytest.fixture
    def cold_start(self):
        tmp_dir = tempfile.mkdtemp(prefix="cold-start-")
        shutil.rmtree(tmp_dir, ignore_errors=True)

        def _run(script):
            env = {
                **os.environ,
                "DATA_DIR": tmp_dir,
                "SECRET_KEY": "cold-start-test",
                "PYTHONPATH": str(PROJECT_ROOT / "src"),
                "PYTHONIOENCODING": "utf-8",
            }
            for key in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "AI_PROVIDER"):
                env.pop(key, None)
            return subprocess.run(
                [sys.executable, "-c", script],
                capture_output=True, text=True, env=env, cwd=str(PROJECT_ROOT), timeout=120,
            )

        try:
            yield _run, tmp_dir
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_importing_the_entry_point_seeds_an_empty_data_dir(self, cold_start):
        run, tmp_dir = cold_start
        result = run(
            "import importlib.util as u;"
            "s = u.spec_from_file_location('e', 'api/index.py');"
            "m = u.module_from_spec(s); s.loader.exec_module(m);"
            "print('OK')"
        )

        assert result.returncode == 0, result.stderr
        assert "OK" in result.stdout
        assert os.path.exists(os.path.join(tmp_dir, "company.db")), "database was not seeded"

    def test_the_app_serves_a_real_answer_on_a_cold_start(self, cold_start):
        run, _ = cold_start
        result = run(
            "import importlib.util as u;"
            "s = u.spec_from_file_location('e', 'api/index.py');"
            "m = u.module_from_spec(s); s.loader.exec_module(m);"
            "from query_assistant.extensions import limiter; limiter.enabled = False;"
            "m.app.config.update(TESTING=True);"
            "r = m.app.test_client().get('/?q=highest+paid+employees');"
            "body = r.get_data(as_text=True);"
            "print(r.status_code, 'Fatima Sheikh' in body)"
        )

        assert result.returncode == 0, result.stderr
        assert "200 True" in result.stdout, result.stdout

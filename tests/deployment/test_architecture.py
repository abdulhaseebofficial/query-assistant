"""Keep dependency direction enforceable in the normal test suite."""

import importlib.util
from pathlib import Path


def test_layer_dependencies_follow_the_architecture():
    script = Path(__file__).resolve().parents[2] / "scripts" / "check_architecture.py"
    spec = importlib.util.spec_from_file_location("architecture_check", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert list(module.violations()) == []

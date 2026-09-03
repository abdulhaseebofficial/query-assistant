"""The README's test-count badge, checked against the real count.

The number used to appear in four files. Every time the suite grew, all four went
stale until somebody noticed — which is what happened, at 556 against an actual
560. It's in one place now, and this checks that one place, so the drift can't
come back quietly.
"""

import pathlib
import re

import pytest

README = pathlib.Path(__file__).resolve().parents[2] / "README.md"


def badge_count():
    match = re.search(r"tests-(\d+)%20passing", README.read_text(encoding="utf-8"))
    return int(match.group(1)) if match else None


def test_the_badge_exists():
    assert badge_count() is not None, "the README lost its test-count badge"


def test_the_badge_matches_the_suite(collection_info):
    if not collection_info.get("whole_suite"):
        pytest.skip("a partial run can't speak for the total")

    assert badge_count() == collection_info["count"], (
        f"README badge says {badge_count()}, the suite has {collection_info['count']} — "
        "update the badge in README.md"
    )


def test_no_other_file_repeats_the_number():
    """Four copies of one number is what caused the drift in the first place."""
    root = README.parent
    for name in ("CONTRIBUTING.md", "tests/README.md"):
        text = (root / name).read_text(encoding="utf-8")
        assert not re.search(r"\b\d{3,} tests\b", text), f"{name} quotes a test count again"

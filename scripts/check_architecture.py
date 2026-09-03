"""Fail when package imports violate the documented dependency boundaries."""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "query_assistant"
RULES = {
    "domain": ("flask", "query_assistant.web", "query_assistant.services", "query_assistant.repositories"),
    "infrastructure": ("query_assistant.web",),
    "repositories": ("query_assistant.web", "query_assistant.services"),
    "services": ("query_assistant.web",),
}


def imports(path):
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module


def violations():
    for layer, forbidden in RULES.items():
        folder = PACKAGE / layer
        for path in folder.rglob("*.py"):
            for imported in imports(path):
                if any(imported == name or imported.startswith(name + ".") for name in forbidden):
                    yield f"{path.relative_to(ROOT)} imports forbidden dependency {imported}"


def main():
    problems = list(violations())
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    print("Architecture dependency rules passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

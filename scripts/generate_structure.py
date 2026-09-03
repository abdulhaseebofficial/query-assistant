"""Generate the portable repository tree used for external developer handoff."""

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "architecture" / "PROJECT_STRUCTURE.txt"
EXCLUDED = {".git", ".pytest_cache", ".ruff_cache", "__pycache__", ".claude"}


def visible(path):
    if path.is_dir() and path.name.startswith(".") and path.name != ".github":
        return False
    if path.name in EXCLUDED or path.name.endswith(".egg-info"):
        return False
    if path.suffix.lower() in {".db", ".sqlite", ".sqlite3", ".pyc"}:
        return False
    relative = path.relative_to(ROOT)
    if len(relative.parts) >= 3 and relative.parts[:2] in {
        ("instance", "uploads"), ("data", "uploads")
    }:
        return path.name == ".gitkeep"
    return path.name != "postgres_connection.json"


def render(directory=ROOT):
    lines = [directory.name + "/"]

    def visit(folder, prefix):
        entries = sorted((entry for entry in folder.iterdir() if visible(entry)),
                         key=lambda entry: (entry.is_file(), entry.name.lower()))
        for index, entry in enumerate(entries):
            last = index == len(entries) - 1
            lines.append(prefix + ("`-- " if last else "|-- ") + entry.name + ("/" if entry.is_dir() else ""))
            if entry.is_dir():
                visit(entry, prefix + ("    " if last else "|   "))

    visit(directory, "")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = render()
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != expected:
            raise SystemExit("PROJECT_STRUCTURE.txt is stale; run python scripts/generate_structure.py")
        print("Generated project tree is current.")
    else:
        OUTPUT.write_text(expected, encoding="utf-8", newline="\n")
        print(f"Wrote {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Central definition of all placeholders that must be replaced once before
the GitHub mirror goes public (stdlib only).

    scripts/placeholders.py list
    scripts/placeholders.py apply GITHUB_USER=<name> SECURITY_CONTACT=<mail> COPYRIGHT_HOLDER="<name>"

`list` prints every occurrence (file:line). `apply` replaces them in all
git-tracked text files; values may be given for a subset. Review the diff,
run the tests, commit.
"""

from __future__ import annotations

from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent

# name -> meaning; written as <NAME> in the files
PLACEHOLDERS = {
    "GITHUB_USER": "GitHub user/organisation of the mirror, repo <GITHUB_USER>/repo_installer",
    "SECURITY_CONTACT": "private e-mail address for security reports (SECURITY.md)",
    "COPYRIGHT_HOLDER": "copyright holder in the license",
}

TOKEN_RE = re.compile(r"<([A-Z][A-Z0-9_]{2,})>")
SELF = Path(__file__).resolve()


def tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        check=True, capture_output=True,
    ).stdout
    return [ROOT / p for p in out.decode().split("\0") if p]


def occurrences() -> list[tuple[Path, int, str]]:
    found = []
    for path in tracked_files():
        if path.resolve() == SELF or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for match in TOKEN_RE.finditer(line):
                if match[1] in PLACEHOLDERS:
                    found.append((path, lineno, match[1]))
    return found


def apply(values: dict[str, str]) -> int:
    unknown = set(values) - set(PLACEHOLDERS)
    if unknown:
        raise SystemExit(f"unknown placeholder(s): {', '.join(sorted(unknown))}")
    changed = 0
    for path in sorted({p for p, _, name in occurrences() if name in values}):
        text = path.read_text(encoding="utf-8")
        for name, value in values.items():
            text = text.replace(f"<{name}>", value)
        path.write_text(text, encoding="utf-8")
        changed += 1
        print(f"updated {path.relative_to(ROOT)}")
    return changed


def main(argv: list[str]) -> int:
    if argv[:1] == ["list"]:
        for path, lineno, name in occurrences():
            print(f"{path.relative_to(ROOT)}:{lineno}: <{name}>")
        return 0
    if argv[:1] == ["apply"] and len(argv) > 1:
        values = dict(arg.split("=", 1) for arg in argv[1:])
        apply(values)
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

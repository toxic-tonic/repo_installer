#!/usr/bin/env python3
"""Release metadata checks (stdlib only), used by the GitHub release workflow.

    scripts/release_meta.py check <tag>             tag == v<manifest version>, CHANGELOG has it
    scripts/release_meta.py notes <version> <sha>   CHANGELOG section + "SHA-256: <sha>"
    scripts/release_meta.py prerelease <version>    prints true/false

Exit code 1 with a message on any mismatch.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "custom_components/repo_installer/manifest.json"
CHANGELOG = ROOT / "CHANGELOG.md"
SECTION_RE = re.compile(r"^## \[(?P<version>[^\]]+)\]", re.MULTILINE)


class ReleaseError(Exception):
    pass


def manifest_version(manifest: Path = MANIFEST) -> str:
    return str(json.loads(manifest.read_text(encoding="utf-8"))["version"])


def changelog_section(version: str, changelog: Path = CHANGELOG) -> str:
    text = changelog.read_text(encoding="utf-8")
    matches = list(SECTION_RE.finditer(text))
    for i, match in enumerate(matches):
        if match["version"] == version:
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            # drop link reference definitions ([0.1.0]: https://…) at the end
            body = re.sub(r"^\[[^\]]+\]:\s*\S+\s*$", "", text[match.end():end], flags=re.MULTILINE)
            body = body.split("\n", 1)[1] if "\n" in body else ""  # rest of heading line (date)
            body = body.strip()
            if not body:
                raise ReleaseError(f"CHANGELOG section [{version}] is empty")
            return body
    raise ReleaseError(f"CHANGELOG.md has no section ## [{version}]")


def check(tag: str, manifest: Path = MANIFEST, changelog: Path = CHANGELOG) -> str:
    if not tag.startswith("v"):
        raise ReleaseError(f"tag {tag!r} does not start with v")
    version = tag[1:]
    if (found := manifest_version(manifest)) != version:
        raise ReleaseError(f"tag {tag} != manifest.json version {found}")
    changelog_section(version, changelog)
    return version


def notes(version: str, sha256: str, changelog: Path = CHANGELOG) -> str:
    if not re.fullmatch(r"[0-9a-f]{64}", sha256):
        raise ReleaseError("invalid SHA-256")
    return f"{changelog_section(version, changelog)}\n\nSHA-256: {sha256}\n"


def is_prerelease(version: str) -> bool:
    # Same rule as the integration itself (custom_components/…/version.py)
    spec = importlib.util.spec_from_file_location(
        "_ri_version", ROOT / "custom_components/repo_installer/version.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.is_prerelease(version)


def main(argv: list[str]) -> int:
    try:
        match argv:
            case ["check", tag]:
                print(check(tag))
            case ["notes", version, sha256]:
                sys.stdout.write(notes(version, sha256))
            case ["prerelease", version]:
                print("true" if is_prerelease(version) else "false")
            case _:
                print(__doc__, file=sys.stderr)
                return 2
    except ReleaseError as err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
